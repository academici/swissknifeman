# Task: достаточно спроектировать, выполнить и проверить

Задание владельца от 22 сентября: одна реализация без master plan, фаз и повторных аудитов.
Этот файл объединяет диагностику и результат; отдельного исполнения отчёта не требуется.

## Исходные материалы и решение

- `roadmap/2026.09.22-task-design-proof-overreach-diagnostic.md`: экономический бюджет
  владельца определяет глубину исследования; компактный контекст и единый finalizer;
  законченный design не требует нового процесса сам по себе.
- `roadmap/2026.09.22-task-plan-exec-control-plane-overhead.md`: механическое обслуживание
  планов переносится из reasoning loop в существующий runtime через одну точку входа;
  дорогой overshoot ограниченных pinned-задач диагностируется до записи.
- `roadmap/2026.09.22-task-owner-session-authority-provider-gap.md`: явные границы
  `owner-session` для ограниченной локальной работы и `provider-proof` для внешних эффектов.
- `roadmap/2026.09.21-consumer-context-rollout-regression.md`: в этом задании исправляется
  подключение Task и связанного harness только по явному вызову. Общий reconcile плагинов,
  inventory/budget skiller и writers maind остаются отдельным остатком исходной записи.
- `roadmap/2026.09.21-cursor-safe-dirs-fail-closed-non-rm-shell.md`: отдельный дефект Cursor;
  в рабочем дереве уже есть чужие незавершённые изменения. Они сохраняются, этот отчёт
  не объявляет их завершёнными.

## Границы реализации

Изменяются Task runtime, канонические команды и их provider projections, соответствующие
источники plan-protocol и opt-in интеграция harness. Существующие планы и фактическая
история исполнения сохраняются. Работа не запускается через Task. Проверки покрывают
изменённое поведение и согласованность сгенерированных поверхностей, без fleet rollout.

Достаточный design фиксирует outcome, scope, необходимые решения и проверку результата.
Полный census findings/callers, обязательные квоты исследований и отдельные bookkeeping
items не являются default acceptance. Явные security/authority ограничения сохраняются.

## Результат и проверка

Реализовано в исходниках: **Task 0.21.0**, **harness 0.5.6**.

- Task включается только явным вызовом. У Claude commands — `disable-model-invocation`,
  у всех 11 Codex skills — `agents/openai.yaml` с `allow_implicit_invocation: false`.
  SessionStart STOP-GATE удалён, keyword router исключает Task даже со старым каталогом,
  Cursor router стал ручным. Полный plan-protocol тоже перестал быть неявным триггером.
- Генератор root instructions сохраняет компактный root для трёх провайдеров; повторная
  генерация не возвращает Task lifecycle. Package guidance и внешний healthcheck сохранены.
- Design использует бюджет владельца, outcome items и необходимые reads. Квоты исследования,
  полный census и отдельный bookkeeping item не обязательны. Design-only завершает свой
  scope в том же root; запуск исполнения остаётся отдельным явным выбором владельца.
- `plan-work.py prepare` объединяет recovery, route, snapshot, batch admission, contract,
  evidence graph и durable start. Модель получает item-spec и краткий результат;
  полные пять carriers не передаются ей. Повтор использует исходный run.
- `design-context` выдаёт поля схемы, выбранную фазу и Routing. `finalize-design` собирает
  проекции, eligible bundles, journal и receipt. Старые ошибки чужих фаз видны отдельно;
  ошибки выбранной фазы, общих carriers, routing и authority остаются блокирующими.
- `finalize` выполняет существующий terminal reconcile. Он принимает фактическое terminal
  evidence и авторский handoff, не создаёт их из предположений.
- `owner-session` разрешает конечную локальную работу с `local-source` и `checkout`/`*_test`.
  Grant связан с исходной репликой, сессией, scope, Files и Validation; follow-up и retry
  не требуют повторной команды, revoke/изменение scope/завершение закрывают grant.
  `provider-proof` остаётся default; отсутствие внешнего verifier даёт один
  `AUTHORITY_PROVIDER_UNAVAILABLE`, а не цикл повторных приглашений.
- Экономический gate отвергает overshoot bounded pinned execution и frontier/xhigh для
  обычного frontier/high design. Явный inherited `plan-run` сохраняет выбор владельца;
  recommended batch не разрешает более дорогую модель автоматически.

Проверки:

- финальная совмещённая выборка Task runtime/authority/recovery/routing/canon: 175 тестов;
- provider command/native discovery: 53 теста, включая настоящую изолированную установку
  через Codex CLI — 11 skills установлены, Task отсутствует в idle prompt;
- дополнительные authority/provider и harness router/instruction/Cursor suites прошли;
- provider command projections, registry и три root instruction projections — актуальны;
  `plan-lint --conflicts` и `git diff --check` — без ошибок.

Ограничения результата: consumer rollout, замер реального времени/токенов и native UI pilot
не выполнялись. `design-context` работает с уже существующей фазой; новый план сначала
получает минимальный skeleton. Finalizers агрегируют существующих writers, но не являются
общей транзакцией всех файлов и не пишут семантический handoff за модель. Внешний
provider-proof channel не реализован; `owner-session` — workflow guard, а не sandbox
и не криптографическое доказательство личности. Общий consumer reconcile и Cursor safe-dirs
остаются у исходных записей; они не объявлены закрытыми. Изменения не опубликованы и не
раскатаны на другие проекты.

Корневые инструкции регенерированы с восстановимыми adjacent backups
`CLAUDE.md.provider-artifact.bak` и `AGENTS.md.provider-artifact.bak`.

Внешние поля opt-in проверены по первичным источникам:
[Codex skills](https://developers.openai.com/codex/skills/),
[Claude skills](https://code.claude.com/docs/en/skills).
Perplexity в этой сессии недоступен; доступ к документации выполнен напрямую.
