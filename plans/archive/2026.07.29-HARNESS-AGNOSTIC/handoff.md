# HANDOFF — 2026-07-30 — after P5

**Next:** план закрыт — все шесть фаз (P0–P5) терминальны (все `🟠 Done with
deviations`, кроме P5.3-уровня внутри P5 которая `🟢`). Кандидаты вне протокола:
`/task:plan-audit 2026.07.29-HARNESS-AGNOSTIC P5` (фаза несёт два `🟠`), затем
`/task:plan-close archive 2026.07.29-HARNESS-AGNOSTIC`.

**Done:** P0 (5/5) · P1 (7/7) · P2 (9/9) · P3 (6/6) · P4 (5/5) · P5 (3/3) — все 35
items плана исполнены и закрыты. Фаза P5 закрыта этим заходом (`plan-close P5`):
таблицы Phase Status ↔ Status Board сведены (1 🟢 + 2 🟠 → фаза `🟠 Done with
deviations`), Phase Handoff заполнен агрегатом Known Deviations трёх items,
docs-sync — обновлено (см. Completion Notes P5.1). Все фазы плана теперь
терминальны → `plans/ACTIVE.md` сброшен на `—`, Status плана в `## 0. Meta` —
`🟠 Done with deviations`.

**Remaining:** items плана не осталось (35/35 исполнены, все шесть фаз терминальны).
Вне протокола: аудит фазы P5 (несёт два `🟠`), затем архивация плана
(`plan-close archive`). Решение о границе наружу (push/PR/тег/релиз) — вне плана.

## Итог плана

Ветка `next/harness-agnostic` слита в `main` локальным `--no-ff` merge (`56eae069`,
102 коммита, 5 фаз). Контур переустановлен из основного дерева. Инвариант М10
подтверждён дельтой парного прогона (`artifacts/P5.3-fleet-delta.md`) — 0
расхождений сверх ожидаемых codex-апгрейдов P2/P4. Изоляция снята: worktree и
временный bin-dir удалены, ветка-якорь `next/harness-agnostic` сохранена (D46).
Граница наружу (`push`/PR/тег/релиз/публикация доков) не пересекалась ни разу —
`main` несёт результат плана только локально.

## Карты «item → коммит»

- **P2:** P2.1 `ed306ca6` · P2.2 `632e75d3`(+`ad325a5e`) · P2.3 `c97e5cfb`(+`3e883a68`) ·
  P2.4 `cf1498a1`(+`966d7764`) · P2.5 `fa826d47` · P2.6 `317622c0`+`23c1090c` · P2.7 `e16082a1` ·
  P2.8 `a264a339` · P2.9 `ffda7173`.
- **P3:** P3.1 `f61ac378` · P3.2 `dd6a1404` · P3.3 `41f2156b` · P3.4 `599878e0` ·
  P3.5 `1373fccf` · P3.6 — без item-коммита (законный исход «покрыто существующим скиллом»).
- **P4:** P4.1 `7ed90cd0` · P4.2 `4d70e7a1` · P4.3 `95ab0492` · P4.4 `c20d40af`(+`65343d45`) ·
  P4.5 `58845143`.
- **P5:** P5.1 — `e42cd412`, `11fbf79e`, `485b9702`, `fab160fc`, `503dc68d` (в ветке) ·
  P5.2 — `56eae069` (merge) + `44864fec` (носитель) · P5.3 — `e50c1e7b` (артефакт дельты)
  + `95663990` (факты снятия изоляции), все в `main`, в ОСНОВНОМ дереве.

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D94, §6 Update Log, §4 Status
Board — все фазы терминальны) · `phases/P5.md` (Phase Handoff, Completion Notes
P5.1/P5.2/P5.3) · `artifacts/P5.3-fleet-delta.md` (дельта, вердикт М10, раздел «НЕ
раскатано») · `artifacts/P5.1-fleet-baseline/` (снимок «ДО») ·
`root/isolation-procedure.md` (§«Возврат в основное дерево», §«Снятие worktree и
откат») · `research/09-p5-return-and-fleet-acceptance.md` ·
`findings/06-rag-fleet-propagation-and-merge-2026-07-29.md` (Ф23–Ф25) ·
`root/contracts/provider-parity-definition.md` · `docs/provider-support.md`
§«Security and operations» · `install.sh` · `roadmap.md` · `journal.jsonl`.

