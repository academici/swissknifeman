---
name: gitops
bucket: devops
version: 0.3.0
description: "Командная Git-стратегия: модель веток (main/develop/feature/hotfix), PR-workflow, защита веток"
risk: read
persona: operator
tags: ["git", "gitops"]
requires: []
produces_for: []
outputs: []
snippets: ["branch-strategy.md", "commit-conventions.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Стандартизация Git workflow для команды: модель веток, PR-процесс, защита веток.

**Границы скилла**: gitops — это *командная стратегия* (какие ветки существуют, как код попадает в `main`, кто и как мержит). Формат сообщений коммитов и порядок локальных действий перед коммитом — скилл `general/git-commit-rules` (husky/commitlint, безопасный порядок `git add`/`git commit`).

## Модель веток

| Ветка | Назначение | Откуда | Куда мержится |
|:---|:---|:---|:---|
| `main` | production, всегда деплоябельна | — | — |
| `develop` | интеграция (если используется gitflow-lite) | `main` | `main` через release-PR |
| `feat/*` | новая функциональность | `develop` (или `main` при trunk-based) | `develop`/`main` через PR |
| `fix/*` | исправление бага | `develop`/`main` | через PR |
| `chore/*` | обслуживание (CI, зависимости, конфиги) | `develop`/`main` | через PR |
| `hotfix/*` | срочный фикс прода | `main` | `main` + обратный мерж в `develop` |

Именование: `feat/<ticket>-short-description`, kebab-case, без личных префиксов.

## PR-workflow

1. Ветка от актуального `main`/`develop` (`git fetch` + `git switch -c feat/... origin/develop`).
2. Небольшие атомарные коммиты (формат — `general/git-commit-rules`).
3. PR: заголовок в стиле conventional commit, описание «что/зачем/как проверить», линк на тикет.
4. CI зелёный + минимум один аппрув → merge. Стратегия merge: squash для feature-веток (одна логическая единица в истории), merge-commit для release/hotfix.
5. Ветка удаляется после мержа.

## Защита веток

- `main` (и `develop`): запрет прямых пушей, обязательный PR, обязательный зелёный CI, минимум 1 review, запрет force-push.
- Hotfix не обходит защиту — тот же PR-процесс, но с ускоренным ревью.

## Когда какой сниппет

| Сниппет | Когда открывать |
|:---|:---|
| `branch-strategy.md` | настройка веточной модели нового репозитория, спор «откуда ветвиться» |
| `commit-conventions.md` | быстрая шпаргалка по типам conventional commits (детали — `general/git-commit-rules`) |

## Чеклист

- [ ] Ветка названа по конвенции (`feat/*`, `fix/*`, `chore/*`, `hotfix/*`)
- [ ] Ветка создана от актуального базового бранча
- [ ] Изменения попадают в защищённые ветки только через PR
- [ ] CI зелёный, есть аппрув, выбрана правильная merge-стратегия
- [ ] Hotfix смержен и в `main`, и обратно в `develop` (если develop используется)
- [ ] Ветка удалена после мержа

## Ссылки

- Формат сообщений коммитов и pre-commit-порядок: скилл `general/git-commit-rules`
