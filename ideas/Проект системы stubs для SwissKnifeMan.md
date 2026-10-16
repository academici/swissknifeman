# Проект системы stubs для SwissKnifeMan

## Краткий вердикт

Идея правильная и хорошо ложится на существующую архитектуру prompt blocks, но её нельзя реализовывать как простую замену файлов `roles/*.md`. Нужен отдельный, версионированный слой **дополнительных инструкций**, который не способен изменить capability contract роли, имеет детерминированный порядок разрешения global/project overrides, попадает в prompt manifest и замораживается на весь run.

Рекомендуемый пользовательский каталог — `.swissknifeman/stubs/` в проекте и XDG-каталог `~/.config/swissknifeman/stubs/` для глобальных пользовательских правил. В source checkout самого SwissKnifeMan обычная project-local папка `<repo>/.swissknifeman/stubs/` будет тем самым вариантом «опубликовать внутри SwissKnifeMan»; писать в установленный Python package или `packages/orch/roles` команда не должна.

## Что уже подходит

В `packages/orch` сейчас есть восемь явных role targets: `advisor`, `bounded-implementer`, `context-scout`, `executor`, `registrar`, `researcher`, `reviewer` и `triager`; canonical instruction и JSON manifest уже разделены по файлам. Manifest reviewer отдельно фиксирует tool capabilities, отсутствие write authority, result shape, минимальный model class и forbidden inputs.

Canonical role text защищён digest-проверкой: `load_role()` загружает manifest и instruction, а `check_instructions()` выдаёт `INSTRUCTIONS_DRIFT`, если текст не соответствует SHA-256 из manifest. Поэтому project customization нельзя реализовывать заменой `reviewer.md`: это уничтожит различие между доверенным контрактом продукта и пользовательской политикой.

Prompt assembler уже представляет prompt как список `Block(kind, origin, text)`, считает digest и token estimate каждого блока и формирует `prompt-manifest/v1` с итоговым digest всего prompt. Это почти готовая точка расширения: stub должен стать отдельным block kind с собственными origin, layer, target ID и digest, а не частью canonical role text.

Project subsystem уже умеет определять корень, работать через `.swissknifeman/`, применять project lock, выполнять durable replacement, отказывать symlink и не трогать неизвестные пользовательские файлы. Новый publisher следует строить на тех же primitives и сохранять правило: после первоначального создания stub является пользовательским файлом и никогда не перезаписывается обычным `sync`.

## Терминология

Название `stubs` удобно как пользовательский термин и имя команды. Во внутреннем contract лучше использовать `instruction overlay`, потому что файл не является заглушкой исполняемого объекта и не заменяет роль.

Предлагаемые понятия:

- **Target** — стабильный логический ID точки кастомизации, например `orch.role.reviewer`.
- **Stub file** — опубликованный редактируемый Markdown-файл одного target.
- **Layer** — `builtin`, `user` или `project`.
- **Slot** — один уровень общности: all, package, kind или exact target.
- **Resolved overlay** — содержимое, выбранное resolver для конкретного target.
- **Instruction snapshot** — неизменяемая копия resolved overlays, используемая данным run.

## Каталоги

Рекомендуемая project-local структура:

```text
.swissknifeman/
├── launcher.py
├── launcher.lock.json
├── config.toml
└── stubs/
    ├── .published.json
    ├── _all.md
    ├── orch/
    │   ├── _all.md
    │   └── roles/
    │       ├── _all.md
    │       ├── advisor.md
    │       ├── bounded-implementer.md
    │       ├── context-scout.md
    │       ├── executor.md
    │       ├── researcher.md
    │       ├── reviewer.md
    │       └── triager.md
    └── planner/
        ├── _all.md
        ├── commands/
        │   ├── design.md
        │   ├── dev.md
        │   ├── fix.md
        │   ├── plan-audit.md
        │   ├── plan-design.md
        │   ├── plan-run.md
        │   ├── research.md
        │   └── review.md
        └── workflows/
            ├── audit-adversarial/
            │   ├── finder.md
            │   ├── dedup.md
            │   └── verifier.md
            ├── author-by-spec/
            │   ├── author.md
            │   └── self-check.md
            ├── dev-slice/
            │   ├── implementer.md
            │   ├── test-fixer.md
            │   └── reviewer.md
            └── research-fanout/
                ├── researcher.md
                └── verifier.md
```

