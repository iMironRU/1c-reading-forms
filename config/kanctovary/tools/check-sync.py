#!/usr/bin/env python3
"""Синхронность базы «Канцтовары»: песочница запросов против конфигурации.

База серии описана дважды: схемой и данными песочницы в книге о запросах и
исходниками конфигурации здесь. Разойтись им нельзя — пример в книге о
запросах должен давать в 1С тот же ответ, что и в песочнице. Скрипт проверяет
три вещи:

1. состав: объекты, реквизиты, типы, табличные части, измерения и ресурсы;
2. данные изнутри: суммы строк и документов;
3. данные против проведения: записи регистров в песочнице — ровно те, что
   запишет проведение документов по коду модулей конфигурации.

Запуск (из корня книги о формах):
    python3 config/kanctovary/tools/check-sync.py
    python3 config/kanctovary/tools/check-sync.py --sandbox ../1c-reading-queries/assets/sandbox

Код выхода 0 — синхронно, 1 — есть расхождения.
"""

import argparse
import collections
import os
import re
import sys
import xml.etree.ElementTree as ET

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "src"))
SANDBOX = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..",
                                        "1c-reading-queries", "assets", "sandbox"))

NS = {
    "md": "http://v8.1c.ru/8.3/MDClasses",
    "v8": "http://v8.1c.ru/8.1/data/core",
    "xr": "http://v8.1c.ru/8.3/xcf/readable",
}

# Что есть только с одной стороны — и так задумано.
ONLY_IN_CONFIG = {"Отчёт.ОстаткиТоваровНаСкладе"}

# Поля, которые в песочнице объявлены явно, а в конфигурации стандартные.
STANDARD = {
    "Справочник": {"Ссылка", "Код", "Наименование", "Родитель", "ЭтоГруппа", "ПометкаУдаления"},
    "Документ": {"Ссылка", "Номер", "Дата", "Проведен", "Проведён", "ПометкаУдаления"},
    "Табличная": {"Ссылка", "НомерСтроки"},
}

KIND = {
    "Catalogs": "Справочник", "Documents": "Документ",
    "InformationRegisters": "РегистрСведений",
    "AccumulationRegisters": "РегистрНакопления", "Reports": "Отчёт",
}
REF = {"CatalogRef": "Справочник", "DocumentRef": "Документ"}


# ─── Конфигурация: XML → простое описание ─────────────────────────────────

def xml_type(type_el):
    """Тип реквизита в записи песочницы: Строка(25), Число(15,2), Ссылка → X."""
    if type_el is None:
        return "?"
    kinds = [t.text for t in type_el.findall("v8:Type", NS)]
    if len(kinds) != 1:
        return "составной"
    k = kinds[0]
    if k == "xs:string":
        length = type_el.find("v8:StringQualifiers/v8:Length", NS)
        return f"Строка({length.text if length is not None else 0})"
    if k == "xs:decimal":
        d = type_el.find("v8:NumberQualifiers/v8:Digits", NS)
        f = type_el.find("v8:NumberQualifiers/v8:FractionDigits", NS)
        return f"Число({d.text},{f.text})"
    if k == "xs:boolean":
        return "Булево"
    if k == "xs:dateTime":
        return "Дата"
    m = re.match(r"(?:\w+:)?(\w+Ref)\.(.+)", k)   # префикс пространства имён бывает разный
    if m and m.group(1) in REF:
        return f"Ссылка → {REF[m.group(1)]}.{m.group(2)}"
    return k


def fields_of(parent, tag):
    out = {}
    for el in parent.findall(f"md:ChildObjects/md:{tag}", NS):
        name = el.find("md:Properties/md:Name", NS).text
        out[name] = xml_type(el.find("md:Properties/md:Type", NS))
    return out


