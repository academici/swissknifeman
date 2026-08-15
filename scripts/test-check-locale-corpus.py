#!/usr/bin/env python3
"""Run the locale corpus checker regression suite."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    suite = unittest.defaultTestLoader.loadTestsFromName("core.tests.locale.test_corpus")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