Глобальный пользовательский слой повторяет эту структуру под:

```text
${XDG_CONFIG_HOME:-~/.config}/swissknifeman/stubs/
```

Встроенный catalog и пустые templates должны поставляться read-only внутри пакетов. Они являются источником для `publish`, но не runtime-слоем пользовательского переопределения.

`registrar` в первой версии публиковать не следует. Его closing prompt требует исполнить ровно одну построенную conductor команду и запрещает любое другое действие; дополнительные инструкции здесь увеличат неоднозначность критического side-effect шага. По той же причине не должны быть targets для `closer`, report fixer, result contracts, check runner и внутренних recovery prompts.

## Почему не `packages/*/stubs`

Папки `packages/orch/stubs` и `packages/planner/stubs` полезны только как **поставляемый каталог шаблонов и registry**, но не как место пользовательского редактирования. Установленный package может находиться в read-only environment, обновление пакета затрёт изменения, а source checkout не должен вести себя иначе, чем установленная версия.

Если команда запущена из корня репозитория SwissKnifeMan, auto resolution найдёт этот Git-проект и создаст `<repo>/.swissknifeman/stubs`. Это выполняет исходное требование без записи в product source и без особого случая для собственного репозитория.

## Catalog targets

Target ID должен быть стабильным публичным интерфейсом и не зависеть от физического Python function name или JS label. Минимальный catalog record:

```json
{
  "$schema": "urn:swissknifeman:aicore:stub-target:v1",
  "id": "orch.role.reviewer",
  "package": "orch",
  "kind": "role",
  "path": "orch/roles/reviewer.md",
  "title": "Reviewer additional instructions",
  "insertion_point": "after-canonical-before-input",
  "customizable": true,
  "since": "1.0",
  "max_bytes": 32768,
  "capability_boundary": "orch.role-manifest/v1"
}
```

Role targets можно генерировать из allowlist role manifests, но не простым `glob('*.md')`: случайно добавленный файл не должен автоматически становиться prompt input. Planner targets нужно зарегистрировать явно, потому что его workflow prompts сейчас встроены в JS-функции `finderPrompt`, `dedupPrompt` и `verifyPrompt`, а вызовы `agent()` используют labels, не являющиеся версионированным API.

Planner уже содержит десять command instruction files и четыре canonical workflow templates. Workflow targets должны описывать **логические функции субагентов**, а не конкретный индекс dimension или judge; например, все `judge:1..3` используют один target `planner.workflow.audit-adversarial.verifier`.

## Формат Markdown

Публикуемый файл должен выглядеть так:

```markdown
<!-- skm-stub:v1 target=orch.role.reviewer mode=replace -->
<!-- Add project-specific reviewer instructions below. An empty body inherits the user/global layer. -->
```

Правила:

- UTF-8 без interpolation, include, environment expansion и executable directives.
- Служебные leading comments не передаются модели.
- Пустое или comment-only body означает `inherit`, даже если metadata содержит `mode=replace`.
- `mode=replace`: непустой project body заменяет body того же slot из user layer.
- `mode=append`: непустой project body применяется после user body того же slot.
- `mode=disable`: подавляет lower-layer body этого slot; другой текст запрещён.
- `target` в metadata обязан совпадать с catalog target/path.
- Неизвестный metadata key — validation error, а не молчаливое игнорирование.
- Line endings нормализуются до LF для digest; финальный newline задаётся renderer детерминированно.

Ключевой случай: команда публикует **все пустые файлы**, но это не должно заглушать существующие глобальные инструкции. Поэтому file existence не может само по себе означать override; resolver обязан учитывать semantic emptiness.

## Разрешение слоёв

Для target `orch.role.reviewer` resolver рассматривает четыре slot:

1. `_all.md`;
2. `orch/_all.md`;
3. `orch/roles/_all.md`;
4. `orch/roles/reviewer.md`.

Внутри каждого slot применяется precedence `project > user > builtin`. Между slot итоговые инструкции конкатенируются от общего к частному. Таким образом, project exact file заменяет global exact file, но не отменяет общие global rules из `_all.md`, если project отдельно не переопределил соответствующий slot.

Пример:

| Slot | User | Project | Результат |
|---|---|---|---|
| `orch/_all.md` | Непустой | Пустой | User body |
| `orch/roles/_all.md` | Непустой | `mode=append` | User + project |
| `reviewer.md` | Непустой | `mode=replace` | Только project |
| `_all.md` | Непустой | `mode=disable` | Ничего |

