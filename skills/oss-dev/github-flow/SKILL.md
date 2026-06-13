---
name: github-flow
bucket: oss-dev
version: 0.2.0
description: "Цепочка Issue → Branch → PR → Merge → Tag → Release на GitHub: naming, labels, SemVer-оракул по типам коммитов, шаблоны Issue/PR. Формат коммитов — git-commit-rules, changelog и pipeline — release-engineering, ревью PR — gh-review."
risk: write
persona: oss-dev
tags: [oss, github, git, semver, release]
requires: [git-commit-rules, release-engineering, gh-review]
produces_for: []
outputs: [".github/PULL_REQUEST_TEMPLATE.md", ".github/ISSUE_TEMPLATE/"]
snippets: [pull-request-template.md, issue-templates.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: GitHub Flow

Применять когда: изменения в OSS-репозитории на GitHub ведутся **от Issue до релиза** и агент участвует в этой цепочке: создаёт Issue/PR через `gh`, именует ветки, назначает labels, определяет следующую версию по коммитам, создаёт тег и GitHub Release.

Разделение ответственности с соседями:
- **формат и стиль commit message** (типы, scopes, BREAKING CHANGE) — `general/git-commit-rules`;
- **SemVer-контракт пакета, CHANGELOG-формат, release pipeline, pre-releases, deprecation** — `oss-dev/release-engineering`;
- этот скилл — **процессная цепочка между ними**: как Issue превращается в ветку, ветка в PR, PR в тег и релиз.

---

## Когда НЕ применять

- Репозиторий не на GitHub (GitLab, внутренний git без Issues) — взять только `git-commit-rules`.
- Нужно формализовать сам релизный процесс (что считается MAJOR, политика deprecation) — это `release-engineering`.
- Разовый фикс в чужом форке без права на Issues/labels — обычный PR по правилам апстрима, не этот flow.

---

## Lifecycle

```
Issue → Branch → Commits → PR → Review → Merge → SemVer Oracle → Tag → GitHub Release
  ▲                          ▲                        ▲             ▲
  вопросы агента             вопросы агента           подтверждение  только после
  (тип/приоритет)            (issues/changelog)       версии         merge
```

Контрольные точки, где агент **обязан остановиться и спросить**:
1. Перед созданием Issue — тип, приоритет, компонент, версия воспроизведения.
2. Перед созданием PR — связанные Issues, тип изменения, нужен ли CHANGELOG-entry.
3. Перед тегом — подтверждение версии, предложенной SemVer-оракулом.

---

## Issues

### Обязательные вопросы перед созданием

1. **Тип** — bug | feature | enhancement | security | docs | refactor | chore
2. **Приоритет** — critical | high | normal | low
3. **Затронутый компонент** (из карты проекта, если есть `project-map`)
4. **Версия пакета**, в которой воспроизводится проблема (для bug/security)

### Заголовок

```
[type] Краткое описание в повелительном наклонении (до 72 символов)
```

Примеры: `[bug] Fix config cache invalidation on publish`, `[feature] Add scoped token resolution`.

### Labels по типу

| Тип Issue | Labels |
|:---|:---|
| bug | `bug`, `needs-triage` |
| feature / enhancement | `enhancement` |
| security | `security`, `priority:critical` |
| docs | `documentation` |
| refactor | `refactor`, `tech-debt` |
| chore | `chore` |

Meta-labels `semver:patch` / `semver:minor` / `semver:major` агент проставляет по оценке влияния (см. SemVer Oracle), `semver:major` — только после подтверждения пользователем.

---

## Branch Naming

Формат: `<type>/<issue-number>-<slug>`

- slug: строчные буквы, цифры, дефисы; до 50 символов после `<type>/`.
- Типы веток: `feat/`, `fix/`, `hotfix/`, `docs/`, `refactor/`, `chore/`, `security/`.
- Ветка создаётся после подтверждения Issue; заголовок брать из `gh issue view <N>`.

```
feat/42-scoped-token-resolution
fix/17-config-cache-invalidation
security/38-path-traversal-loader
```

---

## Pull Requests

### Перед созданием агент запрашивает или вычисляет

1. Связанные Issues (`Closes #N` / `Refs #N`)
2. Тип изменения — bugfix | feature | breaking | security | docs
3. Затронутые компоненты (из diff)
4. Нужен ли CHANGELOG-entry (правила секций — `release-engineering`)

### Заголовок

```
<type>(<scope>): <description> (#<issue>)
```

Пример: `feat(provider): scoped token resolution (#42)`. Формат типа/scope — по `git-commit-rules`.

### Тело и labels

Тело PR — по шаблону `snippets/pull-request-template.md` (копируется в `.github/PULL_REQUEST_TEMPLATE.md`). Labels зеркалятся с Issue, плюс:

- `ready-for-review` — когда PR выходит из draft;
- `needs-changelog` — CHANGELOG не обновлён;
- `breaking-change` — есть `BREAKING CHANGE` footer или `!` в типе.

### Review

Сам шаг ревью (чтение диффа, треды, публикация находок) — через `gh`, не
загрузкой файлов целиком: `gh pr diff <N>`, `gh pr view <N> --comments`,
`gh pr review <N> --approve|--request-changes -b "..."`. Полный алгоритм и
экономия контекста — скилл **`oss-dev/gh-review`**; критерии и severity находок
— `quality/code-review`.

---

## SemVer Oracle — следующая версия по коммитам

Анализ коммитов между последним тегом и HEAD: `git log $(git describe --tags --abbrev=0)..HEAD --pretty=format:"%s" --no-merges`.

| Найдено в коммитах | Bump |
|:---|:---|
| `BREAKING CHANGE` footer или `!` после типа (`feat!:`) | MAJOR |
| `feat` (без breaking) | MINOR |
| `fix`, `perf`, `security` | PATCH |
| только `docs`, `style`, `refactor`, `test`, `build`, `ci`, `chore` | нет (релиз не нужен) |

Берётся максимальный bump по всем коммитам. Что именно считается breaking **для этого пакета** — определяет SemVer-контракт из `release-engineering` (RELEASING.md); при конфликте контракт важнее типа коммита.

### Диалог подтверждения

```
Текущая версия: 1.4.2 (последний тег)
Коммиты с тега: feat(2), fix(1), docs(3)
Предлагаемая версия: 1.5.0
Подтвердить / указать вручную / отменить?
```

### Формат тегов

`vX.Y.Z` — stable; `vX.Y.Z-alpha.N` / `-beta.N` / `-rc.N` — pre-releases (политика pre-release и dist-tags — `release-engineering`).

---

## Merge → Tag → Release

Тег создаётся **только после**: подтверждения версии пользователем, обновления CHANGELOG (секция новой версии с датой), merge PR в default-ветку.

```
1. git checkout main && git pull
2. секция [Unreleased] → [X.Y.Z] - YYYY-MM-DD в CHANGELOG.md
3. bump версии в манифесте пакета (если поле version используется)
4. git commit -m "chore(release): ..." (стиль — git-commit-rules)
5. git tag vX.Y.Z -m "Release vX.Y.Z" && git push origin main --tags
6. gh release create vX.Y.Z --notes-file <CHANGELOG-секция>
7. publish в registry — через CI по тегу, не руками
```

Готовый workflow — `devops/ci-cd/snippets/github-actions-release.yml`; правила pipeline (только из тегов, provenance, 2FA) — `release-engineering`.

---

## Что агент добавляет сам

- **`.github/PULL_REQUEST_TEMPLATE.md` и `ISSUE_TEMPLATE/`** из snippets, если их нет в репо — предложить добавить при первом PR/Issue.
- **Связку Issue ↔ PR.** `Closes #N` в footer коммита или тело PR — Issue закроется при merge автоматически.
- **Чистку веток.** После merge предложить удалить ветку (`gh pr merge --delete-branch`).
- **Языковую специфику релиза.** Для PHP-пакетов — пройти gate из `references/php-package-gate.md` перед тегом.

---

## Ссылки

- [references/php-package-gate.md](references/php-package-gate.md) — composer.json gate, keywords, Packagist-деплой
- [snippets/](snippets/) — шаблоны PR и Issue
- `../release-engineering/SKILL.md` — SemVer-контракт, CHANGELOG, pipeline, deprecation
- `../gh-review/SKILL.md` — ревью/хендофф PR через gh с экономией контекста
- `../../general/git-commit-rules/SKILL.md` — формат коммитов, scopes, BREAKING CHANGE
- `../../devops/ci-cd/snippets/github-actions-release.yml` — release workflow по тегу

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Создавать Issue/PR, не получив ответы на обязательные вопросы (тип, приоритет, связанные Issues).
- Пушить тег до merge PR в default-ветку.
- Назначать `semver:major` / делать MAJOR-bump без явного подтверждения пользователя.
- Бампить версию пакета внутри feature/fix-PR — только в релизном коммите.
- Дублировать SemVer-контракт пакета — он живёт в RELEASING.md (`release-engineering`).
- Force-push в ветку с открытым review без предупреждения ревьюеров.
