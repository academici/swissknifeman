#!/usr/bin/env python3
"""P7.1 real-provider skill replay; evidence is deliberately privacy-minimized."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


EXCLUDED = ["raw-transcript-bodies", "chain-of-thought", "tool-payloads", "secrets"]
VARIANTS = ("no-skill", "minimum-core", "provider-tuned")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fail(message):
    raise ValueError(message)


def source_gate(admission, root):
    if admission.get("status") != "frozen" or admission.get("run_matrix", {}).get("expected_runs") != 54:
        fail("admission is not the frozen 54-row carrier")
    expected = set(admission["selection"]["capability_ids"])
    actual = {row["capability_id"] for row in admission["capabilities"]}
    if expected != actual or len(actual) != 3:
        fail("admission capability exact-set mismatch")
    for key in ("locale_corpus", "p4_3_manifest"):
        row = admission["selection"][key]
        if hashlib.sha256((root / row["path"]).read_bytes()).hexdigest() != row["sha256"]:
            fail(f"admission digest drift: {key}")
    for capability in admission["capabilities"]:
        if hashlib.sha256((root / capability["source_path"]).read_bytes()).hexdigest() != capability["source_sha256"]:
            fail(f"canonical source drift: {capability['capability_id']}")
        for provider in admission["providers"]:
            projection = root / provider["projection_pattern"].format(skill_name=capability["skill_name"])
            if not projection.is_file() or hashlib.sha256(projection.read_bytes()).hexdigest() != capability["projection_sha256"]:
                fail(f"projection drift: {provider['provider_id']}/{capability['skill_name']}")


def provider_command(provider, prompt, variant, capability, root):
    """Use each provider's installed native noninteractive adapter with a read-only boundary."""
    if provider == "claude-code":
        binary = shutil.which("claude")
        if not binary:
            return None
        command = [binary, "-p", prompt, "--output-format", "json", "--permission-mode", "plan", "--no-session-persistence"]
        if variant == "no-skill":
            command.append("--disable-slash-commands")
        else:
            injected = "\n".join(capability["minimum_core"] if variant == "minimum-core" else [
                (root / ".claude" / "skills" / capability["skill_name"] / "SKILL.md").read_text(encoding="utf-8")
            ])
            command += ["--append-system-prompt", injected]
        return command
    if provider == "codex":
        binary = shutil.which("codex")
        if not binary:
            return None
        if variant != "no-skill":
            injected = "\n".join(capability["minimum_core"] if variant == "minimum-core" else [
                (root / ".agents" / "skills" / capability["skill_name"] / "SKILL.md").read_text(encoding="utf-8")
            ])
            prompt = "Provider-tuned context follows; it is additive and not permission to write.\n" + injected + "\n\n" + prompt
        return [binary, "exec", "-C", str(root), "-s", "read-only", "--json", prompt]
    return None


def compact_text(provider, stdout):
    if provider == "claude-code":
        try:
            result = json.loads(stdout)
            return result.get("result", "") if isinstance(result, dict) else stdout
        except json.JSONDecodeError:
            return stdout
    messages = []
    parts = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") if isinstance(event, dict) else None
        if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            messages.append(item["text"])
        def walk(value):
            if isinstance(value, dict):
                for item in value.values(): walk(item)
            elif isinstance(value, list):
                for item in value: walk(item)
            elif isinstance(value, str) and len(value) < 12000:
                parts.append(value)
        walk(event)
    return "\n".join(messages) or "\n".join(parts) or stdout


