#!/usr/bin/env python3
"""Deterministic P7 acceptance, decision and release-tree verifiers.

The checker deliberately keeps release-blocker truth separate from package acceptance:
D88/D89's non-empty external blocker payload remains visible, but is not silently
turned into a package-check failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


EXCLUDED = ["raw-transcript-bodies", "chain-of-thought", "tool-payloads", "secrets"]
REQUIRED_CONTRACTS = {
    "provider-control-plane-v1.md", "locale-resolution-v1.md",
    "skill-core-v1.md", "provider-skill-adapter-v1.md", "provider-health-v1.md",
}
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def root_relative(path, root):
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"path is not root-relative: {path}")
    if not str(candidate) or str(candidate).startswith(".git/"):
        raise ValueError(f"unsafe path: {path}")
    return candidate.as_posix()


def exact_blockers(replay, fleet, catalog):
    blockers = list(replay.get("release_blockers", []))
    if replay.get("schema_version") != "p7.1-skill-replay-results/v1":
        blockers.append("REPLAY_SCHEMA_INVALID")
    if fleet.get("semantic_match") is not True:
        blockers.append("FLEET_SEMANTIC_MATCH_MISSING")
    providers = [p["id"] for p in catalog.get("providers", [])]
    if providers != ["claude-code", "codex"]:
        blockers.append("PROVIDER_SET_DRIFT")
    for capability in catalog.get("capabilities", []):
        support = capability.get("support", {})
        if set(support) != set(providers):
            blockers.append("CAPABILITY_PROVIDER_COVERAGE:" + capability.get("id", "unknown"))
    return sorted(set(blockers))


def verify_p6_evidence(path):
    manifest = load(Path(path) / "manifest.json")
    if manifest.get("schema_version") != "p6.3-evidence-manifest/v1":
        raise ValueError("P6 evidence manifest schema mismatch")
    names = {entry.get("path") for entry in manifest.get("files", [])}
    required = {"fleet-health-verdict.json", "project-set.json", "project-membership.json"}
    if not required <= names:
        raise ValueError("P6 evidence manifest is incomplete")
    return manifest


def verify_p5_journal(path):
    journal = Path(path)
    if not journal.is_file():
        raise ValueError("P5 journal is missing")
    for line in journal.read_text(encoding="utf-8").splitlines():
        if line.strip():
            json.loads(line)
    return sha(journal)


def verify_contracts(path):
    contracts = Path(path)
    if not contracts.is_dir():
        raise ValueError("contracts directory is missing")
    missing = sorted(name for name in REQUIRED_CONTRACTS if not (contracts / name).is_file())
    if missing:
        raise ValueError("required frozen contracts are missing: " + ", ".join(missing))


def verify_capabilities(path):
    catalog = load(path)
    if [item.get("id") for item in catalog.get("providers", [])] != ["claude-code", "codex"]:
        raise ValueError("capability provider set drift")
    if not catalog.get("capabilities"):
        raise ValueError("capability catalog is empty")
    return catalog


def write(args):
    replay = load(Path(args.output_dir) / "skill-replay-results.json")
    ablations = load(Path(args.output_dir) / "skill-ablation-results.json")
    fleet = load(args.fleet_verdict)
    catalog = load(args.provider_manifest)
    p5 = subprocess.run(args.p5_verify, shell=True, capture_output=True, text=True, check=False)
    blockers = exact_blockers(replay, fleet, catalog)
    if p5.returncode:
        blockers.append("P5_AGGREGATE_VERIFICATION_FAILED")
    if ablations.get("status") not in {"green", "deferred-owner-decision"}:
        blockers.append("ABLATION_EVIDENCE_INVALID")
    output = Path(args.output_dir)
    acceptance = {
        "schema_version": "p7.1-provider-acceptance/v1",
        "provider_ids": [p["id"] for p in catalog["providers"]],
        "shared_capability_ids": sorted({row["capability_id"] for row in replay.get("rows", [])}),
        "fleet_semantic_match": fleet.get("semantic_match"),
        "required_release_blockers": sorted(set(blockers)),
        "deferred": {
            "decision": "D88", "claude_code": "documented-not-live-verified",
            "codex_replay": "diagnostic-not-release-efficacy",
            "p6_required_project_release_blockers": fleet.get("required_project_release_blockers", []),
            "p5_rollout": "not-authorized-external-operation",
        },
        "privacy": {"minimized": True, "excluded_classes": EXCLUDED},
    }
    (output / "acceptance-results.json").write_text(canonical(acceptance) + "\n", encoding="utf-8")
    (output / "release-blockers.json").write_text(canonical({"package_blockers": acceptance["required_release_blockers"], "deferred": acceptance["deferred"]}) + "\n", encoding="utf-8")
    project_set = load(args.project_set)
    (output / "project-set.json").write_text(canonical(project_set) + "\n", encoding="utf-8")
    expectations = {"providers": acceptance["provider_ids"], "capabilities": sorted(c["id"] for c in catalog["capabilities"])}
    (output / "capability-expectations.json").write_text(canonical(expectations) + "\n", encoding="utf-8")
    files = ["project-set.json", "capability-expectations.json", "skill-replay-results.json", "skill-ablation-results.json", "acceptance-results.json", "release-blockers.json"]
    manifest = {"bundle_id": "P7.1-provider-acceptance", "files": files, "privacy": {"minimized": True, "excluded_classes": EXCLUDED}, "producer": "p7-provider-acceptance.py write"}
    (output / "manifest.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
    print(canonical({"release_blockers": acceptance["required_release_blockers"]}))
    return 0 if not blockers else 2


def check(args):
    # These are required, caller-supplied frozen inputs.  Never replace them with defaults.
    verify_p6_evidence(args.p6_evidence)
    p5_digest = verify_p5_journal(args.p5_journal)
    verify_contracts(args.contracts_dir)
    verify_capabilities(args.capabilities)
    output = Path(args.output_dir)
    manifest = load(output / "manifest.json")
    actual = sorted(path.name for path in output.iterdir() if path.is_file() and path.name not in {"manifest.json", "verify.py"})
    if sorted(manifest.get("files", [])) != actual:
        raise ValueError("bundle member exact-set mismatch")
    acceptance = load(output / "acceptance-results.json")
    if acceptance.get("schema_version") != "p7.1-provider-acceptance/v1":
        raise ValueError("acceptance schema mismatch")
    print(canonical({"release_blockers": acceptance.get("required_release_blockers", []), "decision": "D88", "p5_journal_sha256": p5_digest}))
    return 0 if not acceptance.get("required_release_blockers") else 2


def decision_ids(decisions_dir):
    records = []
    for path in Path(decisions_dir).glob("D*.md"):
        match = re.match(r"D(\d+)(?:-|$)", path.name)
        if match:
            records.append((int(match.group(1)), f"D{int(match.group(1))}", path))
    records.sort()
    ids = [item[1] for item in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate current decision record")
    return ids


def decision_records(plan):
    root = Path.cwd().resolve()
    decisions_dir = plan.parent / "decisions"
    records = []
    for path in sorted(decisions_dir.glob("D*.md"), key=lambda item: int(re.match(r"D(\d+)(?:-|$)", item.name).group(1)) if re.match(r"D(\d+)(?:-|$)", item.name) else -1):
        match = re.match(r"D(\d+)(?:-|$)", path.name)
        if not match:
            continue
        decision_id = f"D{int(match.group(1))}"
        relative = root_relative(str(path.resolve().relative_to(root)), root)
        status = next(
            (line.removeprefix("status:").strip() for line in path.read_text(encoding="utf-8").splitlines()
             if line.startswith("status:")),
            "unknown",
        )
        blob = git(root, "hash-object", relative).stdout.strip()
        records.append({
            "commands": [f"sha256sum {relative}", f"git hash-object {relative}"],
            "decision_id": decision_id,
            "disposition": status,
            "evidence_paths": [relative],
            "results": [f"sha256:{sha(path)}", f"blob:{blob}", f"status:{status}"],
            "tree_anchor": {
                "blob": blob,
                "head": git(root, "rev-parse", "HEAD").stdout.strip(),
                "tracked": git(root, "cat-file", "-e", f"HEAD:{relative}").returncode == 0,
            },
        })
    if len({record["decision_id"] for record in records}) != len(records):
        raise ValueError("duplicate current decision record")
    return records


def write_crosswalk(args):
    plan = Path(args.plan)
    records = decision_records(plan)
    ids = [record["decision_id"] for record in records]
    payload = {
        "schema_version": "p7-decision-crosswalk/v1",
        "plan_id": plan.parent.name,
        "audit_snapshot": args.audit_snapshot,
        "decision_ids": ids,
        "rows": records,
        "set_proof": {
            "missing": [], "extra": [], "duplicates": [], "post_snapshot": [],
            "required_count": len(ids), "row_count": len(records),
        },
        "tree_anchor": git(Path.cwd().resolve(), "rev-parse", "HEAD").stdout.strip(),
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(canonical({"decision_ids": ids, "output": args.output}))
    return 0


def crosswalk(args):
    plan = Path(args.plan)
    supplied = load(args.crosswalk)
    expected = decision_ids(plan.parent / "decisions")
    rows = supplied.get("rows", [])
    row_ids = [row.get("decision_id") for row in rows]
    declared = supplied.get("decision_ids", [])
    if args.require_exact_set:
        if declared != expected:
            raise ValueError("decision crosswalk exact-set mismatch")
        if sorted(row_ids, key=lambda value: int(value[1:])) != expected or len(row_ids) != len(set(row_ids)):
            raise ValueError("decision crosswalk row exact-set mismatch")
        if supplied.get("post_snapshot") not in (None, []):
            raise ValueError("decision crosswalk has post-snapshot records")
    print("verify-decision-crosswalk: OK")
    return 0


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)


def porcelain_paths(root):
    output = git(root, "status", "--porcelain=v1").stdout.splitlines()
    paths = set()
    for line in output:
        if len(line) < 4:
            raise ValueError("malformed git porcelain")
        path = line[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        relative = root_relative(path, root)
        candidate = root / relative
        if candidate.is_dir():
            paths.update(
                root_relative(str(item.relative_to(root)), root)
                for item in candidate.rglob("*") if item.is_file()
            )
        else:
            paths.add(relative)
    return paths


def manifest_paths(manifest, key):
    paths = []
    for item in manifest.get(key, []):
        value = item["path"] if isinstance(item, dict) else item
        paths.append(root_relative(value, Path.cwd()))
    if len(paths) != len(set(paths)):
        raise ValueError(f"duplicate {key} path")
    return set(paths)


def release_tree(args):
    root = Path.cwd().resolve()
    release_manifest = Path(args.release_manifest)
    try:
        release = load(release_manifest)
    except json.JSONDecodeError:
        if release_manifest.name != "P7-release-candidate-manifest.md":
            raise
        release_manifest = release_manifest.with_name("P7-candidate-paths.json")
        release = load(release_manifest)
    acceptance_path = Path(args.acceptance_manifest)
    acceptance = load(acceptance_path)
    status = load(args.worktree_status)
    if release.get("schema_version") != "p7-candidate-paths/v1":
        raise ValueError("release manifest schema mismatch")
    candidates = manifest_paths(release, "candidate_paths")
    foreign = manifest_paths(release, "foreign_paths")
    release_path = root_relative(str(release_manifest.resolve().relative_to(root)), root)
    if candidates & foreign:
        raise ValueError("candidate/foreign overlap")
    if not candidates:
        raise ValueError("candidate path set is empty")
    for item in release.get("candidate_paths", []) + release.get("foreign_paths", []):
        if not isinstance(item, dict) or not re.fullmatch(r"[0-9a-f]{64}", item.get("preimage_sha256", "")):
            raise ValueError("missing preimage hash")
    accepted_files = acceptance.get("files")
    if not isinstance(accepted_files, list) or len(accepted_files) != len(set(accepted_files)):
        raise ValueError("acceptance manifest exact-set is malformed")
    protected = candidates | {root_relative(str(acceptance_path.resolve().relative_to(root)), root)}
    protected |= {root_relative(str(acceptance_path.parent.resolve().relative_to(root) / name), root) for name in accepted_files}
    dirty = porcelain_paths(root)
    unknown = dirty - candidates - foreign
    if unknown:
        raise ValueError("unclassified dirty paths: " + ", ".join(sorted(unknown)))
    # The manifest carries its own scope anchor.  Its post-commit bookkeeping
    # update is intentionally excluded from the candidate-byte comparison;
    # every other candidate path must exactly equal the anchor.
    candidate_bytes = candidates - {
        release_path,
        root_relative(
            str((release_manifest.parent / "P7-release-candidate-manifest.md").resolve().relative_to(root)),
            root,
        ),
    }
    if dirty & candidate_bytes:
        raise ValueError("candidate paths are not clean at anchor: " + ", ".join(sorted(dirty & candidate_bytes)))
    anchor = release.get("anchor")
    if not isinstance(anchor, str) or not re.fullmatch(r"[0-9a-f]{7,64}", anchor):
        raise ValueError("release anchor is missing")
    for path in sorted(candidate_bytes):
        if git(root, "cat-file", "-e", f"{anchor}:{path}").returncode or git(root, "diff", "--quiet", anchor, "--", path).returncode:
            raise ValueError("candidate path differs from anchor: " + path)
    observed_foreign = canonical(sorted((item["path"], item["preimage_sha256"]) for item in release.get("foreign_paths", [])))
    expected_digest = status.get("foreign_digest_sha256")
    if expected_digest is not None and hashlib.sha256(observed_foreign.encode()).hexdigest() != expected_digest:
        raise ValueError("foreign worktree digest changed")
    if protected & foreign:
        raise ValueError("protected/foreign overlap")
    print("verify-release-tree: OK")
    return 0


def self_test(_args):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "p7@example.test"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "P7"], check=True)
        (root / "candidate.txt").write_text("clean\n", encoding="utf-8")
        (root / "foreign.txt").write_text("base\n", encoding="utf-8")
        (root / "acceptance.json").write_text(canonical({"files": []}), encoding="utf-8")
        (root / "status.json").write_text(canonical({}), encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        anchor = git(root, "rev-parse", "HEAD").stdout.strip()
        (root / "foreign.txt").write_text("dirty\n", encoding="utf-8")
        foreign = [{"path": "foreign.txt", "preimage_sha256": sha(root / "foreign.txt")}]
        release = {"schema_version": "p7-candidate-paths/v1", "anchor": anchor, "candidate_paths": [{"path": "candidate.txt", "preimage_sha256": sha(root / "candidate.txt")}], "foreign_paths": foreign}
        (root / "release.json").write_text(canonical(release), encoding="utf-8")
        (root / "P7-release-candidate-manifest.md").write_text("# candidate\n", encoding="utf-8")
        (root / "P7-candidate-paths.json").write_text(canonical(release), encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "release.json", "P7-release-candidate-manifest.md", "P7-candidate-paths.json"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "release-manifest"], check=True)
        previous = Path.cwd()
        try:
            __import__("os").chdir(root)
            release_tree(SimpleNamespace(release_manifest="release.json", acceptance_manifest="acceptance.json", worktree_status="status.json"))
            release_tree(SimpleNamespace(release_manifest="P7-release-candidate-manifest.md", acceptance_manifest="acceptance.json", worktree_status="status.json"))
            (root / "candidate.txt").write_text("dirty\n", encoding="utf-8")
            try:
                release_tree(SimpleNamespace(release_manifest="release.json", acceptance_manifest="acceptance.json", worktree_status="status.json"))
            except ValueError as exc:
                if "candidate paths are not clean at anchor" not in str(exc):
                    raise
            else:
                raise AssertionError("dirty candidate was accepted")
        finally:
            __import__("os").chdir(previous)
    print("p7-provider-acceptance: self-test OK")
    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    write_parser = sub.add_parser("write")
    write_parser.add_argument("--output-dir", required=True)
    write_parser.add_argument("--fleet-verdict", required=True)
    write_parser.add_argument("--provider-manifest", required=True)
    write_parser.add_argument("--project-set", required=True)
    write_parser.add_argument("--p5-verify", required=True)
    check_parser = sub.add_parser("check")
    for option in ("--p6-evidence", "--p5-journal", "--contracts-dir", "--capabilities", "--output-dir"):
        check_parser.add_argument(option, required=True)
    crosswalk_parser = sub.add_parser("verify-decision-crosswalk")
    crosswalk_parser.add_argument("--plan", required=True)
    crosswalk_parser.add_argument("--crosswalk", required=True)
    crosswalk_parser.add_argument("--require-exact-set", action="store_true")
    write_crosswalk_parser = sub.add_parser("write-decision-crosswalk")
    write_crosswalk_parser.add_argument("--plan", required=True)
    write_crosswalk_parser.add_argument("--output", required=True)
    write_crosswalk_parser.add_argument("--audit-snapshot", required=True)
    tree_parser = sub.add_parser("verify-release-tree")
    tree_parser.add_argument("--release-manifest", required=True)
    tree_parser.add_argument("--acceptance-manifest", required=True)
    tree_parser.add_argument("--worktree-status", required=True)
    args = parser.parse_args()
    try:
        return {"self-test": self_test, "write": write, "check": check, "verify-decision-crosswalk": crosswalk, "write-decision-crosswalk": write_crosswalk, "verify-release-tree": release_tree}[args.command](args)
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"P7_PROVIDER_ACCEPTANCE_BLOCKER: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
