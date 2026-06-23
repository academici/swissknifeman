# Contributing — swissknifeman (монорепо-зонтик)

Гид для контрибьюторов корня монорепо. Это **зонтик экосистемы academici**: один репозиторий —
три независимых пакета (`skiller`, `harness`, `maind`) + общий `core` + корневой роутер
`swissknifeman`. Подробная карта — в [`CLAUDE.md`](CLAUDE.md) (корень и каждый пакет).

## Раскладка

```
core/                 # общий stdlib-only пакет (Env/io/cli/term/text/repo)
packages/skiller/     # реестр скиллов            (CLI skiller)   — см. packages/skiller/CONTRIBUTING.md
packages/harness/     # окружение Claude Code      (CLI harness)
packages/maind/       # хаб памяти/графа/координации (CLI maind)   — см. packages/maind/CONTRIBUTING.md
bin/swissknifeman     # корневой роутер (router + setup-фасад)
install.sh            # зонтичный установщик (делегирует install.sh пакетов)
```

## Установка для разработки

```bash
./install.sh                  # ставит CLI пакетов + симлинк swissknifeman в ~/.local/bin
```

- **Без pip, stdlib-only.** Рантайм-зависимостей в Python нет; `core` подключается через
  `PYTHONPATH` — лаунчеры (`packages/*/bin/*`) добавляют корень монорепо автоматически
  (fallback на standalone-раскладку пакета). Отдельно ничего «устанавливать» для `core` не нужно.
- **IDE-автодополнение `from core import ...`:** если Pylance/PyCharm не видят `core`, добавьте пути
  `core`, `packages/*/lib` в `python.analysis.extraPaths` (или `pyrightconfig.json`) — не через pip.
- **`.mcp.json` и `config.json` машинно-специфичны** (абсолютные пути) и не коммитятся
  (`.gitignore`); шаблоны — `.mcp.json.example` / `config.example.json`. Реальный `.mcp.json` для
  этого репо генерит `maind` (sync/deploy).

## Тесты и валидация

Перед каждым PR — зелёная валидация по затронутым пакетам + smoke `core`:

```bash
bash packages/skiller/scripts/validate.sh
bash packages/harness/scripts/validate.sh
bash packages/maind/scripts/validate.sh
PYTHONPATH=. python3 -m unittest discover -s core/tests -v   # фундамент core
```

`validate.sh` каждого пакета прогоняет `py_compile`, `bash -n`, проверки JSON и юнит-тесты
(`scripts/test.sh`). CI (`.github/workflows/test.yml`) гоняет то же на Python 3.9–3.13.

## Конвенции

- **stdlib-only** в Python (`lib/`, `core/`) — никаких pip-зависимостей в рантайме.
- **`Env` передаётся явно** (frozen dataclass, наследник `core.BaseEnv`) — без модульных глобалей,
  всё тестируемо в tmpdir.
- **Атомарная запись** файлов/JSON — через `core.atomic_write_text` / `atomic_write_json`.
- **Сообщения — на русском** (`die`, `warn`).
- **Коммиты — Conventional Commits на русском** (напр. `fix(core): ...`, `docs: ...`).

## Релизная дисциплина

- Содержательное изменение → запись в `CHANGELOG.md` `[Unreleased]`.
- Правки скиллов/бакетов/плагинов → `skiller registry` (регенерит `skills.json`, marketplace,
  plugin-манифесты, граф) — генерёжку руками не правят.
- Аннотированные semver-теги: `git tag -a vX.Y.Z`; при теге `[Unreleased]` → `[X.Y.Z]`.
  Версии плагинов Claude Code резолвятся в git SHA (поля `version` в манифестах нет).

## PR

1. Ветка от `main` (на `main` напрямую не коммитим).
2. Валидация затронутых пакетов зелёная; `core`-тесты проходят.
3. PR на русском, описание — что и зачем. CI прогонит ту же валидацию.

Пакет-специфика (скиллы, апстримы, память/граф) — в `packages/<pkg>/CONTRIBUTING.md` и `CLAUDE.md`.
