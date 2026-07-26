# HANDOFF — 2026-07-26 — after P2.9

**Next:** /task:plan-close 2026.07.24-AGENT-RELIABILITY P2

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `low` |
| Capabilities | `—` |
| Context | `NEW SESSION — шаг-не-item` |
| Model | Claude Sonnet 5 |
| Thinking | `low` |
| Суть | Все шесть items реопена (P2.6–P2.11) терминальны — снять маркер «УСТАРЕЛ» у `## Phase Handoff`, пересобрать его текст под фактическое состояние (30/31 воспроизводимо, компилятор реально подключён к write-site), свести Status Board и подготовить фазу к аудиту заход 2/2 |

```
/task:plan-close 2026.07.24-AGENT-RELIABILITY P2
```

**Done:**

- **P2.6 закрыт 🟢 Done** (item-коммит `a13614db`): `task_contract.build`/`bundle_lint`,
  `review_policy.LoopBudget.from_committed`, `canonical_actor` с моделью (D72), `task@0.6.0`.
- **P2.7 закрыт 🟠 Done with deviations** (item-коммит `d11c3b74`): write-site pre-mutation в
  `plan-exec.md`, `plan-run.md`/`plan-audit.md`, `snippets/source-evidence-template.md`, §13
  канона + литеральный тест, публикация `plan-protocol@2.13.0`/`skiller@0.6.0`/`task@0.7.0`.
- **P2.10 закрыт 🟠 Done with deviations** (item-коммит `668012bd`): закрытый набор заголовков
  §3 Routing (канон + легаси `Model/effort`/`Model/Effort`), типизированный отказ вместо
  `ValueError` по обеим осям и обеим сторонам маршрута (D74/D78 закрыты), `task@0.8.0`.
- **P2.11 закрыт 🟢 Done** (item-коммит `abd53b4b`): бинарный гейт `pre_mutation == "allow" and
  pre_final == "allow"` (D76 — `n/a` НЕ зелёное), маршрут `actual_route` на pre-final —
  маршрут ИСПОЛНИТЕЛЯ по лестнице D75, `plan-exec.md` шаг 7 получил исполняемую границу (М5),
  различающий тест (D79), публикация `plan-protocol@2.14.0`/`skiller@0.7.0`/`task@0.9.0`.
- **P2.8 закрыт 🟠 Done with deviations** (item-коммит `a36d489b`): `artifacts/P2.5/generate_transcripts.py`
  (committed, детерминированный) гоняет реальные seam'ы для всех 31 кейсов банка,
  перепрогон даёт те же 30/31, независимо пересчитываемо, честный `covered` по всем 12
  категориям.
- **P2.9 закрыт 🟢 Done** (item-коммит `b9ff62f6`): последний ремонтный item реопена —
  восемь бухгалтерских находок аудита сняты поимённо: (F7) литерал Validation P2.4 №3
  `PYTHONPATH=packages/harness/lib:packages/harness …` (прецедент D60/D61, `Ran 17 tests …
  OK`) + отчёт по трём недостающим `validate.sh` (task/harness/analyst, все `validate: OK`);
  (F6) Known Deviations P2.3 о `artifacts/P2.3/base-sha.txt`, уехавшем в bookkeeping-коммит
  `324bae5d` вместо item-коммита `77b574b5`; (F11) полнота отчёта Validation P2.3 —
  `test_canon_literals.py`/`test_journal.py` перепрогнаны на `77b574b5` через изолированный
  `git worktree`, 6/6 и 26/26 OK; (F12) хеш item-коммита P2.5 `14b3e6ce` вписан в Completion
  Notes P2.5 и `findings/P2.5-scenario-results.md:7` вместо мёртвой ссылки; (F13) Known
  Deviations P2.5 об отсутствующей старт-записи журнала; (F14) проверено — «Three cases»
  больше не существует в файле (P2.8 переписал §1–§6), изменений не потребовалось; (F10/F15)
  строка §7 Exported для `task` plugin/routing приведена в соответствие с фактом, ссылки на
  D72/D73 добавлены в Known Deviations P2.4. Ни одной мутации `packages/**`.

