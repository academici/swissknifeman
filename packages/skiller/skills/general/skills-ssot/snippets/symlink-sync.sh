#!/usr/bin/env bash
# Optional publisher for projects explicitly choosing .ai/skills and these target roots.
# Preserve all real directories and links owned by another source/publisher.
set -euo pipefail

SKILL_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SKILL_SOURCE="$SKILL_ROOT/.ai/skills"
SKILL_TARGETS=(".claude/skills" ".cursor/skills")
[[ -d "$SKILL_SOURCE" ]] || { echo "Missing source: $SKILL_SOURCE" >&2; exit 1; }

for target_rel in "${SKILL_TARGETS[@]}"; do
    target_dir="$SKILL_ROOT/$target_rel"
    mkdir -p "$target_dir"
    # A link is managed only when it has the exact target this publisher would create.
    for link in "$target_dir"/*; do
        [[ -L "$link" ]] || continue
        name="${link##*/}"
        expected="../../.ai/skills/$name"
        if [[ "$(readlink "$link")" == "$expected" && ! -e "$link" ]]; then
            rm -- "$link"
            echo "Removed stale managed link: $target_rel/$name"
        fi
    done
    for src in "$SKILL_SOURCE"/*/; do
        [[ -d "$src" && -f "$src/SKILL.md" ]] || continue
        name="$(basename "$src")"
        link="$target_dir/$name"
        expected="../../.ai/skills/$name"
        if [[ -L "$link" ]]; then
            [[ "$(readlink "$link")" == "$expected" ]] && continue
            echo "Preserved foreign link: $target_rel/$name" >&2
            continue
        elif [[ -e "$link" ]]; then
            echo "Preserved existing path: $target_rel/$name" >&2
            continue
        fi
        ln -s -- "$expected" "$link"
        echo "Published: $target_rel/$name"
    done
done