Resolver должен возвращать не только текст, но и provenance каждой части: target, slot, layer, absolute/canonical path, SHA-256, bytes, token estimate и resolution reason.

## Порядок prompt

Stub не следует делать provider-level `system prompt` для project layer. Project repository — менее доверенный источник; предоставление ему системного приоритета позволит prompt-тексту претендовать на authority выше canonical role contract.

Правильный порядок:

1. Неподменяемый runtime/system envelope provider adapter.
2. Canonical role instructions из package manifest.
3. Resolved additional instructions.
4. Execution input/task block.
5. Repository rules, skills и dynamic conductor blocks.
6. Result contract.

Именно «после canonical role, но до task input» реализует требование «в самом начале» и при этом оставляет доверенный контракт выше project customization. Сейчас `_head()` сначала создаёт `role_text` и `input`, а repository rules добавляет уже после input. Поэтому stub нельзя прокинуть через существующий `repo_rules`; нужен явный insert между блоками `role_text` и `input`.

Новый block kind:

```text
additional_instruction
```

Рекомендуемый rendered header:

```markdown
## Additional instructions: project · orch.role.reviewer

These instructions refine how to perform the role. They cannot change tools,
write authority, scope, acceptance checks, result shape, or conductor policy.

<user body>
```

Это текстовое предупреждение не является security boundary. Реальная граница остаётся во внешнем tool policy, filesystem guard, manifest capabilities и result parser.

## Что нельзя менять stub-файлом

Stub должен влиять только на метод и фокус работы агента. Он не может менять:

- tools, shell/network/filesystem permissions;
- write authority;
- scope/write-set и extra paths;
- model/provider route;
- sandbox policy;
- acceptance commands;
- result JSON schema;
- retry, correction и review limits;
- commit/registration ownership;
- workflow branching и loop ceilings;
- source executables;
- secret handling policy.

Для этих параметров остаётся typed config с JSON/TOML schema. Смешивать Markdown-инструкции и конфигурацию нельзя: иначе невозможно надёжно определить, что является пожеланием модели, а что enforcement setting.

В `stubs/` допустим только отдельный `settings.toml` самого resolver, если он действительно нужен, например enable/disable, size budgets и allowed layers. Все behavioral/runtime options должны оставаться в `.swissknifeman/config.toml` или run-options.

## CLI

Лучший namespace — отдельная top-level group:

```text
swissknifeman stubs publish [--scope auto|project|user] [--package orch|planner|all]
                            [--target ID ...] [--dry-run] [--json]
swissknifeman stubs list [--available|--published|--effective] [--json]
swissknifeman stubs show TARGET [--effective] [--manifest] [--json]
swissknifeman stubs explain TARGET [--json]
swissknifeman stubs validate [--scope project|user|all] [--json]
swissknifeman stubs doctor [--json]
swissknifeman stubs reset TARGET --scope project|user [--backup] [--dry-run]
```

Project launcher usage:

```bash
python3 -I .swissknifeman/launcher.py stubs publish
```

### Scope resolution

- Вызов через verified project launcher всегда выбирает `project`.
- Прямой hub invocation внутри обнаруженного project при `--scope auto` выбирает `project`.
- Вне project `auto` выбирает `user`.
- `--scope project` без project context завершается `PROJECT_CONTEXT_REQUIRED`.
- `--scope user` всегда использует XDG path независимо от cwd.
- Для automation рекомендуется обязательный явный `--scope`.

Нельзя вводить скрытый special case «если это репозиторий SwissKnifeMan — писать в packages». Его собственный checkout является обычным project.

### Publish semantics

`publish` должен быть идемпотентным:

- создавать отсутствующие directories и files;
- сообщать `created`, `unchanged`, `refused`;
- никогда не перезаписывать существующий regular file;
- всегда отказывать symlink, FIFO, device и directory вместо файла;
- использовать exclusive create и project/user lock;
- durable write применять только к managed `.published.json`, но пользовательский stub создавать через `O_CREAT|O_EXCL`;
- при появлении новых catalog targets повторный `publish` создаёт только недостающие файлы;
- удалённые targets сохраняются как orphan и показываются `doctor`, но не загружаются.

`reset` — отдельная явно destructive команда. Перед заменой непустого файла она делает backup; обычные `project sync` и package upgrades stubs не меняют.

