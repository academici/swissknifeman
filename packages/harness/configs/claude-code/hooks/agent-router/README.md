# agent-router — opt-in подсказки возможностей проекта

Task запускается только явным вызовом команды или скилла. Обычный запрос на
реализацию, дизайн или ревью не активирует Task.

`router.py` (UserPromptSubmit) по явному включению router оценивает локальные
агенты и скиллы по ключевым словам. Task-команды и Task-скиллы исключены из
генерации и скоринга, включая старые project catalogs. Подсказка остаётся
необязательной; она не разрешает вызов команды или изменение цели.

`session-policy.py` оставлен как пустой compatibility entrypoint для ранее
установленных SessionStart registrations. Он не добавляет контекст при старте,
в том числе при старых `POLICY=propose` и `POLICY=auto_dispatch`.

По умолчанию `POLICY=off`. Старые значения `propose`/`auto_dispatch` сохраняют
только необязательные non-Task подсказки; автоматического запуска Task больше нет.
Per-project override: `.claude/agent-router.env.ini`; каталог:
`.claude/agent-router.config.json`.

```bash
harness hooks --global
harness hooks --target . --router propose
harness router --generate --target .
```

`THRESHOLD` задаёт минимальную сумму весов, `ESCAPE_PREFIX` отключает подсказку
для одного сообщения. Hook принимает JSON на stdin и выводит одну строку
`additionalContext` либо ничего. Невалидный ввод не блокирует работу.