## Open risks

- **`main` слит локально и НЕ отправлен наружу.** Откат стоит одной команды
  (`git reset --hard 8e16a811` в основном дереве) ровно до первого `push`. Второй,
  независимый от reflog якорь — сохранённая ветка `next/harness-agnostic` (D46). Push/PR/тег
  — гейт владельца, вне плана.
- **Раскатка на потребителей не выполнялась** (D45): скиллы connect-канала живут кэшем
  плагинов (auto-update локального marketplace выключен), vendor-копии и agent-packs
  обновляются своими командами. Поимённый перечень с командами —
  `artifacts/P5.3-fleet-delta.md` §5; три из четырёх проверенных целей уже показывают
  `failed`-провизионеры именно по этой причине (ожидаемое состояние, не дефект).
- **Ruff (`0.15.19`, `F,B`) и python-матрица 3.9–3.13 локально не прогонялись** ни на одном
  из трёх items P5 — полную картину даст только push/CI (R2; формула «CI зелёный» не
  употребляется).
- **Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрывался** (D4, OQ-5 Deferred) —
  P5.3 предъявил замером, что он волну изменений пережил (0 расхождений `projects status`,
  mtime не сдвинулись). Риск снят фактически, решение об изоляции остаётся отложенным.
- **`plan-lint`: 0 ERROR / 8 WARN** — счёт не изменился ни на единицу с пред-мердж дерева
  ветки; все восемь — false positive предикатов линтера (см. `phases/P4.md` Completion Notes
  P4.1). Сужение предикатов — правка `packages/task`, дом `roadmap/` либо follow-up fix-item.
- **`verify-citations.py --strict`: 8 остаточных находок**, все в `phases/P1.md`/
  `phases/P4.md`/`plan.md` (поля закрытых items P1/P4), новых от диффа фазы P5: 0 — вне Scope,
  кандидат на follow-up-заход.
- **Три untracked-пути в основном дереве** (`.swissknife/`, `audits/`,
  `packages/task/lib/.claude/`) — `git add -A` утащил бы их незамеченными;
  коммитить только плановые пути.
- **Схема парсера НЕ починена — починен только статус документа.** `driver-plan-protocol.md`
  после P4.5 объявлен историческим, но §1–§6 остаются описанием канона v2.8.0; строитель
  обвязки обязан переиздать parse-подмножество против канона своего дня
  (`roadmap/artifex-thin-wrapper.md` §Ограничения). Цена — `Consequences` D93.
- **«Чем парсится прогон Codex» — открытый вопрос без дома в этом плане** (`[UNVERIFIED]`).
- **Delegation contract доказуемо приземлён только для провайдер-нейтрального канона и
  Claude-шаблона; Codex-хост НЕ покрыт** (D92, §5.5) — записан `limitations[1]` каталога
  capability и §3.12 `root/contracts/codex-parity-verdicts-v1.md`.
- **`decide` не является живой зависимостью** (замер P4.1): формулировка «потребляем
  `decide`» обязана нести `[UNVERIFIED]` (D91).
- **Приёмка AR формально не выполнена** (его D88/D89/D92): `F1 = 0.96`, `F10 = unknown`,
  26/31 кейсов `unmappable`, Codex-сторона наблюдаемости не пробовалась.
- **69 длинных описаний без триггера** в `desc-trigger-burndown.txt` (долг P3.5).
- **Структурный перебор фолбэк-бюджета обнаружения Codex** (9/10 профилей) — решение
  владельца не выбрано (OQ-7, D29).
- **Таблица «Внешние источники, всплывшие в аудитах»** в `references/framework-audits.md` не
  пополнена — кандидат на добор.
- **path-scoped rules — индекс правил в hub не заведён** (P3.1) — кандидат `roadmap/`.
- **Verification-контракты паков — разрыв 4/10 / 1/10 / 6/10** — измерен в ledger'е P3.2,
  кодом не закрыт; дом — `roadmap/`.
