#!/usr/bin/env bash
# Сборка базы «Канцтовары» с данными — из тех же данных, что у песочницы.
#
#   1. проверяем, что песочница и конфигурация синхронны (check-sync.py);
#   2. собираем Kanctovary.cf из исходников;
#   3. во ВРЕМЕННОЙ копии исходников добавляем загрузчик, созданный из
#      kanctovary.data.yaml (make-loader.py), и поднимаем базу;
#   4. Предприятие загружает данные и проводит документы, выгружает регистры;
#   5. сверяем выгрузку с песочницей (check-base.py);
#   6. возвращаем базе чистую конфигурацию из Kanctovary.cf — загрузчик уходит,
#      данные остаются — и выгружаем Kanctovary.dt.
#
# Запуск из корня книги о формах:  bash config/kanctovary/tools/build-base.sh
# Нужна платформа 1С 8.3.27 с лицензией. Во время шага 4 на экране на
# несколько секунд появится окно 1С — оно закроется само.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CFG="$(cd "$HERE/.." && pwd)"
DATA="$(cd "$CFG/../../../1c-reading-queries/assets/sandbox" && pwd)/kanctovary.data.yaml"
V8="${V8:-/opt/1cv8/8.3.27.2130/1cv8}"
WORK="$(mktemp -d)"
IB="$WORK/ib"

step() { printf '\n[%s] %s\n' "$1" "$2"; }
guard() { perl -e "alarm ${TIMEOUT:-600}; exec @ARGV" "$@"; }
log()   { python3 -c "import sys; print(open(sys.argv[1], encoding='utf-8-sig').read().strip()[-${2:-400}:])" "$1"; }

trap 'rm -rf "$WORK"' EXIT
test -x "$V8" || { echo "платформа не найдена: $V8"; exit 1; }
mkdir -p "$CFG/build"

step 1/6 "песочница и конфигурация синхронны?"
python3 "$HERE/check-sync.py"

step 2/6 "Kanctovary.cf из исходников"
guard "$V8" CREATEINFOBASE File="$WORK/cf-ib" /DisableStartupDialogs >/dev/null 2>&1
guard "$V8" DESIGNER /F"$WORK/cf-ib" /LoadConfigFromFiles "$CFG/src" /UpdateDBCfg \
      /DisableStartupDialogs /Out "$WORK/cf.log" >/dev/null 2>&1 || { log "$WORK/cf.log"; exit 1; }
guard "$V8" DESIGNER /F"$WORK/cf-ib" /DumpCfg "$CFG/build/Kanctovary.cf" \
      /DisableStartupDialogs /Out "$WORK/cf.log" >/dev/null 2>&1 || { log "$WORK/cf.log"; exit 1; }
echo "  $(log "$WORK/cf.log" 80)"

step 3/6 "временная база с загрузчиком из kanctovary.data.yaml"
cp -R "$CFG/src" "$WORK/src"
echo '[{"type":"CommonModule","name":"ЗагрузкаКанцтоваров","server":true,"serverCall":true}]' > "$WORK/cm.json"
python3 "$HOME/.claude/skills/meta-compile/scripts/meta-compile.py" -JsonPath "$WORK/cm.json" -OutputDir "$WORK/src" >/dev/null
python3 "$HERE/make-loader.py" --data "$DATA" --out "$WORK/src" >/dev/null
guard "$V8" CREATEINFOBASE File="$IB" /DisableStartupDialogs >/dev/null 2>&1
guard "$V8" DESIGNER /F"$IB" /LoadConfigFromFiles "$WORK/src" /UpdateDBCfg \
      /DisableStartupDialogs /Out "$WORK/load.log" >/dev/null 2>&1 || { log "$WORK/load.log"; exit 1; }
echo "  $(log "$WORK/load.log" 60)"

step 4/6 "Предприятие: загрузка данных и проведение"
RESULT="$WORK/result.tsv"
TIMEOUT=300 guard "$V8" ENTERPRISE /F"$IB" /C"ЗАГРУЗИТЬ:$RESULT" \
      /DisableStartupDialogs /DisableStartupMessages >/dev/null 2>&1 || true
test -s "$RESULT" || { echo "  загрузчик ничего не выгрузил"; exit 1; }
echo "  выгружено строк: $(wc -l < "$RESULT" | tr -d ' ')"

step 5/6 "база 1С против песочницы"
python3 "$HERE/check-base.py" --data "$DATA" --result "$RESULT"

step 6/6 "чистая конфигурация и Kanctovary.dt"
guard "$V8" DESIGNER /F"$IB" /LoadCfg "$CFG/build/Kanctovary.cf" /UpdateDBCfg \
      /DisableStartupDialogs /Out "$WORK/final.log" >/dev/null 2>&1 || { log "$WORK/final.log"; exit 1; }
guard "$V8" DESIGNER /F"$IB" /DumpIB "$CFG/build/Kanctovary.dt" \
      /DisableStartupDialogs /Out "$WORK/final.log" >/dev/null 2>&1 || { log "$WORK/final.log"; exit 1; }
echo "  $(log "$WORK/final.log" 80)"

printf '\nГотово:\n'
ls -la "$CFG/build/"
