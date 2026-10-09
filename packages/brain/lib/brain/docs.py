"""Document sync between a project and the vault: pull, push and the generated manual script.

Only files matched by the configured glob patterns move. ``pull`` copies vault files into the project and
only adds or updates. ``push`` copies project files into the vault and never replaces a vault file whose
content differs unless forced. Neither direction deletes anything.
"""
from __future__ import annotations

import filecmp
import shutil
from pathlib import Path, PurePath
from typing import List, Optional, Sequence

from aicore.util.io import atomic_write_text

from . import settings as _settings
from . import vault as _vault

DIRECTIONS = ("push", "pull", "bidirectional")
DEFAULT_DIRECTION = "pull"
SCRIPT_RELATIVE = Path(".claude") / "sync-brain.sh"


def _shell_quote(s):
    """Enclose a string in single quotes for safe substitution in bash."""
    return "'" + str(s).replace("'", "'\\''") + "'"


def _safe_pattern(pattern: str) -> bool:
    """A pattern must stay inside its root: relative, without ``..``."""
    parts = PurePath(pattern).parts
    return bool(parts) and not PurePath(pattern).is_absolute() and ".." not in parts


class DocsSync:
    """Copies documents between ``project_root`` and ``vault`` by glob ``patterns`` (relative to both roots)."""

    def __init__(self, project_root, vault: Optional[Path], direction: str = DEFAULT_DIRECTION,
                 patterns: Sequence[str] = _settings.DEFAULT_PATTERNS) -> None:
        self.project_root = Path(project_root)
        self.vault = Path(vault) if vault is not None else None
        self.direction = direction if direction in DIRECTIONS else DEFAULT_DIRECTION
        self.patterns = tuple(patterns)
        # Files that ``push`` skipped because the vault holds different content; reset by every ``push``.
        self.conflicts: List[Path] = []

    @classmethod
    def from_settings(cls, project_root, config: _settings.BrainSettings,
                      info: Optional[_vault.VaultInfo]) -> "DocsSync":
        """A syncer for the resolved settings; a missing vault gives a syncer whose copies are no-ops."""
        root = info.path if info is not None and info.exists else None
        return cls(project_root, root, config.docs_direction, config.docs_patterns)

    def _matches(self, root: Path) -> List[Path]:
        found: List[Path] = []
        for pattern in self.patterns:
            if not _safe_pattern(pattern):
                continue
            for source in sorted(root.glob(pattern)):
                if source.is_file() and source not in found:
                    found.append(source)
        return found

    # --- pull (vault -> project) ------------------------------------------------
    def pull(self, dry_run: bool = False) -> List[Path]:
        """Copy vault files to the project; returns the project paths written (or that would be).

        Idempotent; never removes anything. No vault: an empty list."""
        if self.vault is None or not self.vault.is_dir():
            return []
        copied: List[Path] = []
        for source in self._matches(self.vault):
            target = self.project_root / source.relative_to(self.vault)
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            copied.append(target)
        return copied

    # --- push (project -> vault) ------------------------------------------------
    def push(self, dry_run: bool = False, force: bool = False) -> List[Path]:
        """Copy project files to the vault; returns the vault paths written (or that would be).

        A vault file with identical content is left alone. One with different content is skipped and listed
        in ``self.conflicts`` unless ``force``. No vault: an empty list."""
        self.conflicts = []
        if self.vault is None or not self.vault.is_dir():
            return []
        copied: List[Path] = []
        for source in self._matches(self.project_root):
            target = self.vault / source.relative_to(self.project_root)
            if target.is_file():
                if filecmp.cmp(source, target, shallow=False):
                    continue
                if not force:
                    self.conflicts.append(target)
                    continue
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            copied.append(target)
        return copied

    # --- manual script ----------------------------------------------------------
    def write_script(self, path=None) -> Path:
        """Write ``.claude/sync-brain.sh`` (atomic, mode 0o755) and return its path."""
        script = Path(path) if path is not None else self.project_root / SCRIPT_RELATIVE
        atomic_write_text(script, self._render_script(), mode=0o755)
        return script

    def _render_script(self) -> str:
        return _SCRIPT_TEMPLATE.format(
            brain=_shell_quote(str(self.vault) if self.vault else ""),
            patterns=" ".join(_shell_quote(p) for p in self.patterns),
            default_dir=self.direction,
        )


# The generated .claude/sync-brain.sh: copies by glob patterns with find and cp (keeping relative paths).
# Argument 1 is the direction (pull|push|bidirectional); the default is fixed from the configuration.
_SCRIPT_TEMPLATE = """#!/usr/bin/env bash
# Generated by brain docs script — project ↔ vault document sync.
# Edit the [brain] configuration, then run brain docs script again.
set -euo pipefail

BRAIN={brain}
PROJECT="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
PATTERNS=({patterns})
DIRECTION="${{1:-{default_dir}}}"

# find has no recursive wildcard: "docs/**/*.md" must also match a file directly below docs/.
for pat in "${{PATTERNS[@]}}"; do
  flat="${{pat//\\/\\*\\*\\//\\/}}"
  if [[ "$flat" != "$pat" ]]; then PATTERNS+=("$flat"); fi
done

if [[ -z "$BRAIN" ]]; then
  echo "BRAIN is not set: run brain vault to check the vault path" >&2
  exit 1
fi

pull() {{  # vault → project
  for pat in "${{PATTERNS[@]}}"; do
    ( cd "$BRAIN" && find . -path "./$pat" -type f -print0 2>/dev/null ) \\
      | while IFS= read -r -d '' rel; do
          mkdir -p "$PROJECT/$(dirname "$rel")"
          cp -p "$BRAIN/$rel" "$PROJECT/$rel"
        done
  done
  echo "pull done: vault → project"
}}

push() {{  # project → vault
  for pat in "${{PATTERNS[@]}}"; do
    ( cd "$PROJECT" && find . -path "./$pat" -type f -print0 2>/dev/null ) \\
      | while IFS= read -r -d '' rel; do
          mkdir -p "$BRAIN/$(dirname "$rel")"
          cp -p "$PROJECT/$rel" "$BRAIN/$rel"
        done
  done
  echo "push done: project → vault"
}}

case "$DIRECTION" in
  pull) pull ;;
  push) push ;;
  bidirectional) pull; push ;;
  *) echo "unknown direction: $DIRECTION (pull|push|bidirectional)" >&2; exit 2 ;;
esac
"""
