# HANDOFF — 2026-07-30 — after P2.5

**Next:** `/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P3.1`

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — §3 Routing строка P3.1 (`implementation/medium`, `Exec = plan-exec`) |
| Context | continue (/clear) — ручной item |
| Суть | P3.1 — сверить канон каркаса против дерева и первоисточника (открывает фазу P3, батч B3 расформирован D53 — item solo) |

````
/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P3.1
````

**Что сделано этим заходом (`task:plan-exec`, Sonnet/medium — пин команды, совпадает с §3
Routing строкой P2.5).** Перед стартом обнаружено и починено расхождение: `Home` в `## 0. Meta`
указывал на репо-донор `swissknifeman` (стоит на `main`, ветки `next/harness-agnostic` не
видит), хотя вся история P0–P2.4 плана лежит в worktree `swissknifeman-next` — правлено
(коммит `975f7808`, до старта item'а). P2.5 закрыт `🟢` (item-коммит `fa826d47`): шаг гейта
`provider-docs` в `.github/workflows/hygiene.yml` (`test-provider-docs.py -v` +
`provider-docs.py --check`, без ослабления) и артефакт
`artifacts/P2-codex-parity-conformance.md` — 35 capability до/после фазы неизменны, 17
вердиктов вердикт-контракта (12 `closed-by-adapter` сверены программно с манифестом — 0
расхождений `adapter_id`/`level`; 5 `claude-only` с непустым `limitations`; 0
`intent-withdrawn`). Попутно найден и починен предсуществующий красный
`test-provider-docs.py` (дохлая ссылка `README.md:122` на архивированный
`roadmap/self-learning-memory.md`, commit `9b057723`) — без починки сам добавляемый гейт
немедленно краснел бы в CI. **Фаза P2 закрывается этим item'ом: 5/9 (P2.1/P2.5–P2.8 `🟢`;
P2.2/P2.3/P2.4/P2.9 `🟠`), все девять items терминальны.**

**Session:** Claude Sonnet 5/medium (implementation/medium, `Exec = plan-exec` — совпадает с §3
Routing строкой P2.5, перебора/недобора нет).

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · **P2 целиком (9/9 — 5 🟢 + 4 🟠, все items
терминальны).**

**Карта «item → коммит» (P2, продолжение — P2.5):**
P2.5 `fa826d47` (item-коммит, единственный — Files включал только README.md/hygiene.yml/новый
артефакт; `configs/provider-capabilities.json`/`docs/provider-support.md` не изменились от
`--write`).

