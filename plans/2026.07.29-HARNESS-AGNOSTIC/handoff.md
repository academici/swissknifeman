# HANDOFF — 2026-07-30 — after P2.4

**Next:** `/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P2.5`

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — §3 Routing строка P2.5 (`implementation/medium`, `Exec = plan-exec`) |
| Context | continue (/clear) — ручной item |
| Суть | P2.5 — регенерация доков, конформанс-артефакт фазы и машинный гейт от дрейфа provider-доков (замыкает фазу P2) |

````
/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P2.5
````

**Что сделано этим заходом (ручной прогон, implementation/high, `task:plan-run`).** P2.4
закрыт `🟠 Done with deviations` (item-коммит `cf1498a1`, follow-up-коммит `966d7764`). Два
bounded-closure адаптера класса C реализованы по вердикту P2.1 (D89 §6,
`codex-parity-verdicts-v1.md` §3.11–§3.12): `settings.audit` (свой Codex-специфичный
check-set над документированными слоями `~/.codex/config.toml`→`.codex/config.toml`,
`features.hooks`, fail-soft на интерпретаторе <3.11, `settings_audit.py`) и
`agent-packs.lifecycle` (render/check/remove/diagnose над `.codex/agents/*.toml` через
существующие `project_agent_role`/`plan_agent_artifact`/`classify_agent_projection`, роли
`command.workflow-carrier` исключены поимённо, свой `.codex/agent-roles.lock.json`, CLI
`harness agent-packs render|remove|doctor --provider codex`, `agentpacks.py`). Уровни обеих
записей подняты `unsupported`→`adapted` синхронно с реализацией. Пять оставшихся
`unsupported`-записей (`lifecycle.notification`/`workflows.status`/
`analytics.legacy-migration`/`context.output-style`/`context.plans-directory`) приведены к
честной причинной форме (§3.13–§3.17): `limitations` называют класс причины, `evidence`
ссылается на `codex-parity-verdicts-v1.md` с `verified_at: 2026-07-30`. 17 новых тестов (8 +
9) + 1 скорректированная assertion `test_provider_conformance.py`.

**Session:** Claude Sonnet 5/high (implementation/high, `Exec = manual` — совпадает с §3
Routing строкой P2.4, перебора/недобора нет).

**Done:** P0 целиком (5/5) · P1 целиком (7/7) · блок follow-up P2.6–P2.9 (4/4) · P2.1 `🟢` ·
P2.2 `🟠` · P2.3 `🟠` · **P2.4 `🟠` — два bounded-closure адаптера (settings.audit,
agent-packs.lifecycle), пять честных unsupported-записей.**

**Карта «item → коммит» (P1–P2; item-коммит | сопутствующие bookkeeping):**
P1.1 `fd5183af` | `340d0846` · P1.2 `e574fdda` | `d1e393af` · P1.3 `b02e48be` | `4ae56350`
(bookkeeping), `5996d92d` (дозапись журнала), `b191a19c` (Known Deviations) · P1.4 `1e0262a4` |
`d5482b37` · P1.5 `c3b3a8a3` (принятие) + `4647ad4b` (гейт) | `d052698f` · P1.6 `d5e01ef7`
(канон+рендер) + `eb64ea6c` (гейт покрытия) | `4416322e` · P1.7 `003180bf` | `a8abbf9e`,
`7d4f12b7` · P2.6 `317622c0` + `23c1090c` (item-коммит) · P2.7 `e16082a1` · P2.8 `a264a339` ·
P2.9 `ffda7173` · P2.1 `ed306ca6` · P2.2 `632e75d3` (диспетчер+наблюдатели, item-коммит) +
`ad325a5e` (follow-up: регенерация двух provider-audit артефактов + golden-хеш
test-provider-docs.py, вне Files) · P2.3 `c97e5cfb` (шесть гейтов класса B, item-коммит) +
`3e883a68` (follow-up: регенерация двух provider-audit артефактов + golden-хеш
test-provider-docs.py + одна evidence-фикстура test_provider_conformance.py, вне Files) ·
**P2.4 `cf1498a1` (два bounded-closure адаптера + честная форма пяти записей, item-коммит) +
`966d7764` (follow-up: та же регенерация, тот же класс дрейфа, вне Files)**.

