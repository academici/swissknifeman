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
