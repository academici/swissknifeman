#!/usr/bin/env python3
"""docs-impact gate: package-scoped docs-in-the-same-change-set.

Reads one `git diff --name-status -M` over a change-set and fails (exit 1) when the
change-set introduces/removes/renames a surface file, or touches an interface path, of a
package WITHOUT touching that same package's docs in the same change-set.

Trigger is measured rule C (`research/24-P8.4-refine-2026-07-27.md` §1-2), not "any surface
edit": status A/D/R on a surface path always triggers; status M triggers ONLY on interface
paths (`packages/*/{bin,commands,configs}/**`, root `bin/**`, `install.sh`). Editing the body
of `lib/**`/`scripts/*.{sh,py}` is NOT a trigger — the gate does not catch a
behavior change to an existing module without a new file and without an interface edit
(19 of 30 commits red under the rejected rule A on tree `cd93dbc8`); the strong form (rule D)
is deferred to `roadmap.md`. Coverage boundary is intentional, not a gap to silently widen.

Escape hatch: commit trailer `Docs-Not-Needed: <reason>` on any commit in the range (CI or
local), or env var DOCS_NOT_NEEDED="<reason>" (local/`--staged`). An empty value is NOT an
escape (still fails). The escape covers the WHOLE change-set — no partial per-class escape.

A package removed as a whole (every one of its surface entries is a deletion and the package folder is gone at the
head) needs no docs edit: its docs went with it.

`--base REF --worktree` measures the working tree (tracked changes and untracked files) against the merge-base with
REF, so a piece of work can be checked before it is committed.

Range: always three-dot (`<base>...<head>`, merge-base diff) — this generalizes the spec's
"three dots on PR, two dots on push": for a push range like `HEAD~1..HEAD` the merge-base of
two directly-linear commits IS the base itself, so three-dot and two-dot diffs are byte-
identical; using three-dot everywhere avoids a second code path for the same git primitive.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# --- surfaces (DATA card - research/24 §2-3, D119/D120) --------------------------
SURFACE_PKG = re.compile(r"^packages/([^/]+)/(bin|lib|commands|configs)/")
SURFACE_ROOT = re.compile(r"^(bin/|install\.sh$|scripts/[^/]+\.(sh|py)$)")

# NOT surfaces - checked FIRST. Exception `.md` narrowed to DOC-md:
# bodies slash-commands packages/*/commands/**.md and agent-pack-configs packages/*/configs/**.md
# — product, not documentation, and under general "**/*.md" are not covered.
NON_SURFACE = [
    re.compile(r"(^|/)tests?/"),
    re.compile(r"^scripts/test-"),
    re.compile(r"^plans/"),
    re.compile(r"^\.github/"),
    re.compile(r"^docs/"),
    re.compile(r"^packages/[^/]+/docs/"),
    re.compile(r"^[^/]+\.md$"),
    re.compile(r"^packages/[^/]+/(CLAUDE|README|CHANGELOG)\.md$"),
    re.compile(r"^packages/skiller/skills/"),
]

# Interface paths: status M triggers here and only here (D119 rule C).
INTERFACE = re.compile(r"^(packages/[^/]+/(bin|commands|configs)/|bin/|install\.sh$)")

DOCS_NOT_NEEDED_RE = re.compile(r"^Docs-Not-Needed:[ \t]*(.*)$", re.MULTILINE)

SURFACE_DOCS_HINT: dict[str, str] = {}


def surface(path: str) -> str | None:
    if any(rx.search(path) for rx in NON_SURFACE):
        return None
    m = SURFACE_PKG.match(path)
    if m:
        return "pkg:" + m.group(1)
    if SURFACE_ROOT.match(path):
        return "root"
    return None


def credit(path: str) -> set[str]:
    """Classes whose docs `path` counts as. The foundation's durable docs are the architecture pages and the core page."""
    m = re.match(r"^packages/([^/]+)/docs/", path)
    if m:
        return {"pkg:" + m.group(1)}
    if path.startswith("docs/planner/"):
        return {"pkg:planner"}
    if path.startswith("docs/core/"):
        return {"core", "pkg:aicore"}
    if path.startswith("docs/architecture/"):
        return {"pkg:aicore"}
    if re.match(r"^docs/[^/]+\.md$", path):
        return {"root"}
    return set()


def docs_hint(klass: str) -> str:
    if klass in SURFACE_DOCS_HINT:
        return SURFACE_DOCS_HINT[klass]
    if klass.startswith("pkg:"):
        pkg = klass[len("pkg:"):]
        if pkg == "planner":
            return f"packages/{pkg}/docs/** or docs/planner/**"
        return f"packages/{pkg}/docs/**"
    if klass == "root":
        return "docs/*.md (top level)"
    return klass


