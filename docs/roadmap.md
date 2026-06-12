# Roadmap

Идеи развития пакета. Порядок внутри блоков — примерный приоритет;
реализация — по мере реальной потребности, в духе принципа «сначала каркас,
наполнение постепенно».

## Ближайшая фаза

**Миграция собственных скиллов из локальных проектов.** Анализ наработок
в проектах из `.skills-scanner.json`, перенос универсальной части в реестр
(через [сканер](/guide/scanner) и вручную), затем подключение в проекты через
`swissknifeman connect` / `swissknifeman vendor` и удаление локальных копий —
чтобы источник истины был один.

**Vendor-skills в боевых пакетах.** Применить
[механизм публикации скиллов](/guide/vendor-skills) в собственных open-source
пакетах: `resources/skills/` + публикация в ServiceProvider + тест полного
цикла `composer install → vendor:publish → агент видит скилл`.

**Наполнение `configs/`.** Преднастроенные субагенты (`.claude/agents/`),
хуки (автоформатирование, валидация перед коммитом), проверенные `.mcp.json`,
конфиги других IDE — см. [обзор конфигов](/configs/).

## Стратегические

- **Skills Marketplace UI** — веб-интерфейс поверх реестра: поиск по тегам,
  просмотр сниппетов, кнопка «Install to project». Минимум: VitePress +
  GitHub API (документация уже на VitePress — половина пути пройдена).
- **Skill Composition** — `extends: laravel` во frontmatter: агент загружает
  родительский контекст перед выполнением дочернего скилла. Аналог наследования.
- **Versioned Snapshots** — SemVer-теги на репозиторий и pin версии
  в `swissknifeman vendor` (`swissknifeman@1.2.0`). Потребители фиксируют версию,
  а не latest; sha256 в реестре уже есть.
- **Skill Chains (pipeline)** — граф `requires` / `produces_for` уже есть
  во frontmatter. Идея: визуализировать как DAG и выполнять цепочку
  `founder.idea-discovery → pm.brd → architect.architecture` одним вызовом.

## Технические

- **Auto-scoring сниппетов** — GitHub Action: при PR с новым сниппетом
  запускать phpcs/phpstan/hadolint и писать score в `index.json`; кандидаты
  ниже порога из `.skills-scanner.json` блокируются автоматически.
- **Obsidian-плагин** — `skills.json` в sidebar, открытие SKILL.md,
  вставка сниппета в заметку командой `/skill`.
- **MCP-сервер для скиллов** — `get_skill(name)`, `list_skills(bucket)`,
  `search_snippets(query)` через MCP вместо чтения файлов:
  skills-as-a-service для любого MCP-совместимого агента.
- **Quality badges** — автогенерируемые бейджи скилла: `snippets: 5`,
  `used_in: 3 projects`, `last_tested: <дата>`.

## Экспериментальные

- **LLM-generated Gap Analysis** — ежемесячный агент анализирует PR и issues
  в рабочих проектах, находит паттерны, не покрытые скиллами, и создаёт
  draft-PR с новыми SKILL.md.
- **Cross-repo Snippet Leaderboard** — отслеживать, какие сниппеты копируются
  в проекты и насколько остаются неизменными (высокое сходство = хороший сниппет).
- **Skill Health Monitor** — GitHub Action по расписанию: проверять, что
  сниппеты компилируются / проходят lint на актуальных версиях PHP, Node, Docker.
