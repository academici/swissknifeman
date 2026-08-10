# P5 audit reopen round 2 — единый semantic outcome и retry-safe projection boundary

## 1. Вход и граница доказательств

Источник — последний `## Audit P5 — 2026-08-09` (`Заход: 2`) в `phases/P5/P5.md` и код
`packages/task/lib/task/plan_requests.py`. Все три finding'а repo-grounded; внешних
staleness-sensitive fact-классов нет. RAG:— (repo-grounded: audit block; `plan_requests.py`;
`packages/task/tests/test_plan_requests.py`; frozen `decision-request-v1.schema.json`).

## 2. Владельцы remediation

P5.4 остаётся единственным владельцем request/response/auto-answer ingress, reducer'а и
journal→views boundary; P5.5 остаётся closing consumer с executable acceptance. Новый P5.6 снова
создал бы второго владельца тех же product paths и разорвал producer→proof связь. P5.1–P5.3,
frozen contracts и D143 аудит не опроверг. RAG:— (repo-grounded: audit findings 1–3; D144;
`phases/P5/P5.4.md`; `phases/P5/P5.5.md`).

## 3. Один semantic-outcome reducer

Редьюсер получает reduced queue state и возвращает один закрытый semantic verdict, который
потребляют все поверхности:

| Queue fact | Semantic verdict | Subject state | Pending/owner gate | Phase join | Continuation |
|:--|:--|:--|:--|:--|:--|
| request без ответа | `pending` | `blocked` | присутствует | unresolved | нет |
| response option `apply` | `apply` | `in-progress` | отсутствует | resolved | после projection checks |
| response option `park`/`reject`/`escalate` | тот же non-apply outcome | `blocked` | отсутствует | resolved | нет |
| auto-answer, reclassified не в `authorization`, option `apply` | `apply` | `in-progress` | отсутствует | resolved | после checks |
| auto-answer, `reclassified_to=authorization` | `pending-authorization` | `blocked` | присутствует | unresolved | нет |

`states()` остаётся structural reducer событий, а новый semantic reducer — единственное место,
где response/auto-answer превращается в permission/pending. `pending_groups()`,
`unresolved_for_phase()`, `render_gates()` и `_lint_terminal_phase_unresolved_decisions()` не
выводят смысл из `response is not None`/`auto_answer is not None`; state transition использует тот
же verdict. RAG:— (repo-grounded: `plan_requests.py:448-590`; `plan_gates.py:143-162`; audit
finding 1).

## 4. Substantive option bounds

`options.mandatory = [escalate, reject]` не входят в `min_substantive=2` /
`max_substantive=5`. Validator вычисляет substantive rows по id, исключая ровно frozen mandatory
ids, затем отдельно проверяет число 2–5 и присутствие mandatory. Регрессии: mandatory-only
отклоняется; ровно 2+2 и ровно 5+2 принимаются; уникальность продолжает проверяться по всему
массиву. RAG:— (repo-grounded: `decision-request-v1.schema.json:56-64`; audit finding 2).

## 5. Idempotent retry вместо rollback

Append-only queue/journal не откатываются. Поэтому exact retry — канонический repair path:

1. `request()` при существующем decision id сравнивает канонический durable request. Точное
   совпадение не append'ит второй request, а повторяет idempotent transition/refresh; несовпадение
   остаётся duplicate error.
2. `resolve()` при уже записанном response принимает только byte-equivalent response того же
   resolver/decision/action, повторно вычисляет semantic outcome/application и повторяет refresh;
   другой response остаётся reuse error.
3. Durable response event не публикует continuation до завершения boundary. Continuation
   строится в возвращаемом результате только после journal result, item state, `status.md` и
   `decisions/_gates.md` regeneration + `--check`. Поэтому исключение не выдаёт root разрешение.
4. Refresh не добавляет новый journal result, если последний semantic result уже нужный и все три
   views свежи; иначе дописывает ровно необходимый result и регенерирует views. Любой повтор
   сходится к queue/journal/views consistency без duplicate queue events.

Транзакционный rollback отвергнут: он противоречит append-only carrier'ам и не может атомарно
откатить несколько файлов. Idempotent repair сохраняет provenance сбоя и делает transient generator
failure восстанавливаемым. RAG:— (repo-grounded: root append-only rule; `plan_requests.py:420-550`;
audit finding 3).

## 6. Краснота до исправления и acceptance P5.5

P5.4 сначала коммитит test-only regression slice. Этот commit обязан воспроизводимо краснеть на
старом runtime по трём классам: cross-consumer authorization reclassification, substantive bounds,
request/resolve retry. Только следующий scope commit исправляет runtime; итоговый item commit
гоняет те же named tests зелёными. Это differentiating proof, а не тест, впервые появившийся вместе
с исправлением. RAG:— (repo-grounded: plan-protocol §13 differentiating predicate; audit request).

P5.5 расширяет producer acceptance как минимум следующими свежими copies: policy apply;
policy→authorization pending во всех consumers; owner continue/park/reject; lower/upper option
bounds + mandatory-only rejection; request projection failure→exact retry; resolve/apply projection
failure→exact retry без ранней continuation. Results/report получают новую artifact version,
содержат queue event counts, latest journal result, state/status/gate freshness, pending/join verdict
и retry count. Detached replay исполняет эти же сценарии на item commit. RAG:— (repo-grounded:
`artifacts/P5/validate_acceptance.py`; audit findings 1–3).

## 7. Routing, DoR и оркестрация

Последовательность P5.4 → P5.5 сохраняется: P5.5 потребляет исправленный reducer/retry boundary.
Оба item — `implementation/high`, `Exec=manual`: открытых contract/design решений после D146 нет,
но authority boundary и final verification требуют high. Два последовательно связанных scope не
срабатывают как orchestration criterion. RAG:— (repo-grounded: `plan.md` §3; plan-protocol §7/§9).

## 8. Pre-mortem: через 6–12 месяцев D146 провалился

| Причина | Митигация | Владелец |
|:--|:--|:--|
| Новый consumer снова проверяет наличие auto-answer вместо semantic verdict | reducer публично используется всеми пятью surfaces; consumer-conformance test перечисляет их | P5.4 |
| Retry принимает другой payload под тем же decision id | byte-equivalent request/response + resolver/action identity обязательны; mismatch fail-closed | P5.4 |
| Response event раскрывает continuation до падения projection | durable event continuation-free; return continuation строится только после трёх `--check` | P5.4 |
| Граница options опять считает mandatory как substantive | lower/upper valid tests и mandatory-only negative запускаются на RED commit и final tree | P5.4 |
| Acceptance обходит one-shot failure прямой записью queue | fresh copy, реальные producer APIs, инъекция только в projection seam, queue-count assertions | P5.5 |

## 9. Проверка (verification status)

- **RAG:** не запускался — внешних fact-классов нет; решения проверены по repo/code/git carriers
  2026-08-09.
- **Непроверено → ПОВТОРНЫЙ ПРОХОД:** ничего.
- **Обходки/[POSSIBLE-DEFECT]:** нет. Hook preflight этого захода зелёный: effective
  `context.observer` rc=0, оба SHA-256 совпали с provider-artifacts lock.