def load_config(src):
    objects = {}
    for folder, kind in KIND.items():
        path = os.path.join(src, folder)
        if not os.path.isdir(path):
            continue
        for fname in sorted(os.listdir(path)):
            if not fname.endswith(".xml"):
                continue
            root = ET.parse(os.path.join(path, fname)).getroot()
            obj = root[0]
            props = obj.find("md:Properties", NS)
            name = props.find("md:Name", NS).text
            desc = {"kind": kind, "attributes": fields_of(obj, "Attribute")}
            if kind == "Справочник":
                desc["hierarchical"] = props.findtext("md:Hierarchical", default="false", namespaces=NS) == "true"
                desc["Код"] = f"Строка({props.findtext('md:CodeLength', namespaces=NS)})"
                desc["Наименование"] = f"Строка({props.findtext('md:DescriptionLength', namespaces=NS)})"
            if kind == "Документ":
                desc["tabular"] = {}
                for ts in obj.findall("md:ChildObjects/md:TabularSection", NS):
                    ts_name = ts.find("md:Properties/md:Name", NS).text
                    desc["tabular"][ts_name] = fields_of(ts, "Attribute")
            if kind in ("РегистрСведений", "РегистрНакопления"):
                desc["dimensions"] = fields_of(obj, "Dimension")
                desc["resources"] = fields_of(obj, "Resource")
            if kind == "РегистрСведений":
                desc["periodic"] = props.findtext("md:InformationRegisterPeriodicity", namespaces=NS) != "Nonperiodical"
                desc["subordinate"] = props.findtext("md:WriteMode", namespaces=NS) == "RecorderSubordinate"
            if kind == "РегистрНакопления":
                desc["view"] = {"Balance": "Остатки", "Turnovers": "Обороты"}[props.findtext("md:RegisterType", namespaces=NS)]
            objects[f"{kind}.{name}"] = desc
    return objects


# ─── Песочница: YAML → то же описание ─────────────────────────────────────

def sb_type(f):
    t = f["type"]
    if t == "Ссылка":
        return f"Ссылка → {f['refs']}"
    if t in ("УникальныйИдентификатор",):
        return t
    return t.replace(" ", "")


def load_sandbox(path):
    schema = yaml.safe_load(open(os.path.join(path, "kanctovary.schema.yaml"), encoding="utf-8"))
    data = yaml.safe_load(open(os.path.join(path, "kanctovary.data.yaml"), encoding="utf-8"))
    objects = {}
    for t in schema["tables"]:
        kind, name = t["kind"], t["name"]
        desc = {"kind": kind}
        if kind in ("Справочник", "Документ"):
            fields = {f["name"]: sb_type(f) for f in t.get("fields", [])}
            desc["attributes"] = {k: v for k, v in fields.items() if k not in STANDARD[kind]}
            if kind == "Справочник":
                desc["hierarchical"] = "Родитель" in fields
                desc["Код"] = fields.get("Код")
                desc["Наименование"] = fields.get("Наименование")
            if kind == "Документ":
                desc["tabular"] = {
                    ts["name"]: {f["name"]: sb_type(f) for f in ts["fields"] if f["name"] not in STANDARD["Табличная"]}
                    for ts in t.get("tabular", [])
                }
        else:
            desc["dimensions"] = {f["name"]: sb_type(f) for f in t.get("dimensions", [])}
            desc["resources"] = {f["name"]: sb_type(f) for f in t.get("resources", [])}
            desc["attributes"] = {f["name"]: sb_type(f) for f in t.get("attributes", [])}
            if kind == "РегистрСведений":
                desc["periodic"] = t.get("periodic", False)
            if kind == "РегистрНакопления":
                desc["view"] = t.get("view")
        objects[f"{kind}.{name}"] = desc
    return objects, data["records"]


# ─── Сверка ───────────────────────────────────────────────────────────────

