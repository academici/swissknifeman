#!/usr/bin/env bash
# Когерентность двуязычных скиллов. Модель: SKILL.ru.md — полный русский ИСТОЧНИК
# (его правит человек), SKILL.md — компактный EN-канон, ГЕНЕРИРУЕМЫЙ из него (его
# грузит агент; русский агент не видит). Свежесть EN метится строкой
#   <!-- ru-source-sha256: <hash> -->
# в SKILL.md = sha256 файла SKILL.ru.md на момент генерации.
#
# Плюс ГЕЙТ непереводимых литералов (D28): директива `<!-- i18n-keep: <литерал> -->` в
# SKILL.ru.md объявляет строку, которую внешний парсер грепает байт-в-байт (шапки таблиц,
# маркеры) — генератор EN обязан перенести её дословно. Отсутствие литерала в SKILL.md = ❌
# и НЕНУЛЕВОЙ exit в ЛЮБОМ режиме отчёта (не только --strict): переведённый литерал ломает
# парсер молча. Механизм универсален — скилл без директив ведёт себя ровно как раньше.
#
# Гейт ДВУСТОРОННИЙ (2026-07-17): литерал обязан присутствовать не только в EN, но и в ТЕЛЕ
# SKILL.ru.md — не только в самой директиве. Объявленный, но не употреблённый в источнике
# литерал = правило, которого в каноне-источнике НЕТ: оно живёт лишь в EN и будет снесено
# первой же честной регенерацией (EN — derived-артефакт, генератор выкидывает всё, чего нет
# в RU). Инцидент-основание: `<!-- i18n-keep: Вердикт: -->` объявлен, гейт plan-lint по нему
# реализован, RU литерал не спелил — правило прожило до ближайшей регенерации, которая штатно
# и молча его удалила. Прежние гейты (реестр CANON_LITERALS · присутствие в EN · штамп sha)
# смотрят на директиву и на EN, но не на тело источника, — класс не ловился.
#
# Режимы (НЕ вызывается из `skiller registry` — отдельный тулинг):
#   (по умолчанию) отчёт: локальные без RU-источника; EN протух (RU правлен после
#     генерации → регенерить SKILL.md); осиротевшие SKILL.ru.md; гейт литералов.
#   --strict  ненулевой код при ЛЮБЫХ проблемах (для CI; гейт литералов красит и без него).
#   --stamp   проставить/обновить маркер ru-source-sha256 в локальных SKILL.md по
#     текущему SKILL.ru.md (запускать ПОСЛЕ регенерации EN — «подтверждаю синхрон»).
# Usage: scripts/check-translations.sh [--strict|--stamp]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO_ROOT" "$@" <<'PY'
import hashlib
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
flags = sys.argv[2:]
strict = "--strict" in flags
stamp = "--stamp" in flags
skills_root = root / "skills"

# `PENDING` — плейсхолдер, который эмитит промт-генератор EN; без него в альтернативе
# `--stamp` не находил маркер и ДОПИСЫВАЛ второй вместо замены (G11: сработало дважды).
MARKER = re.compile(r"<!--\s*ru-source-sha256:\s*([0-9a-fA-F]{64}|PENDING)\s*-->")
# Директива непереводимого литерала (D28) — по строке на литерал, живёт в SKILL.ru.md.
I18N_KEEP = re.compile(r"<!--\s*i18n-keep:\s*(.+?)\s*-->")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def set_marker(md, digest):
    """Записать/обновить маркер ru-source-sha256 в конце SKILL.md."""
    text = md.read_text(encoding="utf-8")
    line = f"<!-- ru-source-sha256: {digest} -->"
    if MARKER.search(text):
        text = MARKER.sub(line, text, count=1)
    else:
        text = text.rstrip("\n") + "\n\n" + line + "\n"
    md.write_text(text, encoding="utf-8")


local = external = ext_with_ru = stale = missing_ru = orphaned = stamped = 0
literal_misses = 0
problems = []