## Published manifest

`.published.json` должен быть managed metadata, но не источником истины runtime:

```json
{
  "$schema": "urn:swissknifeman:aicore:stub-publication:v1",
  "catalog_digest": "sha256:...",
  "packages": ["orch", "planner"],
  "targets": ["orch.role.reviewer"],
  "published_at": "2026-10-15T20:00:00Z"
}
```

Runtime загружает только targets текущего catalog. Manifest нужен для diagnostics, upgrade diff и обнаружения новых/orphan files. Пользовательские content digests в нём хранить не нужно: иначе каждое ручное редактирование делает manifest stale.

## Reproducibility

Stub content нельзя перечитывать заново на каждом шаге. В начале run conductor должен:

1. Разрешить все targets, которые потенциально понадобятся policy pack.
2. Проверить типы файлов, symlinks, размер, UTF-8 и metadata.
3. Построить `instruction-set/v1` manifest.
4. Скопировать exact normalized bodies в run state.
5. Зафиксировать `instruction_set_digest` в `run.json` и событии `orch.run.started`.
6. Использовать snapshot до завершения run и всех resume.

Изменение project/global stub во время run не должно менять продолжающийся prompt. `resume` использует snapshot; текущая конфигурация может быть показана как `INSTRUCTIONS_CHANGED_SINCE_RUN`, но новый текст применяется только к новому run.

Это особенно важно для shared provider sessions: system/preamble instructions нельзя безопасно менять между resume calls. Instruction digest также должен входить в provider cache key и prompt manifest.

## Prompt manifest

Существующий manifest уже хранит kind, origin, block SHA-256, token estimate и total prompt digest. Для stub blocks нужно расширить origin metadata без потери совместимости:

```json
{
  "kind": "additional_instruction",
  "origin": ".swissknifeman/stubs/orch/roles/reviewer.md",
  "target": "orch.role.reviewer",
  "slot": "orch/roles/reviewer.md",
  "layer": "project",
  "mode": "replace",
  "sha256": "...",
  "tokens": 418
}
```

`orch conduct prompt explain` должен показывать applied, inherited, disabled и excluded stubs. Это позволит оператору ответить на главный вопрос: «почему reviewer получил именно эту инструкцию?»

## Planner integration

В orch интеграция локальна: все основные роли проходят через `_head()`, поэтому resolver можно вызвать в одном месте. В planner ситуация сложнее: prompt builders встроены в копируемые JS workflow templates, а workflow README прямо говорит, что это portable templates, которые копируются в `plans/<ID>/workflows/` и затем живут отдельно.

Перед включением planner stubs нужен стабильный runtime API, например:

```javascript
const extra = await instructions('planner.workflow.audit-adversarial.finder')
return [canonicalPrompt, extra].filter(Boolean).join('\n\n')
```

Требования к helper:

- target разрешается центральным Python/runtime resolver, а не JS filesystem traversal;
- workflow не получает произвольный путь;
- helper возвращает snapshot content данного run;
- target ID и digest входят в workflow journal/cache key;
- неизвестный target останавливает workflow до первого agent dispatch;
- старые скопированные workflows без helper продолжают работать без stubs, но doctor сообщает `STUBS_NOT_SUPPORTED_BY_WORKFLOW`;
- template revision явно указывает supported instruction catalog version.

Без такого API попытка автоматически prepend-ить текст ко всем `agent()` вызовам будет слишком широкой: dedup/control-flow agent, reviewer и implementer имеют разные обязанности и capabilities.

## Командные stubs планера

Planner command files (`design.md`, `dev.md`, `fix.md`, `plan-*`, `research.md`, `review.md`) уже являются отдельными instruction entrypoints. Для них target должен обозначать command invocation, например `planner.command.plan-design`, а вставка выполняться после canonical command contract и до пользовательского запроса.

Command stub не должен автоматически передаваться всем workflow subagents. Если проект хочет одинаковое правило и для команды, и для субагентов, оно помещается в `planner/_all.md`; resolver применит его обоим через общий slot.

## Безопасность

### Filesystem

