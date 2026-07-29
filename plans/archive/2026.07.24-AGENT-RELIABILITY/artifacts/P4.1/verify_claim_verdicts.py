#!/usr/bin/env python3
"""Deterministic read-only verifier for the P4.1 hypothesis verdict record.

The verifier proves four things from committed bytes only, and writes nothing:

1. the adjudicated audit snapshot is the hash-pinned one (`bundle-manifest.json`
   is the single hash/size SSOT — `findings/00-source-evidence-manifest.md`);
2. every verdict points at a real line range inside that snapshot;
3. every verdict carries the evidence its own class requires — `reject`/`accept`
   name function/caller/test/command evidence, `unknown` names the MISSING
   evidence by name, `accept` carries exactly one bounded future proposal with
   owner/contract/tests/observable user outcome;
4. no verdict is argued from acceptance state (D89: hypothesis adjudication and
   acceptance floors are different axes; `observable_relevance` may not mention
   GREEN or acceptance completion at all).

Stdlib only.  Exit code 0 = every check passed, 1 = at least one failed,
2 = usage/IO error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


SCHEMA_VERSION = "hypothesis-verdicts/v1"
VERDICTS = ("accept", "reject", "unknown")
EVIDENCE_KINDS = ("function", "caller", "test", "command", "artifact")
AUDIT_ENTRY = "perplexity-audit.md"
# D89: acceptance state may never be the reason a hypothesis is accepted or rejected.
FORBIDDEN_IN_RELEVANCE = ("GREEN", "green verdict", "приёмка выполнена",
                          "приёмка не выполнена", "acceptance met", "acceptance not met")
PROPOSAL_FIELDS = ("id", "owner", "contract", "tests", "observable_user_outcome",
                   "rule_of_three")


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.checks = 0

    def check(self, condition: bool, message: str) -> bool:
        self.checks += 1
        if not condition:
            self.failures.append(message)
        return bool(condition)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_entry(manifest: dict, name: str) -> dict | None:
    for entry in manifest.get("entries", ()):
        if isinstance(entry, dict) and entry.get("path") == name:
            return entry
    return None


def verify(audit: Path, bundle_manifest: Path, verdicts_path: Path, root: Path) -> Report:
    report = Report()
    manifest = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    verdicts = json.loads(verdicts_path.read_text(encoding="utf-8"))

    # 1. Pinned snapshot identity.
    entry = _manifest_entry(manifest, AUDIT_ENTRY)
    if not report.check(entry is not None, f"bundle manifest has no entry for {AUDIT_ENTRY}"):
        return report
    audit_bytes = audit.read_bytes()
    audit_sha = _sha256(audit)
    audit_lines = audit_bytes.decode("utf-8").count("\n")
    report.check(audit_sha == entry["sha256"],
                 f"audit sha256 {audit_sha} != manifest {entry['sha256']}")
    report.check(len(audit_bytes) == entry["bytes"],
                 f"audit bytes {len(audit_bytes)} != manifest {entry['bytes']}")
    report.check(audit_lines == entry["lines"],
                 f"audit lines {audit_lines} != manifest {entry['lines']}")

    # 2. Record envelope.
    report.check(verdicts.get("schema_version") == SCHEMA_VERSION,
                 f"schema_version must be {SCHEMA_VERSION}")
    report.check(verdicts.get("item") == "P4.1", "record must declare item P4.1")
    source = verdicts.get("generated_from") or {}
    report.check(source.get("audit_sha256") == audit_sha,
                 "generated_from.audit_sha256 does not match the recomputed snapshot digest")
    report.check(source.get("audit_lines") == audit_lines,
                 "generated_from.audit_lines does not match the recomputed snapshot line count")

    hypotheses = verdicts.get("hypotheses")
    if not report.check(isinstance(hypotheses, list) and hypotheses,
                        "hypotheses must be a non-empty list"):
        return report

    proposals = {item.get("id"): item for item in verdicts.get("future_proposals", [])
                 if isinstance(item, dict)}
    report.check(len(proposals) == len(verdicts.get("future_proposals", [])),
                 "future_proposals must have unique non-empty ids")

    seen_ids: set[str] = set()
    referenced: list[str] = []
    counts = {name: 0 for name in VERDICTS}

    for index, item in enumerate(hypotheses):
        label = item.get("id") or f"#{index}"
        report.check(isinstance(item.get("id"), str) and item["id"] not in seen_ids,
                     f"{label}: id must be unique and a string")
        seen_ids.add(item.get("id"))
        report.check(bool(item.get("claim")), f"{label}: claim must be non-empty")
        report.check(bool(item.get("claim_class")), f"{label}: claim_class must be non-empty")

        span = item.get("audit_lines")
        valid_span = (isinstance(span, list) and len(span) == 2
                      and all(isinstance(value, int) for value in span)
                      and 1 <= span[0] <= span[1] <= audit_lines)
        report.check(valid_span, f"{label}: audit_lines must be [start, end] inside 1..{audit_lines}")

        verdict = item.get("verdict")
        if not report.check(verdict in VERDICTS, f"{label}: verdict must be one of {VERDICTS}"):
            continue
        counts[verdict] += 1

        relevance = item.get("observable_relevance") or ""
        report.check(bool(relevance), f"{label}: observable_relevance must be non-empty")
        for token in FORBIDDEN_IN_RELEVANCE:
            report.check(token.lower() not in relevance.lower(),
                         f"{label}: observable_relevance argues from acceptance state "
                         f"('{token}') — forbidden by D89")

        evidence = item.get("evidence") or []
        report.check(isinstance(evidence, list), f"{label}: evidence must be a list")
        for record in evidence:
            if not isinstance(record, dict):
                report.check(False, f"{label}: evidence entries must be objects")
                continue
            kind = record.get("kind")
            report.check(kind in EVIDENCE_KINDS, f"{label}: evidence kind {kind!r} unsupported")
            ref = record.get("ref") or ""
            report.check(bool(ref), f"{label}: evidence ref must be non-empty")
            report.check(bool(record.get("observation")),
                         f"{label}: evidence for {ref!r} must carry an observation")
            if kind in ("function", "caller", "test", "artifact") and ref:
                relative = ref.split("::", 1)[0]
                report.check((root / relative).exists(),
                             f"{label}: evidence path {relative} does not exist under {root}")

        missing = item.get("missing_evidence")
        proposal_id = item.get("future_proposal_id")

        if verdict == "unknown":
            report.check(isinstance(missing, str) and missing.strip(),
                         f"{label}: unknown verdict must name the MISSING evidence")
        else:
            report.check(missing in (None, ""),
                         f"{label}: missing_evidence is only for unknown verdicts")
            report.check(bool(evidence),
                         f"{label}: {verdict} verdict requires at least one evidence record")

        if verdict == "accept":
            report.check(isinstance(proposal_id, str) and proposal_id in proposals,
                         f"{label}: accept requires a bounded future proposal that exists")
        if verdict == "reject":
            report.check(proposal_id in (None, ""),
                         f"{label}: reject must not carry a future proposal")
        if isinstance(proposal_id, str) and proposal_id:
            referenced.append(proposal_id)

    declared = verdicts.get("verdict_counts") or {}
    report.check(declared == counts,
                 f"verdict_counts {declared} does not match recomputed {counts}")

    for proposal_id, proposal in proposals.items():
        report.check(proposal_id in referenced,
                     f"future proposal {proposal_id} is not referenced by any hypothesis")
        for field in PROPOSAL_FIELDS:
            value = proposal.get(field)
            filled = bool(value) if field != "tests" else (isinstance(value, list) and bool(value))
            report.check(filled, f"future proposal {proposal_id}: field '{field}' must be non-empty")
        report.check(proposal.get("implemented_by_this_item") is False,
                     f"future proposal {proposal_id}: must declare implemented_by_this_item=false")

    report.check(len(set(referenced)) == len(referenced),
                 "each future proposal must be referenced by exactly one hypothesis")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--bundle-manifest", required=True)
    parser.add_argument("--verdicts", required=True)
    parser.add_argument("--root", default=".",
                        help="repository root used to resolve evidence paths (default: .)")
    args = parser.parse_args(argv)
    try:
        report = verify(Path(args.audit), Path(args.bundle_manifest),
                        Path(args.verdicts), Path(args.root))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"verify_claim_verdicts: ошибка входа: {error}", file=sys.stderr)
        return 2
    for failure in report.failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    if report.failures:
        print(f"verify_claim_verdicts: {len(report.failures)} из {report.checks} проверок упало",
              file=sys.stderr)
        return 1
    print(f"verify_claim_verdicts: ok — {report.checks} проверок, "
          f"снапшот аудита совпал с bundle-manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
