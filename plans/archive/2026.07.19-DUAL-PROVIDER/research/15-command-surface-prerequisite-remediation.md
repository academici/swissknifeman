# P0 command-surface prerequisite remediation

**Дата:** 2026-07-20
**Основание:** owner escalation 2026-07-20; `brief/01-refinements.md`;
`findings/repository-baseline-2026-07-19.md`;
`findings/P0-provider-coupling-baseline.md`; текущее repository tree.

**Repo anchor:** `d8ac22c04fc4d4219dc95244ee9d181e92553a74`. Проверка выполнена по
`git ls-tree -r --name-only d8ac22c -- <пять roots>` с фильтром только direct `*.md`.

## Диагноз

Pass 1 использовал число `32` для umbrella inventory верхнеуровневых command surfaces,
но подписал его как `task commands`. P0.1 зафиксировал более узкий и сам по себе
воспроизводимый set: только `packages/task/commands/*.md`, то есть 11 файлов. Его helper
и finding затем ошибочно трактовали разницу `-21` как drift/неопределённый старый scope.

Текущий repo-grounded расклад воспроизводит pass-1 число без подгонки:

| Package surface | Explicit non-recursive root | Current |
|:--|:--|--:|
| task | `packages/task/commands/*.md` | 11 |
| skiller | `packages/skiller/skm/commands/*.md` | 5 |
| harness | `packages/harness/commands/*.md` | 6 |
| maind | `packages/maind/commands/*.md` | 8 |
| analyst | `packages/analyst/commands/*.md` | 2 |
| **Итого Command Surface** | union пяти roots | **32** |

RAG:— (owner-grounded: escalation invocation 2026-07-20; repo-grounded:
`d8ac22c04fc4d4219dc95244ee9d181e92553a74`, перечисленные roots). Вложенные agent-pack commands, например
`packages/harness/configs/claude-code/agent-packs/*/commands/*.md`, в umbrella set не входят:
это контент pack'а, а не top-level package command surface.

## Исправленная модель терминов

- **Command Surface** — umbrella inventory class для direct Markdown command definitions
  в пяти явно перечисленных first-party package roots. `32` — anchored observation
  текущего дерева, а не вечный contract invariant.
- **Task Command** — semantic workflow canonical package `task`; его current source set
  `packages/task/commands/*.md` содержит 11 файлов и является подмножеством Command Surface.
- Package commands skiller/harness/maind/analyst не переименовываются в Task Commands:
  у них свои owners и bounded contexts.

RAG:— (repo-grounded: root `CLAUDE.md`; package command roots; owner correction). Эта
дистинкция заменяет draft-формулировку «32 — deprecated scope-undefined baseline»; само
историческое finding P0.1 не переписывается.

## Executable correction carrier

Выбран новый item **P0.5**, фактически исполняемый между terminal P0.1 и повторным P0.2.
Новый ID не меняет P0.1 Completion Notes/journal и не переименовывает уже эскалированный
P0.2. P0.5 создаёт отдельные:

1. `artifacts/p0-command-surface-correction.py` — stdlib-only, read-only scanner пяти
   non-recursive roots с `--write`/`--check`;
2. `findings/P0-command-surface-correction.md` — anchor, raw sorted paths, breakdown
   `11+5+6+8+2=32`, scope boundary и точное утверждение, что только command-surface
   интерпретация P0.1 superseded;
3. plan bookkeeping/index — текущая truth цепочка `P0.1 historical evidence → P0.5
   correction → P0.2 vocabulary freeze`.

P0.5 не меняет `artifacts/p0-provider-inventory.py`,
`findings/P0-provider-coupling-baseline.md`, P0.1 Completion Notes/status или прежние
journal rows. RAG:— (repo-grounded: plan-protocol append-only/provenance rules).

## Owner gate P0.2

P0.2 нельзя закрыть по одному исправленному count. Его новый Approval Owner D# должен
одновременно:

1. сослаться на terminal P0.5 finding и его tree anchor;
2. принять `Command Surface` и `Task Command` как разные glossary entries;
3. принять current breakdown `32 = 11 + 5 + 6 + 8 + 2`, не превращая count в frozen
   invariant;
4. принять остальные vocabulary/scenario semantics P0.2.

До terminal P0.5 и этой явной записи glossary/scenarios остаются blocked draft и не являются
input P0.3.

## Проверка

- Repo-grounding: пять direct roots перечислены явно; nested harness agent-pack commands
  исключены по boundary, а не по подгонке числа.
- Внешних фактов в remediation нет; web/RAG не требуется.
- Непроверенное → ПОВТОРНЫЙ ПРОХОД: фактический tree anchor и raw path set будут созданы
  P0.5 при исполнении; design не выдаёт будущий finding за уже существующее evidence.
- Обходки/[POSSIBLE-DEFECT]: numbering `P0.5` добавлен после исторических P0.1–P0.4, но
  roadmap и D52 задают фактический порядок `P0.1 → P0.5 → P0.2`; существующие IDs и journal
  provenance важнее косметической монотонности номера.
