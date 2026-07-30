# RAG-разведка: нативные поверхности Codex под capability-паритет — 2026-07-29

Слой 1 (внешнее сырьё). Прогон выполнен заходом `plan-design 2026.07.29-HARNESS-AGNOSTIC P2`
(Opus 5/high) по лестнице `perplexity-web → first-party WebFetch`. Дисциплина унаследована
от `2026.07.18-FOREMAN` D19: Perplexity-факт в несущей позиции подтверждается
первоисточником. Все четыре факт-класса ниже несущие для фазы P2 — от них зависит, какой
из 17 записей `unsupported` вообще МОЖЕТ быть присвоен вердикт «закрывается адаптером».

Первоисточник Codex — `learn.chatgpt.com/docs/**` (туда 308-редиректит
`developers.openai.com/codex/**`; тот же домен использован в `findings/02` Ф8).

---

## Ф9. Хук-поверхность Codex CLI

**Вердикт:** ✅ подтверждён first-party (`https://learn.chatgpt.com/docs/hooks`,
WebFetch 2026-07-29, два прохода — события/решения и матчеры/пейлоады).

| Факт | Дословно/точно из доки |
|:--|:--|
| Полный набор событий (11) | `SessionStart`, `SessionEnd`, `SubagentStart`, `SubagentStop`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `UserPromptSubmit`, `Stop` |
| Общие поля пейлоада | `session_id`, `transcript_path` (string \| null), `cwd`, `hook_event_name`, `model`, `turn_id` (для turn-scoped), `permission_mode` («for most events») |
| Доп. поля `PreToolUse` | `turn_id`, `tool_name`, `tool_use_id`, `tool_input` |
| Доп. поля `PostToolUse` | те же + `tool_response` |
| Доп. поля `SessionEnd` | `reason` (сейчас всегда `"other"`) |
| Доп. поля `UserPromptSubmit` | `turn_id`, `prompt` |
| Доп. поля `SubagentStop` | `turn_id`, `agent_id`, `agent_type`, `agent_transcript_path`, `stop_hook_active`, `last_assistant_message` |
| Кто умеет блокировать | `PreToolUse` — `permissionDecision: "deny"` либо exit 2 + stderr; `PermissionRequest` — `behavior: "allow"\|"deny"`; `PostToolUse` — `decision: "block"` либо exit 2 (побочный эффект уже случился, отменить нельзя); `UserPromptSubmit` — `decision: "block"`; `Stop`/`SubagentStop` — `decision: "block"` заставляет ПРОДОЛЖИТЬ, а не отклоняет ход |
| Матчер | «The matcher field is a regex string that filters when hooks fire»; примеры `^Bash$`, `Edit\|Write`, `mcp__filesystem__.*` |
| Имена тулов | `Bash` (shell), `apply_patch` (правки файлов; матчится и как `Edit`/`Write`), MCP-тулы `mcp__<server>__<tool>`, локальные функции (`update_plan`, `spawn_agent`/`Agent`) |
| Где живут хуки | `~/.codex/hooks.json`, `~/.codex/config.toml` (user), `<repo>/.codex/hooks.json`, `<repo>/.codex/config.toml` (project, **требует доверия проекту**); плагинные — из `hooks/hooks.json` плагина |
| Что исполняется | только `type: "command"`; `prompt`/`agent` парсятся, но не запускаются |
| Доверие | non-managed command-хуки требуют явного review/trust; managed (requirements.toml/MDM/system) доверены политикой и не отключаются пользователем |

**Проекция на план.** Это главный факт фазы: девять из пятнадцати Codex-`unsupported`
записей — это поверхности, которые у Claude Code реализованы ХУКАМИ, и у Codex есть
событие-аналог для **восьми** из них (исключение — `lifecycle.notification`: события
`Notification` у Codex нет, носитель — user-scope ключ `notify`, Ф10): `SessionEnd` для
run-report, `PreToolUse`
для command-log/pack-guard/changelog-gate/safe-dirs, `UserPromptSubmit`+`SessionStart` для
router и memory, `SubagentStop` для review-gate). Механизм регистрации в репо уже
построен — `configs/codex/hooks/lifecycle-context-bindings.json` + `render_codex_hooks`
рендерят `.codex/hooks.json` для ЛЮБОГО числа `hook-native` bindings; включён ровно один
(`context.observer`). То есть закрытие этой группы — не изобретение, а заполнение данных +
генерация обработчиков.

