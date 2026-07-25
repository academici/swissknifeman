# Journal F1 remediation — anchored verification

**Дата:** 2026-07-19  
**Режим:** post-remediation evidence для повторного design audit r3  
**HEAD:** `9844f499797faf063aede49b79703c71f7ef666e`

## Anchors

Plan lint-input snapshot: `sha256:3a3f6284f8e5cdd72061ab119af8f573cf97eef83e874c2ae7833b9dd586edfb`.
Он включает terminal plan-design journal row и D51 sidecar, исключая только этот
self-referential verification-report carrier. Воспроизведение:

```bash
find plans/2026.07.19-DUAL-PROVIDER -type f \
  ! -path 'plans/2026.07.19-DUAL-PROVIDER/findings/journal-remediation-verification-2026-07-19.md' \
  -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum
```

Remediation toolchain snapshot:
`sha256:998d3e3f5d98ce89f700e00d817e8a28319f47f9b464c71d653d3b7a0efa36e9`.
Он фиксирует exact writer/linter/tests/package version/command/canon files:

```bash
sha256sum \
  packages/task/lib/task/journal.py \
  packages/task/lib/task/plan_lint.py \
  packages/task/tests/test_journal.py \
  packages/task/tests/test_plan_lint.py \
  packages/task/.claude-plugin/plugin.json \
  packages/task/commands/plan-design.md \
  packages/skiller/skills/general/plan-protocol/SKILL.ru.md \
  packages/skiller/skills/general/plan-protocol/SKILL.md \
  packages/skiller/skills/general/plan-protocol/snippets/journal-template.md \
  | sha256sum
```

## Exact provenance

- Historical `journal.jsonl:11` exact UTF-8 bytes without newline:
  `sha256:94307a3c3bfaf4c5d5d67ea32d8eacb09410a396b0a217ab2eb094b518693184`.
- `journal-exceptions.jsonl:1` carries the same hash, `target_line:11`, exact
  `invalid_fields:["friction"]`, `owner_decision:"D51"`.
- Original row 11, D49 and compensating rows 22/25 remain present; D51 supersedes only
  D49's insufficient schema-remediation semantics.

## Validation

Current scoped gate:

```bash
python3 packages/task/scripts/plan-lint.py plans/2026.07.19-DUAL-PROVIDER
```

Exact result on the anchored plan + toolchain snapshots: **0 ERROR / 0 WARN**, exit code `0`.

Additional gates:

- targeted journal/linter tests: **32/32 OK**;
- full `packages/task` unittest: **186/186 OK**;
- `bash packages/task/scripts/validate.sh`: **OK**; root sweep has 0 errors and only
  pre-existing warnings outside this plan (scoped plan remains 0/0);
- `bash packages/skiller/scripts/check-translations.sh --strict`: **OK**;
- `git diff --check`: exit code `0`.

## Scope

P0.1–P7.4 implementation/items не исполнялись и не менялись. FOREMAN, ACTIVE, fleet,
instruction remediation P5.6→P7 и unrelated user changes не были write-targets этого
remediation. Следующий допустимый шаг — только независимый design audit r3; P0.1 остаётся
закрыт до literal GREEN.
