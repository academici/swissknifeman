# Continue-first: repair, block confirmation и delivery receipt

Task рассматривает ошибку инструмента, route rejection, ожидание решения и локальный дефект как
наблюдения, а не как автоматический `Blocked`. Durable journal различает четыре nonterminal
результата:

| Result | Значение | Влияние на status/attempt |
|:--|:--|:--|
| `routing-rejected` | текущий dispatch не покрывает Routing | не влияет |
| `decision-pending` | ожидается уже материализованное решение | не влияет |
| `local-repair` | выполняется ограниченный обратимый repair | не влияет |
| `block-candidate` | material-гипотеза ожидает подтверждения | не влияет |

Малый обратимый дефект исправляется в текущем attempt, после чего повторяется исходная Validation.
Новый design pass для этого не создаётся.

## Repair evidence v1

Перед checkpoint, block или redesign executor пишет закрытый `repair-decision/v1`. Он связывает
точный исходный red carrier, baseline/candidate digest, affected paths с owner item, bounded diff,
все material-surface оси и pre/post validation. `task.plan_repair.evaluate()` — единственный
классификатор и возвращает `repair-in-current-attempt`, `gather-evidence`, `block-candidate` или
`design-required`.

Обратимый ремонт внутри согласованной задачи продолжается при product/dependency/test delta
и за подсказанным порогом числа файлов. Пути сохраняют owner attribution. Public/security/schema
impact требует доказанного candidate delta и соответствующей проверки. Неразрешённые
frozen/authority/irreversible границы требуют evidence; красный baseline их не отменяет.
Новый выбор результата/Acceptance с `decision_question`, `evidence_gap`, `alternatives`
и `expected_artifact` требует design. Лимит независимых аудитов не расходует право на ремонт;
повтор одной ошибки без новой информации требует смены подхода или checkpoint.
`block-candidate/v1` хранит digest repair record и потребляет его без собственной переклассификации.

Terminal close дополнительно проверяет append-only журнал: каждый qualified repair остаётся
незавершённым, пока более поздняя immutable запись с тем же item, command и digest исходного
carrier не зафиксирует его green в `post_validation`. Поэтому отдельный focused green не может
скрыть неповторённую исходную проверку.

## Producer readiness и correction routing

Producer объявляет связь ровно одной directive ``producer-readiness/v1``. Terminal decision несёт
`producer-readiness/v1`: `nonempty-candidates` привязывает положительный детерминированный набор,
а `empty-by-decision` — нулевой набор и одну принятую owner decision `D#`. Bundle и downstream
передают потребителю только digest-bound projection; валидная readiness сама является green
downstream carrier без обязательного shell-запуска.

`task.plan_readiness.correction_decision()` — единственный reducer для продолжения: verified output
или approved no-op → `continue-current`; stale/missing → `repair-in-current-attempt`; доказанный
contract conflict с `phase-reentry-justification/v1` → `reopen-phase`; закрытый `fix-branch/v1` с
объявленным target → `priority-fix`. Решение всегда nonterminal и проецируется в status/returns.
Lint и delivery отклоняют `plan-design` для терминальной фазы без exact re-entry evidence.

## Когда допустим Blocked

Material-кандидат сериализуется как закрытый `block-candidate/v1`. Для внешней проблемы RAG
обязателен всегда: `rag.status=verified` и хотя бы один evidence ID. Затем отдельный reviewer,
не совпадающий с executor, получает только capsule в контексте `isolated-child-return` и возвращает
один verdict. Reviewer не авторизует действие; `task.plan_blocking.evaluate()` выбирает его
детерминированно:

| Verdict | Действие |
|:--|:--|
| `JUSTIFIED` | разрешить terminal block |
| `AVOIDABLE` | продолжить local repair |
| `INSUFFICIENT_EVIDENCE` | собрать минимально недостающее evidence |
| `OUT_OF_SCOPE` / `MALFORMED` | исправить capsule и повторить review |

Таким образом, неподтверждённое подозрение не красит item и не передаёт его в `plan-design`.
Safety и authority gates остаются fail-closed: reviewer только подтверждает факты, но не выдаёт
право на действие.

