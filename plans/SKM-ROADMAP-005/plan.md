# SKM-ROADMAP-005 — Пакет дисциплины: настройки, workflow, канон планов, CHANGELOG, язык

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | SKM-ROADMAP-005 |
| Title | Пакет дисциплины: настройки, workflow, канон планов, CHANGELOG, язык |
| Version | 0.2.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Last Updated | 2026-07-10 |
| Repository | swissknifeman (монорепо academici) |
| Related Packages | skiller, harness, maind, task, analyst, core |
| Execution Mode | phase-first |
| Target Operator Models | sonnet (exec) · haiku (LOW) · opus (design/audit) |
| Approval Owner | Dmitry Vostrikov |
| Home | repo:plans/SKM-ROADMAP-005 |

## 1. Context

Каталог `roadmap/` накопил шесть спек со статусом «⬜ к внедрению», у которых критерий
внедрения УЖЕ сработал (полевые кейсы 2026-07-10) либо прямо записан как «одним заходом
с пакетом SKM-плана». Этот план — тот самый заход. Шесть направлений: (1) `settings-doctor`
— конфликт-линтер слоёв настроек Claude Code (полевой кейс: промпты каждые полминуты при
`bypassPermissions` в local, неустановленный хук, ~400 мёртвых allow-правил); (2) `wf-status`
— детерминированный статус-репортер фоновых workflow вместо LLM-импровизаций и совета
несуществующей команды `/workflows`; (3) `workflow-craft` — активация конструктора workflow
(кейс vaulter: Opus собрал dev-workflow без обязательного review при живом каноне) + команда-
гейт `/task:make-workflow` с выходным ревьюером; (4) канон планов — репо-дом по умолчанию,
имена с `supersedes`, дом workflow-скриптов `plans/<ID>/workflows/` (правки одного и того же
`plan-protocol` + `plan_lint`, потому слиты в одну фазу); (5) `changelog-discipline` —
enforcement заполнения CHANGELOG; (6) `ecosystem-glossary` — единый язык трёхслойкой
(линтеры per язык · CONTEXT.md per пакет · тонкий term-index). Седьмая фаза закрывает хвост:
спека «ephemeral-дисциплины», на которую ссылаются две существующие спеки, не существует.
Каждая фаза сдаётся вместе с обновлённой строкой статуса в `roadmap/README.md`.

## 2. Execution Rules

- Один item за раз; статус обновляется В ПЛАНЕ до завершения работы.
- Статусы — 6 канонических строк байт-в-байт (plan-protocol §6).
- Коммит-гейт закрытия: `🟢`/`🟠` не ставится без закоммиченного диффа item'а;
  `validate.sh` затронутого пакета зелёный ДО коммита; review-fix — отдельным коммитом.
- Фазы закрываются последовательно; items не прыгают между фазами.
- Фаза-скелет разворачивается `/task:plan-design SKM-ROADMAP-005 Pn` ДО `plan-exec`:
  исполнять item с полями «—» запрещено.
- План разошёлся с кодом → не импровизировать, эскалировать (plan-protocol §10).
- **stdlib-only** во всём python-коде плана (жёсткая рамка корневого CLAUDE.md); внешний
  код — как паттерн, не как зависимость.
- Правка скилла — по двуязычной модели: источник `SKILL.ru.md`, `SKILL.md` регенерируется
  (скилл `skill-authoring`); ручная правка только `SKILL.md` = дефект.
- Внешние факты о Claude Code (ключи settings, хук-события, формат transcript) —
  верифицировать RAG-лестницей при исполнении: доки меняются между версиями CLI.
- Каждая фаза в Deliverables несёт обновление статуса своего пункта в `roadmap/README.md`.
- После закрытия item/фазы — перезаписать `plans/SKM-ROADMAP-005/handoff.md`.

## 3. Routing