**Асимметрии, которые обязана учесть реализация:**

1. У Claude Code событие `Notification` есть, у Codex в списке его НЕТ — уведомления у
   Codex идут через конфиг-ключ `notify` (Ф10), а он **не переопределяется проектным
   конфигом**. Значит `lifecycle.notification` не закрывается проектным артефактом в
   принципе.
2. `Stop`/`SubagentStop` у Codex имеют инвертированную семантику `block` (продолжить, а не
   отклонить). Claude-овский review-gate стоит на `SubagentStop` и трактует блок как
   «не выпускать» — дословный перенос семантики был бы ошибкой.
3. `permission_mode` документирован как «for most events», а наш
   `adapt_codex_hook_payload` требует его безусловно (`hooks.py:167`) — для событий, где
   поля не окажется, адаптер отвергнет валидный пейлоад.
4. Имена тулов не совпадают с Claude (`apply_patch` вместо `Edit|Write|MultiEdit|
   NotebookEdit`), матчер — регулярка. Перенос матчеров дословно даст молчаливо не
   срабатывающий хук.

## Ф10. Слои конфигурации Codex и границы проектного скоупа

**Вердикт:** ✅ подтверждён first-party
(`https://learn.chatgpt.com/docs/config-file/config-reference`, WebFetch 2026-07-29).

| Факт | Дословно/точно из доки |
|:--|:--|
| Два слоя | «User-level configuration lives in `~/.codex/config.toml`. You can also add project-scoped overrides in `.codex/config.toml` files» |
| Чего проектный слой НЕ может | «Project-scoped config can't override machine-local provider, auth, host-owned app request metadata, **notification**, configuration **profile selection**, or telemetry routing keys» |
| Уведомления | ключ `notify` (user-scope) |
| Включение хуков | `features.hooks` |
| Песочница | `sandbox_workspace_write.writable_roots` (+ `exclude_slash_tmp`, `exclude_tmpdir_env_var`, `network_access`) |
| Доверие проекту | `projects.<path>.trust_level` |
| Output style / plans directory | **таких ключей в справочнике нет** |

**Проекция на план.** Три вердикта фактически предопределены измерением, а не вкусом:
`context.output-style` и `context.plans-directory` не имеют у Codex носителя вообще
(кандидаты в законный `Claude-only`), а `lifecycle.notification` имеет носитель, но
исключительно машинно-локальный — то есть вне модели «управляемый проектный артефакт»,
которой живёт весь harness. Одновременно `sandbox_workspace_write.writable_roots` даёт
Codex вторую, деклара­тивную половину `security.safe-dirs`: у Claude allowlist читает
PreToolUse-хук, у Codex тот же allowlist может проецироваться И в хук, И в песочницу.

## Ф11. Субагенты Codex и `.codex/agents/*.toml`

**Вердикт:** ✅ подтверждён first-party
(`https://learn.chatgpt.com/docs/agent-configuration/subagents`, WebFetch 2026-07-29).

- Персональные агенты — `~/.codex/agents/`, проектные — `.codex/agents/`; **один файл =
  один агент**.
- Обязательные поля: `name`, `description`, `developer_instructions`. `name` — источник
  истины (имя файла — конвенция).
- Опционально допускаются ключи `config.toml`: `model`, `model_reasoning_effort`,
  `sandbox_mode`, `mcp_servers`, `skills.config`.
- Глобальное поведение — секция `[agents]`: `agents.enabled` (по умолчанию `true`),
  `agents.max_concurrent_threads_per_session`, `agents.default_subagent_model`,
  `agents.default_subagent_reasoning_effort`, `agents.interrupt_message`.

