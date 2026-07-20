#!/usr/bin/env python3
"""Generate and verify P0.5 command-surface correction evidence."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT_SETS = (
    ("task", "packages/task/commands"),
    ("skiller", "packages/skiller/skm/commands"),
    ("harness", "packages/harness/commands"),
    ("maind", "packages/maind/commands"),
    ("analyst", "packages/analyst/commands"),
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ("git", *args), cwd=root, text=True, stderr=subprocess.STDOUT
    ).rstrip()


def paths_for(root: Path, relative_root: str) -> list[str]:
    directory = root / relative_root
    if not directory.is_dir():
        raise RuntimeError(f"missing explicit root: {relative_root}")
    return sorted(
        path.relative_to(root).as_posix()
        for path in directory.glob("*.md")
        if path.is_file()
    )


def code_block(paths: list[str]) -> str:
    return "```text\n" + "\n".join(paths) + "\n```"


def render(root: Path) -> str:
    path_sets = [(name, relative_root, paths_for(root, relative_root)) for name, relative_root in ROOT_SETS]
    counts = [len(paths) for _, _, paths in path_sets]
    breakdown = " + ".join(str(count) for count in counts)
    tree_anchor = git(root, "rev-parse", "HEAD")
    worktree = git(root, "status", "--short") or "(clean)"

    root_rows = "\n".join(
        f"| {name} | `{relative_root}/*.md` | {len(paths)} |"
        for name, relative_root, paths in path_sets
    )
    raw_sets = "\n\n".join(
        f"### {name} — `{relative_root}/*.md` ({len(paths)})\n\n{code_block(paths)}"
        for name, relative_root, paths in path_sets
    )

    return f"""# P0 command-surface correction\n\n## Anchor\n\n- Tree: `{tree_anchor}` (`git rev-parse HEAD`).\n- Worktree (`git status --short`):\n\n{code_block(worktree.splitlines())}\n\nThis is an anchored observation of the current tree, not a frozen contract invariant.\n\n## Corrected metric\n\n**Command Surface** is the union of direct Markdown command definitions in the five explicit\nfirst-party package roots below. At this anchor it is **{sum(counts)}** files:\n**{breakdown} = {sum(counts)}** (task + skiller + harness + maind + analyst).\n\n**Task Command** is the narrower semantic workflow subset\n`packages/task/commands/*.md`, which contains **{counts[0]}** files at this anchor.\nPackage commands in the other four roots remain owned by their respective bounded contexts.\n\n## Root sets\n\n| Package surface | Explicit non-recursive root | Count |\n|:--|:--|--:|\n{root_rows}\n| **Total Command Surface** | union of the five roots | **{sum(counts)}** |\n\nOnly direct `*.md` files are collected: no recursive glob is used. In particular,\n`packages/harness/configs/**/commands/*.md` is agent-pack content and is outside this\ntop-level package command surface.\n\n## Raw sorted paths\n\n{raw_sets}\n\n## Supersession\n\nThis P0.5 finding supersedes **only the command-surface interpretation** of the historical\nP0.1 finding: its `32 task commands` label is corrected to an umbrella Command Surface\nof {sum(counts)} and a Task Command subset of {counts[0]}. P0.1 helper, finding, status, Completion\nNotes, and journal remain historical evidence and are not rewritten.\n\nThe truth chain is: P0.1 historical Task Command subset → P0.5 umbrella Command Surface\ncorrection → P0.2 owner vocabulary freeze. P0.5 does not approve vocabulary or P0.2.\n\n## Reproduction\n\n```bash\npython3 plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-command-surface-correction.py --write\npython3 plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-command-surface-correction.py --check\n```\n\nThe scanner is stdlib-only and reads the repository except when `--write` updates this\nP0.5 finding. `--check` compares the generated evidence byte-for-byte and returns nonzero\nwhen the anchored tree, worktree, root set, or content has drifted.\n"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write the correction finding")
    mode.add_argument("--check", action="store_true", help="fail when the finding has drifted")
    args = parser.parse_args()

    root = repo_root()
    finding = root / "plans/2026.07.19-DUAL-PROVIDER/findings/P0-command-surface-correction.md"
    try:
        expected = render(root)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"correction scan failed: {error}", file=sys.stderr)
        return 2

    if args.write:
        finding.write_text(expected, encoding="utf-8")
        print(f"wrote {finding.relative_to(root)}")
        return 0

    actual = finding.read_text(encoding="utf-8") if finding.exists() else ""
    if actual != expected:
        print("drift: correction finding differs; run with --write", file=sys.stderr)
        return 1
    print("no drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
