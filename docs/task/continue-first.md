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

Clean-baseline red без доказанного candidate delta и любой bounded reversible repair со всеми
ложными material-surface осями продолжаются в том же attempt, в том числе если затронутый путь не
в `Files`. Exact original carrier обязательно запускается после ремонта. Только material decision
surface с непустыми `decision_question`, `evidence_gap`, `alternatives` и `expected_artifact`
разрешает `design-required`; `FIX_REQUIRED` и мнение reviewer сами по себе не разрешают redesign.
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

После последнего terminal item фаза остаётся `🟡 In progress` как audit candidate. Fingerprint
требует явный Layout v2, привязывает item specs/state и digest объявленных `Files`,
но не общий Git HEAD: audit bookkeeping не инвалидирует собственное доказательство, а изменение
product carrier инвалидирует. Только fresh GREEN разрешает последующий `plan-close Pn`.

## Защита от преждевременного final

После terminal journal event и записи `handoff.md` команды `plan-exec`, `plan-run` и `plan-close`
вызывают `plan-delivery.py --kind terminal`. Receipt связывает plan/subject, terminal run ID и
journal pointer, commit, digests plan/handoff/state/closure и точную рекомендацию из сохранённого
handoff. Нетерминальный state возвращает `FINAL_BEFORE_TERMINAL_FORBIDDEN`; stale handoff —
`HANDOFF_RECOMMENDATION_MISSING` или `STALE_TERMINAL_RECEIPT`.

`plan-design` и `plan-audit` используют `--kind handoff`: это не заявляет product terminality, но
обязывает финальный ответ скопировать точный persisted Next. Финал содержит метку
`Рекомендация следующего шага:` и exact `recommendation` receipt.

Package runtime не видит transport lifecycle провайдера, поэтому heartbeat и проверка уже
отправленного transcript остаются отдельными adapter/harness seam. Receipt честно защищает
package-owned границу до `final`, но не заявляет недоступный transport hook.
