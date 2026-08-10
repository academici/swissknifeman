# P5 audit reopen — fail-closed queue и воспроизводимая acceptance

## 1. Вход и классификация фактов

Источник находок — `phases/P5/P5.md` → `## Audit P5 — 2026-08-09`. Все несущие факты
repo-grounded: текущие ingress находятся в `packages/task/lib/task/plan_requests.py`, frozen форма —
в `root/contracts/decision-request-v1.{md,schema.json}`, а опубликованные состояния — в
`phases/P5/P5.4.state.md` и `P5.5.state.md`. Внешних факт-классов для решения реопена нет.
RAG:— (repo-grounded: audit P5 + перечисленные code/contracts/state carriers).

## 2. Почему владельцы remediation — P5.4 и P5.5

P5.1/P5.2 заморозили формы и прошли audit probes; P5.3 корректно производит typed policy verdict и
provenance. Дефект находится на следующей границе: P5.4 принимает/применяет записи не по полной
frozen форме, а P5.5 доказывает механизм чтением заранее подготовленной очереди. Поэтому новый P5.6
создал бы второго владельца тех же product paths и скрыл producer→consumer ошибку. Исправление идёт
вперёд через существующих владельцев P5.4 → P5.5, как D142 делал для P4.
RAG:— (repo-grounded: audit findings 1–5; `phases/P5/P5.4.md`, `P5.5.md`; D142 precedent).

## 3. P5.4 — одна fail-closed граница записи и применения

`plan_requests.py` получает contract-driven validators трёх frozen sections: request, response и
auto-answer event. Наборы required/closed fields, enum/const/ref, pattern/date-time, option bounds,
reserved outcomes, material fields, timeout envelope и reason codes читаются из
`decision-request-v1.schema.json`; второй ручной список формы запрещён. Дополнительные cross-field
инварианты сверяют `decision_class`/`on_timeout` с действующим authority frame, а
`canonical_action`/`action_digest`/`policy_digest` — с повторным вычислением инструмента.

Применение ответа определяется выбранным option outcome, не фактом наличия response:

| Outcome | Queue state | Journal/item state | Continuation |
|:--|:--|:--|:--|
| `apply` | resolved | `in-progress`, projections regenerated | `resume-root` либо объяснённый `cold-start-root` |
| `park` | resolved-but-parked | `blocked`, projections regenerated | отсутствует |
| `reject` | resolved-rejected | `blocked`, projections regenerated | отсутствует |
| `escalate` | resolved-escalated | `blocked`, projections regenerated | отсутствует |

Auto-answer принимается только парой contract-valid `response` + `auto_answer_event`, произведённой
`plan_authority.auto_answer_clarification()`. Reclassification в `authorization` не снимает блок:
она оставляет/создаёт owner-resolution path. `pending_groups()` и `unresolved_for_phase()` читают
семантический reduced outcome, а не проверяют лишь наличие массива `auto_answers`.
RAG:— (repo-grounded: `plan_requests.py:48-337`; frozen contract §§Options/Clarification; audit 1–3).

## 4. P5.5 — producer-based доказательство

Статический `queue.jsonl` остаётся fixture-входом, но не доказательством. Новый
`artifacts/P5/validate_acceptance.py` на свежей временной копии тестового плана вызывает реальные
producer paths: policy clarification → `append_auto_answer`, return-loop owner request →
claim/resolve с `continue`, `park`, `reject`. Он проверяет queue events, continuation, journal,
item-state/status projections и отсутствие возобновления на non-apply outcomes; затем
детерминированно собирает machine results и report. `--check` сравнивает committed bytes.

После item-коммита тот же validator запускается из detached worktree с явным
`PYTHONPATH="$PWD:$PWD/packages/task/lib"`; acceptance artifacts обязаны находиться в этом tree до
bookkeeping. Это закрывает mismatch exact-command/tree и не позволяет зелёному отчёту пережить
регрессию producer path.
RAG:— (repo-grounded: audit finding 4; `artifacts/P5/acceptance-report.md`; P4 D142 item-tree pattern).

## 5. Декомпозиция, routing и оркестрация

Порядок строго последовательный: P5.5 потребляет исправленные validators/outcome/projections P5.4.
Оба item уже покрыты построчным Routing `implementation/high`, `Exec=manual`; tier не повышается,
потому что frozen semantics не меняется, а реализация следует D144. Независимых трёх scope нет и
длинной цепочки с внешним состоянием нет, workflow не требуется.
RAG:— (repo-grounded: `plan.md` §3; audit scope; plan-protocol §7/§9).

## 6. Отвергнутые варианты

- Новый P5.6 отвергнут: он дублирует ownership `plan_requests.py` и маскирует дефект P5.4/P5.5.
- Расфризить schema v1 отвергнуто: аудит показал runtime under-enforcement, не недостаточность формы.
- Считать non-apply response «разрешением» отвергнуто: это снова fail-open.
- Оставить report статическим отвергнуто: его можно сделать зелёным без producer execution.
- Чинить audit write-scope внутри P5 отвергнуто: finding 6 вне Deliverables P5 и требует owning
  protocol/generator change.

## 7. Проверка (verification status)

- **RAG:** не запускался — внешних факт-классов в решении нет; все несущие выводы проверены по
  audit/code/contracts/git carriers 2026-08-09.
- **Непроверено → ПОВТОРНЫЙ ПРОХОД:** ничего.
- **Обходки/[POSSIBLE-DEFECT]:** hook integrity preflight остаётся красным
  `record-provenance-mismatch` в owning `packages/harness`; в P5 обходка не вводится.

## 8. Pre-mortem remediation: через 6–12 месяцев D144 провалился

| Причина | Митигация | Владелец |
|:--|:--|:--|
| Schema получила новый keyword, локальный interpreter его молча проигнорировал | неизвестный/непокрытый keyword fail-closed; mutation test перечисляет фактический dialect frozen schema | P5.4 |
| Response append прошёл, regeneration упала, а continuation уже ушла root | continuation публикуется только после journal + state/status regeneration + freshness check; сбой пишет blocked compensation и возвращает ошибку | P5.4 |
| Policy auto-answer после reclassification в authorization снова считается `apply` | отдельный negative e2e: authorization остаётся blocked и видим владельцу | P5.4, P5.5 |
| Acceptance опять читает готовую queue, хотя формально «запускает скрипт» | fresh temp copy + обязательные producer call paths; report claims строятся только из observed result object | P5.5 |
| Два прогона расходятся из-за wall-clock `at`/temp path | volatile поля валидируются, но не входят в normalized results; output содержит только стабильные semantic observations и pinned digests | P5.5 |
| Report появился bookkeeping-коммитом после item hash | detached replay и `diff-tree` требуют validator/results/report в P5.5 item tree | P5.5 |