for md in sorted(skills_root.rglob("SKILL.md")):
    d = md.parent
    rel = d.relative_to(root)
    is_external = (d / "upstream.json").is_file()
    ru = d / "SKILL.ru.md"
    if is_external:
        external += 1
        if ru.is_file():
            ext_with_ru += 1
        # внешним RU-справка необязательна; канон — upstream EN, не трогаем
        continue
    local += 1
    if not ru.is_file():
        missing_ru += 1
        problems.append(f"❌ НЕТ RU-источника: {rel}/SKILL.ru.md "
                        f"(локальный скилл — нужен полный русский источник)")
        continue
    if stamp:
        set_marker(md, sha(ru))
        stamped += 1
        continue
    md_text = md.read_text(encoding="utf-8")
    ru_text = ru.read_text(encoding="utf-8")
    # Тело RU = файл БЕЗ строк-директив: по нему сверяем, что литерал реально употреблён,
    # а не только объявлен (иначе `lit in ru_text` всегда истинно — директива сама его несёт).
    ru_body = "\n".join(ln for ln in ru_text.splitlines() if not I18N_KEEP.search(ln))
    # гейт непереводимых литералов: директивы берём из RU (SSOT), присутствие сверяем
    # ПОДСТРОКОЙ в EN — литерал может стоять и в таблице, и в code-блоке, и в прозе.
    for lit in I18N_KEEP.findall(ru_text):
        if lit not in md_text:
            literal_misses += 1
            problems.append(f"❌ EN не несёт непереводимый литерал «{lit}»: {rel}/SKILL.md "
                            f"(объявлен директивой i18n-keep в SKILL.ru.md — регенерируй EN "
                            f"промтом prompts/generate/claude-canon-from-ru.md: литералы "
                            f"переносятся байт-в-байт, править SKILL.md руками нельзя)")
        # Литерал объявлен, но в ТЕЛЕ RU не встречается: канон не учит агента его писать —
        # правило существует только в EN и будет снесено ПЕРВОЙ ЖЕ честной регенерацией
        # (EN — derived-артефакт; генератор обязан выкинуть всё, чего нет в RU).
        # Инцидент-основание: `<!-- i18n-keep: Вердикт: -->` объявлен, гейт plan-lint по нему
        # реализован, а RU литерал не спелил — правило жило только в EN, и регенерация его
        # удалила, штатно и молча. Три прежних гейта (реестр T2 · присутствие в EN · штамп sha)
        # этот класс не ловят: они смотрят на директиву и на EN, но не на тело источника.
        if lit not in ru_body:
            literal_misses += 1
            problems.append(f"❌ литерал «{lit}» объявлен i18n-keep, но НЕ УПОТРЕБЛЁН в теле "
                            f"{rel}/SKILL.ru.md (только в директиве) — источник истины не учит "
                            f"агента его писать: правило живёт лишь в EN и умрёт при первой "
                            f"регенерации. Впиши литерал в прозу/таблицу/code-блок RU либо "
                            f"сними директиву, если он больше не канон")
    # defense-in-depth: маркер должен быть РОВНО один и без stale-плейсхолдера
    marker_lines = [ln for ln in md_text.splitlines() if "ru-source-sha256:" in ln]
    if any("PENDING" in ln for ln in marker_lines):
        stale += 1
        problems.append(f"❌ stale-плейсхолдер ru-source-sha256: PENDING: {rel}/SKILL.md "
                        f"(удали строку-заглушку, оставь реальный хеш)")
    if len(marker_lines) > 1:
        stale += 1
        problems.append(f"❌ несколько маркеров ru-source-sha256 ({len(marker_lines)}): "
                        f"{rel}/SKILL.md (должен быть ровно один)")
    m = MARKER.search(md_text)
    if not m:
        stale += 1
        problems.append(f"⚠️  EN без маркера ru-source-sha256: {rel}/SKILL.md "
                        f"(сгенерируй компактный EN из SKILL.ru.md)")
    elif m.group(1).lower() != sha(ru):
        stale += 1
        problems.append(f"⚠️  EN протух (RU правлен после генерации): {rel}/SKILL.md "
                        f"(регенерируй из SKILL.ru.md)")

# осиротевшие переводы
for ru in sorted(skills_root.rglob("SKILL.ru.md")):
    if not (ru.parent / "SKILL.md").is_file():
        orphaned += 1
        problems.append(f"⚠️  ОСИРОТЕВШИЙ: {ru.relative_to(root)} (нет SKILL.md рядом)")

if stamp:
    print(f"Проставлен маркер ru-source-sha256 в {stamped} локальных SKILL.md "
          f"(без RU-источника пропущено: {missing_ru}).")
    sys.exit(0)

for p in problems:
    print(p)
print(f"\nЛокальных: {local} (RU-источник: {local - missing_ru}, нет: {missing_ru}, "
      f"EN протух/без маркера: {stale}) · внешних: {external} "
      f"(с RU-справкой: {ext_with_ru}) · осиротевших: {orphaned} · "
      f"непереводимых литералов нет в EN: {literal_misses}")

# гейт литералов — ЖЁСТКИЙ, вне зависимости от --strict: EN, разошедшийся с греппаемым
# литералом, ломает внешний парсер молча (G3: план по EN-канону не парсился вовсе).
if literal_misses:
    sys.exit(1)
if strict and (missing_ru or stale or orphaned):
    sys.exit(1)
PY
