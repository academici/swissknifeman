#!/usr/bin/env bash
# Markdown-факты: файлы фактов + индекс MEMORY.md. Схема frontmatter совместима
# с нативной памятью Claude Code (name/description/metadata.type), поэтому один
# парсер читает и общий store, и свои memory/ участников. Источать, не запускать.

slugify() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' \
    | sed -E 's/-+/-/g; s/^-//; s/-$//' | cut -c1-48
}

# store_remember <dir> <type> <brain> <origin> <text> → печатает путь файла.
store_remember() {
  local dir="$1" type="$2" brain="$3" origin="$4" text="$5"
  mkdir -p "$dir" || return 1
  local ts slug name file desc
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  slug="$(slugify "$text")"; [ -n "$slug" ] || slug="fact"
  name="$slug-$(date -u +%Y%m%d%H%M%S)"
  file="$dir/$name.md"
  desc="$(printf '%s' "$text" | head -1 | cut -c1-80)"
  {
    printf -- '---\n'
    printf 'name: %s\n' "$name"
    printf 'description: %s\n' "$desc"
    printf 'metadata:\n'
    printf '  type: %s\n' "$type"
    printf '  brain: %s\n' "$brain"
    printf '  origin: %s\n' "$origin"
    printf '  created: %s\n' "$ts"
    printf -- '---\n\n'
    printf '%s\n' "$text"
  } > "$file" || return 1
  local idx="$dir/MEMORY.md"
  [ -f "$idx" ] || printf '# Memory Index\n\n' > "$idx"
  printf -- '- [%s](%s) — %s\n' "$name" "$name.md" "$desc" >> "$idx"
  printf '%s\n' "$file"
}

# store_count <dir> → число файлов фактов (без MEMORY.md).
store_count() {
  local d="$1"
  [ -d "$d" ] || { echo 0; return; }
  find "$d" -maxdepth 1 -name '*.md' ! -name 'MEMORY.md' 2>/dev/null | wc -l | tr -d ' '
}

# rank_dirs <query> <dir>... → "score<TAB>file" по убыванию score (fixed-string,
# термы ≥3 символов; считаем число вхождений каждого терма по файлу).
rank_dirs() {
  local query="$1"; shift
  local terms; terms="$(printf '%s' "$query" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' ' ')"
  local d f t n score
  for d in "$@"; do
    [ -d "$d" ] || continue
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      score=0
      for t in $terms; do
        [ "${#t}" -ge 3 ] || continue
        n="$(grep -Fio -- "$t" "$f" 2>/dev/null | wc -l | tr -d ' ')"
        score=$((score + n))
      done
      [ "$score" -gt 0 ] && printf '%s\t%s\n' "$score" "$f"
    done < <(find "$d" -maxdepth 1 -name '*.md' ! -name 'MEMORY.md' 2>/dev/null)
  done | sort -rn
}

# recall_print <query> <topN> <dir>... → топ-N фактов с кратким телом.
recall_print() {
  local query="$1" top="$2"; shift 2
  local out; out="$(rank_dirs "$query" "$@")"
  [ -n "$out" ] || { echo "(ничего не найдено по: $query)"; return; }
  local i=0 score file
  while IFS=$'\t' read -r score file; do
    i=$((i + 1)); [ "$i" -le "$top" ] || break
    printf '— [%s] %s\n' "$score" "$file"
    sed -n '/^---$/,/^---$/d; p' "$file" 2>/dev/null | sed '/^[[:space:]]*$/d' | head -4 | sed 's/^/    /'
  done <<< "$out"
}
