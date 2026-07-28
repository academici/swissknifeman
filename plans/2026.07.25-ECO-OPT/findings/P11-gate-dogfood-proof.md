# P11.4 — dogfood-снимок целевого гейта на непочиненном дереве, 2026-07-28

**Слой 1 (сырьё), item P11.4.** Снято ПОСЛЕ P11.1–P11.3 (продукт фазы уже внутри
`plans/verify-citations.py`/`plan_lint.py`), ДО P11.5/P11.8 (починка ещё не началась) — предмет
доказательства, единственное окно, где корпус существует. Все числа ниже — прогон, не пересказ.

## §0. Якорь дерева

| Что | Значение |
|:--|:--|
| `git rev-parse --short HEAD` | `05181229` |
| `git status --porcelain` | `M plans/2026.07.25-ECO-OPT/journal.jsonl` · `M plans/2026.07.25-ECO-OPT/phases/P11.md` (обе правки — открытие ЭТОГО item'а: Status → 🟡, журнал-старт; продукт гейта не тронут) · `?? .swissknife/` · `?? packages/task/lib/.claude/` (унаследованная грязь, не этого захода) |
| Живых планов в `plans/` | 3 — `2026.07.18-FOREMAN`, `2026.07.24-AGENT-RELIABILITY`, `2026.07.25-ECO-OPT` |
| Дата снимка | 2026-07-28 |

## §1. Команды и вывод дословно

### 1.1. `python3 plans/verify-citations.py`

```
$ python3 plans/verify-citations.py > /tmp/dogfood-citations.txt; echo $?
0
```

```
Проверка ссылок-доказательств по 3 план(ам)

  2026.07.18-FOREMAN: цитат проверено 1 · находок 0
  2026.07.24-AGENT-RELIABILITY: цитат проверено 239 · находок 5
  2026.07.25-ECO-OPT: цитат проверено 388 · находок 47

Всего цитат: 628
Известных исключений в перечне: 0
Находок: 52

  plans/2026.07.24-AGENT-RELIABILITY/findings/P4.1-code-grounded-audit.md:90 → `run-report/_lib.py::_protected_sets` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.24-AGENT-RELIABILITY/phases/P2.md:77 → `commands/plan-exec.md:58` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.24-AGENT-RELIABILITY/plan.md:380 → `phases/P5.md:8-11` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.24-AGENT-RELIABILITY/plan.md:388 → `commands/plan-exec.md:58` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.24-AGENT-RELIABILITY/research/06-p2.1-contract-boundary.md:95 → `phases/P5.md:8-11` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/findings/P11-citation-gate-measurements.md:102 → `artifacts/P1.1/remediation-map.json::owners.P2.2` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/findings/P11-citation-gate-measurements.md:107 → `configs/core-policy.json::skills` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/findings/P4-cross-machine-facts.md:61 → `dist/index.mjs:20209-20221` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/findings/P4-cross-machine-facts.md:74 → `dist/index.mjs:15276` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/findings/P4-cross-machine-facts.md:89 → `dist/index.mjs:10177-10400` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/findings/P4-cross-machine-facts.md:216 → `provision/service.py:31-32` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/findings/P5-audit-closure-facts.md:47 → `packages/maind/lib/maind/doctor.py:180-300` — строка 300 вне диапазона 1..299
  plans/2026.07.25-ECO-OPT/findings/P6-context-hygiene-facts.md:263 → `quality/eval.py:42` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P10.md:441 → `core/tests/test_provider_config.py::TestProviderConfigResolution::test_negative_validation_matrix_covers_frozen_contract` — символ 'test_negative_validation_matrix_covers_frozen_contract' не найден в файле
  plans/2026.07.25-ECO-OPT/phases/P10.md:474 → `packages/skiller/lib/skiller/status.py:55-160` — строка 160 вне диапазона 1..156
  plans/2026.07.25-ECO-OPT/phases/P10.md:477 → `scripts/validate.sh:87-100` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P10.md:477 → `quality/eval.py:42` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P11.md:205 → `path/to/file.json::a.b.c` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P11.md:258 → `pkg/data.json::a.b` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P3.md:593 → `packages/skiller/lib/skiller/status.py:55-160` — строка 160 вне диапазона 1..156
  plans/2026.07.25-ECO-OPT/phases/P3.md:696 → `scripts/validate.sh:65` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P4.md:141 → `dist/index.mjs:10177-10400` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P4.md:262 → `dist/index.mjs:20209-20221` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P5.md:76 → `quality/eval.py:311-333` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P5.md:937 → `tests/test_codegraph.py::TestSchemaConnectivity` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P5.md:1154 → `serena/config/serena_config.py:341` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P5.md:1217 → `serena/config/serena_config.py:341` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P5.md:1266 → `serena/config/serena_config.py:341` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P5.md:1637 → `src/serena/config/serena_config.py:341` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/phases/P5.md:1780 → `serena/config/serena_config.py:341` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/plan.md:258 → `dist/index.mjs:20209-20221` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/plan.md:260 → `dist/index.mjs:10177-10400` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/plan.md:351 → `lib/harness/hooks.py::block_output_style` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/plan.md:351 → `scripts/apply-permissions.sh:52-110` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/plan.md:354 → `quality/eval.py:42` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/plan.md:406 → `phases/P1.md:80,118` — строка 118 вне диапазона 1..96
  plans/2026.07.25-ECO-OPT/plan.md:424 → `scripts/validate.sh:87-100` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/plan.md:425 → `lib/skiller/status.py:150` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/plan.md:425 → `packages/skiller/lib/skiller/status.py:55-160` — строка 160 вне диапазона 1..156
  plans/2026.07.25-ECO-OPT/plan.md:487 → `serena/config/serena_config.py:341` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/research/01-P2-opus5-revision-map.md:101 → `_common/pack.json:15` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/research/01-P2-opus5-revision-map.md:101 → `role-tech-lead/pack.json:64` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/research/05-P4-fact-classes.md:19 → `provision/deploy.py:137-140` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/research/05-P4-fact-classes.md:28 → `templates/health/memory-digest-hook.sh:14-15` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/research/11-P8-target-design.md:267 → `configs/core-policy.json::skills` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/research/12-P6-fact-classes.md:77 → `quality/eval.py:42-101` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/research/13-P6-target-design.md:216 → `quality/eval.py:42` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/research/15-P7-fact-classes.md:39 → `lib/harness/cli.py:18-28` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/research/16-P7-target-design.md:14 → `lib/harness/cli.py:18-28` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/research/17-P9-fact-classes.md:103 → `quality/eval.py:42` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/research/18-P9-target-design.md:23 → `lib/harness/hooks.py:91` — файл не найден ни от корня репо, ни от каталога плана
  plans/2026.07.25-ECO-OPT/roadmap.md:409 → `lib/skiller/config.py::load_profile` — файл не найден ни от корня репо, ни от каталога плана
```

### 1.2. `python3 plans/verify-citations.py --strict`

```
$ python3 plans/verify-citations.py --strict; echo $?
1
```
(тот же отчёт, что 1.1, exit-код переключён — находки есть, как и предписано на непочиненном дереве)

### 1.3. `python3 packages/task/scripts/plan-lint.py plans/2026.07.25-ECO-OPT`

```
$ python3 packages/task/scripts/plan-lint.py plans/2026.07.25-ECO-OPT; echo $?
0
```

```
WARN: plans/2026.07.25-ECO-OPT/plan.md:549: Update Log: запись «Что» 748 символов > 300 — канон: ≤2 строк + ссылка на Completion Notes, не пересказ
WARN: plans/2026.07.25-ECO-OPT/plan.md:551: Update Log: запись «Что» 514 символов > 300 — канон: ≤2 строк + ссылка на Completion Notes, не пересказ
WARN: plans/2026.07.25-ECO-OPT/plan.md:557: Update Log: запись «Что» 380 символов > 300 — канон: ≤2 строк + ссылка на Completion Notes, не пересказ
WARN: plans/2026.07.25-ECO-OPT/plan.md:561: Update Log: запись «Что» 366 символов > 300 — канон: ≤2 строк + ссылка на Completion Notes, не пересказ
WARN: plans/2026.07.25-ECO-OPT/plan.md:581: Update Log: запись «Что» 394 символов > 300 — канон: ≤2 строк + ссылка на Completion Notes, не пересказ
WARN: plans/2026.07.25-ECO-OPT/plan.md:583: Update Log: запись «Что» 332 символов > 300 — канон: ≤2 строк + ссылка на Completion Notes, не пересказ
WARN: plans/2026.07.25-ECO-OPT/plan.md:588: Update Log: запись «Что» 394 символов > 300 — канон: ≤2 строк + ссылка на Completion Notes, не пересказ
WARN: plans/2026.07.25-ECO-OPT/plan.md: нет 2026.07.25-ECO-OPT/index.md (карта файлов + провенанс findings/research→фаза, P1.2, опционален) — снипет snippets/index-template.md
WARN: plans/2026.07.25-ECO-OPT/phases/P2.md: item P2.1: execution input «/home/vostrikov/Vaults/Brain/40-AI/Workflow/CLAUDE/fable-5-prompting.md» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P2.md: item P2.1: execution input «/home/vostrikov/Vaults/Brain/40-AI/Workflow/CLAUDE/fable-5-prompting.md» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P2.md: item P2.1: execution input «/home/vostrikov/Vaults/Brain/40-AI/Workflow/CLAUDE/prompting.md» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P2.md: item P2.1: execution input «/home/vostrikov/Vaults/Brain/40-AI/Workflow/CLAUDE/prompting.md» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P2.md: item P2.1: execution input «/home/vostrikov/Vaults/Brain» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P3.md: item P3.1: execution input «~/.swissknifeman/projects.json» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P3.md: item P3.5: execution input «~/.swissknifeman/projects.json» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P3.md: item P3.5: execution input «/home/vostrikov/projects/flexcrm» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P4.md: item P4.1: execution input «/Scope/Context/Decision/Consequences» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P7.md: item P7.3: execution input «~/.claude/settings.json» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P7.md: item P7.3: execution input «~/.codex/hooks.json» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P9.md: item P9.1: execution input «~/.claude/hooks/review-gate/checks» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P9.md: item P9.2: execution input «/agents/reviewer.md» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P9.md: item P9.2: execution input «/rules/reviewer-overrides.md» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P9.md: item P9.2: execution input «/agents/reviewer.md» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P9.md: item P9.3: execution input «/evals/evals.json» — внешний путь (host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, plan-portability-v1.md)
WARN: plans/2026.07.25-ECO-OPT/phases/P2.md: фаза P2 заявляет оркестрацию (multi-agent/fan-out), но нет workflow-скрипта в `plans/2026.07.25-ECO-OPT/workflows/` — DoR §7 (D29)
plan-lint: OK (1 план(ов), 0 ошибок, 25 предупреждений)
```

**Факт, названный вслух:** на ЭТОМ дереве кросс-документный чек `handoff.md`↔доска (P11.3,
`_lint_handoff_board_113`) не выдаёт ни ERROR, ни WARNING по своему правилу — 0 расхождений
`Pn a/b`. Это НЕ означает, что гейт не работает: буквальная F8 (`P9 4/4` vs `2/4`) была снята
design-заходом на `899cab9b` и с тех пор ушла из `handoff.md` (P11.2 переписал файл целиком по
топологии закрытия item'а, ФАЙЛ, а не ЧИСЛО, поправлен); живой дефект ТОГО ЖЕ КЛАССА (P3 «1/6»
vs доска «0/6») машина нашла заново НА item-коммите P11.3 (`f9356837`, ДО его собственной
перезаписи handoff'а) — см. §3.

## §2. Разбивка находок по планам и причинам

| План | Находок |
|:--|--:|
| `2026.07.18-FOREMAN` | 0 |
| `2026.07.24-AGENT-RELIABILITY` | 5 |
| `2026.07.25-ECO-OPT` | 47 |
| **Всего** | **52** |

| Причина | Находок |
|:--|--:|
| файл не найден ни от корня репо, ни от каталога плана | 46 |
| строка вне диапазона | 5 |
| символ не найден | 1 |
| ключ JSON не найден | 0 |
| **Всего** | **52** |

Внутри «файл не найден» три цитаты ECO-OPT — самоссылка ТЗ P11.1/P11.2 на СОБСТВЕННЫЙ ПРИМЕР
формы (`phases/P11.md:205,258` — `path/to/file.json::a.b.c`, `pkg/data.json::a.b`) и уже
известные предсуществующие цитаты, разобранные в `findings/P11-citation-gate-measurements.md`
(`quality/eval.py:*`, `dist/index.mjs:*`, `serena/config/serena_config.py:341` — планы
несуществующих будущих файлов/переносов, разбор — Scope Excluded этого item'а, чинит P11.5).

## §3. Пойманные находки аудита P9

**F8** (`handoff.md` — «`P9 4/4`» против доски «`2/4`») — **поймана** кросс-документным чеком
P11.3. Буквальный литерал F8 на ТЕКУЩЕМ дереве не воспроизводится (снят design-заходом до начала
P11), поэтому цитируется фактическая диагностика, снятая P11.3 на item-коммите `f9356837`
(до его собственной перезаписи `handoff.md`, `phases/P11.md:437-440`, Completion Notes P11.3):

```
ERROR: plans/2026.07.25-ECO-OPT/handoff.md:44: handoff.md:44 говорит «P3 1/6», доска
«## 4. Phase Index & Status Board» несёт «P3 0/6» (расхождение)
```
(`plan-lint: ПРОВАЛ (1 план(ов), 1 ошибок, 25 предупреждений)`)

Это не буквальный токен F8 (`P9 4/4`/`2/4`), а **тот же класс дефекта**, найденный заново на
свежем handoff'е (P3, не P9) тем же гейтом — сильнее буквального совпадения, потому что не
архивный пример, а живое подтверждение класса в моменте между P11.1 и P11.3. Правило поймало
именно тот тип утверждения, который F8 называла: число в прозе `handoff.md` разошлось с доской
`plan.md` §4, и доска оказалась права. На ЭТОМ item-коммите (P11.4, `05181229`) чек молчит,
потому что перезапись `handoff.md` внутри закрытия P11.3 (обязательный шаг 3 topology, plan-
protocol §8) не повторила ложное утверждение в машинно-совпадающей форме `Pn a/b` — находка
никем не «починена ради лога», она перестала существовать как факт текста.

## §4. НЕ пойманные и почему

Поимённая сверка против `research/27-P11-citation-gate-target-design.md` §4 (взята дословно,
Required Reads item'а):

| Находка | Класс дефекта | Почему НЕ ловится |
|:--|:--|:--|
| **F1** (`findings/P9.4-review-stability-delta.md:108` — «`R` не упал НИ В ОДНОМ кейсе» против таблицы §6 того же файла) | семантическая ложность прозы про СОБСТВЕННУЮ таблицу документа | требует понимания смысла утверждения и пересчёта таблицы, а не резолва ссылки; ни `verify-citations.py`, ни `plan_lint.py` число прозы с числом таблицы не сверяют — этот класс фазой P11 сознательно не берётся (D130) |
| **F2** (`findings/P9.2-review-roles-drift.md:3-5,24,33,68` — описан отменённый носитель, ключей `review.*` нет) | упоминание файла/ключа БЕЗ формы цитаты | в тексте стоят голый путь `` `agent-packs/role-bindings.json` `` и голый ключ `` `review.skills` `` — ни одна из проверяемых форм (`path:line`/`path::symbol`/`path.json::key`); класс «голое path-упоминание» отклонён измерением D128 (Scope Excluded P11.1) — гейт вознаграждает цитирование в правильной форме, а не заменяет его |
| **F9** (`.gitignore:26-28` — ссылка на «D-запись в плане» без номера) | ссылка на решение без машинно-резолвимого якоря | ни одна из трёх механик P11.1–P11.3 не резолвит ссылки на D-записи; проверка вида «`D<номер>` существует в §5» тоже не поймала бы, потому что в тексте номера нет вовсе — отдельный класс (D-ссылки), в скоуп фазы не взят |

Этот класс дефекта («три из четырёх названных владельцем находок не ловятся») — честная
граница доказательства (D130), а не молчаливый пропуск: F1/F2/F9 названы вслух здесь и
повторяются в Completion Notes item'а/`handoff.md`.

## §5. Сравнение с «до» (measurements) и с симуляцией

| Метрика | «До» (144-гейт, `findings/P11-citation-gate-measurements.md` §1) | Симуляция «целевого» гейта (§6 того же финдинга) | Факт на этом дереве (P11.4) |
|:--|--:|--:|--:|
| Цитат проверено | 393 | 587 | **628** |
| Находок | 144 | 48 | **52** |
| Известных исключений | 0 | — | 0 |

**Анти-подгонка (честно, не подогнано под симуляцию):** факт расходится с design-симуляцией §6
(628 цитат / 52 находки против предсказанных 587 / 48). Направление совпадает — рост охвата,
падение находок относительно «до» — но точные числа выше предсказанных на 41 цитату и 4
находки. Правдоподобная причина: симуляция §6 снята на дереве `899cab9b`/`80547e71` design-
захода, тогда как этот прогон — на `05181229` (после P11.3, плюс собственная json-класс-
самоссылка `phases/P11.md:205,258`, добавленная P11.1/P11.2 в текст ТЗ, и WARN-строки,
накопленные в `plan.md` за время фазы). Расхождение НЕ разбирается по существу здесь (Scope
Excluded item'а — не оценка «много/мало находок» как основание менять гейт); факт зафиксирован,
разбор остаточного корпуса — предмет P11.5.

Рост доказан по обеим осям одновременно: охват +60% (393→628), находки −64% (144→52) — то же
направление, что заявляла симуляция, числа не совпали буквально.

## §6. Что доказано (четыре измеримых утверждения `research/27-…` §4)

1. **F8-класс найден машиной ДО починки** — да, кросс-документный чек P11.3 поймал живое
   расхождение прозы `handoff.md` против доски `plan.md` §4 на item-коммите `f9356837`
   (§3 выше); на текущем дереве P11.4 буквальный факт уже отсутствует (снят закрытием P11.3),
   но класс доказан фактической диагностикой, процитированной дословно.
2. **18 реальных находок расширенной поверхности** (из design-симуляции, слой 1 §2) — не
   верифицировано отдельным замером в этом item'е (Scope Excluded: item НЕ повторяет измерение
   поверхности слоя 1, только прогоняет готовый гейт); косвенное подтверждение — рост охвата
   393→628 цитат включает файлы вне `plan.md`/`phases/*.md` (findings/research/handoff),
   недоступные одношаговому гейту «до».
3. **Переход находок при росте охвата** — доказан фактом, не симуляцией: 144→**52** находок
   (−64%) при 393→**628** цитат (+60%). Направление симуляции подтверждено, точные числа
   разошлись (§5), расхождение названо, не скрыто.
4. **Находка json-класса при нуле ложных на `owners.P2.2`** — подтверждено: `owners.P2.2`
   (`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.1/remediation-map.json::owners.P2.2`)
   **не входит** в список находок §1 этого снимка (52 строки выше) — ключ резолвится, ложных
   срабатываний json-класса на этом дереве 0.
5. **F1/F2/F9 названы вслух как НЕ пойманные** — §4 выше, поимённо, с классом каждой.

**Вердикт: гейт доказан** — с честной оговоркой D130: доказан по переопределённому измеримому
корпусу (F8 + рост охвата/падение находок + json-класс без ложных), НЕ по буквальному «F1/F2/F8/
F9 все четыре». Формулировка «гейт доказан», умалчивающая, что три из четырёх названных
владельцем находок не ловятся, была бы дефектом (Code Guidance item'а) — этот вердикт её
не совершает.
