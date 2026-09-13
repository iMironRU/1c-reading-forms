#!/usr/bin/env python3
"""Лист сверки на стенде — из пометок в тексте.

Каждая непроверенная экранная деталь помечена в тексте `<!-- FIXME стенд: … -->`,
место для снимка — `<!-- СКРИН: … -->`. Собирать их руками означает однажды
собрать не все, поэтому лист генерируется.

Запуск: python3 scripts/stend-checklist.py [> docs/stend-checklist.md]
"""

import glob
import os
import re
import sys

MARK = re.compile(r"<!--\s*(FIXME стенд|СКРИН):\s*(.+?)\s*-->", re.S)
HEAD = re.compile(r"(?m)^(#{1,2})\s+(.+?)\s*$")

PREAMBLE = """# Лист сверки на стенде

*Собран из пометок в тексте скриптом `scripts/stend-checklist.py`. Платформа —
1С:Предприятие 8.3.27, интерфейс «Такси», база «Канцтовары» из «Дерева
метаданных». Отмечайте галочкой и пишите, что вышло: ответ вернётся в текст, а
пометка из него уйдёт.*

## Перед началом

- [ ] Платформа 8.3.27 установлена, записан точный номер сборки.
- [ ] База «Канцтовары» подключена; в ней есть товары, контрагенты, склады,
      поступления № 12 и № 13, реализации и отчёт об остатках.
- [ ] Вариант интерфейса — «Такси», режим совместимости конфигурации записан.
- [ ] Снимки складывать в `assets/img/screens/`, имя — по номеру параграфа:
      `00-01-okno-zapuska.png`.
"""


def section_at(text, pos):
    """Ближайший заголовок выше пометки — чтобы знать, куда она относится."""
    last = ""
    for m in HEAD.finditer(text, 0, pos):
        last = m.group(2)
    return last


def main():
    files = sorted(glob.glob("chapters/*/*.md"))
    chapters = {}
    checks = shots = 0

    for path in files:
        text = open(path, encoding="utf-8").read()
        title = HEAD.search(text)
        title = title.group(2) if title else os.path.basename(path)
        chapter = path.split(os.sep)[1]
        items = []
        for m in MARK.finditer(text):
            kind, body = m.group(1), " ".join(m.group(2).split())
            where = section_at(text, m.start())
            items.append((kind, where, body))
            if kind == "СКРИН":
                shots += 1
            else:
                checks += 1
        if items:
            chapters.setdefault(chapter, []).append((title, items))

    out = [PREAMBLE, f"\nВсего пунктов: {checks + shots} — сверок {checks}, "
                     f"снимков {shots}.\n"]
    for chapter in sorted(chapters):
        out.append(f"\n# {chapter}\n")
        for title, items in chapters[chapter]:
            out.append(f"\n## {title}\n")
            for kind, where, body in items:
                label = "**снимок**" if kind == "СКРИН" else "сверка"
                place = f" ({where})" if where and not where.startswith("§") else ""
                out.append(f"- [ ] {label}{place}: {body}")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
