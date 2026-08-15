#!/usr/bin/env bash
# Validate the P4.2 EN canonical template and its additive generated projection.
set -euo pipefail

PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
strict="false"
direction=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict) strict="true"; shift ;;
    --direction)
      [[ "${2:-}" == "en-source" ]] || { echo "ERROR: --direction accepts only en-source" >&2; exit 2; }
      direction="$2"; shift 2 ;;
    *) echo "usage: $0 [--strict] [--direction en-source]" >&2; exit 2 ;;
  esac
done
if [[ -n "$direction" && "$direction" != "en-source" ]]; then
  echo "usage: $0 [--strict]" >&2
  exit 2
fi

python3 - "$PACKAGE_ROOT" "$strict" <<'PY'
"""Structure-only source-direction check; corpus admission belongs to locale-corpus."""
from __future__ import annotations

import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
strict = sys.argv[2] == "true"
canonical_path = root / "SKILL_TEMPLATE.md"
generated_path = root / "generate-skill" / "generate-skill" / "snippets" / "SKILL_TEMPLATE.md"
errors: list[str] = []

if not canonical_path.is_file():
    errors.append("AUTHORING_SCHEMA_INVALID: canonical SKILL_TEMPLATE.md is missing")
    text = ""
else:
    text = canonical_path.read_text(encoding="utf-8")

if (not canonical_path.is_file() or not generated_path.is_file()
        or canonical_path.read_bytes() != generated_path.read_bytes()):
    errors.append("AUTHORING_PROJECTION_STALE: generated template differs from canonical source")

if re.search(r"[\u0400-\u04ff]", text):
    errors.append("AUTHORING_SOURCE_NOT_ENGLISH: canonical template contains Cyrillic")

match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
frontmatter: dict[str, str] = {}
if not match:
    errors.append("AUTHORING_SCHEMA_INVALID: canonical template lacks frontmatter")
else:
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            frontmatter[key.strip()] = value.strip()

required = {"name", "bucket", "version", "description", "risk", "invocation_intent",
            "capabilities", "inputs", "outputs", "resources", "provenance"}
missing = sorted(required - frontmatter.keys())
if missing:
    errors.append("AUTHORING_SCHEMA_INVALID: missing template fields: " + ", ".join(missing))

provider_fields = {"adapters", "provider", "claude", "codex", "cursor", "fable", "model",
                   "effort", "approval", "sandbox"}
found_provider_fields = sorted(provider_fields & frontmatter.keys())
if found_provider_fields:
    errors.append("SKILL_EVIDENCE_PROVIDER_TUNING_SHARED: provider controls in shared frontmatter: "
                  + ", ".join(found_provider_fields))

headings = ["# Skill purpose", "## Trigger checks", "## Inputs and outputs",
            "## Invariants and risk", "## Workflow", "## Resources", "## Optional failure modes",
            "## Provenance"]
positions = [text.find(heading) for heading in headings]
if any(position < 0 for position in positions) or positions != sorted(positions):
    errors.append("AUTHORING_INVARIANT_DELETED: minimum Skill Core headings are incomplete")

trigger_checks = ("Positive:", "Negative:", "Boundary:")
if not all(check in text for check in trigger_checks):
    errors.append("SKILL_EVIDENCE_SCHEMA_INVALID: trigger checks require positive, negative, and boundary prompts")
if "references/" not in text and "snippets/" not in text:
    errors.append("SKILL_EVIDENCE_SCHEMA_INVALID: progressive-disclosure resource link is missing")
if "linked observed failure or ablation record" not in text:
    errors.append("SKILL_EVIDENCE_ABLATION_MISSING: optional failure modes need evidence")

# Template alternatives document a cross-field rule; concrete skills are admitted by the ledger.
if frontmatter.get("risk") != "read|draft|write|external" or frontmatter.get("invocation_intent") != "automatic|explicit":
    errors.append("AUTHORING_SCHEMA_INVALID: risk and invocation_intent alternatives changed")
if "for `write` and `external` risk" not in text:
    errors.append("AUTHORING_INVARIANT_DELETED: explicit high-risk invocation boundary is missing")

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1)

mode = "strict" if strict else "default"
print(f"translations ({mode}): EN canonical template and generated projection are valid")
PY
