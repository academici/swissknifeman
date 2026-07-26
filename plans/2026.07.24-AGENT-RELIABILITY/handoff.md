# HANDOFF — 2026-07-26 — after P3.9

**Next:** ЗАПУСК ВРУЧНУЮ: implementation/high (Exec = manual, `plan-exec` пинит sonnet/medium ниже предписанного и обязан отклонить этот item по гейту п. 2)

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `sonnet` (Claude) или `gpt-5.6-sol` (Codex) — по §3 Routing через checked mapping |
| Thinking | `high` — живые парные диспатчи, необратимая цена прогона, исполнение по закрытой карте P3.9 |
| Context | `NEW SESSION — Workflow-оркестрован` |
| Суть | Парный живой layer-2 прогон объявленного множества (5 кейсов) на кандидатном дереве против `PRE_PLAN_SHA 7479972f` → F6/F8/F9/F10 числом с точным знаменателем либо честным `unknown`; артефакты `artifacts/P3.10/layer2-paired.json` + `findings/P3.10-layer2-paired.md`. |

```
/model sonnet
/effort high
/task:plan-run 2026.07.24-AGENT-RELIABILITY P3.10
```

**Done:**

- **P3.9 закрыт 🟢 Done** (item-commit `a374c425`) — построен прибор и **измерено**, а не
  предположено, у скольких кейсов банка события вообще наблюдаемы из машинных артефактов.
  - **`5/31 mappable`** (2 critical: `route-undershoot-silent`, `trace-record-missing`;
    3 control: `honest-http-clean-control`, `control-committed-bundle-highrisk`,
    `control-predecessor-produced-path`), **31/88 ассершенов**. Наблюдаемы **10 из 20**
    типов событий карты и **2 из 22** outcome-путей (`declared_status`, `execution_inputs`).
    26 исключённых кейсов названы поимённо с причиной в `declared-case-set.json`.
  - **Ловушка `event_absent` измерена:** 19 из 23 отрицательных ассершенов банка лежат
    внутри исключённых кейсов — правило D83 «кейс без источника исключается ЦЕЛИКОМ»
    сняло 19/88 ≈ 21.6 % фальшиво-зелёного.
  - **`event-mapping-v1.json` — единственный носитель соответствий**; ни одна пара не
    зашита в код. Санитайзер выбрасывает прозу модели целиком, чем делает греп финального
    текста **структурно невозможным**, а не только запрещённым.
  - **2 живых диспатча** из разрешённых 3, только ради replay-фикстуры, в одноразовом
    detached worktree; оси запинены флагами по §3 Routing (`opus/high`, D46), фактическая
    модель подтверждена полем потока `system.init.model = claude-opus-5`. Суммарно
    **$0.532211**. Негативный replay краснеет по построению (перевёрнутое ожидание → exit 1).
  - `git worktree list --porcelain | grep -c 'skm-p3.9'` → **0** (проверено ПОСЛЕ уборки).
- **Items P3.1–P3.8 НЕ реопенены** — продукты пересчитаны P3.5, реконсилированы P3.6.

**Remaining:**

- **P3.10** ⬜ парный живой layer-2 прогон на `PRE_PLAN_SHA 7479972f` → F6/F8/F9/F10 —
  следующий шаг, `Exec = manual`, `implementation/high`. **Гейт входа выполнен:**
  `artifacts/P3.9/declared-case-set.json` закоммичен ДО прогона.
- **P3.11** ⬜ терминальный аудит фазы, **заход 2/2** — последний из бюджета.
- **P4** ⬜ — **не стартует до GREEN**.

**Sources of truth:**

- `findings/P3.9-mappability.md` — полный отчёт захода: почему число такое (классы причин),
  количественная ловушка `event_absent`, запись живых диспатчей, негативный тест, границы.
- `artifacts/P3.9/declared-case-set.json` — объявленный литералом состав множества layer-2
  (sha256 `b9184b589060c1bc…`, на `a374c425`); `event-mapping-v1.json` — карта наблюдения.
