# Развёртывание: новая машина / команда

Один идемпотентный сценарий поднимает экосистему на **новом компьютере** (переустановка ОС,
второй ноутбук) или у **новых участников команды** — дотфайлс-паттерн (см.
[Roadmap](/roadmap)): версионируемый репо + один скрипт, повторный запуск безопасен.

## Быстрый старт: одна машина

```bash
git clone <адрес-репо-swissknifeman> ~/projects/swissknifeman
cd ~/projects/swissknifeman
scripts/bootstrap-machine.sh
```

Скрипт (`scripts/bootstrap-machine.sh`, роут `swissknifeman setup --machine`) прогоняет
7 ступеней по порядку, проверяя каждую отдельно:

1. `install.sh` — CLI пакетов (skiller/harness/maind/analyst) + симлинк `swissknifeman`.
2. `harness hooks --global` — глобальные хуки Claude Code (merge-only).
3. `harness permissions --global` — глобальный пресет permissions (merge-only).
4. MCP-пресеты — **soft-skip**: у harness/maind сейчас нет `--global`-механизма для MCP,
   раскатка остаётся per-project (`harness mcp --target` / `maind deploy`).
5. `maind service install` — демон памяти как `systemd --user` (мягкая деградация без systemd).
6. `swissknifeman doctor` — финальная диагностика всех пакетов.
7. Манифест проектов (`--projects <файл>`) — см. ниже.

Флаги: `--dry-run` (план без изменений на диске), `--skip-projects` (пропустить ступень 7
целиком), `--bin-dir DIR` (куда класть симлинки CLI, по умолчанию `~/.local/bin`).

## Манифест проектов (`--projects`)

Baseline (сам swissknifeman) ставится всем одинаково; список **зависимых проектов** — у каждого
пользователя свой (per-user overrides, канон dotfiles-паттерна). Манифест — JSON-файл, схема и
плейсхолдеры — [`docs/machine-manifest.example.json`](https://github.com/academici/swissknifeman/blob/main/docs/machine-manifest.example.json):

```json
{
  "version": 1,
  "projects": [
    {
      "repo": "git@github.com:example-org/example-project.git",
      "path": "~/projects/example-org/example-project",
      "profile": ""
    }
  ]
}
```

| Поле | Обязательное | Значение |
|:--|:--|:--|
| `repo` | да | git-адрес репозитория (ssh/https) |
| `path` | да | локальный путь клонирования (`~` раскрывается) |
| `profile` | нет | пометка профиля/типа проекта (информационно; автоопределение профиля при онбординге делает `skiller connect` само) |

Запуск:

```bash
scripts/bootstrap-machine.sh --projects ~/.swissknifeman/machine-manifest.json
```

Поведение шага (идемпотентно — второй прогон не делает лишнего):

- Путь из манифеста **отсутствует** → `git clone <repo> <path>`, затем `swissknifeman setup <path>`
  (полный онбординг: скиллы + окружение + память + граф, см. [ecosystem-integration](/maind/)).
- Путь **уже существует** (клонирован ранее) → `git pull` **не делается** (не трогаем чужое
  рабочее состояние — незакоммиченные изменения, локальные ветки); выполняется только повторный
  `swissknifeman setup <path>` (onboard-проверка, дописывает недостающее, ничего не затирает).
- `--dry-run` печатает план (что будет клонировано / что уже есть) без изменений на диске.
- `--skip-projects` пропускает ступень целиком, даже если `--projects` указан.

Храни личный манифест вне репозитория (например `~/.swissknifeman/machine-manifest.json`) —
в репо коммитится только `.example` с плейсхолдерами (гигиена `.env`↔`.env.example`).

## Сценарий «команда»

1. Baseline — все ставят `bootstrap-machine.sh` без `--projects` (или с общим для команды
   read-only манифестом «обязательных» проектов, если такой согласован).
2. Каждый участник держит свой `~/.swissknifeman/machine-manifest.json` со списком проектов,
   с которыми лично работает — список не автоопределяется (Scope: пишет человек).
3. Секреты/API-ключи — **не в манифесте и не в скрипте**: заводятся отдельно (env/`.env`
   в проекте), bootstrap их не касается.

## Что не входит в этот сценарий

- **Межкомпьютерная синхронизация памяти** — сознательно отложено, см.
  [`roadmap/cross-machine-memory.md`](https://github.com/academici/swissknifeman/blob/main/roadmap/cross-machine-memory.md).
- Автоматическое определение, какие проекты нужны пользователю — список в манифесте пишет
  человек.
- CI/автоматизация bootstrap — сценарий рассчитан на разового оператора машины.

## См. также

- [Разработка с Claude Code](/develop) — что делать после того, как машина поднята.
- [Control-surface проектов](/control-surface) — точечная диагностика/починка слоёв
  подключённого проекта.