- Каждый candidate path canonicalize через existing project boundary helper.
- Запрещены symlink и hardlink с неожиданным inode reuse на load; для строгого режима файл открывается `O_NOFOLLOW`, а затем проверяется через `fstat`.
- User root также не должен проходить через symlinked `stubs` directory без явной политики.
- При snapshot сохраняется содержимое уже открытого descriptor, а не повторно открывается путь.
- Максимум на один body: 32 KiB; максимум applied text на target: 64 KiB; дополнительные token budgets задаются config.
- World-writable user/global file — fail; project file — warn или fail в strict production profile.

### Prompt injection

Project stub по определению является instruction input и может содержать попытку отменить правила. Защита состоит не в blacklist слов, а в невозможности изменить внешние capabilities. Validator может предупреждать о фразах `ignore previous`, `change write set`, `run any command`, но такие эвристики не должны считаться security control.

### Secrets

- Stub files считаются потенциально committed; `doctor` запускает targeted secret scan pattern set.
- Prompt manifest хранит digest, но не дублирует body.
- Snapshot body находится только в ignored run state с mode `0600`.
- `prompt explain` по умолчанию показывает origin/digest/tokens, а полный body — только с `--show-content`.
- Никакой variable expansion из environment, чтобы `${TOKEN}` не превратился в secret.

### Trust profiles

Production config должен иметь:

```toml
[instructions]
enabled = true
layers = ["user", "project"]
project_mode = "allow"
unknown_target = "fail"
invalid_stub = "fail"
max_file_bytes = 32768
max_target_tokens = 12000
snapshot = true
```

Для обработки недоверенных сторонних repositories оператор может задать `layers = ["user"]`; project stubs тогда перечисляются как excluded и никогда не достигают модели.

## Конфликт инструкций

Resolver не должен пытаться семантически решить конфликт LLM-текста. Он детерминированно собирает blocks, а canonical preamble сообщает authority order:

1. External runtime restrictions.
2. Canonical role contract.
3. Additional user/project instructions.
4. Task-specific guidance.
5. Informational context/research.

Если stub просит действие, запрещённое role manifest, фактический tool call блокируется, а run получает beacon `CUSTOM_INSTRUCTION_CONFLICT`. Такой beacon полезно генерировать при denied action с указанием target digest, но без вывода всего potentially sensitive body.

## Новые коды ошибок

- `STUB_TARGET_UNKNOWN`
- `STUB_TARGET_RETIRED`
- `STUB_SYMLINK_FORBIDDEN`
- `STUB_NOT_REGULAR`
- `STUB_OUTSIDE_ROOT`
- `STUB_INVALID_UTF8`
- `STUB_METADATA_INVALID`
- `STUB_TARGET_MISMATCH`
- `STUB_TOO_LARGE`
- `STUB_TOKEN_BUDGET`
- `STUB_MODE_INVALID`
- `STUB_CONFLICT`
- `STUB_PUBLICATION_LOCKED`
- `STUB_CATALOG_CHANGED`
- `STUBS_NOT_SUPPORTED_BY_WORKFLOW`
- `INSTRUCTIONS_CHANGED_SINCE_RUN`

Все ошибки до agent dispatch должны быть hard fail в strict profile. Нельзя молча игнорировать malformed non-empty project stub.

## Сценарии проверки

### Resolution

- Нет user/project файлов.
- Только user exact target.
- Пустой project exact наследует user.
- Project replace, append и disable.
- Общий user `_all` плюс project exact.
- Project отключает только package slot.
- Одновременные общие и exact instructions.
- Неизвестный/orphan target.
- Новый catalog target после upgrade.
- Target removed после downgrade.

### Publication

- Первый publish и повторный idempotent publish.
- Publish после добавления target новой версией.
- Existing edited file никогда не перезаписывается.
- Symlink/FIFO/directory вместо target.
- Конкурентные publish processes.
- Crash до/после create и manifest replace.
- Read-only project/XDG directory.
- Project path с Unicode, пробелами и длинным именем.
- `--scope auto`, explicit project и explicit user.
- Запуск через launcher и через hub binary.

### Parsing

- Empty, whitespace-only и comments-only body.
- BOM, CRLF и no final newline.
- Invalid UTF-8.
- Неверный target в header.
- Duplicate metadata headers.
- Unknown mode/key/version.
- Markdown с backticks, HTML comments и огромной строкой.
- Текст с `${ENV}`, shell syntax и include-like directives остаётся literal.
- Exact byte/digest determinism на Linux/macOS.

### Runtime

