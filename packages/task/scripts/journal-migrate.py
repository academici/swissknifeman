#!/usr/bin/env python3
"""Thin launcher for the owner-gated sealed-journal migrator."""
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent
_MONOREPO_ROOT = _PKG_ROOT.parent.parent
sys.path.insert(0, str(_PKG_ROOT / "lib"))
if (_MONOREPO_ROOT / "core").is_dir():
    sys.path.insert(0, str(_MONOREPO_ROOT))

from task.journal_migration import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
