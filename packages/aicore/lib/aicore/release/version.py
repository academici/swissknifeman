"""Release versions: the last umbrella tag, the commits since it, the semver bump and the version files.

Reads conventional commits since the last umbrella tag (``vX.Y.Z``) and classifies the semver bump. MAJOR is
never produced: a breaking marker is reported, the version stays the owner's manual decision. stdlib only.
"""
import json
import re

from ..util.cli import run_cmd
from ..util.io import atomic_write_text

# Types conventional-commit, givers semver-signal; `!` after type/scope or
# `BREAKING CHANGE` in the commit body - marker breaking (see classify_bump).
CONVENTIONAL_RE = re.compile(
    r"^(?P<type>feat|fix|perf|refactor|docs|chore|test|style|ci|build)"
    r"(?:\([^)]*\))?(?P<bang>!)?:\s*")
MINOR_TYPES = {"feat"}
PATCH_TYPES = {"fix", "perf"}
BREAKING_MARKER = "BREAKING CHANGE"
TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def last_tag(root):
    """Last umbrella-tag `vX.Y.Z` (`git describe --tags --abbrev=0`).
    None — no tags (first release) or `root` not git-repository."""
    result = run_cmd(["git", "describe", "--tags", "--match", "v[0-9]*", "--abbrev=0"],
                      cwd=root, capture=True, check=False)
    if result.returncode != 0:
        return None
    tag = result.stdout.strip()
    return tag or None


def commits_since(root, tag):
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


def next_available_version(root, tag, bump):
    """Calculate a free version without changing the reachable range anchor.

    ``git describe`` supplies the closest reachable release for the commit
    range. A parallel release branch may already have published its calculated
    successor, however. In that case, advance from the global umbrella-tag
    maximum, retaining the requested patch/minor cadence.
    """
    candidate = bump_version(tag, bump)
    if candidate is None:
        return None
    result = run_cmd(["git", "tag", "--list", "v*"], cwd=root, capture=True, check=False)
    used = {value for raw in result.stdout.splitlines()
            if TAG_RE.fullmatch(value := raw.strip())}
    while candidate in used:
        highest = max(used, key=lambda value: tuple(int(part) for part in value[1:].split(".")))
        candidate = bump_version(highest, bump)
    return candidate


def sync_version_files(root, version, version_files):
    """Write the release version into the host's `version_files` before a render.

    A host can keep a catalog that its own renderer treats as the canonical
    version input (provider descriptors are generated from it), so a release
    updates that input first. `version_files` is a sequence of entries with the attributes
    `path` (relative to `root`) and `key`. Missing files are skipped; the value is the
    version without the `v` prefix.
    """
    value_version = version.removeprefix("v")
    for entry in version_files:
        path = root / entry.path
        if not path.is_file():
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get(entry.key) == value_version:
            continue
        value[entry.key] = value_version
        atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
