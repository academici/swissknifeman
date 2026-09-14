# Roadmap

Идеи развития пакета. Порядок внутри блоков — примерный приоритет;
реализация — по мере реальной потребности, в духе принципа «сначала каркас,
наполнение постепенно».

Каталог отложенных тем в `roadmap/` ведётся отдельно от этой обзорной страницы: после
`2026.07.31-SKM-LEAN` у каждой его записи есть явный адрес — закрывший item, решение,
переезд или структурный критерий возврата. Эта страница оставляет только тематические
направления, а не дублирует рабочий каталог.

Инциденты Task от 10–11 сентября 2026 сведены в одно аудит-задание
`tasks/2026.09.11-task-execution-cost/README.md` в репозитории. Локальные исправления завершены:
direct-close на обычном GREEN пути, проверки по риску с reuse актуального evidence и закрытие
текущего пункта в той же сессии. Позднейший Delivery обновил и подтвердил 19 consumer roots,
но четыре остались заблокированы без перезаписи. Причины version/cache/ownership drift и
проект исправления собраны в
[`release-to-runtime attestation and recovery`](../roadmap/archive/2026.09.11-release-to-runtime-attestation-and-recovery.md).
Исходные Task roadmap-записи сохранены рядом с заданием.

Полевая регрессия 13 сентября закрыла непрерывное исполнение compatible ready batch и выбор
`plan-design` для уже детализированной незавершённой фазы. Но 14 сентября в Edufy повторился
terminal output gap: `handoff.md` и delivery receipt содержали native launch, а user-facing final
его не вывел. Живой roadmap-carrier
[`task terminal command emission regression`](../roadmap/2026.09.14-task-terminal-command-emission-regression.md)
задаёт обязательный finalization seam и регрессионные проверки; архивный результат не считается
достаточным, пока это не станет write-site enforcement.

## Ближайшая фаза

**Полевые исправления 2026-09-13 реализованы.** Task сохраняет явный opt-in маршрут,
восстанавливает незавершённый predecessor и отделяет finite owner authority от external/calendar wait.
Релиз проверяет immutable `(unit, version) → bytes`; delivery сохраняет общий owner-union lock,
восстанавливает только известные preimages и проверяет cache/project bytes по digest.
Оригиналы сохранены в `roadmap/archive/`; фактический результат fleet находится в machine-local receipt.

**Миграция собственных скиллов из локальных проектов.** Анализ наработок
в проектах из `.skills-scanner.json`, перенос универсальной части в реестр
(через [сканер](/skiller/guide/scanner) и вручную), затем подключение в проекты через
`skiller connect` / `skiller vendor` и удаление локальных копий —
чтобы источник истины был один.

**Vendor-skills в боевых пакетах.** Применить
[механизм публикации скиллов](/skiller/guide/vendor-skills) в собственных open-source
пакетах: `resources/skills/` + публикация в ServiceProvider + тест полного
цикла `composer install → vendor:publish → агент видит скилл`.

**Наполнение `configs/`.** Преднастроенные субагенты (`.claude/agents/`),
хуки (автоформатирование, валидация перед коммитом), конфиги других IDE — см.
[обзор конфигов](/harness/configs/). Проверенные `.mcp.json` уже раздаются пресетами
(`context7` + курированный сабсет) — каталог в разделе [Интеграции](/harness/integrations/).

## Стратегические

- **Межпроектный агент-оптимизатор** — read-only обзор реализован как
  `system/cross-project-coordinator` (скилл) + агент `code-coordinator`: поверх
  топологии обходит связанные проекты (`git ls-files`, уважает `.gitignore`),
  находит дубли/расхождения/кандидатов в общий пакет и выдаёт приоритизированный
  отчёт. **Дальше:** перевод находок в действие — авто-вынесение в общий пакет и
  PR в целевые проекты (сейчас правки делает человек); связь с памятью —
  координатор пишет межпроектные факты в общий «мозг».
- **Skills Marketplace UI** — веб-интерфейс поверх реестра: поиск по тегам,
  просмотр сниппетов, кнопка «Install to project». Минимум: VitePress +
  GitHub API (документация уже на VitePress — половина пути пройдена).
- **Skill Composition** — `extends: laravel` во frontmatter: агент загружает
  родительский контекст перед выполнением дочернего скилла. Аналог наследования.
- **Versioned Snapshots** — SemVer-теги на репозиторий и pin версии
  в `skiller vendor` (`swissknifeman@1.2.0`). Потребители фиксируют версию,
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
