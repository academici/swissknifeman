#!/usr/bin/env python3
"""Public tree hygiene: tracked paths, machine/plan references and a neutrality ratchet."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NEUTRALITY_FILE = ROOT / "configs/neutrality.json"
BASELINE_FILE = ROOT / "configs/neutrality-baseline.json"
NEUTRALITY_SCHEMA = ROOT / "configs/schemas/neutrality.schema.json"
ATTRIBUTION_FIELDS = {"author", "owner", "homepage", "repository", "url", "email"}
RUNTIME_FOLDERS = {"lib", "configs", "skills", "commands", "templates"}
JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
JSON_COLON = re.compile(r"\s*:")
JSON_WHITESPACE = re.compile(r"\s*")

# Rules - DATA, each with a named reason; expansion "just in case" prohibited
# (Code Guidance P8.6): undecrypted reason The ⇒ gate will start turning red on legal files.
SUFFIX_RULES = [
    (".sqlite", "SQLite-database - private artifact, not published"),
    (".log", "log file - runtime artifact, not published"),
    (".pem", "private key/certificate"),
    (".key", "private key"),
    (".zip", "archive - a binary artifact outside the source tree"),
    (".tar", "archive - a binary artifact outside the source tree"),
    (".tar.gz", "archive - a binary artifact outside the source tree"),
    (".tgz", "archive - a binary artifact outside the source tree"),
    (".rar", "archive - a binary artifact outside the source tree"),
    (".7z", "archive - a binary artifact outside the source tree"),
]

# *.example — exception from ANY suffix/name rules below (fixtures/templates are required
# pass: hygiene catches secret, not extension).
EXAMPLE_SUFFIX = ".example"

ENV_BASENAME = ".env"
ENV_REASON = "secret environment config (.env) — is not published except *.example"

COMPONENT_RULES = [
    ("__pycache__", "compiled cache Python — runtime artifact"),
    (".venv", "virtual environment Python — not published"),
    ("node_modules", "dependencies npm — not published"),
]


# Contents: absolute path of the working environment of a specific machine (home directory + typical
# project layout/configs). Synthetic examples (`/home/user/…`, `/home/example/…`) are not caught - only that
# breaks the installation on another computer and the username is displayed.
CONTENT_RULES = [
    (re.compile(r"(?:/home|/Users)/(?!(?:user|users|example|alice|bob|dev|operator|u|someone|you|me|name"
                r"|username|runner|ci|test)\b)[A-Za-z0-9_.-]+/(?:projects|Vaults|sibintek|Documents|Desktop"
                r"|Downloads|\.config|\.claude|\.codex|\.cursor|\.maind|\.swissknifeman)\b"
                r"|[A-Za-z]:\\+Users\\+(?!(?:user|users|example|alice|bob|dev|operator|u|someone|you|me|name"
                r"|username|runner|ci|test)\b)[A-Za-z0-9_.-]+"),
     "absolute path of the working environment (use a relative path, `<REPO_ROOT>` or `~`)"),
]
CONTENT_MAX_BYTES = 2_000_000
# Files whose bytes are frozen sha256 in code: rewrite path = break the chain. Only with a reason.
CONTENT_EXEMPT = {
    "packages/maind/tests/test_provider_deploy.py":
        "accurate historical preimage D108/D115, sha256 which is pinned to provider_deploy.py",
    "packages/maind/tests/harness_equality.py":
        "the same sealed D108 preimage as above, rebuilt byte for byte for the harness-link equality test",
}
# Sealed measurement evidence: its text is the measured input, so rewriting it would falsify the measurement.
# None remain: the only one (the v2 calibration probe log) was deleted with the v2 runtime.
CONTENT_PLAN_EXEMPT: dict[str, str] = {}
# The exemption holds only while the sealed file is byte-identical to the reviewed one.
CONTENT_PLAN_EXEMPT_SHA256: dict[str, str] = {}

# Records the conductor commits for a piece of a plan kept outside the checkout name the item (`PLANn.Pm`): generated, not authored.
GENERATED_RECORD_DIRS = (".swissknifeman/orch-artifacts/",)
# Working documents are local-only; nothing tracked may live under or point into them.
WORKING_DOC_DIRS = ("plans/", "roadmap/", "tasks/", ".cursor/plans/")
# Concrete plan identity: dated plan ID, Short-ID citation, or a link into the working directories.
# Synthetic fixture IDs are namespaced `DEMO...` and are allowed.
PLAN_REFERENCE_RULES = [
    (re.compile(r"20\d\d\.[01]\d\.[0-3]\d-(?:№\d+-)?(?!DEMO(?:-|\b))[A-Z]"), "concrete plan ID"),
    (re.compile(r"PLAN\d+\.[DPF]\d"), "Short-ID plan citation"),
    (re.compile(r"(?<![\w<{./-])(?:roadmap|tasks)/(?![<{])[\w.№-]"), "link into a working directory"),
    (re.compile(r"(?<![\w<{./-])plans/(?:archive/)?(?:20\d\d\.[01]\d\.[0-3]\d-(?:№\d+-)?)?(?!DEMO)[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+"),
     "path into a plan directory"),
]


# Plan-engine test data exercises the plan ID and Short-ID syntax itself (reference parsing, store,
# views, bridges, golden outputs), so its identifiers cannot avoid that shape. They are synthetic and
# these trees are exempt from the plan-reference rules ONLY; the content rules above still apply.
PLAN_SYNTAX_TEST_TREES = {
    "packages/planner/tests/engine/": "plan engine tests and fixtures: ID, Short-ID and reference syntax",
    "packages/planner/tests/compat/": "frozen synthetic plans of earlier engines: their ID shape",
    "packages/planner/tests/fixtures/events/": "planner.* event envelopes the engine emitted for its synthetic demo plan: its ID shape",
    "bridges/planner-orch/tests/": "plan-to-orchestration bridge tests: Short-ID subjects and parity with plan files",
    "packages/orch/fixtures/exec/": "orchestration exec-contract fixtures: plan-bound identifiers",
    "packages/orch/tests/": "orchestration tests and goldens: plan-bound identifiers and profile examples",
    "tests/golden/": "golden fixtures of the plan CLI output on the synthetic engine demo plan: its ID shape",
}


def plan_reference_violations(paths, read=None):
    """Tracked files must not sit in working directories or reference concrete plans."""
    read = read or _read_text
    found = [(path, "tracked working document (plans/, roadmap/, tasks/, .cursor/plans/ are local-only)")
             for path in paths if path.startswith(WORKING_DOC_DIRS)]
    for path in paths:
        if (path.startswith(WORKING_DOC_DIRS) or path.startswith(tuple(PLAN_SYNTAX_TEST_TREES))
                or path.startswith(GENERATED_RECORD_DIRS)):
            continue
        text = read(path)
        if path in CONTENT_PLAN_EXEMPT:
            if text is not None and hashlib.sha256(text.encode("utf-8")).hexdigest() != CONTENT_PLAN_EXEMPT_SHA256[path]:
                found.append((path, "sealed measurement changed; exemption no longer applies"))
            continue
        if text is None:
            continue
        for pattern, reason in PLAN_REFERENCE_RULES:
            match = pattern.search(text)
            if match:
                found.append((f"{path} ({match.group(0)})", reason))
    return found


def content_violations(paths, read=None):
    """Content violations tracked-text files; binary and large ones are skipped."""
    read = read or _read_text
    found = []
    for path in paths:
        if path in CONTENT_EXEMPT:
            continue
        text = read(path)
        if text is None:
            continue
        for pattern, reason in CONTENT_RULES:
            match = pattern.search(text)
            if match:
                found.append((f"{path} ({match.group(0)})", reason))
    return found


def _read_text(path):
    try:
        with open(path, "rb") as stream:
            data = stream.read(CONTENT_MAX_BYTES + 1)
    except OSError:
        return None
    if len(data) > CONTENT_MAX_BYTES or b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", "replace")


class NeutralityConfigError(ValueError):
    """Invalid gate data, including a malformed or unreadable baseline."""

    def __init__(self, pointer, message):
        super().__init__(f"NEUTRALITY_CONFIG_INVALID: {pointer or '/'}: {message}")


def _schema_context():
    lib = str(ROOT / "packages/aicore/lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    from aicore.util import schema
    registry = schema.load_schema_file(NEUTRALITY_SCHEMA, urn_prefix="urn:swissknifeman:hub:", kind="neutrality")
    return schema, registry


def _validate_neutrality(document, definition=None):
    try:
        schema, registry = _schema_context()
        if definition:
            node, owner = registry.resolve(f"#/$defs/{definition}", "urn:swissknifeman:hub:neutrality:v1")
            issues = schema.validate_node(registry, node, owner, document)
        else:
            issues = schema.validate(document, "neutrality", registry)
    except (ImportError, OSError, ValueError, LookupError) as exc:
        raise NeutralityConfigError("/", str(exc)) from exc
    if issues:
        issue = issues[0]
        prefix = f"{issue.path or '/'}: "
        message = issue.message.removeprefix(prefix)
        raise NeutralityConfigError(issue.path, message)


def _load_neutrality_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise NeutralityConfigError("/", f"{Path(path).name}: {exc}") from exc


def _glob_regex(glob):
    """Path globs: ** spans directories; * and ? stay within one component."""
    parts = []
    index = 0
    while index < len(glob):
        if glob.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif glob.startswith("**", index):
            parts.append(".*")
            index += 2
        elif glob[index] == "*":
            parts.append("[^/]*")
            index += 1
        elif glob[index] == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(glob[index]))
            index += 1
    return re.compile("".join(parts))


def _runtime_path(path):
    parts = path.split("/")
    return ("agent-packs" in parts or
            (len(parts) >= 3 and parts[0] == "packages" and parts[2] in RUNTIME_FOLDERS))


def neutrality_rules(path=NEUTRALITY_FILE):
    """Load closed-profile gate data and compile its patterns once."""
    rules = _load_neutrality_json(path)
    _validate_neutrality(rules)
    ids = set()
    patterns = []
    for index, term in enumerate(rules["terms"]):
        pointer = f"/terms/{index}"
        if term["id"] in ids:
            raise NeutralityConfigError(pointer + "/id", "duplicate term id")
        ids.add(term["id"])
        try:
            pattern = re.compile(term["pattern"])
        except re.error as exc:
            raise NeutralityConfigError(pointer + "/pattern", str(exc)) from exc
        if not term["reason"].strip():
            raise NeutralityConfigError(pointer + "/reason", "reason must not be blank")
        patterns.append((term["id"], pattern))
    path_allow = []
    field_allow = []
    for index, allow in enumerate(rules["allow"]):
        pointer = f"/allow/{index}"
        if allow["term"] != "*" and allow["term"] not in ids:
            raise NeutralityConfigError(pointer + "/term", "unknown term id")
        if not allow["reason"].strip():
            raise NeutralityConfigError(pointer + "/reason", "reason must not be blank")
        if "json_fields" in allow:
            if set(allow["json_fields"]) - ATTRIBUTION_FIELDS:
                raise NeutralityConfigError(pointer + "/json_fields", "only attribution fields may be allowed")
            field_allow.append((allow["term"], set(allow["json_fields"])))
        else:
            # Exact runtime targets are invalid; broad globs also cannot exempt a runtime path below.
            probe = allow["path_glob"].replace("*", "_").replace("?", "_")
            if _runtime_path(probe):
                raise NeutralityConfigError(pointer + "/path_glob", "path allowances cannot cover runtime surfaces")
            path_allow.append((allow["term"], _glob_regex(allow["path_glob"])))
    rules["_patterns"] = patterns
    rules["_exclude"] = [_glob_regex(glob) for glob in rules["scope"]["exclude_globs"]]
    rules["_path_allow"] = path_allow
    rules["_field_allow"] = field_allow
    return rules


def _json_segments(text):
    """Keep physical offsets while decoding JSON strings, including escaped owner terms.

    Full parsing is required before any attribution exemption applies. Attribution values may be
    strings or containers (for example an author object); their keys remain subject to scanning.
    """
    try:
        json.loads(text)
    except ValueError:
        return [(text, 0, False, set())]
    segments = []
    attribution = []
    decoder = json.JSONDecoder()
    end = 0
    for token in JSON_STRING.finditer(text):
        segments.append((text[end:token.start()], end, False, set()))
        value = json.loads(token.group())
        colon = JSON_COLON.match(text, token.end())
        if colon and value in ATTRIBUTION_FIELDS:
            start = JSON_WHITESPACE.match(text, colon.end()).end()
            _value, finish = decoder.raw_decode(text, start)
            attribution.append((start, finish, value))
        fields = {field for start, finish, field in attribution
                  if not colon and start <= token.start() and token.end() <= finish}
        segments.append((value, token.start(), True, fields))
        end = token.end()
    segments.append((text[end:], end, False, set()))
    return segments


def neutrality_hits(paths, rules, read=_read_text):
    """Return (term id, path, physical line, excerpt) for every non-exempt occurrence."""
    hits = []
    for path in sorted(paths):
        if not any(path.startswith(entry) if entry.endswith("/") else path == entry
                   for entry in rules["scope"]["include"]):
            continue
        if any(glob.fullmatch(path) for glob in rules["_exclude"]):
            continue
        text = read(path)
        if text is None:
            continue
        segments = _json_segments(text) if path.endswith(".json") else [(text, 0, False, set())]
        for term_id, pattern in rules["_patterns"]:
            if not _runtime_path(path) and any(
                    term in ("*", term_id) and glob.fullmatch(path) for term, glob in rules["_path_allow"]):
                continue
            allowed_fields = set().union(*(fields for term, fields in rules["_field_allow"] if term in ("*", term_id)))
            for segment, offset, decoded, fields in segments:
                if fields & allowed_fields:
                    continue
                for match in pattern.finditer(segment):
                    position = offset if decoded else offset + match.start()
                    line = text.count("\n", 0, position) + 1
                    start = max(segment.rfind("\n", 0, match.start()) + 1, match.start() - 20)
                    excerpt = segment[start:match.end() + 60].split("\n", 1)[0][:80]
                    hits.append((term_id, path, line, excerpt))
    return hits


def _neutrality_counts(hits):
    return dict(sorted(Counter(f"{term}|{path}" for term, path, _line, _excerpt in hits).items()))


def ratchet(hits, baseline):
    """Allow existing counts; return excess occurrences and every decrease, including removals."""
    counts = _neutrality_counts(hits)
    old = baseline["counts"]
    seen = Counter()
    violations = []
    for hit in hits:
        key = f"{hit[0]}|{hit[1]}"
        seen[key] += 1
        if seen[key] > old.get(key, 0):
            violations.append(hit)
    improved = [{"key": key, "old": old[key], "new": counts.get(key, 0)}
                for key in sorted(old) if counts.get(key, 0) < old[key]]
    return violations, improved


def _neutrality_baseline(path, initialize=False):
    # Absence is the only bootstrap case. An existing empty or invalid baseline never permits growth.
    if initialize and not path.exists():
        return None
    baseline = _load_neutrality_json(path)
    _validate_neutrality(baseline, "baseline")
    return baseline


def list_tracked_files():
    try:
        out = subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"git ls-files not available: {exc}", file=sys.stderr)
        sys.exit(2)
    return [line for line in out.stdout.splitlines() if line]


def violation_reason(path):
    if path.endswith(EXAMPLE_SUFFIX):
        return None
    basename = path.rsplit("/", 1)[-1]
    if basename == ENV_BASENAME:
        return ENV_REASON
    for suffix, reason in SUFFIX_RULES:
        if path.endswith(suffix):
            return reason
    parts = path.split("/")
    for name, reason in COMPONENT_RULES:
        if name in parts:
            return reason
    return None


def check(paths):
    violations = []
    for path in paths:
        reason = violation_reason(path)
        if reason:
            violations.append((path, reason))
    return violations


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--neutrality-strict", action="store_true", help="require zero neutrality hits")
    modes.add_argument("--neutrality-update-baseline", action="store_true", help="initialize or decrease the baseline")
    parser.add_argument("--json", action="store_true", help="print a schema-validated JSON report")
    args = parser.parse_args(argv[1:])
    try:
        rules = neutrality_rules(NEUTRALITY_FILE)
        baseline = None if args.neutrality_strict else _neutrality_baseline(
            BASELINE_FILE, initialize=args.neutrality_update_baseline)
        paths = sorted(list_tracked_files())
        legacy = [(kind, path, reason) for kind, found in (
            ("path", check(paths)), ("content", content_violations(paths)),
            ("plan-reference", plan_reference_violations(paths))) for path, reason in found]
        hits = neutrality_hits(paths, rules, read=_read_text)
        counts = _neutrality_counts(hits)
        violations, improved = ratchet(hits, baseline) if baseline is not None else ([], [])
        if args.neutrality_strict:
            violations = hits
        reasons = {term["id"]: term["reason"] for term in rules["terms"]}
        report = {"violations": [{"path": max((p for p in paths if path == p or path.startswith(p + " (")),
                                               key=len, default=path), "line": 0, "term": kind, "reason": reason}
                                 for kind, path, reason in legacy] +
                  [{"path": path, "line": line, "term": term, "reason": reasons[term]}
                   for term, path, line, _excerpt in violations], "improved": improved, "counts": counts}
        growth = [(key, baseline["counts"].get(key, 0), count) for key, count in counts.items()
                  if baseline is not None and count > baseline["counts"].get(key, 0)]
        if args.neutrality_update_baseline and growth:
            growth_reasons = {key: f"NEUTRALITY_BASELINE_GROWTH: {key} {old}→{new}" for key, old, new in growth}
            for violation in report["violations"]:
                key = f"{violation['term']}|{violation['path']}"
                if key in growth_reasons:
                    violation["reason"] = growth_reasons[key]
        _validate_neutrality(report, "report")
        if args.neutrality_update_baseline and not growth and not legacy:
            document = {"schema_version": 1, "counts": counts}
            _validate_neutrality(document, "baseline")
            BASELINE_FILE.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (NeutralityConfigError, OSError) as exc:
        message = str(exc) if isinstance(exc, NeutralityConfigError) else str(NeutralityConfigError("/", str(exc)))
        if args.json:
            print(json.dumps({"violations": [{"path": "configs/neutrality.json", "line": 0,
                                             "term": "config", "reason": message}], "improved": [], "counts": {}}))
        else:
            print(message, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        for _kind, path, reason in legacy:
            print(f"{path} — is prohibited by the rule «{reason}»")
        if args.neutrality_update_baseline and growth:
            for key, old, new in growth:
                print(f"NEUTRALITY_BASELINE_GROWTH: {key} {old}→{new}")
        else:
            for term, path, line, _excerpt in violations:
                print(f"{path}:{line} — neutrality «{term}»: {reasons[term]}")
        for row in improved:
            print(f"neutrality: improved {row['key']} {row['old']}→{row['new']} (run --neutrality-update-baseline)")
        if not report["violations"]:
            print("public-hygiene: 0 violations")
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
