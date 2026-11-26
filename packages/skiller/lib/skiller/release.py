"""release — build monorepo release proposal.

Reading `[Unreleased]` root `CHANGELOG.md`, classifies semver-bump from
conventional commits since last umbrella-tag (`vX.Y.Z`) and -
WITHOUT `--dry-run` — moves the section to `[X.Y.Z] - <date>` + prints the finished
tag command. NEVER tags/does not push itself and does NOT output MAJOR: sign
breaking-changes - refusal, the version remains a manual decision of the owner.

Semver-oracle (minor=capability/feat, patch=fix/perf) — from
an earlier audit, NOT reinvented here.
stdlib-only, `Env` is passed explicitly (tested in tmpdir)."""
import sys

from aicore.state import backup
from aicore.util.io import atomic_write_text
from aicore.util.repo import find_repo_root

from aicore.util.cli import parse_flags
from .host import load_host
from aicore.release.changelog import (
    read_unreleased_section, release_changelog, unreleased_is_empty)
from aicore.release.version import (
    classify_bump, commits_since, last_tag, next_available_version, sync_version_files)


def cmd_release(env, argv):
    opts = parse_flags(argv, {"--dry-run": "bool"})
    if opts["help"]:
        print("skiller release [--dry-run]\n"
              "  Collects a monorepo release proposal: semver-bump from conventional "
              "commits since last tag (feat:->minor, fix:/perf:->patch) "
              "+ transfer [Unreleased] -> [X.Y.Z] in CHANGELOG.md + print tag command.\n"
              "  MAJOR is never output - breaking-marker fails, version "
              "remains the owner's decision. git tag/push are NOT executed.\n"
              "  --dry-run: plan printing only, CHANGELOG.md does not change.")
        return

    root = find_repo_root(env.root) or env.root
    changelog = root / "CHANGELOG.md"
    if not changelog.is_file():
        print(f"skiller release: {changelog} not found - nothing to collect.")
        return

    tag = last_tag(root)
    commits = commits_since(root, tag)
    bump, reason = classify_bump(commits)

    if bump == "breaking":
        print(f"skiller release: suspicion of breaking-change (commit: {reason!r}) "
              "— MAJOR-version is ALWAYS a manual decision of the owner, its automation is not "
              "outputs. Evaluate the range yourself and enter the version manually.")
        sys.exit(1)

    if bump is None:
        print(f"skiller release: since {tag or '(first commit)'} no "
              "conventional-commits feat/fix/perf — nothing to release.")
        return

    new_version = next_available_version(root, tag, bump)
    if new_version is None:
        print(f"skiller release: last tag {tag!r} does not match vX.Y.Z — "
              "enter the version manually.")
        sys.exit(1)

    try:
        text = changelog.read_text(encoding="utf-8")
    except OSError as e:
        print(f"skiller release: {changelog} is not readable ({e}) — pass.")
        return

    parsed = read_unreleased_section(text)
    if parsed is None:
        print(f"skiller release: section `## [Unreleased]` not found in {changelog} "
              "— there is nothing to transfer.")
        return
    if unreleased_is_empty(parsed[3]):
        print("skiller release: section `[Unreleased]` is empty - there is nothing to transfer "
              "(fill in CHANGELOG before release, see `oss-dev/release-engineering`).")
        return

    print(f"skiller release: proposal - {tag or '(no tag)'} -> {new_version} "
          f"({bump}, {len(commits)} commit(ov) in the range)")
    tag_cmd = f'git tag -a {new_version} -m "release: {new_version}"'

    if opts["dry_run"]:
        print(f"[dry-run] CHANGELOG.md not changed. After checking: {tag_cmd}")
        return

    backup(changelog)
    atomic_write_text(changelog, release_changelog(text, new_version))
    sync_version_files(root, new_version, load_host(env.root).version_files)
    print(f"CHANGELOG.md updated: [Unreleased] -> [{new_version.removeprefix('v')}]. "
          "Regenerate provider artifacts, then attest the final bytes:\n"
          f"  skiller registry\n  skiller attest --release {new_version}"
          + (f" --previous {tag}" if tag else "")
          + f"\nTag and push — manually:\n  {tag_cmd}\n  git push origin {new_version}")