**Remaining:** P2.5 (1) → P3 (6) → P4 (5) → P5 (3). Итого **15 из 35** items плана ещё не
исполнено.

**Sources of truth:** `root/contracts/codex-parity-verdicts-v1.md` (**sealed v1** — §3.5–§3.12
уже закрыты P2.2–P2.4) · `root/contracts/provider-parity-definition.md` (**sealed v1**) ·
`plan.md` (§3 Routing, §5 D1–D89, §6 Update Log с картой хешей, §4 Status Board — P2 `4/9 🟡`
(счёт только `🟢`; P2.1/P2.6–P2.8 — четыре; P2.2/P2.3/P2.4/P2.9 закрыты `🟠`)) · `phases/P2.md`
(P2.1–P2.4 Completion Notes — прогоны и числа; P2.5 ТЗ) · `configs/provider-capabilities.json`
(12 записей класса A+B/C теперь `adapted` у Codex, плюс `lifecycle.daemon-safety` у Claude; 5
`claude-only` из 17 Codex-овых честно оформлены, минус 2 both-provider уже закрытых) ·
`roadmap.md` (v0.10.0, 35 items) · `journal.jsonl`.

**Open risks:**
- **Golden-хеш `scripts/test-provider-docs.py` и два сгенерированных provider-audit артефакта
  (`packages/harness/docs/reference/provider-harness.md`,
  `plans/archive/2026.07.19-DUAL-PROVIDER/artifacts/P5-harness-conformance.md`) дрейфуют при
  КАЖДОМ подъёме уровня capability** — P2.2/P2.3/P2.4 их регенерировали (Known Deviation, диф
  вне `Files`); P2.5 замыкает эту петлю МАШИННЫМ гейтом от дрейфа (Deliverables item'а), после
  чего эта строка снимается.
- **CLI-обвязка `harness doctor --settings --provider codex` не заведена** (P2.4 Pending Work
  (1)): владелец роутинга settings.audit (`doctor.py`) вне `Files` P2.4; движок настоящий,
  покрыт 8 тестами напрямую. Дом — follow-up item или `roadmap/`.
- **Декларативный (не инкрементальный) CLI `harness hooks --provider codex`** (заведён P2.3),
  тот же приём унаследован `harness agent-packs --provider codex render` (P2.4): оператор
  обязан перечислять ВСЕ желаемые поверхности/паки при каждом вызове; merge-режим — кандидат
  `roadmap/`.
- **Точная схема пейлоада Codex `apply_patch`** за пределами `tool_name` — `[UNVERIFIED]`
  (`findings/03`); носитель — `roadmap/`.
- **`plan-lint` WARN нового рода на `phases/P2.md`** (сохраняется, K=0 не задет): DoR-чеклист
  фазы цитирует синтаксис маркера уточнения дословно.
- **Посторонний незакоммиченный дифф в дереве не убран и не тронут:** `roadmap/README.md` (M) +
  untracked `roadmap/2026.07.29-launch-block-command-row.md`. Живучесть подтверждена седьмой
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
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ** (долг P0.5); `scripts/test-provider-docs.py`
  несёт один ПРЕДСУЩЕСТВУЮЩИЙ красный (`test_internal_markdown_links_resolve...` — битая ссылка
  `roadmap/self-learning-memory.md`, `provider-parity-definition` §6.3, не регрессия P2.x);
  `scripts/public-hygiene.py` — предсуществующе красный.
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
  (заведён P2.3) · CLI-флаг `harness doctor --settings --provider codex` (заведён P2.4).
  **Снято из deferred:** ничего (P2.4 долгов не закрывал, только назвал новые).
- open_questions: OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф канона ролей
  (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-3/OQ-6 закрыты D86/D87 (P2.1);
  OQ-2 закрыта D71, OQ-1 — D31, OQ-4 — D27. Новых открытых вопросов P2.4 не добавил.
