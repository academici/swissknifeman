"""release — build monorepo release proposal.

Reading `[Unreleased]` root `CHANGELOG.md`, classifies semver-bump from
conventional commits since last umbrella-tag (`vX.Y.Z`) and -
WITHOUT `--dry-run` — moves the section to `[X.Y.Z] - <date>` + prints the finished
tag command. NEVER tags/does not push itself and does NOT output MAJOR: sign
breaking-changes - refusal, the version remains a manual decision of the owner.

Semver-oracle (minor=capability/feat, patch=fix/perf) — from
an earlier audit, NOT reinvented here.
stdlib-only, `Env` is passed explicitly (tested in tmpdir)."""
import re
import sys
from datetime import date

from core import atomic_write_text, backup_file, find_monorepo_root, run_cmd

from .common import parse_flags

# Types conventional-commit, givers semver-signal; `!` after type/scope or
# `BREAKING CHANGE` in the commit body - marker breaking (see classify_bump).
CONVENTIONAL_RE = re.compile(
    r"^(?P<type>feat|fix|perf|refactor|docs|chore|test|style|ci|build)"
    r"(?:\([^)]*\))?(?P<bang>!)?:\s*")
MINOR_TYPES = {"feat"}
PATCH_TYPES = {"fix", "perf"}
BREAKING_MARKER = "BREAKING CHANGE"
TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
UNRELEASED_RE = re.compile(r"^##\s*\[Unreleased\]\s*$", re.IGNORECASE)
NEXT_HEADING_RE = re.compile(r"^##\s*\[")


def _last_tag(root):
    """Last umbrella-tag `vX.Y.Z` (`git describe --tags --abbrev=0`).
    None — no tags (first release) or `root` not git-repository."""
    result = run_cmd(["git", "describe", "--tags", "--match", "v[0-9]*", "--abbrev=0"],
                      cwd=root, capture=True, check=False)
    if result.returncode != 0:
        return None
    tag = result.stdout.strip()
    return tag or None


def _commits_since(root, tag):
    """[(subject, body), ...] commits in range `tag..HEAD` (entire log, if
    tag=None). Separators `\\x1e`/`\\x1f` — are practically not found in the text
    commit, safer than line-by-line parsing `git log --oneline`."""
    range_arg = f"{tag}..HEAD" if tag else "HEAD"
    result = run_cmd(["git", "log", range_arg, "--pretty=format:%s%x1f%b%x1e"],
                      cwd=root, capture=True, check=False)
    if result.returncode != 0 or not result.stdout:
        return []
    out = []
    for chunk in result.stdout.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        subject, _, body = chunk.partition("\x1f")
        out.append((subject.strip(), body.strip()))
    return out


def classify_bump(commits):
    """(bump, reason) from `[(subject, body), ...]`.

    bump: 'breaking' (failure - D34, MAJOR DO NOT output, reason=suspicious subject) ·
    'minor' (yes feat:) · 'patch' (only fix:/perf:) · None (nothing to release,
    in range none conventional-commits with signal). breaking is checked FIRST
    and short circuit - we don’t guess the version at the slightest suspicion breaking."""
    minor = patch = False
    for subject, body in commits:
        m = CONVENTIONAL_RE.match(subject)
        if not m:
            continue
        if m.group("bang") or BREAKING_MARKER in body:
            return "breaking", subject
        t = m.group("type")
        if t in MINOR_TYPES:
            minor = True
        elif t in PATCH_TYPES:
            patch = True
    if minor:
        return "minor", None
    if patch:
        return "patch", None
    return None, None


def bump_version(tag, bump):
    """New `vX.Y.Z` from the previous tag + bump ('minor'|'patch'). Without tag -
    first release (`v0.1.0`/`v0.0.1`). tag does not match `vX.Y.Z` → None (caller
    refuses instead of guessing)."""
    if tag is None:
        return "v0.1.0" if bump == "minor" else "v0.0.1"
    m = TAG_RE.match(tag)
    if not m:
        return None
    major, minor_v, patch_v = (int(x) for x in m.groups())
    if bump == "minor":
        return f"v{major}.{minor_v + 1}.0"
    return f"v{major}.{minor_v}.{patch_v + 1}"


def read_unreleased_section(text):
    """(lines, start, end, body) sections `## [Unreleased]` text CHANGELOG.
    `body` — lines between title and next `## [...]` (or end of file),
    WITHOUT the title itself. None — section is not in the file."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if UNRELEASED_RE.match(ln):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if NEXT_HEADING_RE.match(lines[j]):
            end = j
            break
    return lines, start, end, lines[start + 1:end]


def unreleased_is_empty(body_lines):
    """Empty = not a single non-empty line, not counting `###`-group subheadings
    Keep a Changelog (`### Added` without entries - also «empty»)."""
    return not any(ln.strip() and not ln.strip().startswith("###") for ln in body_lines)


def _release_changelog(text, new_version):
    """Text CHANGELOG after transfer `[Unreleased]` → `[new_version] - <date>`:
    old section is freed (empty `## [Unreleased]`), its contents go under
    new version header. Does not affect other sections of the file."""
    lines, start, end, body = read_unreleased_section(text)
    new_heading = f"## [{new_version.removeprefix('v')}] - {date.today().isoformat()}"
    new_lines = (lines[:start] + ["## [Unreleased]", "", new_heading]
                 + body + lines[end:])
    return "\n".join(new_lines) + "\n"


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

    root = find_monorepo_root(env.root) or env.root
    changelog = root / "CHANGELOG.md"
    if not changelog.is_file():
        print(f"skiller release: {changelog} not found - nothing to collect.")
        return

    tag = _last_tag(root)
    commits = _commits_since(root, tag)
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

    new_version = bump_version(tag, bump)
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

    if (root / ".agents/plugins/marketplace.json").is_file():
        from .release_attestation import build, check_transition
        errors = check_transition(build(root, ref=tag), build(root)) if tag else []
        if errors:
            print("skiller release: " + "; ".join(errors), file=sys.stderr)
            sys.exit(1)

    print(f"skiller release: proposal - {tag or '(no tag)'} -> {new_version} "
          f"({bump}, {len(commits)} commit(ov) in the range)")
    tag_cmd = f'git tag -a {new_version} -m "release: {new_version}"'

    if opts["dry_run"]:
        print(f"[dry-run] CHANGELOG.md not changed. After checking: {tag_cmd}")
        return

    backup_file(changelog)
    atomic_write_text(changelog, _release_changelog(text, new_version))
    if (root / ".agents/plugins/marketplace.json").is_file():
        from .release_attestation import cmd_attest
        args = ["--release", new_version]
        if tag:
            args += ["--previous", tag]
        cmd_attest(env, args)
    print(f"CHANGELOG.md updated: [Unreleased] -> [{new_version.removeprefix('v')}]. "
          f"Tag and push — manually:\n  {tag_cmd}\n  git push origin {new_version}")
