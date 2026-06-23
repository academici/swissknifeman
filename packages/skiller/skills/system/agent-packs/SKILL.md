---
name: agent-packs
bucket: system
version: 0.1.0
description: "Установка и ВЕРСИОНИРОВАННЫЙ апгрейд agent-packs (агенты/воркфлоу/хуки Claude Code) из harness в проект-потребитель: детект стека -> интервью -> рендер+копия -> lock; апгрейд по CHANGELOG-дельте с 3-way reasoning через sha256 в lock, без diff-движка. Активировать при словах: внедрить/обновить agent-pack, поставить роли+dev-loop+review-gate в проект, версионный upgrade шаблонов агентов, agent-pack.lock."
risk: write
persona: architect
tags: [agent-packs, templates, versioning, upgrade, install, claude-code, harness, lock]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude]
sha256: ""
---

# Agent Packs — установка и версионный апгрейд

## Контекст

**Пак** — версионируемый бандл артефактов Claude Code (агенты `.claude/agents/`,
воркфлоу `.claude/workflows/`, хуки, фрагмент `settings`, guideline-доки), который
живёт в `harness/configs/claude-code/agent-packs/<pack>/` и **устанавливается агентом**
в проект-потребитель. Раздаются ДАННЫЕ (`pack.json` + `CHANGELOG.md` + шаблоны), а
установку/адаптацию/upgrade выполняет агент по понятным метаданным — **без
Python/Mustache движка-генератора**.

Ценность версионности: правишь пак в одном месте, а проекты обновляются по changelog
с сохранением локальных адаптаций. Состояние внедрения проект хранит в
`.claude/agent-pack.lock.json` (коммитится с проектом, как `composer.lock`).

## Когда активировать

- «Внедри agent-pack / поставь роли + dev-loop + review-gate в проект».
- «Обнови agent-pack» (вышла новая версия пака в harness).
- Нужен версионируемый набор агентов/воркфлоу/хуков вместо ручного копирования.

**Анти-триггер:** правка ОДНОГО агента/воркфлоу под конкретную задачу — правь файл
напрямую, пак не трогай (паки — про версионируемый НАБОР, не про разовую правку).

## Манифест пака (`pack.json`)

```jsonc
{
  "schema": 1, "pack": "<name>", "version": "0.1.0", "description": "...",
  "stack": { "shape": "backend|frontend|fullstack", "framework": "...",
             "detect": { "all_of": ["artisan", "composer.json"] } },
  "requires": { "skills": ["..."], "harness_presets": ["base", "laravel"] },
  "interview": [ { "id": "PACK_PREFIX", "q": "...", "default": "{project_dirname}",
                   "kind": "slug|bool|enum", "detect": "<shell|file-hint>" } ],
  "files": [ { "src": "agents/reviewer.md",
               "target": ".claude/agents/{PACK_PREFIX}-reviewer.md",
               "kind": "template|verbatim|merge", "role": "agent",
               "user_owned": false } ]
}
```

`kind`: **template** — подставить `{{PLACEHOLDER}}` из ответов + разрешить блоки
`<!-- pack:if KEY -->...<!-- pack:endif -->` по булеву ответу, записать. **verbatim** —
скопировать без правок (+ chmod, если задан). **merge** — JSON-merge в существующий
файл проекта append-if-absent. `user_owned: true` — файл правит пользователь
(например `.env.ini`): на апгрейде НИКОГДА не перезаписывается молча.

## Install — алгоритм

1. **Детект стека.** Выполни `stack.detect` (например `test -f artisan && test -f
   composer.json`); подбери подходящий(е) пак(и). Префилл дефолтов из детекта.
2. **Интервью — только проектное.** Спрашивай лишь `interview[]`, что не определилось
   детектом; покажи дефолт, дай принять. (Неоднозначный `TEST_FRAMEWORK` —
   спрашивай явно: неверная догадка тихо портит вывод агентов.)
3. **Предусловия.** Проверь `requires.harness_presets` (предложи
   `harness permissions --target . --preset ...`) и `requires.skills` (через
   `skm:skills`/профиль). Warn, не hard-fail.
4. **Рендер + копия.** Для каждого `files[]`: подставь `{PLACEHOLDER}` в `target` и
   (для `template`) в контент; разреши `pack:if`-блоки; запиши. `verbatim` — копия +
   chmod. `merge` — JSON-merge фрагмента append-if-absent (бэкап `.bak`, не затирай
   чужие хуки).
5. **Lock.** Создай `.claude/agent-pack.lock.json` (схема ниже): версия, ответы,
   `files[]` с `base_sha256` ОТРЕНДЕРЕННОГО контента.