**Remaining:**

- Все шесть items реопена (P2.6, P2.7, P2.8, P2.9, P2.10, P2.11) терминальны — фаза P2
  готова к `task:plan-close … P2` (снимает маркер «УСТАРЕЛ» у `## Phase Handoff`, сводит
  Status Board), затем аудит фазы **заход 2/2**.
- **P3–P4** ⬜ — не стартуют до терминальной P2.

**Sources of truth:**

- `plan.md` — §0 Meta (v1.16.4), §3 Routing (строки P2.6–P2.11), §4 Status Board
  (P2 = `6/11 🟢-counted, 11/11 items терминальны`), §6 Update Log (последняя строка — P2.9),
  §7 Contracts (строка `task@0.5.0` приведена к факту).
- `phases/P2.md` — ТЗ P2.9 Completion Notes несёт построчное соответствие `F# → файл:поле`
  для всех восьми находок; блок `## Audit P2 — 2026-07-26` (F6/F7/F10–F15 сняты, F1–F5/F9
  остаются — владельцы см. `research/07` §8).
- `findings/P2.5-scenario-results.md` — item-commit `14b3e6ce` в строке 7–8.
- `roadmap.md` — carrier'ы P2.6–P2.11; `journal.jsonl` — прогоны (P2.9: старт +
  `closed-green`).
- **Дерево, на которое смотрит этот handoff (D55): item-коммит `b9ff62f6`** — bookkeeping
  этого закрытия коммитится СЛЕДОМ (шаг 6, plans/-carve-out); холодная сессия стартует с
  committed-дерева после bookkeeping-коммита.

**Open risks:**

- **Cap аудитов.** `## Audit P2` — заход 1 из двух; третий заход — решение владельца, не
  автоматический раунд.
- **Дрейф генерируемых деревьев вне owner-карты.** P2.6–P2.9 отсутствуют в
  `remediation-map.json::baseline_owners` → `assert_generated_scope.py` не запускается для
  них (та же граница, что у P2.1/P1.4 по D63) — компенсация ручная сверка `git show --stat`
  против `Files` (для P2.9: 3 файла, точное совпадение `Files`, без companion-коммита).
- **F1–F5, F9 остаются открытыми названными долгами** вне scope P2.9: F1/F2 — Blocker,
  закрыты производителем (P2.6) и write-site (P2.7); F3/F4 — закрыты P2.8; F5 — закрыт
  P2.6 (`LoopBudget.from_committed`); F9 — вне scope владельца, `PROMOTE-CANDIDATE`
  (атрибуция diff-scope guard по автору/сессии), не чинится этим реопеном.

**Workarounds / Deferred / Open questions:**

- **F9 (Minor) не чинится** — вне скоупа реопена, названный долг с `PROMOTE-CANDIDATE`.
- **Обобщение D79** — `PROMOTE-CANDIDATE` в канон `plan-protocol`; владелец продвижения —
  отдельная D-запись после терминального P2 (терминален — открыт вопрос продвижения).
- **Fresh-subagent dispatch** — недоставленная позиция Scope P2.2; владелец — **P3.4**.
- **Docs-sync `packages/task/CLAUDE.md`** — долг остаётся, владелец **P3.1**.
- **`plan.md` §4, строка фазы P0** — предсуществующий дефект бухгалтерии P0.4, владелец —
  `task:plan-close … P0`.
- **WARN `plan-lint` на `plan.md`** (длина строки Update Log P1.4) — предсуществующий, не
  блокер.
- **`trace-record-missing`** — единственный честный residual P2.5/P2.8; владелец **P3.1/P3.2**
  (unified trace ещё не существует).