def response_assertions(text):
    """The prompt requires this compact envelope; never persist the provider body."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    assertions = value.get("assertions") if isinstance(value, dict) else None
    if not isinstance(assertions, list) or not all(isinstance(item, str) for item in assertions):
        return None
    return sorted(set(assertions))


def run_one(provider, capability, workflow, variant, root):
    requested = sorted(set(workflow["required_assertions"] + workflow["forbidden_assertions"]))
    prompt = (
        "You are performing a read-only skill-efficacy replay. Do not edit files, run tools, create records, "
        "or expose secrets, roots, settings, or hidden reasoning. Answer ONLY JSON: "
        '{"assertions":["exact assertion ids satisfied"]}. The only allowed assertion ids are: '
        + canonical(requested) + ".\nWorkflow:\n" + workflow["prompt"]
    )
    command = provider_command(provider, prompt, variant, capability, root)
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if command is None:
        return {"outcome": "unavailable", "assertions": [], "error": "provider-cli-unavailable", "observed_at": observed_at}
    try:
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=180, check=False)
    except subprocess.TimeoutExpired:
        return {"outcome": "unavailable", "assertions": [], "error": "timeout", "observed_at": observed_at}
    text = compact_text(provider, completed.stdout)
    assertions = response_assertions(text)
    if completed.returncode or assertions is None:
        return {"outcome": "unavailable", "assertions": [], "error": f"provider-exit:{completed.returncode}", "observed_at": observed_at}
    required = set(workflow["required_assertions"])
    forbidden = set(workflow["forbidden_assertions"])
    asserted = set(assertions)
    outcome = "pass" if required <= asserted and not (forbidden & asserted) else "fail"
    return {
        "outcome": outcome, "assertions": assertions, "observed_at": observed_at,
        "response_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def release_blockers(rows, admission):
    blockers = []
    keys = {(r["capability_id"], r["workflow_id"], r["provider_id"], r["variant"]) for r in rows}
    expected = {(c["capability_id"], w["id"], p["provider_id"], v)
                for c in admission["capabilities"] for w in c["workflows"]
                for p in admission["providers"] for v in VARIANTS}
    if keys != expected or len(rows) != 54:
        blockers.append("REPLAY_MATRIX_NOT_EXACT")
    if len(keys) != len(rows):
        blockers.append("REPLAY_MATRIX_DUPLICATE")
    # D88: live provider outcomes remain diagnostic.  Only a malformed replay carrier is a
    # P7.1 package blocker; unavailable access and model efficacy are never promoted to green.
    return sorted(set(blockers))


def write(args):
    root = Path.cwd()
    admission = load(args.admission)
    source_gate(admission, root)
    requested_providers = args.providers.split(",")
    if requested_providers != [p["provider_id"] for p in admission["providers"]]: fail("provider order/set drift")
    rows = []
    for capability in sorted(admission["capabilities"], key=lambda row: row["capability_id"]):
        for workflow in capability["workflows"]:
            for provider in requested_providers:
                for variant in VARIANTS:
                    result = run_one(provider, capability, workflow, variant, root)
                    rows.append({
                        "capability_id": capability["capability_id"], "workflow_id": workflow["id"],
                        "provider_id": provider, "variant": variant, "provider_version": "unknown",
                        "model_id": "provider-reported-unavailable", "tool_identity": provider,
                        "source_snapshot_sha256": capability["source_sha256"], "privacy_redactions": EXCLUDED,
                        "evidence_ref": "sha256:" + result.get("response_sha256", "unavailable"), **result,
                    })
    rows.sort(key=lambda row: tuple(row[key] for key in ("capability_id", "workflow_id", "provider_id", "variant")))
    blockers = release_blockers(rows, admission)
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    results = {"schema_version": "p7.1-skill-replay-results/v1", "admission_sha256": digest(admission), "rows": rows, "release_blockers": blockers}
    (output / "skill-replay-results.json").write_text(canonical(results) + "\n", encoding="utf-8")
    ablations = {"schema_version": "p7.1-skill-ablation-results/v1", "status": "deferred-owner-decision", "release_blockers": [], "decision": "D88", "reason": "live efficacy is deferred outside package acceptance"}
    (output / "skill-ablation-results.json").write_text(canonical(ablations) + "\n", encoding="utf-8")
    print(canonical({"rows": len(rows), "release_blockers": blockers + ablations["release_blockers"]}))
    return 0 if not blockers else 2


def check(args):
    admission = load(args.admission); source_gate(admission, Path.cwd())
    results = load(Path(args.output_dir) / "skill-replay-results.json")
    blockers = release_blockers(results.get("rows", []), admission)
    if results.get("release_blockers") != blockers: fail("replay blocker set is stale")
    ablations = load(Path(args.output_dir) / "skill-ablation-results.json")
    if ablations.get("status") not in {"green", "deferred-owner-decision"}: blockers.append("ABLATION_EVIDENCE_INVALID")
    print(canonical({"release_blockers": sorted(set(blockers))}))
    return 0 if not blockers else 2


def reclassify(args):
    """Apply D88 to already captured privacy-minimized observations without provider calls."""
    admission = load(args.admission)
    source_gate(admission, Path.cwd())
    output = Path(args.output_dir)
    results = load(output / "skill-replay-results.json")
    rows = results.get("rows", [])
    blockers = release_blockers(rows, admission)
    results["release_blockers"] = blockers
    results["classification"] = {"decision": "D88", "live_efficacy": "diagnostic-not-release-gate"}
    (output / "skill-replay-results.json").write_text(canonical(results) + "\n", encoding="utf-8")
    ablations = {"schema_version": "p7.1-skill-ablation-results/v1", "status": "deferred-owner-decision", "release_blockers": [], "decision": "D88", "reason": "live efficacy is deferred outside package acceptance"}
    (output / "skill-ablation-results.json").write_text(canonical(ablations) + "\n", encoding="utf-8")
    print(canonical({"rows": len(rows), "package_blockers": blockers, "provider_calls": 0}))
    return 0 if not blockers else 2


def self_test(_args):
    assert digest({"b": 1, "a": 2}) == digest({"a": 2, "b": 1})
    print("p7-skill-replay: self-test OK")
    return 0


def main():
    parser = argparse.ArgumentParser(); commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("self-test")
    for name in ("write", "check", "reclassify"):
        command = commands.add_parser(name); command.add_argument("--admission", required=True); command.add_argument("--output-dir", required=True)
        if name == "write": command.add_argument("--providers", required=True); command.add_argument("--contracts-dir", required=True)
    args = parser.parse_args()
    try:
        return {"self-test": self_test, "write": write, "check": check, "reclassify": reclassify}[args.command](args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"P7_SKILL_REPLAY_BLOCKER: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(main())
