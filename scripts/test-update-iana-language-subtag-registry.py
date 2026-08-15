#!/usr/bin/env python3
"""Deterministic smoke coverage for the explicit registry updater."""
from __future__ import annotations
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory() as directory:
    target = Path(directory) / "registry.txt"
    command = [sys.executable, str(ROOT / "scripts/update-iana-language-subtag-registry.py"),
               "--source", str(ROOT / "core/locale/data/language-subtag-registry.txt"),
               "--target", str(target), "--provenance", str(ROOT / "core/locale/data/upstream.json")]
    subprocess.run(command, check=True)
    subprocess.run(command + ["--check"], check=True)