def compare_structure(cfg, sb, problems):
    for key in sorted(set(cfg) | set(sb)):
        if key in ONLY_IN_CONFIG:
            continue
        if key not in cfg:
            problems.append(f"в конфигурации нет объекта {key}")
            continue
        if key not in sb:
            problems.append(f"в песочнице нет объекта {key}")
            continue
        a, b = cfg[key], sb[key]
        for part in ("attributes", "dimensions", "resources"):
            if part not in a and part not in b:
                continue
            fa, fb = a.get(part, {}), b.get(part, {})
            for f in sorted(set(fa) | set(fb)):
                if f not in fa:
                    problems.append(f"{key}: поле «{f}» есть только в песочнице")
                elif f not in fb:
                    problems.append(f"{key}: поле «{f}» есть только в конфигурации")
                elif fa[f] != fb[f]:
                    problems.append(f"{key}.{f}: тип {fa[f]} в конфигурации, {fb[f]} в песочнице")
        for prop in ("hierarchical", "periodic", "view", "Код", "Наименование"):
            if prop in a and prop in b and a[prop] != b[prop]:
                problems.append(f"{key}: {prop} — {a[prop]} в конфигурации, {b[prop]} в песочнице")
        for ts in sorted(set(a.get("tabular", {})) | set(b.get("tabular", {}))):
            ta, tb = a.get("tabular", {}).get(ts), b.get("tabular", {}).get(ts)
            if ta is None or tb is None:
                problems.append(f"{key}: табличная часть «{ts}» только с одной стороны")
            elif ta != tb:
                problems.append(f"{key}.{ts}: состав {ta} в конфигурации, {tb} в песочнице")


def compare_data(records, problems):
    docs = {}
    for kind in ("Документ.ПоступлениеТоваров", "Документ.РеализацияТоваров", "Документ.ПриказОбИзмененииЦен"):
        for d in records.get(kind, []):
            docs[f"{kind}:{d['Ссылка']}"] = (kind, d)

    stock, sales, prices = [], [], []
    for key, (kind, d) in docs.items():
        rows = d.get("Товары", [])
        if "СуммаДокумента" in d and sum(r["Сумма"] for r in rows) != d["СуммаДокумента"]:
            problems.append(f"{key}: сумма документа не равна сумме строк")
        for r in rows:
            if "Количество" in r and r["Количество"] * r["Цена"] != r["Сумма"]:
                problems.append(f"{key}, строка {r.get('НомерСтроки')}: сумма ≠ количество × цена")
        if not d.get("Проведен"):
            continue
        # Правила — те же, что в модулях объектов конфигурации.
        for r in rows:
            if kind.endswith("ПоступлениеТоваров"):
                stock.append((d["Дата"], key, "Приход", r["Товар"], d["Склад"], r["Количество"]))
            elif kind.endswith("РеализацияТоваров"):
                stock.append((d["Дата"], key, "Расход", r["Товар"], d["Склад"], r["Количество"]))
                sales.append((d["Дата"], key, r["Товар"], d["Контрагент"], r["Количество"], r["Сумма"]))
            else:
                prices.append((d["Дата"], key, r["Товар"], r["Цена"]))

    def check(name, expected, actual):
        e, a = collections.Counter(expected), collections.Counter(actual)
        if e != a:
            extra = list((a - e).elements())
            missing = list((e - a).elements())
            problems.append(f"{name}: записи не совпадают с проведением — лишние {extra[:3]}, недостающие {missing[:3]}")

    check("РегистрНакопления.ТоварыНаСкладах", stock,
          [(r["Период"], r["Регистратор"], r["ВидДвижения"], r["Товар"], r["Склад"], r["Количество"])
           for r in records.get("РегистрНакопления.ТоварыНаСкладах", [])])
    check("РегистрНакопления.Продажи", sales,
          [(r["Период"], r["Регистратор"], r["Товар"], r["Контрагент"], r["Количество"], r["Сумма"])
           for r in records.get("РегистрНакопления.Продажи", [])])
    check("РегистрСведений.ЦеныТоваров", prices,
          [(r["Период"], r.get("Регистратор"), r["Товар"], r["Цена"])
           for r in records.get("РегистрСведений.ЦеныТоваров", [])])
    return len(docs), len(stock) + len(sales) + len(prices)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sandbox", default=SANDBOX)
    ap.add_argument("--src", default=SRC)
    args = ap.parse_args()

    problems = []
    cfg = load_config(args.src)
    sb, records = load_sandbox(args.sandbox)
    compare_structure(cfg, sb, problems)
    ndocs, nmoves = compare_data(records, problems)

    print(f"Конфигурация: {len(cfg)} объектов · песочница: {len(sb)} таблиц · "
          f"документов {ndocs}, движений по проведению {nmoves}")
    if problems:
        print(f"\nРасхождений: {len(problems)}")
        for p in problems:
            print("  ✗", p)
        return 1
    print("✓ песочница и конфигурация синхронны")
    return 0


if __name__ == "__main__":
    sys.exit(main())
