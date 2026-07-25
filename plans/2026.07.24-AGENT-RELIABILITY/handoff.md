# HANDOFF — 2026-07-25 — after P1.1

**Committed item tree: `628092b3`** (завершающий item-коммит; собран двумя атомарными
коммитами — `1ba0b4e0` запечатал 11 файлов ТЗ, `628092b3` покрыл hook identities, названные
в Scope Included/Intent, но пропущенные первым проходом). Этот файл коммитится следом
бухгалтерией; собственный хеш в него не вписывается.

**P1.1 закрыт `🟢 Done`.** Заморожены два контракта — `semantic-identity-ownership-v1.md`
(оба инварианта дословно) и `generated-artifact-version-v1.md` (ledger + baseline-carrier
D36 + diff-scope guard с foreign-commit атрибуцией D47). Детекция коллизий стала
**repo-derived и холодной** (D44) вместо диффа против прозаического before-state: Codex —
20 worst-case коллизий (17 `root-vs-unit`, 9 `unit-vs-unit`), Claude Code — 9; под
объявленным enabled-литералом `findings/12` — 16 `root↔installed` + 1 `installed↔installed`
и 14 уникальных root-carriers, то есть D40 воспроизведён счётом, а не пересказан. Все 29
измеренных коллизий обоих провайдеров имеют owner-item; class-A карта 13 identity / 26
проекций проходит acceptance D38. Детали и команды — `phases/P1.md` P1.1 Completion Notes.

**Коммит-гигиена, живое предупреждение (не изменилось).** Рабочее дерево несёт чужой дифф
параллельного процесса, **в том числе 12 записей в индексе** (`roadmap/*.md` удаления,
`packages/harness/lib/harness/agentpacks.py`, `test_agentpacks.py`,
`test_settings_audit_fieldcase.py`, `packages/skiller/skills.json`, `docs/*`, архивные
`plans/*`). Оба коммита этого item'а сделаны формой `git commit … -- <пути>`, поэтому чужое
содержимое осталось ровно там же и в том же виде. Каждое закрытие в этом дереве обязано
использовать pathspec-форму; stash/revert/reset чужих правок запрещены.

**Next:** P1.2 — 13 приватных канонических skill-источников + root/core publication.
Routing (`plan.md` §3): `implementation/high` / `manual` / `Review=full` — выше пина
`plan-exec` (`sonnet/medium`), поэтому routing-гейт обязан отклонить запуск
`/task:plan-exec`. Форма — **ЗАПУСК ВРУЧНУЮ** (эквивалент: `/model sonnet` + `/effort high`
+ `/task:plan-run`). `roadmap.md` числит P1.2 как `solo` — это одиночный запуск, не группа.

| Параметр | Значение |
|:--|:--|
| Model | sonnet (`implementation` по §3 Routing; renderer-таблица roadmap, D33) |
| Thinking | high — публикационная мутация, correctness-critical |
| Capabilities | `command.subagents` |
| Context | `continue (/clear) — ручной item` |
| Суть | Создать 13 приватных двуязычных канонов, заменить рукописные root-копии генерируемыми тонкими проекциями (26 целей + lock), поднять skiller/core/skm до 0.4.1 и root-bootstrap до 0.1.0, удалить шесть core-коллизий root после доказательства бандла |

````
РЕЖИМ: task:plan-run 2026.07.24-AGENT-RELIABILITY P1.2 (Routing = manual, implementation/high; НЕ plan-exec — тот пинит sonnet/medium и по гейту протокола обязан отклонить этот item).
ВХОД: plans/2026.07.24-AGENT-RELIABILITY/plan.md → handoff.md → phases/P1.md Phase Context + P1.2 целиком → Required Reads P1.2 (48 пунктов, порядок как в ТЗ).
ПРЕДУСЛОВИЕ: P1.1 закрыт 🟢 на item-коммите `628092b3` — сверить по `phases/P1.md` Phase Status ДО любой мутации; контракты `root/contracts/semantic-identity-ownership-v1.md` и `generated-artifact-version-v1.md` и карты `artifacts/P1.1/{remediation-map.json,repository-bootstrap-map.json}` — замороженный вход, не переизобретать.
ПОРЯДОК (шаг 0 первым, до любой другой owned-записи): `python3 plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.1/assert_generated_scope.py baseline --repo . --owner P1.2 --scope-map plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.1/remediation-map.json --baseline-file plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.2/base-sha.txt --capture-or-verify`; при resume байты переиспользуются, перезапись запрещена; ITEM_BASE_SHA берётся ТОЛЬКО через `baseline --verify-and-print`.
СКОУП: строго Scope Included P1.2 — 13 приватных `SKILL.ru.md` из запиненных seed'ов (карта называет claude-seed для 10 расходящихся пар и причину), EN-каноны штатным промтом + `check-translations.sh --stamp`, приватный source-only бакет `repository-bootstrap`, version-first (skiller/core/skm 0.4.1, root-bootstrap 0.1.0), 26 тонких проекций + один combined lock ТОЛЬКО через `registry.py`→`publication.py`, удаление ровно шести root core-коллизий ПОСЛЕ доказательства бандла.
НЕ ТРОГАТЬ: task-адаптеры команд (P1.3); четыре `architect` root-дубля, `workflow-craft` и детектор D42 (P1.5); user-owned enabled-множество провайдера; `skillset.py` как продюсер root (только consumer-исключение).
ЗАКРЫТИЕ: полный цикл 1–8 протокола — вся Validation P1.2 зелёная ДО item-коммита (включая `generated-scope` и `bash packages/skiller/scripts/validate.sh`), item-коммит ПО PATHSPEC, bookkeeping-коммит плановых путей, handoff.md с реальным хешем, plan-lint --baseline HEAD.
УЧЕСТЬ (измерено P1.1, не блокер): `packages/task/scripts/validate.sh` красный доitem-ным дефектом (устаревший путь в `packages/task/tests/test_provider_command_parity.py:25`) — это НЕ пакет P1.2 и чинится по Pending Work P1.1; висячие ссылки `templates/skills/<identity>/SKILL.md` у `ecosystem-mcp`/`ecosystem-setup` обязан разрешить этот item при авторинге канона, а не перенести в проекцию.
````

