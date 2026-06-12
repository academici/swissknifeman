#!/usr/bin/env bash
# Source: anonymized production Laravel project
#
# symlink-sync.sh — генерация симлинков на скиллы из единого источника .ai/skills.
#
# Идемпотентный: повторный запуск ничего не ломает.
#   1. Удаляет битые симлинки в целевых каталогах (источник переименован/удалён).
#   2. Для каждого каталога в .ai/skills создаёт/обновляет симлинк
#      в .claude/skills и .cursor/skills.
#   3. НЕ трогает реальные каталоги (vendor-копии из .agents/skills и т.п.) —
#      о конфликте имён только предупреждает.
#
# Запуск из любого места внутри git-репозитория: bash scripts/symlink-sync.sh
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SOURCE_DIR="$ROOT/.ai/skills"
TARGETS=(".claude/skills" ".cursor/skills")

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Ошибка: нет каталога $SOURCE_DIR — нечего синхронизировать" >&2
  exit 1
fi

for target_rel in "${TARGETS[@]}"; do
  target_dir="$ROOT/$target_rel"
  mkdir -p "$target_dir"

  # --- Шаг 1: удаляем битые симлинки -------------------------------------
  while IFS= read -r -d '' link; do
    if [[ ! -e "$link" ]]; then
      echo "rm  (битый симлинк): ${link#"$ROOT"/}"
      rm -f "$link"
    fi
  done < <(find "$target_dir" -maxdepth 1 -type l -print0)

  # --- Шаг 2: создаём/обновляем симлинки на каждый скилл из источника ----
  for src in "$SOURCE_DIR"/*/; do
    [[ -d "$src" ]] || continue
    name="$(basename "$src")"
    link="$target_dir/$name"
    # Относительный путь: цель лежит на два уровня ниже корня
    # (.claude/skills/<name>, .cursor/skills/<name>), поэтому ../../
    rel="../../.ai/skills/$name"

    if [[ -L "$link" ]]; then
      # Симлинк уже есть — пересоздаём, только если указывает не туда
      [[ "$(readlink "$link")" == "$rel" ]] && continue
      rm -f "$link"
    elif [[ -e "$link" ]]; then
      # Реальный каталог (копия/vendor-скилл) — не трогаем
      echo "skip (реальный каталог, не симлинк): $target_rel/$name" >&2
      continue
    fi

    ln -s "$rel" "$link"
    echo "ln  $target_rel/$name -> $rel"
  done
done

echo "Готово: симлинки агентов синхронизированы с .ai/skills"
