# P1 provider control-plane design synthesis

**Date:** 2026-08-14
**Item:** P1.1
**Scope:** desired/status contract only; no package, provider-target, carrier, or fleet writes

## Decision

Use one result envelope around four deliberately separate semantic carriers:

1. `desired` is the complete materialized projection of the frozen provider-config resolver,
   including leaf provenance and a canonical semantic digest.
2. `last_applied` is adapter/artifact provenance from one successful committed apply.
3. `observed` is one provider-qualified, freshness-bounded evidence record.
4. provider `status` and `aggregate` are deterministic derivations, never configuration.

Schema/input errors produce `result=null`; they do not leak a partial desired/provider result.
One selected provider cannot mask a stale, missing, drifted, unsupported, untrusted, unknown,
or errored selected peer.

## Alternatives rejected

| Alternative | Verdict | Reason |
|:--|:--|:--|
| New monolithic control-plane SSOT | Reject | Duplicates provider-config selection, capability support, and artifact provenance. |
| Read rendered provider output as desired intent | Reject | Reverses Canonical Source → Adapter → Rendered Artifact ownership. |
| One `healthy` boolean | Reject | Collapses unsupported, trust, freshness, drift, and unknown evidence. |
| Timestamp inside semantic hashes | Reject | Identical desired intent would drift with wall-clock time. |
| Provider-specific payload bags | Reject | Leaks unstable syntax and prevents deterministic cross-provider checking. |
| Treat refresh evidence as universally complete | Reject | Official Terraform documentation recommends refreshing all possible schema values but does not promise omniscience over remote state. |

## Trace table

| New field/rule | Existing owner or evidence | Composition rule |
|:--|:--|:--|
| `desired.selection` | frozen provider-config v1.0.0 | Exact materialized projection; no new precedence or defaults. |
| desired leaf provenance | frozen provider-config v1.0.0 | Copy each effective leaf winner; containers get no winner. |
| `capability_catalog_version` | frozen capability v1.0.0 + current manifest | Observed version only; support remains manifest-owned. |
| Provider IDs | capability manifest | Exact stable IDs; aliases/model/CLI names are invalid. |
| `last_applied.artifacts` | frozen artifact v1.3.0 lock records | Copy stable identity and source/rendered hashes after committed apply. |
| `observed.capability` | capability catalog + selected requirements | Derived `satisfied/unsupported/unknown`; never config-authored. |
| `observed.artifacts` | artifact observation state machine | Collapse only to `clean/drifted/unknown`; detailed observation remains adapter evidence. |
| `observed.trust` | separate Project Trust evidence | Never infer it from approval or sandbox. |
| freshness metadata | adapter observation contract | Timestamps evaluate freshness but never enter semantic hashes. |
| provider status | P1.1 contract | Closed first-match derivation over selected/apply/observation/diagnostics. |
| aggregate | P1.1 contract | Exact selected set and non-masking priority over provider statuses. |
| machine diagnostics | config/capability/artifact structured diagnostics | Stable English code/source; only `message` may localize. |
| no-partial result | P1.1 + verified state-upgrade pattern | Error returns `result=null`; no silent partial adoption. |

## Schema and checker shape

The positive fixture proves a ready Claude Code row plus a stale Codex row yields aggregate
`unknown`, and that an all-disabled desired selection yields `no-providers-selected` without
observations. Negative fixtures are single JSON-pointer mutations of a named positive base.
They cover unknown major/field/status, digest and provenance mismatch, missing/duplicate
provider rows, stale masking, collapsed trust, partial result, raw payload, apply mismatch,
localized machine code, and invalid project identity.

The checker uses only the Python standard library. It re-computes desired canonical digests,
validates exact shapes and provenance coverage, re-derives provider and aggregate status, and
requires every negative mutation to fail with its exact declared code. It neither imports the
current provider runtime nor writes any carrier.

## Provider-version rebind

The execution environment reported `Claude Code 2.1.228` and `codex-cli 0.147.0` on
2026-08-14. These are local observed versions used only in the normative observation fixture;
they are not claims that either version is the latest release, and they do not alter Provider
IDs or schema semantics.

## Verification

- RAG: Context7 `/websites/developer_hashicorp_terraform` ×2 OK; Perplexity Web ×2 OK,
  official HashiCorp sources only, retrieved 2026-08-14.
- External fact — state upgrade: saved schema-version mismatch dispatches the exact prior-version
  upgrader; missing support returns an error; the upgrader populates complete target state; an
  errored response retains prior state. Source: <https://developer.hashicorp.com/terraform/plugin/framework/resources/state-upgrade>,
  page updated 2026-03-05. Confidence: high (primary source, two retrieval engines).
- External fact — desired/observed drift: normal plan refreshes provider state before comparing
  it to configuration; out-of-band changes surface in plan. Source:
  <https://developer.hashicorp.com/terraform/cli/commands/plan> and
  <https://developer.hashicorp.com/terraform/plugin/framework/resources/read>, retrieved
  2026-08-14. Confidence: high (primary sources, two retrieval engines).
- Boundary correction: `plan -refresh-only` is remote-write-free, while applying a refresh-only
  plan writes Terraform state; P1.1 therefore defines check as no-write and does not borrow
  Terraform's apply semantics. Source: <https://developer.hashicorp.com/terraform/cli/commands/apply>
  and <https://developer.hashicorp.com/terraform/cli/commands/refresh>, retrieved 2026-08-14.
  Confidence: medium (primary sources, Perplexity synthesis).
- Unverified → repeat pass: whether the locally installed Claude Code/Codex versions are latest;
  the design deliberately makes no such claim.
- Workarounds/[POSSIBLE-DEFECT]: none.