**Remaining:** Фаза P2 не закрыта формально (`plan-close Pn` реконсиляция — не входит в этот
заход plan-exec одного item'а) → затем P3 (6) → P4 (5) → P5 (3). Итого **14 из 35** items
плана ещё не исполнено (плюс формальное закрытие фазы P2).

**Sources of truth:** `root/contracts/codex-parity-verdicts-v1.md` (**sealed v1** — все 17
записей закрыты P2.1–P2.5) · `root/contracts/provider-parity-definition.md` (**sealed v1**) ·
`plan.md` (§3 Routing, §5 D1–D89, §6 Update Log, §4 Status Board — P2 `5/9`, все items
терминальны) · `phases/P2.md` (P2.1–P2.5 Completion Notes) · `configs/provider-capabilities.json`
(35 capability: 12 Codex-адаптированных, 5 честных Codex-`unsupported`) ·
`artifacts/P2-codex-parity-conformance.md` (снимок «до/после» этой фазы) ·
`.github/workflows/hygiene.yml` (новый шаг `provider-docs`) · `roadmap.md` (v0.10.0, 35 items) ·
`journal.jsonl`.

**Open risks:**
- **Фаза P2 требует формального закрытия** (`plan-close 2026.07.29-HARNESS-AGNOSTIC P2` —
  реконсиляция девяти items, таблицы, Phase Handoff) — этим заходом НЕ сделано (вне скоупа
  одного item'а `plan-exec`).
- **CLI-обвязка `harness doctor --settings --provider codex` не заведена** (P2.4 Pending Work
  (1)): движок настоящий, покрыт тестами напрямую, роутинг вне `Files` P2.4. Дом — follow-up
  item или `roadmap/`.
- **Декларативный (не инкрементальный) CLI `harness hooks --provider codex` /
  `harness agent-packs --provider codex render`**: оператор обязан перечислять ВСЕ желаемые
  поверхности/паки при каждом вызове; merge-режим — кандидат `roadmap/`.
- **Точная схема пейлоада Codex `apply_patch`** за пределами `tool_name` — `[UNVERIFIED]`
  (`findings/03`); носитель — `roadmap/`.
- **`plan-lint` WARN — три штуки, все предсуществующие** (K=0 не задет): `NEEDS
  CLARIFICATION`-маркеры в DoR-прозе фаз P0/P1/P2 (не предмет закрытых items).
- **Посторонний незакоммиченный дифф в дереве не убран и не тронут:** `roadmap/README.md` (M) +
  untracked `roadmap/2026.07.29-launch-block-command-row.md`. Живучесть подтверждена восьмой
  заход подряд — не наш предмет.
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`instructions.py:1005-1022`) — дом правки
  `roadmap/`, спека не заведена.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — не заведён.
- **Order-sensitivity `apply_instructions`** — дом заведён P2.8 (`roadmap/instruction-authorize-order.md`),
  реализация отложена (D84).
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков между
  маркерами запрещена навсегда.
- **Гейт `[9/9]` живёт только в `packages/harness/scripts/validate.sh`** — `analyst`/`task` в CI
  не покрыты (OQ-9).
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ** (долг P0.5); `scripts/public-hygiene.py`
  — предсуществующе красный (не тронут этим item'ом).
- **`vitepress build` в дереве не прогоняется** — `node_modules` отсутствуют.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47) — строка
  `Session: <model>/<effort>` в отчёте и Update Log обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а.
- deferred: замер формата транскрипта Codex · opt-in флаг Claude-половины `git-guardrails` ·
  проекция `writable_roots` из allowlist'а · правка `_validate_conflicts`/схемы `obligations` ·
  починка order-sensitivity `apply_instructions` (дом заведён P2.8) · фикстурный `provenance`
  P1.2 · изоляция общего state (OQ-5) · тонкая обвязка супервизора (P4.1, D38) · round-trip гейт
  живым прогоном Codex (D3) · структурный перебор листинга Codex (OQ-7) · общий differ канона
  ролей (OQ-8) · машинные гейты PROMOTE-CANDIDATE · `skiller registry` не прогнан (P0.5) ·
  раскатка на потребителей (D45) · push/PR/тег и публикация доков (D41) · расширение CI на
  `analyst`/`task` (OQ-9) · русский канон скиллов в `.gitignore` (Р5) · раскатка adoption-режима ·
  удаление pre-image'ов P1.5 · починка архивных упоминаний A7 в `phases/P1.md` · декларативный
  merge-режим `harness hooks --provider codex` (заведён P2.3) · декларативный merge-режим
  `harness agent-packs --provider codex render` (заведён P2.4) · точная схема Codex
  `apply_patch` (заведён P2.3) · отдельный machine-owned `check_command` для Codex `review-gate`
  (заведён P2.3) · CLI-флаг `harness doctor --settings --provider codex` (заведён P2.4) ·
  формальное закрытие фазы P2 (`plan-close`).
  **Снято из deferred:** golden-хеш `test-provider-docs.py`/сгенерированные provider-audit
  артефакты — гейт `provider-docs` в `hygiene.yml` теперь ловит дрейф механически (P2.5).
- open_questions: OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф канона ролей
  (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-3/OQ-6 закрыты D86/D87 (P2.1);
  OQ-2 закрыта D71, OQ-1 — D31, OQ-4 — D27. Новых открытых вопросов P2.5 не добавил.
