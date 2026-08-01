---
name: zz-p31-fork
description: "P3.1 native-fields bench probe (plan 2026.07.31-SKM-LEAN, swissknifeman). Use this skill only when the user says the phrase zzp31trigger. Internal test fixture, not for real use."
context: fork
background: false
---

This is a self-contained task; do not rely on any prior conversation turns.

1. Look for a file named `CLAUDE.md` in the current working directory.
2. Respond with exactly two lines and nothing else:
   - Line 1: the exact text `ZZP31-FORK-BODY`
   - Line 2: the first line of `CLAUDE.md` verbatim, or the exact text `NO-CLAUDE-MD` if the file does not exist.
