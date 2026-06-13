---
name: gh-review
bucket: oss-dev
version: 0.1.0
description: "Ревью и хендофф изменений через GitHub CLI (gh) с экономией контекста: gh pr diff/view/comment/review, gh api для точечного чтения файлов вместо загрузки целиком. Активировать при ревью PR, передаче работы dev'у, чтении чужих изменений на GitHub."
risk: write
persona: oss-dev
tags: [github, gh, review, handoff, tokens, context]
requires: [context-economy]
produces_for: [github-flow]
outputs: []
snippets: [gh-review-commands.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: GitHub Review через gh

## Контекст

Платформенный слой работы с изменениями (PR, ревью-треды, чужой код на GitHub)
проходит через **`gh`**, а не через чтение файлов целиком и не через веб-UI.
Это не замена `git`: локальный VCS (`commit`, `branch`, `diff` рабочего дерева,
`log`, `rebase`) остаётся за `git` — `gh` его не умеет. Разделение:

- **Локально** → `git` (история, ветки, состояние рабочего дерева).
- **Платформа / совместная работа** → `gh` (PR, issue, review, release,
  `gh api`).

**Почему это экономит токены.** `gh pr diff 12` отдаёт *только* дифф;
`gh pr view 12 --comments` — *только* треды ревью; `gh api .../contents/<path>`
— *один* файл. Альтернатива — загрузить весь файл/каталог/историю в контекст —
тратит токены на то, что не относится к задаче. Контекст — постоянный налог
(см. `context-economy`); ревью через `gh` держит в окне только релевантный срез.

## Когда активировать

- Ревью pull request (свой или чужой).
- Передача работы dev'у / приём чужой работы (handoff) на GitHub.
- Нужно прочитать чужие изменения, тред обсуждения, статус проверок.
- Импорт/сверка внешнего скилла из GitHub-репозитория (точечный fetch).

Анти-триггер: чисто локальные операции (коммит, ветка, разрешение конфликтов
рабочего дерева) — это `git`, не `gh`.

## Алгоритм

### 1. Читай ревью-контекст точечно, не файлами

Вместо «прочитать весь PR/файлы» — минимальный срез под задачу:

```bash
gh pr view <N>                      # заголовок, описание, статус, чеклисты
gh pr view <N> --comments           # только треды ревью/обсуждения
gh pr diff <N>                      # только дифф (не файлы целиком)
gh pr diff <N> -- path/to/file      # дифф одного пути
gh pr checks <N>                    # статусы CI без логов целиком
gh pr view <N> --json files -q '.files[].path'   # список затронутых путей
```

Файл целиком тяни **только если diff недостаточен** — и точечно через `gh api`
(см. шаг 3), а не загрузкой локального файла, если он не в рабочем дереве.

### 2. Постит ревью через gh, не вручную в UI

```bash
gh pr comment <N> --body "..."                      # одиночный комментарий
gh pr review <N> --comment -b "..."                 # ревью без вердикта
gh pr review <N> --approve -b "LGTM: ..."           # апрув
gh pr review <N> --request-changes -b "..."         # запрос правок
```

Находки группируй по severity (как в `quality/code-review`); в теле — путь и
строка, не пересказ файла.

### 3. Точечное чтение файлов из чужого репозитория

Для импорта/сверки внешнего кода без клонирования:

```bash
# содержимое одного файла на ветке/теге (base64 в .content)
gh api repos/{owner}/{repo}/contents/{path}?ref={ref} \
  -q '.content' | base64 -d

# список файлов каталога без скачивания содержимого
gh api repos/{owner}/{repo}/contents/{dir}?ref={ref} -q '.[].path'

# метаданные коммита/тега (когда менялся файл) — для upstream-дрейфа
gh api repos/{owner}/{repo}/commits?path={path}\&per_page=1 -q '.[0].sha'
```

Это канал для **импортируемых скиллов**: `gh api` авто-аутентифицируется
(токен из `gh auth`), уважает rate-limit и отдаёт один файл — против загрузки
всего репозитория. Связка с `scripts/update-upstreams.sh` и `upstream.json`
(`source: github`) — см. `docs/guide/upstream-sync.md`.

### 4. Handoff: оставляй ссылку, не дамп

Передавая работу — ссылайся на артефакт через `gh`, не вставляй его телом:

```bash
gh pr view <N> --json url -q .url           # ссылка на PR
gh issue view <N> --json url -q .url        # ссылка на issue
```

Следующий агент/разработчик подтянет нужный срез сам тем же `gh`, не неся
весь контекст из предыдущей сессии (см. `session-handoff`).

## Чеклист качества

- [ ] Ревью-контекст взят точечно (`gh pr diff`/`--comments`), не загрузкой файлов целиком
- [ ] Чужой файл прочитан через `gh api .../contents`, а не клонированием/полной загрузкой
- [ ] Находки запостены через `gh pr comment`/`gh pr review`, а не в веб-UI
- [ ] Локальные VCS-операции оставлены за `git` (gh их не дублирует)
- [ ] Handoff — ссылкой на PR/issue через `gh`, не дампом артефакта в контекст

## Ссылки

- snippets/gh-review-commands.md — шпаргалка команд
- `general/context-economy` — общая дисциплина расхода токенов (раздел про gh)
- `oss-dev/github-flow` — процесс Issue→PR→Merge→Release (ревью-шаг ссылается сюда)
- `quality/code-review` — критерии и severity находок
- `docs/guide/upstream-sync.md` — gh-fetch при импорте внешних скиллов
