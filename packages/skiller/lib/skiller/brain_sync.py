"""BRAIN docs-sync — synchronize files between Brain-valt and project.

Before this block brain in integrate was printing ONLY a hint (was configured from the outside
volta). Here is the minimum deterministic layer (stdlib-only): pull glob-patterns
from BRAIN to project and generation bash-script `.claude/sync-brain.sh` (double-sided
wrapper over rsync-a similar copy via shell, so that the developer can drive the sync outside
Claude Code).

Config brain — from `.swissknife.json::memory_brain` (see common.CONFIG_KEYS):
  string          → path to volt, no sin rules (documentsync disabled, only
                    memory-hook in integrate — back-compat);
  object {path,    → doc-sync: path + sync{direction, on_integrate, patterns}.
          sync?}

BrainSync normalizes both forms: the string becomes {"path": <string>}.
"""
import shutil
from pathlib import Path

from core import atomic_write_text

# Default glob-patterns doc-sync, if in the config patterns are not specified. docs/ —
# main documentation; README — entry point. Relative to the root BRAIN/project.
DEFAULT_PATTERNS = ("docs/**/*.md", "README.md")
# Default direction if sync.direction not specified: pull (BRAIN → project) —
# the safest (we pull a ready-made document into the project, we don’t write silently from the project to volt).
DEFAULT_DIRECTION = "pull"
DIRECTIONS = ("push", "pull", "bidirectional")


def normalize_brain_config(brain_config):
    """Bring config brain to canonical dictionary {"path": str, "sync": {...}}.

    String → {"path": string} (back-compat: path without synchronization rules). The object is taken
    as is. None/empty → {}. Returns a NEW dictionary (input is not mutated)."""
    if not brain_config:
        return {}
    if isinstance(brain_config, str):
        return {"path": brain_config}
    if isinstance(brain_config, dict):
        return dict(brain_config)
    return {}


class BrainSync:
    """File synchronizer project↔BRAIN by glob-patterns.

    project_path — consuming project root; brain_config — value
    `memory_brain` from .swissknife.json (path string OR object {path, sync?})."""

    def __init__(self, project_path, brain_config):
        self.project_path = Path(project_path)
        cfg = normalize_brain_config(brain_config)
        self.brain_path = Path(cfg["path"]) if cfg.get("path") else None
        sync = cfg.get("sync") or {}
        self.direction = sync.get("direction") or DEFAULT_DIRECTION
        self.on_integrate = bool(sync.get("on_integrate", False))
        self.patterns = list(sync.get("patterns") or DEFAULT_PATTERNS)

    # --- pull (BRAIN → project) -------------------------------------------------
    def sync_pull(self):
        """Copy files from BRAIN to the project by self.patterns. For everyone glob
        (relative to root BRAIN) — mkdir destination directory + copy2 with saving
        relative path. Returns a list of copied files (paths in the project).

        Idempotent (overwrite), DOES NOT remove unnecessary things in the project (safety: pull only
        adds/updates). If brain_path is not specified or does not exist - [] (softly)."""
        if not self.brain_path or not self.brain_path.is_dir():
            return []
        copied = []
        for pattern in self.patterns:
            for src in sorted(self.brain_path.glob(pattern)):
                if not src.is_file():
                    continue
                rel = src.relative_to(self.brain_path)
                dst = self.project_path / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(dst)
        return copied

    # --- generation shell-script -----------------------------------------------
    def generate_sync_script(self, script_path=None):
        """Generate `.claude/sync-brain.sh` — bash-manual sync wrapper
        BRAIN↔project (rsync). Writes atomically; returns Path script.

        The script can pull/push by argument (default - self.direction) and knows
        hardwired path to BRAIN and patterns from the config. chmod 755 hangs the caller
        (integrate) — there is only content here."""
        if script_path is None:
            script_path = self.project_path / ".claude" / "sync-brain.sh"
        script_path = Path(script_path)
        script_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(script_path, self._render_script())
        return script_path

    def _render_script(self):
        """Body bash-sync script. Patterns and the way to BRAIN — from the config."""
        brain = str(self.brain_path) if self.brain_path else ""
        patterns = " ".join(_shell_quote(p) for p in self.patterns)
        default_dir = self.direction if self.direction in DIRECTIONS else DEFAULT_DIRECTION
        return _SCRIPT_TEMPLATE.format(
            brain=_shell_quote(brain),
            patterns=patterns,
            default_dir=default_dir,
        )


def _shell_quote(s):
    """Enclose string in single quotes for safe substitution bash."""
    return "'" + str(s).replace("'", "'\\''") + "'"


# Template of the generated .claude/sync-brain.sh. Synchronizes by glob-patterns via
# rsync (keeping relative path). Argument 1 - direction (pull|push), default
# is programmed from the config. Comments/messages in Russian.
_SCRIPT_TEMPLATE = """#!/usr/bin/env bash
# Generated skiller (brain_sync) — project documentation synchronization↔BRAIN.
# Edit config.swissknife.json::memory_brain, then `skiller integrate` will be regenerated.
set -euo pipefail

BRAIN={brain}
PROJECT="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
PATTERNS=({patterns})
DIRECTION="${{1:-{default_dir}}}"

if [[ -z "$BRAIN" ]]; then
  echo "BRAIN is not set in .swissknife.json::memory_brain — nothing to sync" >&2
  exit 1
fi

pull() {{  # BRAIN → project
  for pat in "${{PATTERNS[@]}}"; do
    ( cd "$BRAIN" && find . -path "./$pat" -type f -print0 2>/dev/null ) \\
      | while IFS= read -r -d '' rel; do
          mkdir -p "$PROJECT/$(dirname "$rel")"
          cp -p "$BRAIN/$rel" "$PROJECT/$rel"
        done
  done
  echo "pull ready: BRAIN → project"
}}

push() {{  # project → BRAIN
  for pat in "${{PATTERNS[@]}}"; do
    ( cd "$PROJECT" && find . -path "./$pat" -type f -print0 2>/dev/null ) \\
      | while IFS= read -r -d '' rel; do
          mkdir -p "$BRAIN/$(dirname "$rel")"
          cp -p "$PROJECT/$rel" "$BRAIN/$rel"
        done
  done
  echo "push ready: project → BRAIN"
}}

case "$DIRECTION" in
  pull) pull ;;
  push) push ;;
  bidirectional) pull; push ;;
  *) echo "unknown direction: $DIRECTION (pull|push|bidirectional)" >&2; exit 2 ;;
esac
"""
