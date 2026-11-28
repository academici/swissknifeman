# P09.Z — M4: pinned resources и объяснимый полный контекст

Приёмка связывает extensions, context, execution и planning через production bus,
PostgreSQL, CLI и локальные подпроцессы. Тесты находятся в
[test_m4_resources.py](../../tests/e2e/test_m4_resources.py), данные и host wiring — в
[M4 fixtures](../../tests/fixtures/e2e/m4/). Внешняя сеть и платные провайдеры не нужны.

| Переносимое поведение | Владелец v2 и свидетельство |
|---|---|
| `skiller` registry, upstream, compat и `aicore/content/skill.py` | Immutable extension packs, явные overrides, admission и quarantine; `ext sync`, install/enable и отказ расширения прав |
| `aicore/content/budget.py`, orch context/prompts | Двухфазная сборка, обязательные блоки, бюджеты, manifest; missing/overbudget не публикуют prompt; ранний overbudget не создаёт draft |
| orch conductor stages research | Host research ladder с реальными bounded command adapters и PostgreSQL ledger; пустые нижние tiers и evidence верхних, недоступный источник — error без success TTL |
| harness roles и planner templates | Ресурсы core; роли и workflow фиксируются bundle, service-plan `review-only` скрыт из обычного списка |
| planner receipt freshness | Immutable review request/revision/run и idempotency; дополнительные freshness и branch-инварианты проверяет [review suite](../../tests/e2e/test_review_request.py) |

Донор используется только как источник поведения и инертного контента; пакеты донора не
импортируются. Алгоритмы с IO разделены на host adapters и чистые правила. Полномочия,
классификация и owner guard принадлежат v2, а не инструкциям из skill или repository.

## Версии и воспроизводимость

`test_active_run_keeps_overlay_catalog_and_exact_prompt` устанавливает operator overlay,
включает его через настройки и проверяет происхождение уровня `pack`, а также явный override профиля executor. После публикации
контекста работающего run обновляются core и overlay. Старые `PackPins` продолжают
разрешать прежние prompt block, профиль и runtime catalog; повтор исходного DTO публикации
сохраняет те же UTF-8 bytes и SHA-256. Новый run фиксирует новые версии. Явный digest pin ресурса и quarantine старой версии приводят
к отказу pinned resolution: подмена на latest запрещена. Полный M3 worker сохраняет prompt
на фактическом runtime handoff и дополнительно проверяет выполнение и интеграцию ожидаемого изменения после обновления core.

`step-context --blocks` объясняет источники и причины, а `step-prompt` возвращает текст
сохранённого артефакта побайтно. Поля, неприменимые к исключённому или self-loaded блоку,
могут быть null: это не доказательство чтения содержимого runtime. Проверки реального
runtime handoff, авторизации, content policy и tampering дополняет
[test_m4_context.py](../../tests/e2e/test_m4_context.py).

## Fail-closed границы

Отрицательные сценарии проверяют `CONTEXT_INPUT_MISSING`, `CONTEXT_OVER_BUDGET`, stale
claim (`LEASE_LOST`), S26 third-party config, flag-K isolation/selection/ceiling keys и
`EXTENSION_WIDENS_PERMISSIONS`. Невалидная установка не оставляет доступного pack.
Нормативные проверки отсутствующего owner guard, неизменяемости manifest, replay и
транзакций включены в [context contracts](../../tests/contracts/context/).

## Сверка skills

При первоначальном переносе P09.06 в packs попали 198 из 218 исходных skills. После обновления
core до 2.1.0 в 18 мигрированных packs осталось 134 skills, ещё 84 учтены в `excluded_skills`.
Локальные packs содержат 106 skills, upstream packs — 28. M4 сверяет текущую таблицу отчёта
с экспортом и файлами пакетов. [Отчёт](skills.md) · [Экспорт](../../resources/overlays/exports.json)

## Валидация и ревью

Команда приёмки: PostgreSQL pytest с `SKM_REQUIRE_PG=1`, `-n 4`, M4 resources/context,
review request и contracts context/extensions; затем Ruff format/lint, Pyright, docs links и
`git diff --check`.

Контрольный прогон 2026-11-17: **162 passed, 1 skipped**. Пропуск — memory-вариант
`test_postgres_triggers_keep_every_version_immutable`: триггеры 0018 существуют только
в PostgreSQL; соответствующий PostgreSQL-вариант прошёл. Нефильтрованный
`tests/architecture/test_contract_imports.py`: **59 passed**. Ruff format/lint и Pyright
прошли; ссылки и чистота diff проверяются финальной цепочкой.

Ручная проверка diff исполнителем: scope и сохранность чужих изменений, immutable pins,
граница общего бюджета, rollback установки, lease/replay и ошибки источников.
Независимое manual review: **changes_requested** (три Major); исправления проверены исполнителем.
Повторное независимое ревью не запускалось; статус accepted не заявляется.

После независимого ревью: runtime-child сохраняет фактически прочитанные stdin bytes;
OLD/NEW тексты проверяются на шагах активного и нового run; CLI rows/excluded/runtime_self_loads
сверяются с final manifest в БД. Повторная приёмка M4 resources: 16 сценариев.
