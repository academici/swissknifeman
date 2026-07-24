# Source evidence bundle

This directory is the portable, committed evidence carrier for plan
`2026.07.24-AGENT-RELIABILITY`. It intentionally contains the complete external
audit snapshot, seven lossless journal snapshots, a minimized incident record,
precomputed corrected telemetry, a critical-case corpus, and sanitized runtime
observations. A Claude or Codex session can validate the bundle without opening
the original session pool, another project, or user-owned `tmp/` files.

## Privacy and minimization

The `sessions/` records are not transcripts. They retain only a hash-pinned
original path, record selector, timestamp, concise observable summary, and
confidence. They exclude raw user and assistant text, hidden reasoning, tool
payloads, credentials, and unrelated messages. Runtime files are likewise
sanitized projections: they retain conclusions needed by the plan while removing
host paths, commands, configuration values, authentication details, and secrets.

Original external paths in manifests are optional provenance only. They are never
execution prerequisites: `verify_source_bundle.py` reads this directory alone.
The audit and journal bytes in this directory are the self-contained snapshots.
The incident selector records deliberately do not attempt to reproduce raw
sessions; they preserve only load-bearing, findings-backed facts and say when
confidence is not high.

## Contents and verification

- `perplexity-audit.md` is the byte-for-byte 279780-byte audit snapshot.
- `journals/` contains exactly seven byte-for-byte JSONL snapshots.
- `sessions/selected-incident-events.jsonl` contains five minimized critical and
  control records, including the clean HONEST-HTTP control.
- `precomputed/baseline.json` records corrected dedup telemetry and denominators.
- `precomputed/corpus.json` maps requirements, prohibitions, public acceptance,
  source paths, and confidence.
- `runtime/` contains non-secret runtime evidence.
- `manifests/bundle-manifest.json` is the integrity manifest. It cannot hash
  itself, so it covers every other committed bundle file.

Run from any checkout with Python 3 standard library:

```bash
python3 plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence/verify_source_bundle.py verify
python3 plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence/verify_source_bundle.py map-state
python3 plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence/verify_source_bundle.py verify-results
python3 plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence/verify_source_bundle.py verify-claim-inventory
```