| Items | Model/effort И/ИЛИ Tool Capability | Почему |
|:--|:--|:--|
| P1.* | sonnet/medium + **claude-code-guide / perplexity-web (RAG)** | Таксономия проверок стоит на доках Claude Code (settings/permissions/hooks); доки меняются между версиями CLI — факты сверять при исполнении против `findings/P1-cc-settings-facts.md` (дата фиксации в файле) |
| P2.1 | sonnet/medium + **чтение локальной FS** (`~/.claude/projects/**/subagents/workflows/wf_*`) | Формат transcript-директории внутренний и недокументированный: источник истины — фикстура с реального прогона, а не доки |
| P3.3, P3.4 | **opus/high** | Дизайн команды-гейта и критериев выходного ревьюера = декомпозиция + инварианты (SSOT-матрица §9: effort high+ обязателен) |
| P4.1, P4.2 | **opus/high** | Правка SSOT-скилла `plan-protocol` — публичный контракт протокола для всей экосистемы (класс «public contract/SemVer»); дешёвая модель канон не переписывает |
| P6.4 | **sonnet/low** | Наполнение term-index — механический перенос терминов из готовых источников; thinking вреден (SSOT-матрица §9) |
| P7.1 | **opus/high** + интервью владельца | Авторинг отсутствующей спеки — проектирование, не исполнение |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P1 | settings-doctor: конфликт-линтер настроек Claude Code | 6/6 | 🟢 Done |
| P2 | wf-status: консольный статус-репортер workflow-прогонов | 4/5 | 🟠 Done with deviations |
| P3 | workflow-craft: активация конструктора + команда-гейт | 0/5 | ⬜ Not started |
| P4 | Канон планов: репо-дом, имена, дом workflow-скриптов | 0/6 | ⬜ Not started |
| P5 | changelog-discipline: enforcement заполнения CHANGELOG | 0/3 | ⬜ Not started |
| P6 | ecosystem-glossary: единый язык трёхслойкой | 0/4 | ⬜ Not started |
| P7 | ephemeral-дисциплина и закрытие пакета | 0/2 | ⬜ Not started |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-10 | Scope плана — ровно 6 пунктов `roadmap/` со статусом ⬜, у которых критерий сработал. Вне scope: `workflow-craft` ч.2 (fleet-синтез), `skill-rules-sidecar`, остаток `self-learning-memory` (P5 event-stream), default-on `mcp-config-example-emit` | Их критерии внедрения НЕ сработали (repo-grounded: `roadmap/README.md`, колонка «Критерий внедрения»); анти-bloat-политика репо — не внедрять спекулятивно. Альтернатива «взять всё подряд» отвергнута владельцем |
| D2 | 2026-07-10 | `workflow-craft` ч.1.6 (канон места/имён workflow-скриптов) и `plan-homes` исполняются ОДНОЙ фазой P4, а не двумя | Обе правят один и тот же `plan-protocol` + `plan_lint.py`; `roadmap/plan-homes.md` §Критерий: «делать одним заходом, чтобы не перекатывать канон дважды». Альтернатива (две фазы) даёт двойной bump версии скилла и второй прогон линтер-тестов |
| D3 | 2026-07-10 | `skipDangerousModePermissionPrompt` НЕ считать каноническим ключом settings.json. Policy-профиль `max-permissive` строится на `permissions.defaultMode: bypassPermissions` + `permissions.ask: []` + неприкосновенные deny-guardrails | RAG:✅ 2026-07-10 (`code.claude.com/docs/en/settings.md` — ключа НЕТ в таблице документированных). Спека `settings-doctor` декларирует его по полевому наблюдению. Альтернатива «гейтить проверку №10 на этом ключе» отвергнута: doctor не может выдавать error на недокументированном ключе — переформулировать в info. Выжимка — `findings/P1-cc-settings-facts.md` |
| D4 | 2026-07-10 | Построение «эффективной конфигурации» в doctor обязано различать два режима слияния слоёв: обычные ключи — override по приоритету, **permission-правила — merge across scopes** | RAG:✅ 2026-07-10 settings.md: «Exception: Permission rules merge across scopes rather than override». Наивный override даст ложные вердикты по проверкам №3/№4/№7 — класс дефекта, ради которого doctor и заводится |
| D5 | 2026-07-10 | Хук-событие `PermissionRequest` существует и входит в таксономию проверок №5 наравне с `PreToolUse`; при этом ни один хук не обходит `deny`/`ask` | RAG:✅ 2026-07-10 hooks.md + permissions.md («Hook decisions don't bypass permission rules»). Спека знала только `PreToolUse` — таксономия расширяется |
| D6 | 2026-07-10 | `permissions.autoApprove` подтверждён как НЕканонический ключ → эталонный кейс проверки №2 (молча игнорируемые ключи) | RAG:✅ 2026-07-10 settings.md: ключа нет в таблице. Поведение «молча игнорируется» — ровно тот класс, который doctor обязан ловить |
| D7 | 2026-07-10 | «ephemeral-дисциплина» получает собственный item (P7.1): сначала спека `roadmap/`, затем отдельное решение о внедрении | Repo-grounded: `grep -rin ephemeral roadmap/` — спеки нет, но `plan-homes.md` и `changelog-discipline.md` ссылаются на неё как на часть этого пакета. Висячая ссылка = дефект каталога. Альтернативы (вычеркнуть ссылки / оставить маркер `[NEEDS CLARIFICATION]`) отвергнуты владельцем 2026-07-10 |
| D8 | 2026-07-10 | Reuse-вердикт: НОВЫХ пакетов не заводим. `settings-doctor` — модуль в существующем doctor-слое (`skiller doctor` + `maind doctor --audit`), `wf-status` — группа существующего корневого router'а (`swissknifeman wf status`) | Repo-grounded: `bin/swissknifeman` — router-фасад, `skiller doctor` и прецедент `maind doctor --audit pao` уже есть; рамка корневого CLAUDE.md «единый источник истины > копий». Спека `workflow-status-cli.md` явно отвергла альтернативу «копия bash-артефакта в каждый пакет» (копии дрейфуют) |
| D9 | 2026-07-10 | `Home: repo:plans/SKM-ROADMAP-005` — план живёт в репо, а не в Brain | Deliverables плана — код и скиллы этого монорепо (plan-protocol §12 «план живёт там, где deliverables»); dogfooding правила, которое сам план вводит в P4.1 |
| D10 | 2026-07-10 | **Уточняет D8** (supersedes часть «дом»): движок `settings-doctor` живёт в пакете **harness** (`lib/harness/settings_audit.py`, CLI `harness doctor --settings`). `skiller doctor --settings` — фасад через subprocess; `maind doctor --audit settings` — fleet. Тезис D8 «новых пакетов не заводим» в силе | Repo-grounded: harness — SSOT окружения Claude Code (пресеты `configs/claude-code/`, писатель `scripts/apply-permissions.sh`, hooks, safe-dirs); doctor обязан быть парой к писателю, иначе профили дублируются. skiller окружением больше не владеет (его CLAUDE.md: «источник истины пресетов больше не здесь»). Альтернативы: движок в skiller (нужен доступ к чужим `configs/` либо дубль профилей); движок в `core/` (core — мелкие примитивы, не доменный модуль с таксономией из 13 проверок). Выбор владельца 2026-07-10 |
| D11 | 2026-07-10 | Проект объявляет ожидаемую политику ключом `policy_profile` в `.swissknife.json`; профили — `packages/harness/configs/claude-code/policy/<name>.json` (`max-permissive`, `base`) | В `.claude/settings.json` свой ключ класть нельзя: собственная проверка №2 doctor'а пометит его как неканонический (RAG:✅ 2026-07-10 settings.md — эталон `permissions.autoApprove`, D6). Прецедент кросс-пакетного ключа: `memory_brain` пишет harness, валидирует skiller. Альтернативы: новый файл `.claude/policy.json` (лишний конфиг в проекте); поле в реестре maind (per-project doctor без maind слепнет). Выбор владельца 2026-07-10 |
| D12 | 2026-07-10 | Opt-in `UserPromptSubmit`-хук settings-doctor (п.3 «Точек интеграции» спеки) — ВНЕ scope P1, в `Scope Excluded` фазы | Критерий не сработал: полевой кейс лечится on-demand командой. Хук — резидентный расход на КАЖДЫЙ промпт (`context-economy`), заводим по факту следующего трения. Альтернатива (седьмой item фазы) отвергнута владельцем 2026-07-10 |
| D13 | 2026-07-10 | Канонические ключи/hook-события — вендоренный снапшот `packages/harness/configs/claude-code/settings-keys.json` с провенансом (`source` + `verified` + `cli_version`); сетевого фетча схемы в рантайме нет | Официальная JSON-схема существует (RAG:✅ 2026-07-10 `https://json.schemastore.org/claude-code-settings.json`, уже стоит в `$schema` пресетов harness), но её загрузка = сеть, а doctor обязан работать офлайн при stdlib-only. Спека прямо требует «выжимку, не полную копию апстрим-схемы — иначе протухнет». Альтернатива (фетч + кэш) отвергнута: рантайм-зависимость от сети ради проверки уровня `warn` |
| D14 | 2026-07-10 | Проверки №12/№13 (VSCode-слой) — гейтящие `warn`, имена ключей зафиксированы: `claudeCode.initialPermissionMode`, `claudeCode.allowDangerouslySkipPermissions`. Снимает оговорку `findings` §5 | RAG:✅ 2026-07-10 эмпирика: `~/.vscode/extensions/anthropic.claude-code-2.1.206-linux-x64/package.json` (14 ключей `claudeCode.*`, оба присутствуют) + `vs-code-extension.md`. Прежняя оговорка «имя второго ключа только UI-лейблом» больше не действует |
| D15 | 2026-07-10 | Семантика слияния `permissions.additionalDirectories` across scopes — **[UNVERIFIED]**; дизайн её обходит: ядро хранит значения per-layer + union, проверка №8 работает per-layer | Два прохода RAG разошлись (проход 1 — «arrays merge, включая additionalDirectories»; проход 2 — «не задокументировано, вероятен override»). Молча принятое допущение = дефект (plan-protocol §7). Альтернатива «выбрать один режим» отвергнута: вердикт doctor'а не должен стоять на непроверенном факте. Выжимка — `findings/P1-cc-settings-facts.md` |
| D16 | 2026-07-10 | Канон имён планов — `<ГГГГ>.<ММ>.<ДД>-<КОДОВОЕ-ИМЯ>` (напр. `2026.07.10-SETTINGS-DOCTOR`). Внедряется в **P4** (там же, где `supersedes`): синхронно правятся `plan-protocol` (`SKILL.ru.md` → `SKILL.md`) и `packages/task/lib/task/plan_lint.py`. Back-compat: старый паттерн `[A-Z][A-Z0-9-]+` остаётся валидным, существующие планы (включая этот) НЕ переименовываются | Планы копятся и хранятся постоянно; датовый префикс даёт хронологическую сортировку каталога `plans/` и мгновенную ориентацию «когда это было» без чтения Meta. Требование владельца 2026-07-10 (в ходе plan-design P1). Альтернатива «переименовать существующие планы» отвергнута: ломает git-историю, ссылки handoff'ов и D-логов. Repo-grounded: текущий паттерн задан только в `SKILL.md`/`SKILL.ru.md` §2 — в `plan_lint.py` регулярки ID нет, её предстоит завести |
| D17 | 2026-07-10 | Дом движка `wf-status` — пакет **harness** (`lib/harness/wf_status.py`, CLI `harness wf status`); `swissknifeman wf status` — root-фасад→harness. **Уточняет D8** (supersedes часть «дом»: D8 задал поверхность `swissknifeman wf`, не дом движка) | Owner-confirmed 2026-07-10. Зеркалит D10 (settings-doctor→harness): harness — SSOT окружения Claude Code и уже читатель CC-рантайма (`settings_audit` читает `.claude/`); спека прямо: «Дом: прецедент harness-команд». Root-router — тонкий bash-диспетчер без логики, группу `wf` обязан делегировать в пакет. Альтернативы: maind (память+граф, workflow-транскрипты CC-нативны — не оркеструет; слабее прецедент); новый root-python (ломает философию «root без логики», прецедента нет) — обе отвергнуты владельцем |
| D18 | 2026-07-10 | Привязка агент→фаза журналом НЕ выводится: отчёт показывает декларации фаз из `export const meta` скрипта + ОБЩИЙ прогресс агентов (started/done/inflight, грубый %); per-phase счётчики опущены. Деградирует обещание спеки §3 «фазы таблицей с счётчиком агентов» осознанно | RAG:✅ 2026-07-10 эмпирика (`findings/P2-workflow-transcript-format.md`): `journal.jsonl` несёт только `agentId`+`key`(sha)+`result`, `agent-*.meta.json` = `{agentType,spawnDepth}` — ни label, ни phase. Восстановить можно лишь из `agent-<id>.jsonl` (0600, дорого, хрупко к версии CC). Альтернатива «парсить транскрипты агентов» отвергнута: stdlib-only + robust + cheap важнее полноты; вердикт doctor'а не должен стоять на хрупком парсе |
| D19 | 2026-07-10 | Скрипт прогона с `export const meta` лежит НЕ в `wf_<id>/`, а в sibling `<session>/workflows/scripts/*-wf_<id>.js`; discovery скрипта по этому пути, парс `phases[]` регуляркой (НЕ `eval`/`json.loads` JS-объекта) | RAG:✅ 2026-07-10 эмпирика (`findings/P2-workflow-transcript-format.md`): реальные прогоны loqum/swissknifeman. Спека подразумевала скрипт «в директории прогона» — расхождение зафиксировано, дизайн его обходит |
| D20 | 2026-07-10 | Дом скилла `workflow-craft` — бакет `general/` реестра skiller (`packages/skiller/skills/general/workflow-craft/`), рядом с `plan-protocol`/`complex-task-orchestrator`/`spec-interview`. Спека говорила «в паке task» | Repo-grounded: у пакета `task` НЕТ каталога `skills/` (только `commands/`+`lib/`); все скиллы физически живут в реестре skiller, доставляются в проекты через marketplace/vendor. «Дом task» в спеке — про домен дисциплины, не про физ. расположение. Альтернатива (завести `skills/` в task) отвергнута: раздвоит источник скиллов, ломает генерацию marketplace из `skiller/skills/**` |
| D21 | 2026-07-10 | SSOT две-типа-матрицы (design-only vs dev: обязательные стадии, чего НЕТ) — в САМОМ скилле `workflow-craft` (P3.1). Команда `/task:make-workflow` и её выходной ревьюер её ЦИТИРУЮТ, не дублируют. Origin таблицы — спека §1.5 | Единый источник > копий (рамка корневого CLAUDE.md): три поверхности (скилл/команда/ревьюер) на одну матрицу дадут дрейф при первой правке. Альтернатива (таблица в конструктор README) отвергнута: матрица — про дисциплину активации (что обязательно по типу), README — про заполнение слотов; смешение размывает оба. Ревьюер сверяет ИНВАРИАНТЫ по README, ОБЯЗАТЕЛЬНЫЕ СТАДИИ — по скиллу |
| D22 | 2026-07-10 | `/task:make-workflow` — slash-команда пакета `task` (`packages/task/commands/make-workflow.md`, `model: opus`/`effort: high`), НЕ отдельный workflow-скрипт. Выходной ревьюер — под-агент (Agent tool) внутри контура команды, СТАТИЧЕСКИЙ (читает скрипт, не исполняет); RED блокирует выдачу | Прецедент: весь plan-протокол и интент-задачи — slash-команды `task` с пиннингом модели (CLAUDE.md пакета). Интервью+генерация+ревью — одна сессия команды, а не Workflow-прогон (у авторинга нет N-элементного fan-out). Статический ревьюер: прогон сгенерированного скрипта = побочные эффекты/токены до утверждения. Альтернатива (ревьюер запускает скрипт) отвергнута — сначала статическая проверка инвариантов, исполнение уже пользователем |
| D23 | 2026-07-10 | Discovery (P2.2) уважает `$CLAUDE_CONFIG_DIR` как env-override корня конфигурации Claude Code (заменяет `~/.claude` целиком), иначе дефолт `~/.claude` | RAG:✅ 2026-07-10 perplexity-web (gist.github/jamesfishwick, ccusage.com/guide/claude): официальный env-override, all-or-nothing, «respected everywhere» в 2025-2026. Внешний факт про CC — верифицирован RAG-лестницей перед фиксацией в коде (методология решений корневого CLAUDE.md) |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-10 | issue-planner/opus | План создан: 7 фаз-скелетов, 31 item. Scope и ephemeral-item подтверждены владельцем |
| 2026-07-10 | issue-planner/opus | Active переключён на SKM-ROADMAP-005 (прежний — SKM-AUDIT-004, статус терминальный 🟠, Paused By не требуется) |
| 2026-07-10 | issue-planner/opus | RAG-верификация фактов Claude Code settings → `findings/P1-cc-settings-facts.md`; три расхождения со спекой зафиксированы как D3/D5/D6 |
| 2026-07-10 | issue-planner/opus | Фаза P1 развёрнута из скелета: 6 items с полными ТЗ, Scope Included/Excluded, DoR пройден. Три развилки закрыты владельцем → D10 (дом движка — harness), D11 (декларация профиля), D12 (хук вне scope) |
| 2026-07-10 | issue-planner/opus | Пере-сверка фактов CC (проход 2, + эмпирика package.json расширения 2.1.206) → D13/D14/D15; выжимка дописана в `findings/P1-cc-settings-facts.md` |
| 2026-07-10 | issue-planner/opus | D16: канон имён планов `ГГГГ.ММ.ДД-КОДОВОЕ-ИМЯ` (требование владельца) — внедряется в P4, отмечен в его Phase Context |
| 2026-07-10 | package-implementer/sonnet | P1.5 закрыт: проверки 6–8, 10, 12–13 + JSONC VSCode-reader + интеграционный fieldcase-тест. `validate.sh` зелёный, реальный прогон на этом репо подтвердил находки. Коммит `7c11f46` |
| 2026-07-10 | package-implementer/sonnet | P1.6 закрыт: измерение `settings` в `maind doctor --audit settings\|all` (subprocess к harness, fail-soft), `roadmap/README.md`/`roadmap/settings-doctor.md`/`CHANGELOG.md` приведены к факту внедрения. Фаза P1 закрыта 6/6 🟢 |
| 2026-07-10 | issue-planner/opus | P2 развёрнута из скелета: 5 items с полными ТЗ, DoR пройден. Формат прогона сверён эмпирикой → `findings/P2-workflow-transcript-format.md`; дом движка = harness (owner → D17); два расхождения со спекой обойдены дизайном (D18 per-phase attribution, D19 расположение скрипта) |
| 2026-07-10 | issue-planner/opus | P3 развёрнута из скелета: 5 items с полными ТЗ, DoR пройден — детали см. phases/P3.md. Развилки закрыты: D20 (дом скилла), D21 (SSOT матрицы), D22 (форма команды+ревьюера) |
| 2026-07-10 | package-implementer/sonnet | P2.1 закрыт: защищённый парсер `wf_status.py` (`parse_run`/`parse_script_meta`/`summarize_result`) в harness — journal.jsonl + agent-*.meta.json + sibling-скрипт `export const meta` (D19), degraded-флаг вместо трейсбека, per-phase attribution намеренно не выводится (D18). `validate.sh` зелёный |
| 2026-07-10 | package-implementer/sonnet | P2.2 закрыт: discovery прогонов (база `$CLAUDE_CONFIG_DIR`/`~/.claude` — D23, RAG:✅ perplexity-web) — детали см. phases/P2.md P2.2 Completion Notes |
| 2026-07-10 | package-implementer/sonnet | P2.3 закрыт: рендер отчёта + `--json` + `--watch` (плоский, фикс-шаблон, D18) — детали см. phases/P2.md P2.3 Completion Notes |
| 2026-07-10 | package-implementer/sonnet | P2.4 закрыт 🟠: CLI `harness wf status` + root-фасад + фикстура/интеграционный тест; CHANGELOG-строка → Pending Work (permission-deny среды) — детали см. phases/P2.md P2.4 Completion Notes |
| 2026-07-10 | package-implementer/sonnet | P2.5 закрыт: подсказка «swissknifeman wf status, не /workflows» в dev.md+конструктор; фаза P2 закрыта 4/5 🟢 + P2.4 🟠 — детали см. phases/P2.md P2.5 Completion Notes |
