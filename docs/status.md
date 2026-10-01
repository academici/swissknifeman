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
| skiller | `budget --first-turn --with-plugins` — полная цена первого хода | available | `packages/skiller/bin/skiller budget --first-turn --with-plugins --target .` печатает проектную и плагинную составляющие; `broken`/`unparsed` не маскируются нулём |
| skiller | нативный скоуп Claude Code для процедурных скиллов | experimental | `context: fork` проверен на четырёх скиллах через explicit и auto-trigger; `paths:` сознательно не раскатан, а `when_to_use` проходит совместный гейт листинга |
| skiller | `eval` — поведенческий прогон скилла (with-skill vs baseline) | behind-gate | требует `claude -p` (внешний вызов модели) — не гоняется в CI; включается вручную по скиллу (`skiller eval <skill>`) |
| skiller | канон каркаса — гейт свежести версий паков (`framework-overview.md` vs `pack.json`) | available | `bash packages/skiller/scripts/validate.sh` — «канон каркаса: таблица «пак → версия» совпадает с pack.json (10 паков)»; доказан обеими сторонами: реальный дрейф `_common 0.4.1` vs факт. `0.5.0` пойман этим прогоном и красил ERROR до правки строки |
| skiller | `budget --provider` — вторая (provider-aware) модель бюджета обнаружения | behind-gate | `packages/skiller/bin/skiller budget --target. --provider codex` — «ПЕРЕБОР (×1.1)» на профиле этого репо; WARN-гейт в `validate.sh` — структурный перебор листинга, не «работает без оговорок» |
| harness | `permissions` — влить presets в `.claude/settings*.json` | available | `packages/harness/bin/harness doctor` подтверждает наличие всех presets |
| harness | `mcp` — влить MCP-presets в `.mcp.json` | available | `packages/harness/bin/harness doctor` — 9 MCP-пресетов на месте |
| harness | `hooks` — установка хуков (auto-approve/memory/router/run-report) | experimental | `harness doctor` называет границу сам: «хук run-report протух (`_lib.py`) — повтори `harness hooks --global`» — известный дрейф, не скрыт |
| harness | `agent-packs` — детерминированный рендер паков субагентов | available | `packages/harness/bin/harness doctor` перечисляет 10 установленных паков |
| harness | `instructions` — канон корневых инструкций (`plan\|check\|adopt\|apply\|repair`) | available | `harness instructions check` — «OK — 12 целей», все `clean/noop`; принятие живой транзакцией на 12 целях уже прогнано |
| core | provider control plane — provider-qualified support and no-write operator checks | available | `python3 scripts/provider-docs.py --check`, `harness doctor --provider-audit --json`, and P7.2 regression gates keep manifest, diagnostics, and generated reference aligned; `native`/`adapted`/`unsupported` stay distinct |
| core | provider release candidate — P7.3 evidence manifest | behind-gate | D88 defers live Claude efficacy and external P5/P6 rollout; the current non-empty release-blocker set makes the candidate explicitly non-releasable and grants no tag/push/publish authority |
| harness | `hooks --provider codex` — Codex lifecycle/context наблюдатели и гейты класса B | behind-gate | `harness hooks --target <repo> --provider codex --observer --safe-dirs --daemon-safety --trusted --dry-run` — план строится (`3 surface(s)`), но round-trip с живым Codex CLI не проверялся — граница отдельно названа в `configs/provider-capabilities.json` |
| harness | `execution-policy` — декларативная политика исполнения (носитель + `execpolicy.py`) | available | `PYTHONPATH=packages/harness/lib python3 -m harness.execpolicy --check` — «OK — 7 проверок»; шаг `[10/10]` в `validate.sh`; принуждение по-прежнему через потребителя (грамматику PLAN), не автоматическое |
| harness | `swissknifeman env run <PLAN-ID> Pn` — последовательная exec-волна | available | `packages/harness/bin/harness run --dry-run` строит очередь без записи; сквозной прогон P4.6 на изолированной фикстуре выполнил два item’а живыми воркерами |
| maind | `memory` — демон памяти (agentmemory) | available | `packages/maind/bin/maind status` — «память: запущена — http://127.0.0.1:4111» |
| maind | `graph` — федерация кросс-проектного графа | available | `packages/maind/bin/maind status` — «граф: federation — 294 узлов, 1019 рёбер» (числа плавают, команда воспроизводима) |
| maind | `agents` — реестр живых субагентов | behind-gate | `maind status` — «агенты: 0 живых / 0 всего» на момент правки: механизм есть, живых регистраций сейчас нет — требует активной сессии-регистранта |
| maind | `onboard`/`sync`/`deploy` — раскатка артефактов на проекты флота | available | `packages/maind/bin/maind status` — «проекты: 25 (подключено: 22)»; раскатка воспроизводится `maind sync --only <artefact> --dry-run` |
| analyst | `digest`/`review`/`promote` — конвейер continuous learning (human-gate) | available | `packages/analyst/bin/analyst status --project .` — 5 уроков в `ephemeral`, счётчики по стадиям |
| analyst | `scan`/`suggest` — cross-project паттерны → черновик скилла | experimental | P2/P3 по roadmap пакета (`packages/analyst/CLAUDE.md`): механизм есть, кросс-проектный прогон этим репо не выполнялся |
| task | `/task:plan-*` — исполнимые мастер-планы | available | этот же документ — продукт `/task:plan-run`; `packages/task/scripts/validate.sh` зелёный |
| task | `plan-lint --conflicts` — согласованность плановых проекций | available | `python3 packages/task/scripts/plan-lint.py --conflicts` сверяет канонический русский источник и provider-проекции; launch-block принимает явную строку команды или legacy fence |
| task | `task_contract` — pre-mutation/pre-final гейт | available | `PYTHONPATH=packages/task/lib python3 -m task.task_contract` (вызов из этой же команды, п. 2/7 протокола) даёт `pre_mutation: allow` |
| core | `core.io` — атомарная запись (tmp + `os.replace`) | available | `PYTHONPATH=. python3 -m unittest discover -s core/tests` |
| core | `core.repo` — единый поиск корня репо/монорепо | available | используется лаунчерами всех пяти пакетов (`find_repo_root`/`find_monorepo_root`), покрыт `core/tests/test_core.py` |