После последнего terminal item фаза становится кандидатом для закрытия. Fingerprint
требует явный Layout v2, привязывает item specs/state и digest объявленных `Files`,
но не общий Git HEAD: audit bookkeeping не инвалидирует собственное доказательство, а изменение
product carrier инвалидирует. GREEN acceptance по умолчанию допускает direct-close; legacy
`Audit Intent: required`, integration и число items сами не назначают audit. Дополнительный audit
требует адресного owner consent и конкретного evidence gap, связанных с candidate и одним run
через `audit-admission/v2` в decision record. Новые phase-audit start events проверяют это согласие;
исторические terminal rows без run ID остаются читаемыми, но не авторизуют новый run.
Reviewer может закончить с audit-attention/audit-red и
`decision.action=return-owning-continuation`, `signal_class=acceptance`, `scope_class=<owning item>`,
`terminal=false`, `recovered=false`, reason_code, evidence_ids и точным exec-items/run-items
continuation для owning item той же фазы. Journal/lint/delivery принимают этот результат,
но фаза остаётся открытой. Исполнитель ремонтирует, подтверждает affected acceptance и закрывает
результат без автоматического второго phase audit. Старые authority/block RED outcomes остаются читаемыми.

Уже зелёные проверки переиспользуются при неизменных релевантных product/test/tool/config inputs
и окружении. Lifecycle-переход и bookkeeping-only diff не требуют продуктового replay;
изменившиеся входы требуют affected rerun, live check выполняется на своей live boundary.

## Защита от преждевременного final

После terminal journal event и записи `handoff.md` команды `plan-exec`, `plan-run` и `plan-close`
вызывают `plan-delivery.py --kind terminal`. Receipt связывает plan/subject, terminal run ID и
journal pointer, commit, digests plan/handoff/state/closure и точную рекомендацию из сохранённого
handoff. Нетерминальный state возвращает `FINAL_BEFORE_TERMINAL_FORBIDDEN`; stale handoff —
`HANDOFF_RECOMMENDATION_MISSING` или `STALE_TERMINAL_RECEIPT`.

`plan-run` доводит GREEN item до journal/state/closure в той же owner session. После последнего
GREEN item delivery требует также допустимое закрытие фазы (`PHASE_CLOSURE_REQUIRED` — продолжить
локальный close), прежде чем отдать внешний Next. `plan-close` текущего item, его повторный запуск
и audit без admission не могут быть таким Next. Отдельный явно запрошенный `plan-close` сохраняется.

`plan-design` и `plan-audit` используют `--kind handoff`: это не заявляет product terminality, но
обязывает финальный ответ скопировать точный persisted Next. Финал содержит метку
`Рекомендация следующего шага:` и exact `recommendation` receipt.

Package runtime не видит transport lifecycle провайдера, поэтому heartbeat и проверка уже
отправленного transcript остаются отдельными adapter/harness seam. Receipt честно защищает
package-owned границу до `final`, но не заявляет недоступный transport hook.

## Terminal admission lease

`terminal_admission` adds the repository-owned seam between a Task run and a documented provider
Stop adapter. Its ignored `.swissknifeman/task-terminal/` state binds provider/session, Task
session, plan, subject, command and run ID to one monotonic, expiring lease; turn identity remains
in each event, so a later turn of the same run stays applicable. Concurrent Task runs never replace
each other. `arm` follows run admission;
`refresh` needs a changed progress fingerprint or typed `waiting-owner`; `release` is explicit.
`check` is a total reducer: no matching lease is `NOT_APPLICABLE`, while invalid, stale or ambiguous
applicable state fails closed with a recovery action.

For a terminal decision it requires the exact validated P1.3 `terminal` continuity result that was
last refreshed into the lease, rebuilds the receipt and compares only
`plan_delivery.required_final_message(receipt)` with the in-memory proposed fragment. JSONL events
contain identities, sequence, verdict/reason and SHA-256 values, never raw transcript text. A stale,
released or corrupted lease has the named `re-arm` recovery. This is local deterministic admission
proof; provider payload translation and transport capability claims belong to P4.2.

При прерывании после terminal journal и до state projection delivery возвращает
`STALE_TERMINAL_RECEIPT`. Повторный `append_idempotent_terminal` не дублирует запись;
регенерация через `plan-views state` восстанавливает проекцию. Writer не переписывает
байт-идентичный файл. Проверки нельзя объявлять выполненными по переданному списку имён.
