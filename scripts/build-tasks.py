#!/usr/bin/env python3
"""Собирает tasks/*.yaml в один tasks.json для BSLexicon и проверяет его.

Контракт: docs/book-integration/task-schema.md в репозитории iMironRU/BSLexicon.
Копия схемы лежит рядом (scripts/task-schema.json) — чтобы сборка не зависела
от сети. Обновлять её командой:

    curl -sL https://raw.githubusercontent.com/iMironRU/BSLexicon/main/docs/book-integration/task-schema.json \\
         -o scripts/task-schema.json

Проверка намеренно своя, без jsonschema: ворота должны срабатывать на любой
машине, где собирается книга, а не только там, где доустановили пакет. Если
jsonschema всё же доступен, он отрабатывает вторым проходом как перекрёстная
сверка.

Использование:
    python3 scripts/build-tasks.py                 # → tasks.json
    python3 scripts/build-tasks.py --out dist/tasks.json
    python3 scripts/build-tasks.py --check         # только проверить, не писать
"""

import argparse
import json
import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:
    sys.exit("build-tasks: нужен PyYAML — pip install pyyaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(ROOT, "tasks")
SCHEMA = os.path.join(ROOT, "scripts", "task-schema.json")

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+")
REPO = re.compile(r"^[\w.-]+/[\w.-]+$")

TASK_REQUIRED = ("id", "title", "chapter", "statement", "starter", "tests")
TASK_OPTIONAL = ("section", "book_url", "hints", "difficulty", "tags")
DIFFICULTY = ("intro", "easy", "medium", "hard")

errors = []


def err(where, message):
    errors.append(f"{where}: {message}")


# ─── чтение книги ────────────────────────────────────────────────────────────

def read_meta():
    with open(os.path.join(ROOT, "metadata.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def git_repo_slug():
    """owner/repo из origin. Переименование репозитория тут отражается сразу —
    в отличие от book_id, который обязан пережить переименование."""
    try:
        url = subprocess.run(["git", "-C", ROOT, "remote", "get-url", "origin"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    m = re.search(r"[:/]([\w.-]+/[\w.-]+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def build_book(meta):
    book = {
        "id": meta.get("book_id") or "",
        "title": meta.get("title") or "",
        "version": str(meta.get("version") or ""),
        "repo": git_repo_slug() or "",
    }
    site = meta.get("site_url")
    if site:
        book["site"] = site.rstrip("/")

    if not book["id"]:
        err("metadata.yaml", "нет поля book_id — стабильный слаг книги для BSLexicon; "
                             "он не меняется даже при переименовании репозитория")
    elif not SLUG.match(book["id"]):
        err("metadata.yaml", f"book_id «{book['id']}» — только строчные латинские, цифры и дефис")
    if not book["title"]:
        err("metadata.yaml", "нет поля title")
    if not SEMVER.match(book["version"]):
        err("metadata.yaml", f"version «{book['version']}» — нужен SemVer вида 0.9.0")
    if not REPO.match(book["repo"]):
        err("metadata.yaml", "не удалось определить owner/repo по git remote origin")
    return book


# ─── проверка задачи ─────────────────────────────────────────────────────────

def check_test(where, t, i):
    at = f"{where}: tests[{i}]"
    if not isinstance(t, dict):
        return err(at, "тест должен быть словарём")
    kind = t.get("kind")
    if kind == "stdout":
        allowed = {"kind", "name", "expect", "hidden"}
        if "expect" not in t:
            err(at, "у теста kind=stdout обязателен expect")
    elif kind == "call":
        allowed = {"kind", "name", "invoke", "expect", "hidden"}
        for k in ("invoke", "expect"):
            v = t.get(k)
            if not isinstance(v, str) or not v.strip():
                err(at, f"у теста kind=call обязателен непустой {k}")
    else:
        return err(at, f"kind должен быть stdout или call, а не «{kind}»")

    for k in t:
        if k not in allowed:
            err(at, f"лишнее поле «{k}» — схема запрещает произвольные ключи")
    if "hidden" in t and not isinstance(t["hidden"], bool):
        err(at, "hidden — булево")
    if "expect" in t and not isinstance(t["expect"], str):
        err(at, "expect — строка (литерал BSL), даже если это число")


def check_task(path, task):
    where = os.path.basename(path)
    if not isinstance(task, dict):
        return err(where, "файл должен содержать один словарь-задачу")

    for k in TASK_REQUIRED:
        if k not in task:
            err(where, f"нет обязательного поля «{k}»")
    for k in task:
        if k not in TASK_REQUIRED + TASK_OPTIONAL:
            err(where, f"лишнее поле «{k}» — схема запрещает произвольные ключи")

    tid = task.get("id", "")
    if tid and not SLUG.match(str(tid)):
        err(where, f"id «{tid}» — только строчные латинские, цифры и дефис")
    title = task.get("title", "")
    if isinstance(title, str) and len(title) > 200:
        err(where, "title длиннее 200 символов")
    for k in ("title", "chapter", "statement"):
        if k in task and not str(task[k]).strip():
            err(where, f"поле «{k}» пустое")
    if "difficulty" in task and task["difficulty"] not in DIFFICULTY:
        err(where, f"difficulty «{task['difficulty']}» — допустимо: {', '.join(DIFFICULTY)}")
    if "tags" in task:
        tags = task["tags"]
        if not isinstance(tags, list) or len(set(map(str, tags))) != len(tags):
            err(where, "tags — список без повторов")
    if "hints" in task and not isinstance(task["hints"], list):
        err(where, "hints — список строк")
    if "<" in str(task.get("statement", "")) and re.search(r"<[a-zA-Z/]", str(task["statement"])):
        err(where, "в statement похоже на HTML — контракт требует plain markdown")

    tests = task.get("tests")
    if not isinstance(tests, list) or not tests:
        err(where, "tests — непустой список")
    else:
        for i, t in enumerate(tests):
            check_test(where, t, i)


# ─── сборка ──────────────────────────────────────────────────────────────────

def collect():
    if not os.path.isdir(TASKS_DIR):
        return []
    files = sorted(f for f in os.listdir(TASKS_DIR) if f.endswith((".yaml", ".yml")))
    tasks = []
    seen = {}
    for name in files:
        path = os.path.join(TASKS_DIR, name)
        try:
            with open(path, encoding="utf-8") as f:
                task = yaml.safe_load(f)
        except yaml.YAMLError as e:
            err(name, f"не разбирается как YAML — {str(e).splitlines()[0]}")
            continue
        if task is None:
            err(name, "файл пуст")
            continue
        if isinstance(task, dict):
            task.setdefault("id", os.path.splitext(name)[0])
        check_task(path, task)
        if isinstance(task, dict):
            tid = task.get("id")
            if tid in seen:
                err(name, f"id «{tid}» уже занят файлом {seen[tid]} — прогресс читателя "
                          f"хранится по этому ключу, он обязан быть уникальным")
            seen[tid] = name
            tasks.append(task)
    # сортировка по главе, затем по параграфу — чтобы диффы tasks.json были стабильны
    def key(t):
        sec = str(t.get("section", ""))
        parts = tuple(int(p) for p in re.findall(r"\d+", sec)) or (999,)
        return (str(t.get("chapter", "")), parts, str(t.get("id", "")))
    return sorted(tasks, key=key)


def cross_check(doc):
    """Второй проход настоящей jsonschema, если она есть в системе."""
    try:
        import jsonschema
    except ImportError:
        return None
    with open(SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    v = jsonschema.Draft202012Validator(schema)
    found = sorted(v.iter_errors(doc), key=lambda e: list(e.path))
    for e in found:
        err("jsonschema", f"{'/'.join(map(str, e.path)) or '<корень>'} — {e.message}")
    return len(found)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "tasks.json"))
    ap.add_argument("--check", action="store_true", help="только проверить, файл не писать")
    args = ap.parse_args()

    if not os.path.isdir(TASKS_DIR):
        print("build-tasks: папки tasks/ нет — книга не публикует задачи")
        return 0

    tasks = collect()
    if not tasks and not errors:
        print("build-tasks: в tasks/ нет задач — нечего собирать")
        return 0

    doc = {"version": 1, "book": build_book(read_meta()), "tasks": tasks}
    checked = cross_check(doc)

    if errors:
        print(f"build-tasks: задачи не прошли проверку ({len(errors)}):", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        print("\n  Контракт: https://github.com/iMironRU/BSLexicon/blob/main/docs/book-integration/task-schema.md",
              file=sys.stderr)
        return 1

    note = "" if checked is not None else "  (jsonschema не установлена — работал встроенный контроль)"
    if args.check:
        print(f"build-tasks: {len(tasks)} задач(и), проверка пройдена{note}")
        return 0

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"build-tasks: {len(tasks)} задач(и) → {os.path.relpath(args.out, ROOT)}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