**Done:**
- `root/contracts/semantic-identity-ownership-v1.md` — детекция repo-derived/cold (D44),
  оба инварианта дословно (root-набор == declared target set; `core` ↔ донорские бакеты
  взаимоисключающи — диагностика, не запись профиля), класс A / класс B, hook identities,
  форма записи и запрет «`unknown` как зелёное».
- `root/contracts/generated-artifact-version-v1.md` — version-first/generator-closed,
  ledger из 15 бампов пяти owner-item'ов (каждое `From` прочитано из репо),
  baseline-carrier D36 и diff-scope guard с foreign-commit атрибуцией D47.
- `artifacts/P1.1/build_effective_inventory.py` — единственный владелец детекции, одного
  named read-only capture, генерации и обоих гейтов (`--check-bootstrap-map`,
  `--check-collision-owners`).
- `artifacts/P1.1/assert_generated_scope.py` — baseline `capture-or-verify` /
  `verify-and-print` + `generated-scope` (private-leakage, version-completeness,
  byte-identical guards, undeclared drift, foreign-commit атрибуция, no-op).
- `artifacts/P1.1/effective-runtime-before-state.json` — schema v1, Codex `read`
  (23 enabled, совпало с объявленным литералом), Claude Code `unknown`.
- `artifacts/P1.1/{effective-inventory,remediation-map,repository-bootstrap-map}.json` —
  472 identity-записи, 29 owner-записей коллизий, 13/26 class-A.
- `findings/P1.1-capability-gaps.md` — 3 capability-пробела по литералам носителя,
  5 identity с неразрешёнными ссылками, 21 недекларированный файл root-поверхности,
  hook-ownership и провенанс `pinned-not-recomputable`.
- 92 фокусных теста (63 + 29), Validation 13/13 зелёная.

**Remaining:** 17/22 items `⬜` (плюс P0.4 `🟠`). Порядок фаз не изменился: P0 → P1
(**P1.2** → P1.3 → **P1.5** → P1.4, D41) → P2 → P3 → P4. Следующий — P1.2.

**Sources of truth:** `plan.md` v1.12.6 (§4 P1 1/5, §7 Contracts — обе строки
`committed P1.1`) · `phases/P1.md` (P1.1 Completion Notes/Pending Work) ·
`root/contracts/{semantic-identity-ownership-v1,generated-artifact-version-v1}.md` ·
`artifacts/P1.1/{remediation-map,repository-bootstrap-map,effective-inventory,
effective-runtime-before-state}.json` · `findings/P1.1-capability-gaps.md` · `journal.jsonl`.

**Open risks:**
- **`packages/task/scripts/validate.sh` красный — доitem-ный дефект, не мой дифф.**
  `packages/task/tests/test_provider_command_parity.py:25` держит путь
  `plans/2026.07.19-DUAL-PROVIDER/root/contracts/provider-command-routing-contract.md`,
  архивированный коммитом `5b79f926`. Доказано в чистом worktree на `HEAD` (те же 7 тестов,
  1 error). Класс тот же, что D61(3), который P0.4 закрыл только в `harness`. Владелец —
  P1.3 (пакет `task` в его Files) либо отдельный fix-item; P1.1 его не чинил, потому что
  его Scope Excluded прямо называет source fixes.
- **21 недекларированный файл в root-поверхности** (17 `agents/openai.yaml` — множество их
  каталогов равно РОВНО 17 Codex `root-vs-unit` identity; 4 `SKILL.md.bak`). 12 исчезнут
  вместе с каталогами удалений P1.2/P1.3; остаток обязан закрыть гейт полноты P1.5.
- **`command.interactive-user-input` отсутствует в каталоге capability**, при том что
  `task:design` спелит `AskUserQuestion`; добавление публичного id идёт по D23
  (proposal/ADR/SemVer), владелец — P1.3.
- **Claude enabled-set остаётся `unknown`** (объявленной read-only команды нет) — прежний
  названный долг `plan.md` §10; на repo-derived worst-case это не влияет по построению.
- `plan-lint` держит 1 WARN «phase-first: P0 ещё не терминальна» — статус ФАЗЫ P0
  остаётся `🟡` (все её items терминальны, закрытие фазы — отдельный шаг `plan-close`).
- Прежний долг без изменений: три находки A2; A1 F11; Claude-проекция `workflow-craft`;
  read-only измерение Claude enabled-set; несоответствие провенанса harness-CLI ↔
  maind-адаптера (из P0.4).
- `plans/README.md` § «Очередь планов» по-прежнему показывает устаревший счётчик item'ов
  этого плана — вне Files/carve-out этого item'а, не трогалось.

**Workarounds/Deferred/Open questions:**
- workarounds: —;
- deferred: расхождение провенанса harness-CLI ↔ maind-адаптера (из P0.4, владельца-item
  нет); добавление capability id `command.interactive-user-input` (требует D23-гейта);
- open_questions: —.
