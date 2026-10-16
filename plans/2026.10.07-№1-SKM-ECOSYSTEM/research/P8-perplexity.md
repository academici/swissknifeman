# P8: внешние предпосылки (perplexity-web, 2026-10-09)

Маршрут: perplexity-web-mcp stdio через bash (JSON-RPC, инструмент search). Ответы — как вернул сервис.

## Q1 — Agent Skills: поля frontmatter, лицензия при vendoring, skills-lock.json

```text
October 2026. Answer in Russian, prose, max 600 words, with URLs to primary sources (agentskills.io specification, Anthropic Claude Code docs, OpenAI Codex docs).
1) Agent Skills open standard (agentskills.io, SKILL.md frontmatter): what is the current exact list of frontmatter fields and their constraints — name (length/charset, must match directory?), description (max length), license, compatibility (max length, meaning), allowed-tools (status: experimental?, format space-delimited?), metadata (string map) — and are unknown extra fields (e.g. version, requires, tags) allowed or rejected by the reference validator `skills-ref validate`?
2) Is there a convention for where a skill's license is declared when it is vendored from another repository (frontmatter `license` vs a LICENSE file in the skill dir)?
3) Does the vercel-labs `skills` CLI (npx skills add) write a `skills-lock.json` at the project root, and what is its role (committed or not)?
```

## 1. Frontmatter стандарта и валидатор

На 9 октября 2026 года Agent Skills определяет шесть полей верхнего уровня: name, description, license, compatibility, allowed-tools, metadata. Только первые два обязательны. Первичный источник: .
name: 1–64 символа; строчные буквенно-цифровые символы и дефис; нельзя начинать или заканчивать дефисом, использовать последовательные дефисы --. Значение должно совпадать с именем непосредственно содержащего SKILL.md каталога. Важная неточность текста: спецификация буквально пишет «unicode lowercase alphanumeric characters», одновременно приводя a-z, 0-9. Поэтому её формулировку нельзя уверенно пересказывать как исключительно ASCII; для максимально переносимых имён используйте [a-z0-9-] с перечисленными ограничениями.
description: непустая строка длиной 1–1024 символа, описывающая, что делает skill и когда его применять. license: название лицензии или ссылка на включённый в пакет файл лицензии; рекомендуется краткое значение, отдельного числового ограничения длины спецификация не устанавливает.
compatibility: при наличии 1–500 символов; описание требований к окружению — целевой продукт, системные пакеты, сетевой доступ и т. п. Это не стандартизованная схема зависимостей или диапазонов версий.
allowed-tools: экспериментальное поле; строка инструментов, разделённых пробелами, например Bash(git:*) Bash(jq:*) Read, а не YAML-массив. Оно обозначает предварительно разрешённые инструменты; поддержка зависит от реализации агента.
metadata: отображение строковых ключей в строковые значения. Дополнительные свойства размещаются здесь: например, metadata.version: "1.0". Нативные списки, вложенные объекты и boolean не соответствуют заявленному типу, хотя reference validator не полностью проверяет это ограничение.
Неизвестные поля верхнего уровня — version, requires, tags — skills-ref validate отвергает как Unexpected fields in frontmatter. Список полей задуман исчерпывающим; это прямо подтверждено в обсуждении проекта: https://github.com/agentskills/agentskills/discussions/211. Не путайте это с поведением конкретного загрузчика.
Claude Code расширяет стандарт собственными полями и игнорирует нераспознанные; его правила не равны правилам skills-ref: . Codex документирует обязательные name и description, а зависимости и продуктовые настройки выносит в agents/openai.yaml: https://developers.openai.com/codex/skills.

## 2. Лицензия при vendoring

Спецификация не устанавливает особого правила для vendoring и не требует обязательного файла именно с именем LICENSE. Допустимы как license: Apache-2.0, так и ссылка на включённый файл; официальный пример — license: Proprietary. LICENSE.txt has complete terms. Следовательно, frontmatter и файл лицензии не конкурирующие варианты: поле может указывать на файл с полными условиями.
Практический вывод: при копировании skill сохраняйте исходное объявление и относящийся к нему текст лицензии вместе с необходимыми уведомлениями; если условия находятся только в корне исходного репозитория, перенос одного каталога skill оставит их за пределами vendored-пакета. Это рекомендация по комплектованию, а не дополнительное требование Agent Skills.

## 3. skills-lock.json

Да: проектная установка через npx skills add создаёт/обновляет проектный skills-lock.json. Он хранит происхождение установленных skills и хеш содержимого для управления установками и обновлениями; это файл CLI Vercel, не часть стандарта Agent Skills.
Его предполагается коммитить: официальный AGENTS.md прямо обозначает local-lock.ts как «skills-lock.json, checked in». Там же описано восстановление через skills install без аргументов, алиас skills i и skills experimental_install: https://github.com/vercel-labs/skills/blob/main/AGENTS.md. Не смешивайте его с глобальным ~/.agents/.skill-lock.json.