6. **Пост-проверка.** Прогони чеклист `docs/skiller/agent-framework/post-integration-checklist.md`.
   Воркфлоу проверяй балансом скобок/непустотой (top-level return/await — `node --check` НЕ применять).

## Lock (`.claude/agent-pack.lock.json`)

```jsonc
{ "schema": 1, "packs": {
    "<pack>": {
      "version": "0.1.0",
      "source": "harness:configs/claude-code/agent-packs/<pack>",
      "answers": { "PACK_PREFIX": "...", "PHP_RUNNER": "...", "...": "..." },
      "files": [ { "src": "agents/reviewer.md",
                   "target": ".claude/agents/<prefix>-reviewer.md",
                   "kind": "template",
                   "base_sha256": "<sha256 ОТРЕНДЕРЕННОГО при install>",
                   "local_modified": false } ],
      "removed_optional": [] } } }
```

Три поля делают апгрейд возможным БЕЗ diff-движка: **version** (откуда дельта),
**answers** (детерминированный ре-рендер новой версии), **files[].base_sha256**
(хэш того, что мы записали → расхождение = одно сравнение хэшей).

## Upgrade — алгоритм (сердце)

1. **Дельта.** Из `CHANGELOG.md` собери версии `(V_old, V_new]`: их «Migration notes»
   + изменения по файлам.
2. **Ре-интервью только нового.** Если notes объявили новый `interview`-ответ —
   спроси только его; иначе используй `lock.answers`.
3. **3-way по файлу (без diff-движка):**
   - `local_modified` = `sha256(файл_на_диске) != lock.base_sha256` (правлен локально).
   - `base_changed` = `sha256(ре-рендер V_new с answers) != lock.base_sha256` (изменилось вверху).
4. **Категории:**
   - **safe-apply** (`base_changed && !local_modified`) → перезаписать ре-рендером.
   - **conflict** (`base_changed && local_modified`) → НЕ перезаписывать; показать
     дельту из CHANGELOG; опц. положить `<target>.pack-new` для ручного merge.
   - **new-optional** (файл новый, в CHANGELOG помечен OPTIONAL) → предложить опт-ин.
   - **removed** (был в lock, нет в `V_new.files`) → НЕ удалять авто; спросить.
   - **user_owned** — даже при `base_changed` не перезаписывать; лишь упомянуть новый дефолт.
5. **План → подтверждение → применить.** Покажи categorized-план, дождись согласия,
   применяй (бэкап `.bak`), затем **bump lock**: `version=V_new`, пересчитай все
   `base_sha256`, обнови `local_modified` и `answers`. Conflict-файлы оставь с
   `local_modified:true` и пометкой отложенного апгрейда.

## Безопасность от конфликтов

- settings — merge-only append-if-absent (event,matcher,command); не плодить дубль хука.
- Boost-проект — НЕ трогать сгенерённые CLAUDE.md/AGENTS.md (всё в `.ai/guidelines/` +
  `boost:update`).
- Имена агентов под `{PACK_PREFIX}` — проверить коллизии с существующими и с агентами плагина.
- Несколько паков — детект коллизий путей (общий verbatim с идентичным контентом → skip).
- Никогда не авто-удалять файлы проекта и не перезаписывать локально-правленые.

## Анти-паттерны

- Движок-генерация (Mustache/Python) вместо агент-driven рендера.
- Авто-перезапись локально-правленого файла или авто-удаление removed-файла.
- Ре-интервью ответов, которые не менялись между версиями.
- Per-template версии (версия — per-PACK).
- `node --check` к dev-loop-воркфлоу (top-level return/await — ложно падает).

## Чеклист качества

- [ ] Стек определён детектом; интервью только по проектному (не доопределённому).
- [ ] Все `template`-файлы отрендерены (нет остаточных `{{...}}`); `verbatim` скопированы + chmod.
- [ ] `merge` влит append-if-absent с `.bak`; чужие хуки целы.
- [ ] Lock записан/обновлён; `base_sha256` = хэш отрендеренного; `answers` полны.
- [ ] Upgrade: conflict-файлы показаны, НЕ перезаписаны; removed не удалён авто.
- [ ] Пройдена пост-проверка (post-integration-checklist).

## Ссылки

- `harness/configs/claude-code/agent-packs/` — базы паков (источник истины).
- `docs/skiller/agent-framework/` — модель каркаса; `post-integration-checklist` — пост-проверка.
- `php/laravel-subagents` — протокол оркестрации, который реализуют роли пака.
- `general/context-economy`, `general/session-handoff` — контекст основной сессии при делегировании.