- `phases/P3.md` — `## Phase Status` (11 items), P3.9 Completion Notes/Pending Work/Known
  Deviations, ТЗ P3.10–P3.11, блок `## Audit P3 — 2026-07-26` (исторический, не правится).
- `plan.md` — §0 Meta (v1.20.0), §3 Routing, §4 Status Board (`4/11`), D80–D87, §6.

**Open risks:**

- **GREEN на объявленном множестве 5/31 недостижим без правки контракта приёмки.**
  Каждый floor F6/F8/F9/F10 обязан нести `scope: declared-subset 5/31` и не может быть
  объявлен `met`: D#-предложение формулирует P3.10, решение принимает P3.11. Тихое
  повышение `unknown` до `met` запрещено (D30). Дополнительно: 2 critical + 3 control —
  F6 («controlled bank») и F8 («весь банк») получат знаменатели разной природы.
- **Ложно-положительный `block`** из канала reason-кодов, если диспатч просто НАПЕЧАТАЕТ
  литерал кода (греп по исходникам). Направление fail-safe (лишний `block` валит
  контрольный кейс), но P3.10 обязан это учитывать при чтении своих чисел.
- **`handoff_emitted`** — единственный из 10 наблюдаемых типов, не произведённый живой
  фикстурой; его правило проверено только статически.
- **`contract_ref`/`finding_refs` не заполняются P3.4-харнесом** (находка P3.8) — остаток
  F1; носитель не назван. Живая фикстура P3.9 показала, что канал `analyst.trace` СПОСОБЕН
  дать `completeness = 1.0`, значит остаток — в инструментовке P3.4, а не в схеме.
- **Живая цена P3.10** не экстраполируется с $0.53 двух smoke-вызовов: там пара деревьев ×
  объявленное множество. Бюджет и стоп-правило объявлены в ТЗ; превышение — стоп с записью.
- **`verify_result_manifest.py` self-hash re-drift** (D87) — ожидаемо, не новая находка.
- **Остаточный lint вне диффа:** `plan-lint` — 0 ERROR при 1 WARN (строка Update Log P1.4,
  303 символа при пороге 300), открыт с предыдущих handoff'ов.
- **`analyst`/`harness` package-API minor bumps** (`0.1.0`→`0.2.0`, `0.3.0`→`0.4.0`) и
  CLI-подключение `analyst metrics` / `skiller eval` — долги с P3.1/P3.2/P3.3.
- **P0 phase-index row** (`task:plan-close … P0`) — все items P0 терминальны, строка доски
  остаётся `🟡`; открыто с ранних handoff'ов.

**Workarounds / Deferred / Open questions:**

- **Пустой каталог-родитель одноразового worktree** (`/tmp/skm-p3.9.rYq0Th`, 0 записей)
  остался на диске: `rmdir` жёстко запрещён локальным хуком вне `safe-dirs.json`.
  Регистраций `skm-p3.9` — 0; тот же класс остатка, что раскрыл P3.4.
- **Литерал Validation `… | grep -c 'skm-p3.9'`** печатает требуемый `0`, но `grep -c`
  при нуле совпадений выходит с кодом 1; фикс-предложение для будущих items —
  `test "$(… | grep -c 'skm-p3.9' || true)" = 0`.
- **Codex-сторона наблюдаемости не пробовалась** (acting provider — Claude, D33/D50);
  карта Codex-специфичных правил не несёт. Паритет — предмет `provider_capability_matrix`.
- **Строгий канал компилятора** (структурный артефакт вывода вместо литерального грепа
  `tool_result`) — назван кандидатом для отдельного item'а, здесь не расширялся.
- **`docs-sync` follow-up** (`packages/task/CLAUDE.md`, описание compiler/enforcement seam) —
  долг P3.1, не тронут.
- **Валидационная self-reference P3.6** (см. Known Deviations item'а) — предложенный фикс
  не сделан, чтобы не расширять правку сверх Scope.
