# Post-Integration Checklist — проверка после внедрения

Скилл `system/agent-packs` ПРОГОНЯЕТ этот чеклист после каждого install/upgrade пака;
`skiller doctor` — по требованию. Цель — гарантировать целостность и **отсутствие
конфликтов**. На любой находке install/upgrade считается НЕзавершённым.

## Целостность пака

- [ ] `.claude/agent-pack.lock.json` есть, валиден (JSON парсится), `version` совпадает с `pack.json`.
- [ ] Все файлы из `lock.files[].target` существуют; нет осиротевших (в lock есть, на диске нет).
- [ ] Нет коллизий путей между несколькими установленными паками.

## Settings и хуки (главное по конфликтам)

- [ ] `.claude/settings.json` парсится как JSON.
- [ ] Хуки, что были ДО установки, на месте: `diff` против `.claude/settings.json.bak`
      не показывает удалённых записей (только добавленные).
- [ ] `review-gate.sh` исполняемый (`test -x`), `bash -n` без ошибок.
- [ ] review-gate зарегистрирован на `SubagentStop` ровно ОДИН раз (нет дублей).
- [ ] (Agent Teams) `TeammateIdle`/`TaskCompleted` зарегистрированы по разу; не конфликтуют
      с `PreToolUse`(auto-approve)/`SubagentStop`(review-gate) — события разные.

## Агенты и скиллы (фикс «скиллы не видны»)

- [ ] Каждый агент `.claude/agents/*.md`: валидный frontmatter (`name`, `description`).
- [ ] ВСЕ имена в `skills:` агентов существуют в `skills.json` — ноль silent no-op
      (иначе `⚠` в hub + находка `skiller doctor`).
- [ ] Нет дублей `name` среди `.claude/agents/*` и агентов включённых плагинов.
- [ ] `tools:`-scope осмысленный (read-only роли без Edit/Write).

## Воркфлоу и правила

- [ ] Каждый `.claude/workflows/*.js`: `node --check` без ошибок (на отрендеренном).
- [ ] Каждый `.claude/rules/*.md` (если есть): валидный `paths:` frontmatter; правило
      не дублирует текст скилла (ссылается на него) — нет «правила в трёх местах».

## Hub и Boost

- [ ] Hub перегенерён (`generate-hub.sh`): есть agent-routing срез; `⚠`-несостыковок ноль; freshness свежий.
- [ ] В Boost-проекте: блок в `.ai/guidelines/swissknifeman-hub.md` обновлён; НЕ трогали
      сгенерённые CLAUDE.md/AGENTS.md; напоминание `php artisan boost:update` выдано.

## Поведение проекта

- [ ] Тесты проекта зелёные (для ретрофита/upgrade — behavior-preserving).

## Формат вывода

Компактный отчёт: `PASS` или список находок по разделам. При находках —
конкретный шаг починки, install/upgrade не закрывается.