class GitError(RuntimeError):
    pass


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def parse_name_status(text: str) -> list[tuple[str, str]]:
    """→ list of (status, path); renames yield two entries (D old, A new)."""
    entries: list[tuple[str, str]] = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0][0]
        if status == "R":
            old_path, new_path = parts[1], parts[2]
            entries.append(("D", old_path))
            entries.append(("A", new_path))
        else:
            entries.append((status, parts[-1]))
    return entries


def classify(entries: list[tuple[str, str]], exists=None):
    """→ (needed: {class: [(path, status)]}, credited: {class}). ``exists(path)`` says whether a path is in the head;
    a package whose surface entries are all deletions and whose folder is gone is credited (removed as a whole)."""
    needed: dict[str, list[tuple[str, str]]] = {}
    credited: set[str] = set()
    for status, path in entries:
        klass = surface(path)
        if klass:
            triggers = status in ("A", "D") or (status == "M" and INTERFACE.match(path))
            if triggers:
                needed.setdefault(klass, []).append((path, status))
        credited |= credit(path)
    if exists is not None:
        for klass, rows in needed.items():
            if klass.startswith("pkg:") and all(status == "D" for _, status in rows) \
                    and not exists(f"packages/{klass[len('pkg:'):]}"):
                credited.add(klass)
    return needed, credited


def escape_reason(range_args: list[str] | None) -> str | None:
    import os

    env_reason = os.environ.get("DOCS_NOT_NEEDED")
    if env_reason:
        return env_reason
    if range_args is None:
        return None
    try:
        messages = git("log", "--format=%B", *range_args)
    except GitError:
        return None
    reasons = [m.strip() for m in DOCS_NOT_NEEDED_RE.findall(messages) if m.strip()]
    if reasons:
        return "; ".join(reasons)
    return None


def report(needed: dict[str, list[tuple[str, str]]], credited: set[str]) -> list[str]:
    lines = []
    for klass in sorted(needed):
        if klass in credited:
            continue
        for path, status in needed[klass]:
            lines.append(f"{path} — {klass}, status {status}, were waiting for an edit {docs_hint(klass)}")
    return lines


def run(entries: list[tuple[str, str]], range_args: list[str] | None, exists=None) -> int:
    needed, credited = classify(entries, exists)
    missing = report(needed, credited)
    if not missing:
        print("docs-impact: OK")
        return 0
    reason = escape_reason(range_args)
    if reason:
        classes = sorted({klass for klass in needed if klass not in credited})
        print(f"docs-impact: bypass (Docs-Not-Needed: {reason}) — classes: {', '.join(classes)}")
        return 0
    print("docs-impact: there are not enough docks in the same change-set'e:")
    for line in missing:
        print(f"  {line}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--base", help="range base point (with --head)")
    group.add_argument("--staged", action="store_true", help="index (git diff --cached)")
    ap.add_argument("--head", help="high point of range (required with --base, unless --worktree)")
    ap.add_argument("--worktree", action="store_true",
                    help="with --base: the working tree (and untracked files) against the merge-base, before a commit")
    args = ap.parse_args()

    if args.base and not args.head and not args.worktree:
        ap.error("--base requires --head or --worktree")

    def in_tree(ref: str | None):
        def exists(path: str) -> bool:
            if ref is None:
                return (ROOT / path).exists()
            return subprocess.run(["git", "cat-file", "-e", f"{ref}:{path}"], cwd=ROOT, capture_output=True).returncode == 0
        return exists

    try:
        if args.staged:
            diff_text = git("diff", "--name-status", "-M", "--cached")
            range_args, exists = None, in_tree(None)
        elif args.worktree:
            base = git("merge-base", args.base, "HEAD").strip()
            diff_text = git("diff", "--name-status", "-M", base)
            untracked = git("ls-files", "--others", "--exclude-standard")
            diff_text += "".join(f"A\t{line}\n" for line in untracked.splitlines() if line)
            range_args, exists = [f"{args.base}..HEAD"], in_tree(None)
        else:
            diff_text = git("diff", "--name-status", "-M", f"{args.base}...{args.head}")
            range_args, exists = [f"{args.base}..{args.head}"], in_tree(args.head)
    except GitError as exc:
        print(f"docs-impact: error git — {exc}", file=sys.stderr)
        return 2

    entries = parse_name_status(diff_text)
    return run(entries, range_args, exists)


if __name__ == "__main__":
    sys.exit(main())