- **CLI-обвязка `harness doctor --settings --provider codex` не заведена** (P2.4).
- **Декларативный merge-режим `harness hooks --provider codex` /
  `harness agent-packs --provider codex render`** — кандидат `roadmap/`.
- **Точная схема пейлоада Codex `apply_patch`** за пределами `tool_name` — `[UNVERIFIED]`.
- **`phases/P1.md` несёт два остаточных вхождения фразы A7** — историческое свидетельство.
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`instructions.py:1005-1022`) — `roadmap/`.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — не заведён.
- **Order-sensitivity `apply_instructions`** — дом заведён P2.8, реализация отложена (D84).
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков запрещена.
- **Гейт `[10/10]` живёт только в `packages/harness/scripts/validate.sh`** — OQ-9.
- **`vitepress build` в дереве не прогоняется** — `node_modules` отсутствуют.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47).

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит. · Доказательство §16/§17 `validate.sh` изолированным раннером — вынужденная
  форма. · P5.1 починил пять пре-существующих/P2-производных красных гейтов сайд-патчем вне
  `Files` item'а по явному решению owner. · P5.2 прошёл предусловие «дерево чистое» при трёх
  untracked-путях по явному решению owner. · P5.3 удалил временный bin-dir через
  `find … -delete` вместо `rm -rf` — последний заблокирован политикой окружения
  (`deny_hard`); предмет и результат тождественны, отклонение названо в процедуре.
- deferred: **весь остаток супервизора — ОДИН адрес `roadmap/artifex-thin-wrapper.md`**
  (каркас пакета · ядро цикла · retry-лестница · run-folder · unattended-профиль ·
  поведенческий канон · каналы TG/MAX + remote-approve · репортинг в mAInd · пак раскатки ·
  документация · боевой пилот) · замер формата транскрипта Codex · opt-in флаг Claude-половины
  `git-guardrails` · проекция `writable_roots` из allowlist'а · правка
  `_validate_conflicts`/схемы `obligations` · order-sensitivity `apply_instructions` (P2.8) ·
  фикстурный `provenance` P1.2 · изоляция общего state (OQ-5) · round-trip гейт живым прогоном
  Codex (D3) · структурный перебор листинга Codex (OQ-7) · общий differ канона ролей (OQ-8) ·
  машинные гейты PROMOTE-CANDIDATE · раскатка на потребителей (D45) ·
  push/PR/тег и публикация доков (D41) · расширение CI на `analyst`/`task` (OQ-9) ·
  русский канон скиллов в `.gitignore` (Р5) · раскатка adoption-режима · удаление pre-image'ов
  P1.5 · починка архивных упоминаний A7 · декларативный merge-режим `harness hooks --provider
  codex` (P2.3) и `harness agent-packs --provider codex render` (P2.4) · точная схема Codex
  `apply_patch` (P2.3) · отдельный machine-owned `check_command` для Codex `review-gate` (P2.3) ·
  CLI-флаг `harness doctor --settings --provider codex` (P2.4) · индекс `path-scoped rules`
  (P3.1) · унификация verification-контрактов паков 4/10→10/10 (P3.2) · добор таблицы внешних
  источников (P3.3) · сокращение 69 длинных описаний (P3.5) · перевод прозы «кап делегирования»
  на ссылку к SSOT `execution-policy-v1.md` (P4.2) · рычаг №4 владельца (ECO-OPT D74, OQ-7) ·
  Codex-досягаемость delegation contract (D92) · общий differ «канон ↔ инсталляционный
  шаблон» (OQ-8) · ruff+python-матрица CI не воспроизведены локально (R2).
- open_questions: OQ-7 структурный перебор бюджета обнаружения Codex — измерен P3.4/P3.5
  (9/10), решение между тремя вариантами открыто · OQ-8 дрейф канона ролей (Deferred) ·
  OQ-9 CI не покрывает `analyst`/`task` (Deferred) · OQ-5 изоляция общего state (Deferred) —
  действовала на P5.3, риск снят замером, решение остаётся отложенным. OQ-2 закрыта полностью
  (D71 + D93/D94, исполнено P4.5); OQ-3/OQ-6 — D86/D87 (P2.1); OQ-1 — D31; OQ-4 — P3.4/D27.
