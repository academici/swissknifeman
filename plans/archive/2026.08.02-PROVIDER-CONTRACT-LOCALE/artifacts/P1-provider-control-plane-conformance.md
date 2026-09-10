# P1 provider control-plane conformance

**Contract candidate:** `root/contracts/provider-control-plane-v1.md`

**Candidate status:** complete; exact C1–C6 Owner freeze decision pending

## Covered boundaries

- schema/digest/provenance/provider/aggregate validation and no-partial result;
- exhaustive ownership matrix, capability negotiation, Skill Core neutrality and additive
  third-provider registration;
- recognized legacy/provider-config source classes, complete P0 classification and ownership;
- no-write plan/check/dry-run, exact apply authority, preimage and backup admission;
- all-provider atomicity, rollback, readback and empty second reconcile;
- dynamic archived G01–G11 source-row digest crosswalk with an explicit no-weaken rule.

## Normative evidence

`migration-positive.json` contains compatibility-noop, no-write plan, successful atomic apply and
restored partial-provider outcomes. `migration-negative.json` changes one boundary per case and
covers every closed `MIG_*` refusal code, including changed preimage, unknown/newer source,
ambiguous/local/unowned state, partial provider result, rollback failure, readback mismatch and a
non-empty second reconcile.

The checker computes results from the contract-authored records. It does not import a migrator,
derive expected results from runtime serializers, special-case a fleet path/hash or perform a
provider, package, Brain, credential or fleet write.

## Validation receipt

- Initial candidate checker: `--self-test all` passed after one targeted fixture repair.
- Package regression carrier: the declared core/skiller/maind unittest command passed.
- Owner freeze gate: pending exact reply
  `APPROVE P1.3 PROVIDER-CONTROL-PLANE C1-C6 AS WRITTEN`.
