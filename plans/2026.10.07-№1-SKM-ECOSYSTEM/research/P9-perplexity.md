# P9: внешние предпосылки (perplexity-web, 2026-10-09)

Маршрут: perplexity-web-mcp stdio через bash (JSON-RPC, инструмент search). Ответ — как вернул сервис.

## Q1 — переименование плагина Claude Code, вызов команды из команды, CLAUDE_PLUGIN_ROOT

```text
October 2026. Answer in Russian, prose, max 600 words, with URLs to primary sources (Anthropic Claude Code docs: plugins, plugins-reference, slash commands, skills; GitHub anthropics/claude-code issues/changelog).
Context: a Claude Code plugin named `task` (commands /task:plan-run etc., installed from a directory marketplace) is being renamed to `planner` (/planner:*). We need /task:* to keep working for one release with a deprecation warning.
1) Does Claude Code support any native alias, rename or deprecation mechanism for a plugin name or for plugin slash commands (e.g. fields in .claude-plugin/plugin.json or marketplace.json such as aliases, deprecated, replacedBy, renamed)? If not, what is the recommended way to rename a plugin in a marketplace without breaking users who have `task@marketplace` in enabledPlugins?
2) Can a slash command (custom command markdown file in a plugin's commands/ directory) invoke another plugin's slash command programmatically — via the SlashCommand tool or the Skill tool — and does frontmatter `disable-model-invocation: true` on the target command prevent that invocation?
3) What does ${CLAUDE_PLUGIN_ROOT} resolve to for a plugin installed from a local directory marketplace — the plugin cache copy (~/.claude/plugins/cache/<marketplace>/<plugin>/<version>) or the source directory — and are sibling directories of the plugin (outside the plugin folder) available at runtime?
```

На октябрь 2026 ответ отличается от старых описаний: нативный механизм переименования плагинов уже документирован, а плагин с относительным source из локального directory marketplace загружается непосредственно из исходников. Однако миграция установки не обеспечивает совместимость старых /task:*.

## 1. Переименование и сохранение /task:*

В marketplace.json существует верхнеуровневый renames: для вашего случая "renames": {"task": "planner"}. Claude Code разрешает старое имя в новое и переписывает ключи enabledPlugins и pluginConfigs в user/project/local settings. Managed settings он не переписывает: администратор должен обновить их отдельно. Историю renames рекомендуется сохранять постоянно. Для marketplace из Git/URL документация дополнительно предупреждает: после переименования может понадобиться однократный /plugin install planner@marketplace. .
Это не aliases, deprecated, replacedBy или renamed в plugin.json: таких документированных полей нет. Неизвестные поля манифеста игнорируются/удаляются; нативного deprecation state также нет. displayName меняет только подпись интерфейса, не namespace команд. , .
Для одного переходного релиза я рекомендую оставить две самостоятельные записи: task с манифестом "name": "task" и planner с "name": "planner". Старый плагин должен предоставлять прежние команды, сначала сообщающие «/task:plan-run устарела; используйте /planner:plan-run», затем выполняющие прежнюю процедуру. Это архитектурная рекомендация, не встроенный alias: namespace определяется именем манифеста. Не заменяйте старую запись одним renames, пока требуются старые команды. После переходного релиза уберите compatibility-плагин и добавьте миграцию. , .

## 2. Может ли команда вызвать другую команду?

Да, Claude может вызвать доступную prompt-based команду другого включённого плагина через Skill, используя полное имя, например planner:plan-run, и передав аргументы. Но Markdown сам не выполняет программный вызов: он инструктирует модель вызвать инструмент; это не детерминированный redirect. SlashCommand — прежнее название механизма; custom commands объединены со skills. , .
disable-model-invocation: true у целевой команды блокирует её вызов моделью через Skill, а не только автоматический выбор по описанию. Ручной /planner:plan-run пользователя остаётся разрешённым. Поэтому wrapper /task:* не сможет обойти флаг инструкцией «вызови новую команду». allowed-tools также не отменяет этот запрет. , .
Если целевые команды user-only, надёжнее генерировать обе версии Markdown из общего шаблона при сборке, добавляя предупреждение только старым командам, вместо delegation через Skill.

## 3. ${CLAUDE_PLUGIN_ROOT} и соседние каталоги

Для marketplace, добавленного локальным путём, и записи с относительным source, например ./plugins/planner, текущие docs прямо указывают in-place loading: ${CLAUDE_PLUGIN_ROOT} соответствует исходному каталогу плагина, не cache copy. Изменения применяются после /reload-plugins либо нового сеанса. Для остальных обычных marketplace-установок используется ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/. .
При in-place загрузке соседние файлы физически остаются на диске; скрипт может обращаться к ним при соответствующих permissions. Но объявлять компоненты через ../shared нельзя: пути компонентов должны оставаться внутри plugin root. В cached installation соседние каталоги автоматически не копируются. Поэтому runtime-зависимости лучше включать внутрь каждого дистрибутива. Старый описывает прежнее кэширование; для актуального поведения приоритетны текущие docs, а версии следует сверять с .

Sources:
1. [Документация миграции](https://code.claude.com/docs/en/plugins/host-marketplace#rename-or-remove-a-plugin)
2. [code.claude](https://code.claude.com/docs/en/plugins/host-marketplace)
3. [plugins-reference](https://code.claude.com/docs/en/plugins-reference)
4. [marketplace reference](https://code.claude.com/docs/en/plugins/marketplace-reference)
5. [Обзор plugins](https://code.claude.com/docs/en/plugins)
6. [правила имён](https://code.claude.com/docs/en/plugins/loading#entry-name-and-manifest-name)
7. [Slash commands](https://code.claude.com/docs/en/slash-commands)
8. [#17578 — GitHub issue о merger](https://github.com/anthropics/claude-code/issues/17578)
9. [Skills](https://code.claude.com/docs/en/skills#control-who-invokes-a-skill)
10. [#19141 — уточнение в issue #19141](https://github.com/anthropics/claude-code/issues/19141)