# Статус возможностей

Матрица зрелости возможностей флота — не «есть команда», а «доказано работает». Значения
`Зрелость` — словарь из `general/plan-protocol` § Statuses (EN-канон,
`packages/skiller/skills/general/plan-protocol/SKILL.md` § Capability maturity), byte-for-byte:
`available` · `experimental` · `behind-gate` · `disabled` · `superseded`. Проверяется
`scripts/status-check.py`; шаг `status-check` в CI-job `hygiene`.

## Матрица

| Пакет | Возможность | Зрелость | Evidence / boundary |
|:--|:--|:--|:--|
| swissknifeman (router) | `swissknifeman <group>` — фан-аут в пакеты | available | `./bin/swissknifeman --help` печатает все группы (skills/env/maind/analyst/setup/doctor/status/wf/release) |
| swissknifeman (router) | `swissknifeman doctor` — диагностика флота | available | fan-out в `doctor` каждого пакета; проверено чтением `bin/swissknifeman` |
| skiller | `connect` — раздача скиллов через plugin marketplace | available | `packages/skiller/bin/skiller status --target .` — канал `marketplace`, включённые бакеты видны в выводе |
| skiller | `vendor`/`sync` — физ. перенос скиллов в проект | experimental | не используется этим репо (канал — connect); покрыт тестами `packages/skiller/tests/test_skillset.py`, не проверен на реальном стороннем проекте этим заходом |
| skiller | `registry` — регенерация `skills.json`/marketplace/graph | available | `bash packages/skiller/scripts/validate.sh` прогоняет `registry --check` |
| skiller | `budget` — токеновый бюджет набора скиллов | available | `packages/skiller/bin/skiller status --target .` печатает строку бюджета (`⊕ always … · ↻ bodies …`) |
| skiller | `eval` — поведенческий прогон скилла (with-skill vs baseline) | behind-gate | требует `claude -p` (внешний вызов модели) — не гоняется в CI; включается вручную по скиллу (`skiller eval <skill>`) |
| harness | `permissions` — влить presets в `.claude/settings*.json` | available | `packages/harness/bin/harness doctor` подтверждает наличие всех presets |
| harness | `mcp` — влить MCP-presets в `.mcp.json` | available | `packages/harness/bin/harness doctor` — 9 MCP-пресетов на месте |
| harness | `hooks` — установка хуков (auto-approve/memory/router/run-report) | experimental | `harness doctor` называет границу сам: «хук run-report протух (`_lib.py`) — повтори `harness hooks --global`» — известный дрейф, не скрыт |
| harness | `agent-packs` — детерминированный рендер паков субагентов | available | `packages/harness/bin/harness doctor` перечисляет 10 установленных паков |
| maind | `memory` — демон памяти (agentmemory) | available | `packages/maind/bin/maind status` — «память: запущена — http://127.0.0.1:4111» |
| maind | `graph` — федерация кросс-проектного графа | available | `packages/maind/bin/maind status` — «граф: federation — 294 узлов, 1019 рёбер» (числа плавают, команда воспроизводима) |
| maind | `agents` — реестр живых субагентов | behind-gate | `maind status` — «агенты: 0 живых / 0 всего» на момент правки: механизм есть, живых регистраций сейчас нет — требует активной сессии-регистранта |
| maind | `onboard`/`sync`/`deploy` — раскатка артефактов на проекты флота | available | `packages/maind/bin/maind status` — «проекты: 25 (подключено: 22)»; раскатка воспроизводится `maind sync --only <artefact> --dry-run` |
| analyst | `digest`/`review`/`promote` — конвейер continuous learning (human-gate) | available | `packages/analyst/bin/analyst status --project .` — 5 уроков в `ephemeral`, счётчики по стадиям |
| analyst | `scan`/`suggest` — cross-project паттерны → черновик скилла | experimental | P2/P3 по roadmap пакета (`packages/analyst/CLAUDE.md`): механизм есть, кросс-проектный прогон этим репо не выполнялся |
| task | `/task:plan-*` — исполнимые мастер-планы | available | этот же документ — продукт `/task:plan-exec 2026.07.25-ECO-OPT P8.5`; `packages/task/scripts/validate.sh` зелёный |
| task | `task_contract` — pre-mutation/pre-final гейт | available | `PYTHONPATH=packages/task/lib python3 -m task.task_contract` (вызов из этой же команды, п. 2/7 протокола) даёт `pre_mutation: allow` |
| core | `core.io` — атомарная запись (tmp + `os.replace`) | available | `PYTHONPATH=. python3 -m unittest discover -s core/tests` |
| core | `core.repo` — единый поиск корня репо/монорепо | available | используется лаунчерами всех пяти пакетов (`find_repo_root`/`find_monorepo_root`), покрыт `core/tests/test_core.py` |

## Known limitations

- **Видимая CLI-группа не доказывает, что её рантайм включён.** Наличие команды в `--help`
  (например, `skiller vendor` или `maind agents`) не значит, что путь исполнялся на реальных
  данных этого репо — только то, что интерфейс существует. Строка `Evidence / boundary` обязана
  называть, ЧТО именно проверено, а не пересказывать наличие команды.
- **Граница самой матрицы.** Она ловит нечестную зрелость (заявлено `available`, а на деле нет
  воспроизводимого доказательства) — но НЕ ловит пропущенную возможность: сверка полноты со
  списком реальных возможностей пакетов (приём D2, `Scope Excluded` этого item'а) отложена и не
  выполняется здесь. Список строк матрицы — выборка значимых возможностей, не исчерпывающий
  каталог.
