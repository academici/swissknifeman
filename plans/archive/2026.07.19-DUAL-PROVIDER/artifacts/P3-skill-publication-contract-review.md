# P3.1 skill publication contract review

**Status:** approved review; D77 recorded

**Contract:** `root/contracts/provider-skill-publication-contract.md` v1.0.0 frozen

**Scope:** P3.1 contract decision only. No package code, registry output, provider manifest,
generated bundle, live install, FOREMAN, fleet or owner-worktree change is authorized here.

## Decision matrix

| Alternative | Advantages | Material cost/risk | Recommendation |
|:--|:--|:--|:--|
| A. One semantic catalog with independent Claude and Codex renderers | one identity source; native provider shapes; independent parity evidence | requires catalog/provenance seam before adapters | **Accept** |
| B. Derive Codex JSON from Claude marketplace JSON | short initial implementation | Claude format becomes hidden canon; provider gaps and cache constraints are lost | Reject |
| C. Maintain a complete `.agents/skills` copy as a second tree | immediately visible Codex files | duplicates canonical content and makes drift a normal workflow | Reject |
| D. Automatically install Codex plugins during render/update | fewer explicit operator actions | silently mutates user-global/trust state and obscures partial provider failure | Reject |

## Candidate checks

| Candidate rule | Consumer | Failure made diagnosable |
|:--|:--|:--|
| semantic IDs are provider-path independent | P3.2 catalog, P3.5 parity | `SPUB_ID_INVALID` / `SPUB_CATALOG_MISMATCH` |
| Claude and Codex render independently | P3.2/P3.3 adapters | projection mismatch before write |
| cache/vendor output is contained and provenance-locked | P3.3/P3.4 | `SPUB_PATH_UNCONTAINED`, `SPUB_BUNDLE_INCOMPLETE`, ownership refusal |
| legacy no-provider configuration remains Claude-only | P3.4 provider loop | no implicit Codex enablement |
| global Codex install is explicit | P3.4 operation boundary | `SPUB_INSTALL_EXPLICIT_REQUIRED` and zero subprocess in ordinary operations |
| catalog examples have both provider outcomes | P3.5 conformance | missing/extra semantic member or unsupported projection |

## Approval record candidate

The owner-level fork is whether the S1–S6 identity, bundle/version, compatibility and native
install semantics become frozen public contract. Routine rendering choices remain deferred to
P3.2–P3.5 and do not need separate owner decisions when they conform to the approved contract.

**Owner verdict:** Approved → D77, 2026-07-20.

**Minimal approval wording:**

```text
APPROVE P3.1 SKILL-PUBLICATION S1-S6 AS WRITTEN
```

The owner gave the exact approval above. D77 freezes contract v1.0.0 and authorizes only P3.1's
declared contract close. It does not authorize P3.2+, package/runtime writes, public-command
design, native installation, live configuration, FOREMAN, fleet or changes to unrelated owner dirt.
