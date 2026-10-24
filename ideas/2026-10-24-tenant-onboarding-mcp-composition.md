# Tenant: конфликт владельцев MCP при onboarding пустого PHP-пакета

Дата: 2026-10-24. Модуль-владелец: maind; соседний производитель: skiller → harness.
Статус: подтверждённое полевое наблюдение, без изменения политики владения MCP.

На пустом `tenant` с явно заданным типом `php-package` выполнено:

```bash
maind onboard tenant --memory manual --skills-channel connect --namespace axioma --with-code --yes
maind sync --project tenant --only mcp --json
```

`skiller integrate` сначала создаёт `.mcp.json` с единственным HTTP-сервером
`context7`. Следующий этап maind владеет целым `.mcp.json` и отклоняет его как
`unmanaged-target-diverged`. При этом итоговый onboarding печатает `✓ deploy`,
`deployed=true` и завершается с кодом 0. MCP Codex и Cursor в отчёте остаются
`planned`; нужных файлов на диске нет. Повторный точечный sync уже показывает
`status=failed`, `provider_aggregate=non-green` с диагностикой Claude.

Для завершения установки сохранён только что созданный собственным onboarding
файл Context7 в `/tmp/tenant-onboard-context7.json`, после чего штатный
`maind sync --project tenant --only mcp --json` создал конфигурации всех трёх
провайдеров и вернул `provider_aggregate=green`. В tenant оставлен состав MCP
maind + codegraph + perplexity, как у существующих PHP-пакетов. Чужих файлов
и существующих подключений этот шаг не затрагивал.

Отдельно найден локальный дефект harness: исключение машинных настроек через
подмену `home` скрывало workspace `local/config.toml` при генерации `hooks.env`.
Исправление использует пустой machine layer, сохраняя настоящий поиск workspace;
регрессионный тест проверяет выбор local вместо checkout и отсутствие утечки
машинного bypass. Это исправление не решает композицию MCP.

Направление: согласовать владельца начального MCP-файла между integrate и deploy,
а итог onboarding строить по фактическому агрегату provider deploy. Не снимать
проверку `unmanaged-target-diverged` и не перезаписывать пользовательские серверы.

Критерий принятия: новый пустой PHP-проект после одной команды onboarding имеет
все заявленные MCP-файлы; повторный запуск не меняет их и не конфликтует;
сохранность заранее добавленного пользовательского MCP проверяется отдельно;
отказ обязательного провайдера даёт ненулевой итог onboarding.