- Stub изменён между run start и reviewer stage.
- Stub удалён перед resume.
- Global config изменён после snapshot.
- Shared session и per-item session.
- Frozen run меняет собственный stubs implementation.
- Prompt cache различает два instruction digests.
- `prompt explain` полностью объясняет provenance.
- Invalid stub останавливает run до provider charge.
- Project layer выключен production config.
- Denied tool call после конфликтующей instruction.

### Planner

- Все logical workflow roles получают только свой target.
- Finder не получает verifier-only instruction.
- Judge panel из трёх агентов получает один snapshot/digest.
- Copied old workflow сообщает unsupported, но не ломается.
- Resume workflow не меняет instructions.
- Cache invalidируется изменением stub.
- Command stub не протекает в subagent без `_all`.
- Unknown target останавливает dispatch.

## Тестовые инварианты

- Canonical role digest не зависит от stubs.
- Stub никогда не меняет role manifest/tool policy/result shape.
- Один и тот же catalog + layers + files даёт один instruction-set digest.
- Пустой published project file не маскирует user layer.
- Existing user content никогда не перезаписывается `publish` или `project sync`.
- Resume использует тот же instruction snapshot, что начальный run.
- Prompt manifest перечисляет каждый applied body ровно один раз.
- Unknown file не загружается только потому, что имеет расширение `.md`.
- Symlink никогда не читается как stub.
- Изменение effective body меняет prompt/cache digest.
- `mode=disable` не передаёт lower-layer body.
- Project stubs не применяются, если policy исключает project layer.

## Реализация по этапам

### Этап 1 — orch MVP

1. В `aicore` добавить catalog/resolver/parser/snapshot library.
2. Добавить top-level `stubs` CLI.
3. Опубликовать orch targets, кроме registrar/control-only prompts.
4. Вставлять `additional_instruction` между canonical role и input.
5. Добавить provenance в prompt manifest и `prompt explain`.
6. Включить instruction-set digest в run metadata и resume.
7. Добавить doctor/validate и полный negative corpus.

### Этап 2 — production hardening

1. `O_NOFOLLOW`, size/token limits, permission checks.
2. Project/user locks и crash-safe publication metadata.
3. Secret diagnostics.
4. Policy, позволяющая отключать project layer.
5. Config/schema/docs parity.
6. Fault injection и property tests.

### Этап 3 — planner commands

1. Создать stable IDs для command targets.
2. Подключить тот же resolver и snapshot semantics.
3. Гарантировать canonical-before-stub-before-user-input order.
4. Добавить explain output.

### Этап 4 — planner workflows

1. Создать централизованный `instructions(target)` runtime helper.
2. Версионировать workflow template support.
3. Зарегистрировать logical subagent targets.
4. Обновить четыре canonical templates.
5. Добавить migration/doctor для уже скопированных workflows.

## Acceptance criteria

Функция готова к production, когда:

- `publish` идемпотентен и не перезаписывает пользовательские файлы;
- project override имеет документированную, тестируемую precedence;
- пустые опубликованные файлы корректно наследуют global layer;
- canonical role contracts и capability manifests остаются неизменными;
- stubs видны отдельными blocks в prompt manifest;
- run и resume используют один instruction snapshot;
- project layer можно полностью отключить policy;
- malformed, oversized и symlink stubs отказываются до provider call;
- planner использует stable target registry, а не filesystem wildcard или JS label;
- `doctor` называет orphan, unsupported workflow, conflict, permission и secret risks;
- каждый effective prompt объясним командой `stubs explain`/`prompt explain`.

## Дополнительные находки

Самый важный скрытый риск идеи — публикация всех пустых файлов при обычном file-existence override: она мгновенно замаскировала бы все глобальные инструкции. Semantic-empty inheritance и явные modes обязательны.

Второй риск — называть project text «system prompt». Project является менее доверенным слоем, поэтому он должен быть ранним instruction block, но не иметь provider-level system authority. Canonical role contract и внешние capability enforcement должны оставаться выше.

Третий риск — planner workflow templates копируются в планы и содержат prompts непосредственно в JavaScript. Поэтому planner workflow stubs нельзя надёжно добавить одним глобальным prepend hook; сначала нужен stable target/runtime API.

Наконец, существующая block/manifest архитектура orch делает MVP сравнительно небольшим и хорошо проверяемым изменением. Начинать следует с orch roles и CLI/resolver, а не одновременно менять planner workflows, project sync и все prompt entrypoints.