**Проекция на план.** Целевой путь, который harness уже рендерит для Codex
(`.codex/agents/{{PACK_PREFIX}}-<role>.toml`, `agentpacks.py:1114`), совпадает с
first-party конвенцией — значит `agents.catalog` у Codex `adapted` заслуженно, а
`agent-packs.lifecycle` (`unsupported`) — разрыв не в целевом формате, а в движке паков
(интервью/lock/upgrade рендерит `.claude/**`-шаблоны). Поля `model`/
`model_reasoning_effort` в TOML-агенте дают Codex-эквивалент model-тиров пака
(`MODEL_REVIEWER`/`MODEL_SLICE_BUILDER`/`MODEL_RECON`, `findings/01` Ф6).

## Ф12. Repo-grounded срез машинных ограничений (не RAG)

Приведено здесь, потому что вердикты триажа исполнимы только вместе с этими фактами.

| Ограничение | Источник |
|:--|:--|
| Уровень в манифесте и наблюдаемая активация сверяются машинно: расхождение = `HARNESS_CAPABILITY_MANIFEST_INVALID:<provider>:<surface>:expected-…:observed-…` | `packages/harness/lib/harness/provider_audit.py:244-260` |
| Форма записи поддержки жёсткая: `native` требует `binding`+`evidence` и ЗАПРЕЩАЕТ `adapter_id`; `adapted` требует `adapter_id`+`limitations`+`evidence`; `unsupported` запрещает `binding`/`adapter_id` и требует непустой evidence + fail-closed формулировку диагностики | `core/provider_manifest.py:368-382` |
| Набор capability-ID выводится независимо (task command-routing ∪ harness profile-catalog surfaces ∪ instructions catalog ∪ секции analytics-контракта); лишний/недостающий ID = `PROVIDER_DOCS_CONFORMANCE_FAILED` | `scripts/provider-docs.py:29-64,96-148` |
| Для команд `task:*` оба провайдера обязаны иметь уровень ∈ {`native`,`adapted`}; для harness-поверхностей допустимы все три уровня | `scripts/provider-docs.py:67-93` |
| `docs/provider-support.md` И блок в `README.md` — генерируемые; правка руками ловится `--check` | `scripts/provider-docs.py:276-317` |
| Codex-bindings валидируются: `support_level ∈ {hook-native, config-native, unsupported}`; `hook-native` требует `event`+`handler`, остальные — запрещают `event`/`matcher`/`handler` | `packages/harness/lib/harness/hooks.py:104-126` |
| `render_codex_hooks` уже рендерит ЛЮБОЕ число `hook-native` bindings в `.codex/hooks.json`, вызывая один обработчик с `--surface <id>`; но `render_codex_hook_handler` реализует ровно `context.observer` и на прочих `sys.exit(2)` | `hooks.py:183-205` |
| CLI умеет только `harness hooks --provider codex --observer`; иных поверхностей оператору не выдать | `hooks.py:617-622` |
| `provider-docs.py --check` и `scripts/test-provider-docs.py` **не вызываются ни одним гейтом** (ни `validate.sh` пакетов, ни `.github/workflows/*`) | `grep -rn provider-docs .github/workflows packages/*/scripts` — пусто; дом root-скриптовых гейтов — `.github/workflows/hygiene.yml` |

## Не проверено (риск принят явно)

- `[UNVERIFIED]` Живой прогон Codex CLI с несколькими `hook-native` поверхностями не
  делался — вся Ф9 стоит на доке; round-trip гейт вне скоупа плана (D3).
- `[UNVERIFIED]` Для каких именно событий `permission_mode` отсутствует — дока говорит
  «for most events», поимённого перечня нет. Реализация обязана трактовать поле как
  опциональное для событий вне уже проверенного `SessionStart`.
- `[UNVERIFIED]` Формат транскрипта Codex (`transcript_path`, `agent_transcript_path`) не
  изучался: пригодность для run-report-разбора уровня Claude неизвестна.
- `[UNVERIFIED]` Версия Codex CLI у владельца не фиксировалась; доки читаны 2026-07-29 и
  могут опережать установленный бинарь (та же оговорка, что в `findings/02`).
