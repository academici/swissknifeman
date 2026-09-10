# Design-audit remediation evidence — 2026-08-03

## Scope

This finding captures only the external provenance and repository reproductions used to
remediate design-audit findings F8–F12. It does not authorize code, provider, fleet, Brain,
generated-artifact or release mutation.

## IANA/RFC carrier verification

- Official source: <https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry>
- Retrieved: 2026-08-03.
- Observed header: `File-Date: 2026-06-14`.
- Observed byte length: `731605`.
- Observed SHA-256: `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a`.
- Verification commands:

  ```text
  curl -fsS https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry | sha256sum
  curl -fsS https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry | sed -n '1p'
  curl -fsS https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry | wc -c
  ```

The registry is a mutable official dataset, so host-time lookup is not a reproducible semantic
input. The plan pins the exact bytes above in `core/locale/data/language-subtag-registry.txt`
with adjacent `upstream.json`; P2.1 freezes the data identity, P4.1 implements the stdlib reader
and explicit update producer over that same carrier, and P7.3 verifies the identity in release
provenance. Confidence: high (official primary source, exact bytes locally hashed).

RFC 5646 was re-opened at <https://www.rfc-editor.org/rfc/rfc5646.html> on 2026-08-03.
Section 3.1.7 defines `Preferred-Value` as a canonicalization mapping; sections 2.2.7 and 4.6
keep private-use sequences valid and opaque outside private agreement. Confidence: high
(official RFC Editor source).

## Hook public-CLI reproduction

From repository root, the exact relative-target public command:

```text
packages/harness/bin/harness hooks --target . --provider codex --observer --trusted --dry-run
```

exits nonzero at `core/provider/lock.py:_root` with
`ValueError: root must be explicit and absolute`. The exact absolute-target form:

```text
packages/harness/bin/harness hooks --target /home/vostrikov/projects/packages/swissknifeman --provider codex --observer --trusted --dry-run
```

exits zero, emits a deterministic plan identity and reports the existing
`stale-source -> update` operations for lifecycle hooks/handler. This isolates the defect to
public CLI target normalization before the shared artifact-lock boundary; it does not justify
weakening the shared absolute-root invariant. Repository observation, high confidence.

## External design provenance to publish

P7.3 must add exact dated entries to `docs/reference.md` for:

- RFC 5646: <https://www.rfc-editor.org/rfc/rfc5646.html>
- IANA Language Subtag Registry: the URL, `File-Date`, pinned SHA-256 and update command above.
- HashiCorp drift guidance:
  <https://developer.hashicorp.com/terraform/plugin/sdkv2/best-practices/detecting-drift>
- HashiCorp state-upgrade guidance:
  <https://developer.hashicorp.com/terraform/plugin/framework/resources/state-upgrade>

Both HashiCorp pages were re-opened from the official developer site on 2026-08-03. They remain
design provenance only; SKM does not add Terraform as a dependency. Confidence: medium for each
individual page (one official primary source).

## Verification status

- RAG: official IANA registry, RFC Editor RFC 5646 and two official HashiCorp pages — 4 source
  classes checked on 2026-08-03; exact IANA bytes additionally hashed locally.
- Unverified -> repeat pass: none.
- Workarounds/[POSSIBLE-DEFECT]: none; the relative-target hook failure is assigned to P3.2 as
  an implementation/regression defect, not normalized away in this design session.

## Repository-grounded remediation F16–F18

No new external fact class is needed for the fourth-audit findings. F16 is closed by parsing the
append-only Decision Log itself and requiring exact set equality with one P7 crosswalk row per
current D#; D47–D49 become part of the denominator, so the current set is D1–D49 and a future D#
cannot be hidden behind a static range. F17 is closed by one shared P5 canonical-JSONL transaction
carrier with stable project/action/transaction IDs, hash-chain ordinals, pre/post hashes, frozen
manifest/action/source identities, `flush`+`fsync` at every state boundary and deterministic
restart reconciliation before the first non-terminal transaction. F18 is closed by the explicit
root/package-cwd matrix in `roadmap.md` plus fully expanded helper subcommands and manifest/action/
evidence/contract arguments in P4.4/P4.6, P5.1–P5.4, P6.1/P6.3 and P7.1/P7.4 Validation.

The design-only preflight on 2026-08-03 reproduced the same environment boundary as the fourth
audit: worktree-local plan lint and citations are green, while relative hook target normalization
still fails and the absolute dry-run reports two `stale-source` operations. That defect remains
assigned to P3.2/P7.2; no code, provider, fleet, Brain, generated artifact or release state was
changed by this remediation.

## Scope extension history — append-only clarification

The original Scope at lines 3–7 remains historical truth for the first creation of this file:
it covered external provenance and repository reproductions for F8–F12 only. The file was then
extended append-only during the fourth-audit remediation to carry the repository-grounded F16–F18
record above; that addition did not retroactively broaden the original capture scope. During the
fifth-audit remediation it is extended once more with the F19–F25 repository-grounded record below.
No new external source class is introduced by either extension, and neither extension authorizes
code, provider, fleet, Brain, generated-artifact or release mutation.

## Repository-grounded remediation F19–F25

- F19/F20: `packages/harness/lib/harness/instructions.py` proves positional equality between the
  writable target tuple and `authorized_target_paths`; D50/P4/roadmap now freeze the plan hash,
  alphabetic Harness target order, exact `--authorize` argument and one verifier-owned
  `deferred-derived-only` state whose ordered `DERIVED_TARGET_STALE` rows are the only legal
  pre-terminal nonzero results. P4.6 closes only after the deferred union is empty and every
  package/docs validation is 0 on a byte-stable second owner run.
- F21/F22: D51/P0.3 add the plan-local `p0-recovery-gates-check.py`, tests, schema/hash evidence and
  exact branch commands consumed by P0.4. `contract_freeze_decision`, conditional
  `containment_mutation_decision` and P4.6 technical generated-target authorization are separate;
  no contract/security D# is reused for ordinary repository generation.
- F23: D52/P6.1 add a hash-chained, append+flush+fsync Brain WAL with stable action/boundary IDs,
  deterministic reconcile/resume/whole-project rollback and crash fixtures after every append and
  public CLI apply/readback boundary. Aggregate results are accepted only from a terminal chain.
- F24: D53/P5.1 now states the byte boundary precisely: `plan` may atomically initialize only its
  named manifest/journal and writes no consumer/provider target; `check` changes no byte anywhere,
  with separate delta assertions.
- F25: this append-only history distinguishes the file's original F8–F12 scope from its later
  F16–F18 and F19–F25 extensions instead of rewriting the earlier observation.

Verification status for this extension: repository/code-grounded only, checked against the named
plan carriers and Harness implementation on 2026-08-03; no new RAG query, unverified external fact
or workaround was introduced.
