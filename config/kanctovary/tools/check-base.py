#!/usr/bin/env python3
"""Сравнение базы 1С с песочницей: то, что записала 1С, против данных YAML.

Загрузчик (make-loader.py) выгружает из базы справочники, документы и записи
регистров в текстовый файл. Этот скрипт сверяет выгрузку с
`kanctovary.data.yaml`: коды и наименования, номера, даты, проведённость и
суммы документов, и главное — движения регистров, которые 1С записала сама,
проводя документы.

Запуск: python3 check-base.py --data <kanctovary.data.yaml> --result <result.tsv>
"""

import argparse
import collections
import sys

import yaml

REG_KIND = {"ПоступлениеТоваров", "РеализацияТоваров", "ПриказОбИзмененииЦен"}


def num(v):
    f = float(v)
    return str(int(f)) if f == int(f) else str(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--result", required=True)
    args = ap.parse_args()

    records = yaml.safe_load(open(args.data, encoding="utf-8"))["records"]

    # идентификаторы песочницы → коды и номера, по которым узнаём записи 1С
    code = {}
    for key, rows in records.items():
        if key.startswith("Справочник."):
            for r in rows:
                code[r["Ссылка"]] = r["Код"]
    number = {}
    for kind in REG_KIND:
        for d in records.get(f"Документ.{kind}", []):
            number[f"Документ.{kind}:{d['Ссылка']}"] = f"{kind}:{d['Номер']}"

    expected = collections.Counter()
    for kind in REG_KIND:
        for d in records.get(f"Документ.{kind}", []):
            expected[("Документ", kind, d["Номер"], d["Дата"], "1" if d.get("Проведен") else "0",
                      num(d["СуммаДокумента"]) if "СуммаДокумента" in d else "")] += 1
    for key, rows in records.items():
        if key.startswith("Справочник."):
            for r in rows:
                expected[("Справочник", key.split(".", 1)[1], r["Код"], r["Наименование"],
                          "1" if r.get("ПометкаУдаления") else "0")] += 1
    for r in records.get("РегистрНакопления.ТоварыНаСкладах", []):
        expected[("ТоварыНаСкладах", r["Период"], number[r["Регистратор"]], r["ВидДвижения"],
                  code[r["Товар"]], code[r["Склад"]], num(r["Количество"]))] += 1
    for r in records.get("РегистрНакопления.Продажи", []):
        expected[("Продажи", r["Период"], number[r["Регистратор"]], code[r["Товар"]],
                  code[r["Контрагент"]], num(r["Количество"]), num(r["Сумма"]))] += 1
    for r in records.get("РегистрСведений.ЦеныТоваров", []):
        expected[("ЦеныТоваров", r["Период"], number[r["Регистратор"]], code[r["Товар"]],
                  num(r["Цена"]))] += 1

    actual = collections.Counter()
    for line in open(args.result, encoding="utf-8-sig"):
        line = line.rstrip("\n")
        if not line:
            continue
        parts = tuple(line.split("\t"))
        if parts[0] in ("ТоварыНаСкладах", "Продажи", "ЦеныТоваров"):
            parts = parts[:-1] + (num(parts[-1]),)
            if parts[0] == "Продажи":
                parts = parts[:5] + (num(parts[5]), parts[6])
        if parts[0] == "Документ" and parts[5]:
            parts = parts[:5] + (num(parts[5]),)
        actual[parts] += 1

    groups = collections.Counter(k[0] for k in expected.elements())
    missing = expected - actual
    extra = actual - expected
    print("Ожидалось по песочнице:", dict(groups))
    print("Выгружено из 1С:       ", dict(collections.Counter(k[0] for k in actual.elements())))
    if missing or extra:
        print(f"\nРасхождений: {sum(missing.values()) + sum(extra.values())}")
        for m in list(missing.elements())[:10]:
            print("  нет в 1С:     ", m)
        for e in list(extra.elements())[:10]:
            print("  лишнее в 1С:  ", e)
        return 1
    print("✓ база 1С совпадает с песочницей до записи")
    return 0


if __name__ == "__main__":
    sys.exit(main())