## Какие риски покрывают проверки

Эта карта связывает механизм с проверяемым сбоем. Статус `available` выше не означает,
что все свойства проверены на живом клиенте или при выключении питания.

| Сбой | Механизм и автоматическая проверка | Предел доказательства / полевая проверка |
|:--|:--|:--|
| Чужой файл перезаписан проекцией | `core.provider.lock` отказывает при ownership conflict и managed drift; `core/tests/provider/test_lock.py`, `packages/harness/tests/test_provider_instructions.py` | Проверки идут в изолированных каталогах; фактическую активную проекцию конкретного проекта смотрите через `skiller doctor --effective-source --json` и provider audit. |
| Два локальных writer'а или погибший holder оставили lock | `flock` сериализует записи; `core/tests/provider/test_lock.py` проверяет конкуренцию и освобождение после `SIGKILL` | Это семантика одного Linux-хоста с локальной ФС; NFS/SMB и атомарность нескольких provider-файлов этим тестом не доказаны. |
| Плановый item ошибочно закрыт GREEN | `task_contract`, terminal journal и digest-bound delivery receipt; `packages/task/tests/test_plan_delivery.py`, `packages/task/tests/test_plan_work.py` | Тесты не заменяют живое выполнение declared Validation и проверку результата пользователем; прямые задачи вне Task не получают такой receipt автоматически. |
| Релизная поставка разошлась с тегом | `verify-tag`, release attestation и `release-fleet` проверяют локальную поставку; `packages/skiller/tests/test_release_attestation.py` | Публикация GitHub Release — отдельная операция; наличие тега и локального receipt её не доказывает. |
| Секрет попал в отслеживаемый файл | `scripts/public-hygiene.py` запрещает имена ключей и приватных артефактов | Это проверка **имён файлов**, не содержимого. Она не доказывает отсутствие секретов в JSON, shell-скриптах или примерах. |

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
