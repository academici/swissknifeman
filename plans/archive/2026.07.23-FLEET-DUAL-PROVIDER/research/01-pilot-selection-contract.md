# P1 replacement pilot — target scope и selection contract

## Evidence

- `findings/P0.2-fleet-rerun.md` называет только прежний pilot и aggregate
  classes; следующего совместимого кандидата committed evidence не доказывает.
- `findings/P1.1-pilot.md` фиксирует конфликт: ordinary Laravel consumer получил
  пять отсутствующих swissknifeman package scopes и unmanaged root targets.
- `packages/maind/lib/maind/provision/sync.py::_instruction_request` передаёт все
  `SCOPES`; `packages/harness/lib/harness/instructions.py` принимает явный
  непустой ordered subset и сохраняет fail-closed observation/authorization.

## Contract

RAG:— (repo-grounded:
`packages/maind/lib/maind/provision/sync.py:270-333`;
`packages/harness/lib/harness/instructions.py:915-1012`).

1. mAInd передаёт `root` плюс package scopes только для точных реальных
   `packages/<scope>` directories; symlink/absence scope не включает и не
   создаёт synthetic package tree. Порядок остаётся frozen `SCOPES`.
2. Candidate order — `maind projects list --json` registry order. Исключаются
   D5 `sibintek-insiders`, self-host, unavailable/non-git и dirty roots.
3. До выбора требуются оба effective providers, green MCP/skills и instruction
   plan только по applicable scopes. Допустимы clean/noop, missing/create и
   managed stale-source/update; ownership/boundary/provenance/managed-drift,
   repair/refuse исключают candidate.
4. Выбирается первый прошедший candidate и получает ровно один apply. Пустой
   результат даёт blocked finding без consumer writes и без ослабления гейта.

Alternatives: all-scopes rejected как повтор topology conflict; root-only
everywhere rejected как потеря package guidance; ручной per-project scope list
rejected как второй drift-prone carrier.

## Disposable fallback carrier after exhausted live selection

Повторные D7 scans в `findings/P1.1-pilot-retry.md` дали один и тот же пустой
eligible-set. Новый scan не создаёт кандидата и не меняет acceptance, поэтому
минимальный следующий носитель — существующий local conformance carrier:

- `packages/maind/lib/maind/provision/sync.py:683-916` создаёт все target roots
  внутри `TemporaryDirectory`, включая dual-provider case и project `matrix`;
- dual-provider case выполняет public instruction apply/check/no-op через тот же
  `run_sync`, а `matrix` строится из обоих effective providers через полный
  provisioner dry-run;
- `packages/maind/lib/maind/provision/sync.py:929-934` экспортирует этот carrier
  как `maind sync --conformance <artifact-path>` и завершает команду non-zero,
  если обязательные conformance checks красные.

RAG:— (repo-grounded:
`packages/maind/lib/maind/provision/sync.py:683-916`;
`findings/P1.1-pilot-retry.md`).

Fallback выбирает только dual-provider temp-root case как P1.1 pilot; остальные
cases команды — compatibility controls, не дополнительные rollout candidates.
Пишутся только disposable roots и указанный plan artifact. Live registry,
consumer repos и их user-owned bytes не являются target surface. D7 provider,
ownership, boundary и instruction acceptance применяются без ослабления; red
переводит тот же carrier в P1.2 owning repair, а не в ещё один registry scan.
Встроенный temp-only managed-block repair case остаётся conformance safety
control: он не является consumer repair и не разрешает запуск CLI `--repair`.
GREEN доказывает synthetic MVP, а не завершение live fleet rollout; последний
остаётся отдельным P2.