Sources:
1. [https://agentskills.io/specification](https://agentskills.io/specification)
2. [https://github.com/agentskills/agentskills/discussions/211](https://github.com/agentskills/agentskills/discussions/211)
3. [https://code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills)
4. [https://developers.openai.com/codex/skills](https://developers.openai.com/codex/skills)
5. [https://github.com/vercel-labs/skills/blob/main/AGENTS.md](https://github.com/vercel-labs/skills/blob/main/AGENTS.md)
## Q2 — плагины Claude Code и Codex со skills, гранулярность в монорепозитории

```text
October 2026. Answer in Russian, prose, max 600 words, with URLs to primary sources (Anthropic Claude Code plugin docs, OpenAI Codex plugin/skills docs).
1) Claude Code plugins: can one plugin (.claude-plugin/plugin.json) ship both slash commands, agents and skills (skills/ directory) at once; how are plugin skills namespaced (plugin:skill) and does a plugin skill conflict with a project skill of the same name in .claude/skills?
2) OpenAI Codex CLI plugins: what is the current `.codex-plugin/plugin.json` format, can a Codex plugin bundle skills only (no commands), and how is a repository marketplace declared (`.agents/plugins/marketplace.json`)? Are Codex skills otherwise discovered from `.agents/skills/` in the repo?
3) Best practice for a monorepo where several independent modules each own a few skills: publish each module as its own plugin in one marketplace, vs aggregating all skills into one library plugin? Any guidance from Anthropic/OpenAI docs on plugin granularity and context budget (skill descriptions loaded at startup)?
```

## 1. Claude Code: команды, агенты и skills вместе

Да: один плагин с .claude-plugin/plugin.json может одновременно содержать commands/*.md, agents/*.md и skills/<skill>/SKILL.md. Эти каталоги располагаются в корне плагина, рядом с .claude-plugin/, а не внутри неё. Стандартные каталоги обнаруживаются автоматически; минимальному манифесту достаточно {"name":"module-a"}. Для новых команд Anthropic рекомендует skills: пользовательские slash-команды объединены с ними, но прежний формат commands/ сохраняется.
Skill плагина вызывается как /module-a:review. Проектный .claude/skills/review/SKILL.md вызывается как /review: оба загружаются и не вытесняют друг друга, поскольку plugin skill имеет отдельное пространство имён. Это прямо описано в разделе разрешения совпадающих имён.
Документация: https://code.claude.com/docs/en/plugins/manifest-reference и https://code.claude.com/docs/en/skills#resolve-skills-that-share-a-name.

## 2. Codex: формат плагина и marketplace

В актуальной документации есть важное изменение: .codex-plugin/plugin.json остаётся поддерживаемым compatibility-форматом, но для новых пакетов OpenAI рекомендует переносимый plugin.json в корне с $schema: "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json". Специфичные для OpenAI настройки размещаются в extensions.com.openai; если этот объект присутствует, он заменяет compatibility-overlay целиком, а не объединяется с ним.
Для запрошенного .codex-plugin/plugin.json простой skills-only вариант выглядит так: {"name":"module-a","version":"1.0.0","description":"Module A workflows","skills":"./skills/"}. Каталог skills/ находится в корне плагина; команды, MCP и приложения для такого пакета не нужны. Генератор @plugin-creator пока создаёт именно compatibility-layout и объявляет skills: "./skills/". В новом переносимом формате поле skills не требуется: корневой skills/ обнаруживается по соглашению.
Repository marketplace объявляется в $REPO_ROOT/.agents/plugins/marketplace.json. Пример содержимого: {"name":"repo-tools","plugins":[{"name":"module-a","source":{"source":"local","path":"./modules/a/ai-plugin"},"policy":{"installation":"AVAILABLE","authentication":"ON_INSTALL"},"category":"Productivity"}]}. Путь разрешается относительно корня marketplace — здесь корня репозитория, не каталога .agents/plugins/. Добавляйте отдельную запись в plugins[] для каждого плагина. Наличие каталога делает плагины обнаруживаемыми, но не означает автоматического включения всех пакетов.
Да, standalone skills обнаруживаются из .agents/skills/: Codex проверяет такие каталоги от текущей рабочей директории вверх до корня Git-репозитория. Это не рекурсивное сканирование всех соседних модулей вниз.
Документация: https://developers.openai.com/plugins/build/plugins и https://developers.openai.com/codex/skills.

## 3. Гранулярность в монорепозитории и контекст

Для независимых модулей я рекомендую отдельный плагин на модуль в одном marketplace, а общие действительно переиспользуемые skills — в небольшом shared-плагине. Это архитектурный вывод, не обязательное правило Anthropic/OpenAI: он даёт независимые версии, владельцев и выборочное включение. Агрегирующий library-плагин разумен, если весь набор всегда нужен вместе и выпускается синхронно. OpenAI прямо допускает множество плагинов в одном marketplace и индивидуальное включение/выключение.
Само разбиение не экономит контекст, если включены все те же skills. У обоих инструментов сначала загружаются метаданные, а полный SKILL.md — при использовании. В Codex начальный список содержит имя, описание и путь; бюджет составляет максимум 2% окна контекста либо 8 000 символов при неизвестном размере окна. При переполнении описания сокращаются, затем часть skills может исключаться с предупреждением.
Claude загружает описания model-invocable skills при старте; disable-model-invocation: true исключает описание до явного вызова. Для чисто локальных модульных workflows плагины необязательны: вложенные skill-каталоги обеспечивают область обнаружения; у Claude вложенные skills также подгружаются при работе с файлами модуля.
Подробнее о контексте: https://code.claude.com/docs/en/features-overview#understand-context-costs.

Sources:
1. [code.claude](https://code.claude.com/docs/en/skills)
2. [https://code.claude.com/docs/en/plugins/manifest-reference](https://code.claude.com/docs/en/plugins/manifest-reference)
3. [https://code.claude.com/docs/en/skills#resolve-skills-that-share-a-name](https://code.claude.com/docs/en/skills#resolve-skills-that-share-a-name)
4. [developers.openai](https://developers.openai.com/plugins/build/plugins)
5. [developers.openai](https://developers.openai.com/codex/skills)
6. [https://code.claude.com/docs/en/features-overview#understand-context-costs](https://code.claude.com/docs/en/features-overview#understand-context-costs)