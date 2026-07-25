# P2 repo recon — artifact generation, provenance, locks и drift

**Дата:** 2026-07-19

**Метод:** read-only `rg`/`cat`/`sed` по текущему worktree + recall
`project:swissknifeman` через mAInd. Package code, tests и generators не запускались.

## Наблюдаемые реализации

- `core/io.py` уже владеет общими `atomic_write_text/json`, а `core/block.py` —
  deterministic managed markdown block + content hash. Это существующие extension points,
  которые новый artifact kernel обязан переиспользовать.
- `packages/skiller/lib/skiller/skillset.py` имеет versioned `skills-lock.json`,
  source/content hashes, pure-ish `plan_sync`, managed-only prune, unmanaged conflicts и
  восстановление ownership hints при битом lock. Семантика специализирована на skills.
- `packages/harness/lib/harness/agentpacks.py` имеет deterministic provenance header без
  timestamp, hash rendered bytes, edit policies, lock, categories `safe-apply/conflict`,
  user-owned/merge exclusions и read-only drift doctor. Семантика специализирована на
  Claude agent packs.
- `packages/maind/lib/maind/health.py`/`doctor.py` используют managed hashes/drift для
  blocks/templates и агрегируют package diagnostics, но общего artifact contract не дают.
- Три независимых current consumers (`skiller`, `harness`, `maind`) уже решают один класс
  задачи разными state models. Rule of Three для deliberate shared `core` contribution
  выполнен; package-specific render semantics при этом остаются downstream.

## Ограничения, подтверждённые repo evidence

- `core` — stdlib-only и не импортирует packages; explicit inputs/targets обязательны.
- Existing writers работают merge-/managed-aware; auto-adoption чужого path или silent
  overwrite противоречат текущим защитным паттернам.
- Timestamp в provenance ломает stable rendered hash; текущий agent-packs header намеренно
  timestamp-free.
- Битый lock нельзя молча трактовать как отсутствие ownership: `skiller.skillset` уже
  содержит incident-driven recovery/fail-safe логику.
- mAInd checkpoint повторяет принятое D2 направление: canonical source + deterministic
  provider adapters + lock/hash/drift; новых решений сверх файлов плана память не внесла.

## Не выполнялось и не менялось

- Не запускались Python modules, tests, validators, generators или package CLI.
- Не читались и не редактировались package-specific semantic assets вне узкого recon.
- Не изменялись `plans/2026.07.18-FOREMAN`, root/fleet configs или downstream projects.

## Verdict

P2 должен вводить минимальный flat `core` kernel через proposal/ADR gate: общий artifact
plan/provenance + lock/drift/apply primitives + explicit immutable adapter catalog.
Реальные adapters/CLI остаются P3–P6; global discovery/service locator не нужен.
