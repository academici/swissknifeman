<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# [https://github.com/academici/swissknifeman](https://github.com/academici/swissknifeman)

Смотри, в чём проблема. Я хочу, чтобы ты посмотрел пакет Task и Harness с Artifex. Что меня не устраивает? Меня не устраивает, что такие вот провайдеры, как Codex и Grok, они очень плохо работают вот с таким вот, ну, с пакетом Task. То есть они постоянно путаются, что-то не так делают, зависают. Что я придумал? Я сейчас доработаю Task таким образом, чтобы его основным назначением было просто разбить план по задачам и как бы составить её описание такое. И всё. А дальше мы... дальше я хочу выстроить... Ну, то есть я от Harness и Artifex, по сути, откажусь, потому что он у меня слабый и очень нестабильный и очень много времени уйдёт на его доработку. Поэтому я хочу, чтобы ты для меня подобрал оптимальное окружение. Я тебе скину ссылки, то, что я как бы нашёл, но ты можешь что-то ещё подобрать и вот несколько вариаций для моей системы накидать. Что я хочу получить в итоге? Я хочу получить в итоге вот что-то типа Harness'а такого, то есть который в себе содержит разных... может управлять разными другими провайдерами. То есть у меня есть учётка Cloud Code, у меня есть учётка Codex, есть учётка Grok. И чтобы я в терминале писал, то есть у меня было настроено окружение так, что там, допустим, считывается что-то из конфига, задачи, и он сам понимает, как оркестрировать. То есть у меня, допустим, первая, самая какая-нибудь дешёвая модель, она собирает контекст по задаче. То есть всё, что нужно... её задача — просто собрать всю инфу и представить уже в таком вот конечном виде. Дальше уже идут сами мозги. То есть такая вот сложная модель, она делает самую сложную часть работы. То есть там накидывает каркас, а уже добить, ну, написать там сам код, вот именно такой вот банальный, уже более такая слабая модель. И ревью можно вообще такой сильной моделью. Вообще там, допустим, то есть выполняет ChatGPT, а ревью делает Grok. Ну, то есть в рамках каждой задачи я могу как угодно менять вот эту вот последовательность и схему работы. То есть где-то, допустим, ревью вообще не нужен, где-то я не захочу передавать написание кода на другие модели. Вот так, чтобы это легко и гибко настраивалось, и я мог на любой провайдер нужную задачу как бы ставить. И тут вот несколько вариантов: есть типа готовые CLI-решения, а есть типа такое что-то API на JavaScript, которое позволит мне в рамках моего Harness'а написать тоже вот типа такие скрипты, которые будут покрывать все мои сценарии. Единственное только, я бы, конечно, хотел видеть всё, что происходит в консоли. И вот когда я говорю, допустим, Codex, выполни, допустим, какую-то команду и сделай ревью на Grok. Я не вижу, что там происходит, то есть для меня это всё скрыто. И он может тупить, он может неправильно делать, то есть для меня это всё должно тоже открытым оставаться. Поэтому для меня нужно подобрать самое грамотное такое окружение. Ну и плюс ко всему я там, допустим, чтобы встраивал свои скиллы, код-ревью, чтобы не мне писать там, допустим, какие-то собственные скиллы, а вот чтобы было готово. То есть я тебе сейчас скину материалы, ты их просто проанализируй, но ты можешь ещё своё как бы дополнять. Мне нужно подобрать идеальное окружение.

[https://www.harness.io/products/platform/cli](https://www.harness.io/products/platform/cli)
[https://pydantic.dev/docs/ai/harness/](https://pydantic.dev/docs/ai/harness/)
[http://hermes-agent.nousresearch.com/](http://hermes-agent.nousresearch.com/)
[https://github.com/autonomous-ai/openharness](https://github.com/autonomous-ai/openharness)
[https://github.com/vercel/ai](https://github.com/vercel/ai)
[https://github.com/awslabs/cli-agent-orchestrator](https://github.com/awslabs/cli-agent-orchestrator)
[https://github.com/PrimeIntellect-ai/prime-agent](https://github.com/PrimeIntellect-ai/prime-agent)
[https://github.com/obra/superpowers](https://github.com/obra/superpowers)
[https://github.com/affaan-m/ECC](https://github.com/affaan-m/ECC)
[https://github.com/tirth8205/code-review-graph/](https://github.com/tirth8205/code-review-graph/)
[https://github.com/lidge-jun/opencodex](https://github.com/lidge-jun/opencodex)
[https://github.com/wshobson/agents](https://github.com/wshobson/agents)
[https://github.com/langgenius/dify](https://github.com/langgenius/dify)
[https://github.com/ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd)

Оптимальная архитектура для твоего случая — **не искать ещё один монолитный Harness**, а оставить `Task` генератором формализованных заданий и построить тонкий детерминированный CLI-оркестратор, который сам запускает Claude Code, Codex и Grok как отдельные процессы. Модель не должна просить другую модель что-либо сделать: маршрутизация, тайм-ауты, порядок стадий, логи и проверки должны находиться в обычном коде.

## Главный вывод

Я бы выбрал такую комбинацию:


| Слой | Рекомендация |
| :-- | :-- |
| Формирование задач | Твой переработанный `Task` |
| Исполнение workflow | Упрощённый `Harness` → `Runner` или `Orchestrator` |
| Провайдеры | Нативные CLI Claude Code, Codex CLI, Grok CLI |
| Готовые skills | Superpowers как основа + выборочные skills из ECC |
| Изоляция | `git worktree` на задачу или стадию |
| Видимость | PTY + `tmux`/`zellij` + JSONL event log |
| Состояние | Артефакты на диске + небольшая SQLite-база |
| Проверки | Обычные команды: PHPUnit/Pest, PHPStan, Pint, ESLint, тесты |
| API-модели | Только как дополнительный adapter, не основа |
| Artifex | Вывести из эксплуатации |
| Prime Agent | Рассматривать как отдельного long-running worker, но не центральный оркестратор |

В [swissknifeman](https://github.com/academici/swissknifeman) уже разделены `task`, `harness` и `artifex`, поэтому переход можно сделать эволюционно, а не переписывать весь проект сразу.

## Почему Harness нестабилен

Проблема, судя по описанию, не столько в конкретных моделях, сколько в том, что **оркестрация сейчас частично отдана самой модели**:

- Модель должна понять Task.
- Решить, кого и когда вызвать.
- Правильно сформировать дочерний запрос.
- Дождаться результата.
- Определить, завершилась ли работа.
- Интерпретировать неструктурированный ответ.
- Продолжить выполнение без потери состояния.

Это слишком много неявных обязанностей. Codex или Grok могут прекрасно писать код, но быть плохими диспетчерами процессов: зависнуть, повторно выполнить действие, потерять критерии готовности или заявить об успехе без проверки.

Правильная граница ответственности выглядит так:

```text
TaskSpec
   ↓
Deterministic Orchestrator
   ├── Claude Code process
   ├── Codex CLI process
   ├── Grok CLI process
   ├── Tests / linters
   └── Human approval
```

Ни один провайдер не запускает другого провайдера. Каждый CLI видит только свою стадию, рабочую директорию и заранее подготовленные входные артефакты.

## Новый контракт Task

`Task` действительно стоит оставить только для декомпозиции и подготовки задания. Но результатом должен быть не свободный Markdown-план, а стабильный `TaskSpec`, пригодный для машинного исполнения.

Минимальный контракт:

```yaml
version: 1

task:
  id: CRM-142
  title: Add idempotent invoice generation
  goal: >
    Generate one invoice per billing period even when the job is retried.

  non_goals:
    - Changing payment provider integration
    - Redesigning the billing UI

  constraints:
    - Laravel transaction boundaries must be explicit
    - PostgreSQL must enforce the uniqueness invariant
    - Existing public API must remain compatible

  acceptance:
    - Concurrent retries cannot create duplicate invoices
    - A failed attempt can be retried safely
    - Existing billing tests remain green

  verification:
    - php artisan test --testsuite=Billing
    - vendor/bin/phpstan analyse
    - vendor/bin/pint --test

  dependencies: []
  risk: high

execution:
  preset: risky-backend

  overrides:
    context:
      provider: claude

    architecture:
      provider: claude

    implementation:
      provider: codex

    review:
      enabled: true
      provider: grok

    fix:
      provider: codex
```

Ключевые поля каждой подзадачи:

- `goal`;
- `non_goals`;
- `constraints`;
- `acceptance`;
- `verification`;
- `dependencies`;
- `risk`;
- `context_queries`;
- `expected_outputs`;
- `execution.preset`;
- точечные `execution.overrides`.

При этом `Task` не должен знать, с какими аргументами запускается `codex` или где Claude Code хранит сессии. Он выбирает логические роли и workflow, а технические детали остаются в provider adapters.

## Конфигурация workflow

Базовая конфигурация должна жить отдельно от Task:

```yaml
providers:
  claude:
    adapter: claude-code
    auth: native
    profile: default

  codex:
    adapter: codex-cli
    auth: native
    profile: default

  grok:
    adapter: grok-cli
    auth: native
    profile: default

workflows:
  risky-backend:
    stages:
      - id: context
        provider: claude
        role: context-researcher
        access: read-only
        outputs:
          - context.md
          - relevant-files.json

      - id: architecture
        provider: claude
        role: architect
        access: read-only
        inputs:
          - task.yaml
          - context.md
        outputs:
          - design.md

      - id: implementation
        provider: codex
        role: implementer
        access: workspace-write
        inputs:
          - task.yaml
          - context.md
          - design.md
        skills:
          - tdd
          - laravel-patterns
          - postgres-patterns

      - id: verify
        runner: command
        commands:
          - php artisan test
          - vendor/bin/phpstan analyse
          - vendor/bin/pint --test

      - id: review
        provider: grok
        role: reviewer
        access: read-only
        optional: true
        outputs:
          - review.json

      - id: fix
        provider: codex
        role: implementer
        when: review.has_blocking_findings

      - id: final-verify
        runner: command
```

Для маленькой задачи можно использовать другой preset:

```yaml
workflows:
  small-fix:
    stages:
      - id: implementation
        provider: codex

      - id: verify
        runner: command
```

Для сложной архитектурной задачи:

```yaml
workflows:
  architecture-heavy:
    stages:
      - id: context
        provider: codex

      - id: architecture
        provider: claude

      - id: implementation
        provider: claude

      - id: review
        provider: grok

      - id: fix
        provider: claude

      - id: final-verify
        runner: command
```

Это даст именно ту гибкость, которую ты описал: review можно отключить, реализацию не обязательно делегировать дешёвой модели, а одного провайдера можно использовать на нескольких стадиях.

## Не transcript, а artifacts

Модели не должны передавать друг другу длинные истории сессий. Контрактом между стадиями должны быть файлы:

```text
.swissknifeman/runs/CRM-142-20261005T143000/
├── task.yaml
├── run.json
├── context/
│   ├── context.md
│   └── relevant-files.json
├── architecture/
│   └── design.md
├── implementation/
│   ├── transcript.log
│   └── result.json
├── review/
│   ├── findings.json
│   └── transcript.log
├── verification/
│   ├── phpunit.log
│   ├── phpstan.log
│   └── result.json
└── events.jsonl
```

Артефакт следующей стадии должен содержать только необходимую информацию. Полные терминальные логи сохраняются для диагностики, но не становятся автоматически контекстом следующей модели.

`review.json` лучше сделать структурированным:

```json
{
  "verdict": "changes_required",
  "findings": [
    {
      "severity": "blocking",
      "file": "app/Billing/InvoiceService.php",
      "line": 84,
      "category": "concurrency",
      "description": "Application-level check does not prevent concurrent inserts",
      "suggested_verification": "Add a concurrent retry integration test"
    }
  ]
}
```

Review-агент не должен редактировать код. Он только создаёт findings; исправления выполняет отдельная стадия с чистым контекстом.

## Полная видимость

Для твоего требования «видеть всё» обычного `stdout` недостаточно. Provider adapter должен запускать CLI внутри PTY, а не через скрытый tool call модели.

Рекомендуемый интерфейс:

```bash
skm run CRM-142
skm attach <run-id>
skm status <run-id>
skm logs <run-id> --stage implementation
skm replay <run-id>
skm cancel <run-id>
skm retry <run-id> --from review
```

В режиме `tmux`:

```text
┌ Control ──────────────┬ Active provider ───────────────┐
│ stage: implementation │ raw Codex terminal output      │
│ elapsed: 08:14        │ commands, prompts, responses   │
│ heartbeat: 4s         │                                │
├ Events ───────────────┼ Verification ──────────────────┤
│ file changed          │ PHPUnit: running               │
│ command started       │ PHPStan: pending               │
│ output received       │ Pint: pending                  │
└───────────────────────┴────────────────────────────────┘
```

Оркестратор обязан показывать:

- PID и provider adapter;
- текущую стадию;
- рабочую директорию и worktree;
- используемый input artifact;
- время последнего вывода;
- запущенную команду;
- текущий timeout;
- retry number;
- причину перехода между состояниями;
- exit code;
- результат deterministic verification.

Если процесс молчит, например, 60 секунд, это должно быть видно как `idle`, а не выглядеть как работа. После configurable timeout можно предложить `continue`, `interrupt`, `restart` или `open shell`.

## Технологический стек

Поскольку существующий swissknifeman уже выглядит как Python-проект, минимально рискованный путь — сохранить Python и радикально уменьшить Harness:


| Компонент | Вариант |
| :-- | :-- |
| CLI | Typer |
| Терминальный UI | Rich или Textual |
| Процессы | `asyncio.subprocess` |
| PTY | `pty`/`pexpect` |
| Схемы | Pydantic |
| Конфиг | YAML + Pydantic validation |
| Состояние | SQLite |
| Event log | JSONL |
| Изоляция | `git worktree` |
| Мультиплексор | `tmux` или `zellij` |

Если хочется вынести оркестратор в самостоятельный TypeScript-проект:


| Компонент | Вариант |
| :-- | :-- |
| Runtime | Node.js или Bun |
| Процессы | `execa` |
| PTY | `node-pty` |
| Схемы | Zod |
| TUI | Ink |
| Логи | Pino |
| Состояние | SQLite |
| Конфиг | YAML |
| Изоляция | `git worktree` |

Я бы **не переписывал существующий Runner на TypeScript только ради Vercel AI SDK**. Для запуска CLI-процессов Python достаточно; TypeScript имеет смысл, только если оркестратор станет отдельным продуктом с плагинным SDK.

## Готовые skills

### Superpowers

[Superpowers](https://github.com/obra/superpowers) сейчас выглядит лучшей основой для общей инженерной методологии. Он поддерживает Claude Code, Codex CLI, Grok Build CLI, Gemini CLI, Hermes, OpenCode и другие harness-окружения, а набор включает worktrees, TDD, systematic debugging, code review, verification и subagent-driven development.

Но нельзя устанавливать его одинаково для всех стадий:

- `context`: только исследование и verification-before-completion;
- `architecture`: brainstorming/architecture при необходимости;
- `implementation`: TDD, debugging, verification;
- `review`: requesting-code-review;
- `fix`: receiving-code-review, debugging, verification.

У тебя `Task` будет владеть планированием, поэтому автоматические `brainstorming` и `writing-plans` на implementation-стадии могут конфликтовать с уже утверждённым TaskSpec. Skills должны подключаться **по профилям стадий**, а не глобально целиком.

### ECC

[ECC](https://github.com/affaan-m/ECC) намного шире: он содержит специализированные агенты и skills для code review, security, TDD, Laravel, PostgreSQL, Docker и verification. При этом сам проект прямо разделяет уровень поддержки: Claude Code является основной платформой, Codex поддерживается через native plugin, а несколько других adapters имеют частичную или экспериментальную функциональность.

Для твоей системы я бы брал из ECC только:

- `laravel-patterns`;
- `laravel-security`;
- `laravel-tdd`;
- `laravel-verification`;
- `postgres-patterns`;
- `database-migrations`;
- `docker-patterns`;
- `deployment-patterns`;
- `security-review`;
- `verification-loop`;
- `iterative-retrieval`;
- `search-first`;
- code-reviewer и database-reviewer.

Не стоит подключать весь ECC одновременно. Его огромный каталог, hooks, memory и собственная оркестрация начнут конкурировать с Task/Runner и увеличат контекст; выборочная установка здесь надёжнее.

### Практическая комбинация

```text
Superpowers
  └── общая методология:
      TDD, debugging, worktrees, review, verification

ECC selective
  └── предметные skills:
      Laravel, PostgreSQL, security, migrations, Docker

Swissknifeman
  └── orchestration policy:
      кто, когда, в каком worktree, с какими входами и тайм-аутами
```

Skills дают моделям методику. Swissknifeman остаётся единственным владельцем lifecycle и состояния.

## Оценка вариантов

| Вариант | Соответствие | Основная проблема | Вердикт |
| :-- | --: | :-- | :-- |
| Собственный тонкий CLI Runner | 10/10 | Нужно написать adapters и state machine | Основной выбор |
| Prime Agent | 7/10 | Сам становится новым сложным harness | Альтернативный worker |
| Vercel AI SDK | 5/10 | Ориентирован на API, а не подписочные CLI | Дополнительный API adapter |
| Pydantic AI | 6/10 | Хорош для typed API workflows, но не решает terminal transparency сам | Возможная библиотека |
| Superpowers | 9/10 как skills | Не является центральным оркестратором | Обязательно протестировать |
| ECC | 8/10 выборочно | Полная установка тяжёлая и неодинакова между harnesses | Использовать частями |
| Готовый CLI orchestrator | Потенциально 6–8/10 | Нужно проверить native auth, PTY и resumability | Только через bake-off |
| Dify-подобная платформа | 3/10 | Слишком далеко от terminal-first coding workflow | Не выбирать ядром |

### Prime Agent

[Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent) интересен именно для долгоживущих задач: у него есть persistent Python REPL, встроенные subagents, background daemon, reattach, heartbeat, schedules и bounded autonomous mode. Он также позволяет выбрать subscription- или API-key provider при входе.

Но это уже самостоятельный harness со своей моделью состояния, skills и orchestration semantics. Поэтому его лучше использовать как один из provider adapters для специальных long-running задач, а не помещать над Claude, Codex и Grok как обязательный центральный слой. Кроме того, проект прямо предупреждает, что выполнение идёт с пользовательскими правами и не является security sandbox.

### Vercel AI SDK

[Vercel AI SDK](https://github.com/vercel/ai) даёт единый TypeScript API для разных model providers, structured output и tool-loop agents. Однако его основная модель подключения — AI Gateway или прямые provider SDK, то есть API-аутентификация, а не управление уже авторизованными подписочными CLI-сессиями.

Поэтому он полезен для:

- дешёвого API context collector;
- классификатора задач;
- structured output;
- fallback-моделей;
- небольших служебных стадий.

Но он не решает твою главную проблему: открытый терминал, native CLI subscriptions, attach к процессу и наблюдение за реальными действиями coding agent.

## Provider adapters

Нужен небольшой capability contract:

```python
class ProviderAdapter(Protocol):
    async def capabilities(self) -> Capabilities: ...
    async def start(self, request: StageRequest) -> RunningSession: ...
    async def attach(self, session_id: str) -> AsyncIterator[Event]: ...
    async def interrupt(self, session_id: str) -> None: ...
    async def resume(self, session_id: str, message: str) -> None: ...
    async def terminate(self, session_id: str) -> None: ...
```

Capabilities должны определяться для каждой версии CLI:

```yaml
capabilities:
  interactive_pty: true
  non_interactive: true
  session_resume: true
  structured_output: false
  model_selection: true
  read_only_mode: true
  approval_mode: true
  native_skills: true
```

Нельзя строить общий adapter на предположении, что у всех CLI одинаковые флаги. Общей должна быть семантика, а перевод в конкретные аргументы — версионированным внутри `ClaudeAdapter`, `CodexAdapter` и `GrokAdapter`.

## Защита от зависаний

У каждой стадии должны быть отдельные параметры:

```yaml
runtime:
  startup_timeout: 30s
  idle_warning: 60s
  idle_timeout: 5m
  hard_timeout: 30m
  retries:
    process_failure: 2
    validation_failure: 0
  heartbeat: 5s
```

Важно различать:

- процесс не стартовал;
- процесс работает, но молчит;
- CLI ждёт интерактивного подтверждения;
- модель завершилась без требуемого артефакта;
- модель завершилась с ошибочным артефактом;
- тесты упали;
- review нашёл blocking findings;
- исчерпан retry budget;
- требуется решение человека.

Повторять автоматически можно transport/process failure. Логическую ошибку или красные тесты лучше передавать на специальную fix-стадию с явным failure packet.

## Инварианты исполнения

Оркестратор должен жёстко обеспечивать несколько правил:

- Одна задача — один worktree.
- Только одна write-стадия одновременно работает в конкретном worktree.
- Context и review запускаются read-only.
- Reviewer никогда не исправляет собственные findings.
- Success определяется не текстом модели, а наличием валидного output artifact и успешными gates.
- Каждый запуск получает idempotency key.
- Retry не создаёт второй worktree или второй PR.
- Prompt, конфиг, commit SHA и версия CLI записываются в run metadata.
- Все destructive operations требуют отдельной policy или human approval.
- Финальная проверка выполняется вне LLM.

Особенно важно последнее: модель не должна сама решать, что PHPUnit «скорее всего пройдёт».

## Что делать с пакетами

### Task

Оставить и усилить:

- формальная декомпозиция;
- dependency DAG;
- acceptance criteria;
- verification commands;
- ограничения;
- workflow preset и overrides;
- стабильная сериализация TaskSpec;
- schema versioning.

Убрать:

- непосредственное управление provider sessions;
- ожидание дочерних моделей;
- интерпретацию terminal output;
- retry logic;
- принятие решения об успешности реализации.


### Harness

Не выбрасывать полностью, а превратить в маленькое ядро:

- загрузка TaskSpec;
- workflow state machine;
- provider adapters;
- PTY;
- event log;
- artifact validation;
- worktree lifecycle;
- deterministic gates;
- attach/replay/cancel/resume.

Это будет уже не AI-agent framework, а обычный надёжный process supervisor.

### Artifex

Вывести из critical path. Если там есть полезные provider wrappers или prompt templates, перенести их в adapters/skills, но не сохранять отдельный автономный уровень orchestration.

## Порядок внедрения

1. Зафиксировать `TaskSpec v1` и JSON Schema/Pydantic-модель.
2. Сделать только один workflow: `context → implementation → verify`.
3. Реализовать Codex adapter через PTY и полный raw transcript.
4. Добавить Claude adapter без унификации provider-specific flags.
5. Добавить Grok только как read-only reviewer.
6. Ввести `git worktree` и run directory.
7. Добавить idle detection, timeout, cancel и attach.
8. Подключить Superpowers на implementation/review стадиях.
9. Выборочно импортировать Laravel/PostgreSQL/security skills из ECC.
10. Только после стабильности добавить DAG, параллельные context collectors и automatic fix loops.

Не стоит начинать с параллельной мультиагентности. Первая версия должна быть последовательной и полностью наблюдаемой; параллелизм добавляется после того, как каждый adapter стабильно проходит одинаковый набор тестовых задач.

## Финальная конфигурация

Если выбирать один конкретный вариант, я бы сделал так:

```text
Task
  → создаёт TaskSpec и decomposition

Swissknifeman Runner
  → Python
  → Pydantic + asyncio + PTY + Rich
  → SQLite + JSONL
  → tmux integration
  → git worktree isolation

Claude Code
  → context + architecture

Codex CLI
  → implementation + fixes

Grok CLI
  → independent review

Superpowers
  → TDD, debugging, review, verification

ECC selective
  → Laravel, PostgreSQL, security, Docker

PHPUnit/Pest + PHPStan + Pint
  → окончательный источник истины
```

Это даст максимальную прозрачность, сохранит использование существующих подписок, позволит менять последовательность для каждой задачи и не потребует поддерживать ещё один сложный автономный Harness. Самая важная архитектурная перемена: **оркестратор управляет моделями как процессами, а не просит одну модель управлять другими моделями**.

---

# Так, хорошо, я тебя услышал. Но не. Проще ли именно... ну, вот этот вариант я разберу, конечно. А если мы говорим, что я всё-таки отказываюсь от своего Харнеса, потому что я говорю: его очень сложно одному затачивать, я очень много времени потратил, и кодекс постоянно тупит. То есть даже нет гарантии, что после вот этих правок система. Улучшится. То есть в целом, видишь, вот эти готовые Харнесы, то, что есть, вот то, что я тебе ссылки скидывал, если предположить, что я выстраиваю новую систему. И. Просто в неё встрою проектирование. Плана. Вот это task, но вся вот... весь вот этот движок переключения между моделями, то есть их взаимодей... между агентами и их взаимодействием между собой, будет действительно использовать уже готовый движок. То есть тот, кто уже обкатан, и. Тот, кто реально нормально взаимодействует. То есть который может нормально общаться, давать на субагенты правильную. Там задачи и так далее. То есть, а от меня будет просто, что я разобью план, там. На фазах, и буду уже просто как бы подстроюсь под этот готовый движок. И вот в этом случае тогда какую. Схему посоветуешь? То есть из того, что я скинул, и из того, что ты новое найдёшь. Вот типа выстрои систему таким образом. То, что мы используем такой-то готовый движок, его настраиваем, то есть у меня есть три CL. CLI, ну, консольных вот этих вот агентов по подпискам, кодекс, clot код, игрок. То есть я авторизовался, у меня активная подписка, и я их как-то интегрирую с Харнесом, и настраиваю. Вот инструкции под себя. То есть мне важно, чтобы было 100% нормально вот эта работала. И давай вот ещё раз проштудируй и выстрои для меня несколько вариантов по таким Харнесам. То есть когда я буду использовать там какой-то API, ну вот этот JavaScript-овое, и. Отдельно когда полностью движок там устанавливается и как-то настраивается. То есть мне как минимум надо знать, как это работает, чтобы понять, как вот доработать. И давай вот накидай ещё такие варианты тогда. Когда мы отказываемся от моего Харнеса, а task встраиваем уже, подстраиваем под вот этот готовый Харнес.

Да. Если ты **полностью отказываешься от собственного Harness**, то из перечисленного сейчас наиболее точное попадание — **AWS Labs CLI Agent Orchestrator, CAO**. Он уже умеет запускать Claude Code, Codex CLI и официальный Grok Build CLI как нативные терминальные процессы, использовать их существующую авторизацию, раздавать задания через `assign`/`handoff`, показывать терминалы в `tmux` и выполнять программируемые многошаговые workflows.

Но я бы использовал CAO не в чистом «супервизор-модель сама всем управляет» режиме, а в **гибридном**: твой `Task` формирует план, CAO Workflow детерминированно назначает провайдеров и стадии, а внутренняя агентная делегация CAO применяется только там, где действительно нужна динамика.

## Рекомендуемое ядро

Целевая схема:

```text
Swissknifeman Task
    │
    │ создаёт task.yaml / execution-plan.json
    ▼
AWS Labs CAO Workflow Engine
    │
    ├── Codex CLI: сбор контекста
    ├── Claude Code: архитектура и сложные решения
    ├── Codex CLI: реализация
    ├── PHPUnit / PHPStan / Pint: детерминированные проверки
    ├── Grok Build CLI: независимое ревью
    ├── Codex CLI: исправление замечаний
    └── Claude/Grok: финальная проверка при необходимости
```

Здесь твой код **не управляет PTY, процессами, зависаниями, сессиями и передачей сообщений**. Всё это берёт CAO; у тебя остаётся только генерация плана и небольшой адаптер `Task → CAO execution plan`.

CAO запускает локальный сервер, создаёт для агентов отдельные терминальные сессии и оставляет Claude Code, Codex и Grok полноценными CLI-процессами с их нативной аутентификацией и возможностями. Это принципиально отличается от Vercel AI SDK, Pydantic AI и Dify, где основной путь — обращение к моделям через API.

## Почему именно CAO

CAO практически дословно соответствует твоим требованиям:


| Требование | CAO |
| :-- | :-- |
| Claude Code по подписке | Поддерживается существующая авторизация Claude Code. |
| Codex по подписке ChatGPT | Поддерживаются API key и интерактивный `codex login`. |
| Grok CLI | Поддерживается официальный Grok Build CLI через `grok login` или API key. |
| Настоящие CLI-процессы | Да, запускаются в `tmux`. |
| Возможность открыть терминал | Да, это не скрытый API tool call |
| Несколько специализированных агентов | Agent profiles |
| Передача задания агенту | `handoff` |
| Параллельная работа | `assign` и workflow fan-out |
| Фиксированная последовательность | Python workflows |
| Ветвления и циклы | Python workflows |
| Продолжение после сбоя | Durable journal и `resume`. |
| Отмена и наблюдение | `status`, `events`, `wait`, `cancel`. |
| Skills | Глобальные, проектные и plugin-provided skills. |
| Read-only reviewer | Ограниченные agent profiles |
| Worktree | Поддерживается изоляция рабочих задач |
| Human approval | Plan approval и manual recovery decisions. |

Особенно важно, что CAO уже содержит provider-specific код, который тебе пришлось бы самостоятельно поддерживать: распознавание состояния TUI, извлечение последнего ответа, обнаружение ожидания пользователя, отправку многострочных сообщений, возобновление сессий и управление `tmux`.

## Как работает CAO

Архитектурно CAO состоит из четырёх слоёв:

```text
cao CLI / Web UI
        │
        ▼
cao-server
        │
        ├── workflow journal
        ├── terminal lifecycle
        ├── skills
        ├── agent profiles
        └── MCP orchestration tools
                │
                ▼
        tmux terminal sessions
                │
        ┌───────┼────────┐
        ▼       ▼        ▼
      Claude   Codex    Grok
```

Каждый worker — это настоящий CLI-процесс. CAO не заменяет Claude Code или Codex собственным API-агентом, а добавляет к ним профиль, skills и MCP-инструменты для взаимодействия с другими агентами.

У supervisor-агента есть три основных механизма:

- `assign` — отправить независимую работу worker-агенту, обычно асинхронно;
- `handoff` — передать работу и дождаться результата;
- `send_message` — отправить дополнительную информацию уже работающему агенту.

Для Grok CAO специально отключает нативные Grok subagents и workflows, чтобы все делегации проходили через контролируемые `assign` и `handoff`. Это позволяет CAO учитывать роли, permissions, callbacks и состояние терминалов.

## Три режима CAO

### Workflow-first

Это наиболее надёжный вариант.

Твой `Task` определяет:

- список фаз;
- зависимости;
- provider/profile для каждой фазы;
- входные артефакты;
- ожидаемый результат;
- verification commands;
- необходимость review;
- условия повторного исправления.

CAO Workflow исполняет этот план программно:

```python
context = run_step(
    "codex",
    "context_collector",
    context_prompt,
    step_id="context",
    recovery="manual",
)

architecture = run_step(
    "claude_code",
    "architect",
    architecture_prompt(context.output),
    step_id="architecture",
    recovery="manual",
)

implementation = run_step(
    "codex",
    "laravel_developer",
    implementation_prompt(architecture.output),
    step_id="implementation",
    recovery="manual",
)

review = run_step(
    "grok_cli",
    "code_reviewer",
    review_prompt(implementation.output),
    step_id="review",
    recovery="manual",
)
```

Это иллюстративная схема, но она показывает главное: переключение между Claude, Codex и Grok делает CAO Workflow, а не очередная модель.

CAO считает Python scripts основным способом построения workflows. Они поддерживают условия, настоящие циклы, параллельный fan-out, обработку результатов и parameterized inputs; YAML сейчас годится в основном для простой последовательности, потому что YAML-режимы `parallel`, `pipeline` и `loop` зарезервированы, но пока не исполняются.

### Supervisor-first

Здесь ты запускаешь, например, Claude Code как supervisor:

```text
Task Plan
    ▼
Claude Supervisor
    ├── assign → Codex context collector
    ├── handoff → Claude architect
    ├── handoff → Codex implementer
    ├── handoff → Grok reviewer
    └── handoff → Codex fixer
```

Преимущество — почти не нужно писать workflow-код. Supervisor сам выбирает агентов, уточняет задания и реагирует на результаты.

Недостаток — ты снова частично отдаёшь управление модели. Хотя CAO намного лучше контролирует процессы, чем твой старый Harness, supervisor всё равно может:

- выбрать не тот профиль;
- плохо сформулировать handoff;
- запустить лишнего агента;
- неверно интерпретировать результат;
- пропустить обязательную проверку;
- зациклиться на исправлениях.

Этот режим я бы использовал для исследовательских задач, troubleshooting и неопределённых задач, где невозможно заранее построить фиксированный pipeline.

### Гибридный режим

Это лучший вариант для твоего случая:

```text
Task определяет верхнеуровневый DAG
        │
        ▼
CAO Workflow управляет фазами
        │
        ├── context phase
        │     └── supervisor запускает 2–3 read-only subagents
        │
        ├── architecture phase
        │     └── один сильный Claude
        │
        ├── implementation phase
        │     └── один Codex
        │
        ├── verification
        │     └── обычные команды
        │
        └── review phase
              └── Grok или Claude reviewer
```

Таким образом, критический порядок стадий остаётся детерминированным, но внутри конкретной стадии можно задействовать агентную оркестрацию CAO.

## Как встроить Task

Не нужно генерировать новый Python workflow для каждой задачи. Лучше один раз написать несколько стабильных CAO workflows:

```text
~/.aws/cli-agent-orchestrator/workflows/
├── small_fix.py
├── normal_feature.py
├── risky_backend.py
├── database_migration.py
├── security_change.py
└── architecture_research.py
```

`Task` выбирает preset и создаёт execution plan:

```yaml
version: 1
task_id: CRM-142
workflow: risky_backend

goal: >
  Сделать генерацию счетов идемпотентной.

stages:
  context:
    profile: codex_context
    enabled: true

  architecture:
    profile: claude_architect
    enabled: true

  implementation:
    profile: codex_laravel_developer
    enabled: true

  review:
    profile: grok_backend_reviewer
    enabled: true

  fix:
    profile: codex_laravel_developer
    max_iterations: 2

verification:
  - php artisan test --testsuite=Billing
  - vendor/bin/phpstan analyse
  - vendor/bin/pint --test
```

Запуск:

```bash
cao workflow run risky_backend \
  --run-id CRM-142-attempt-1 \
  --input task_file=/absolute/path/to/CRM-142/task.yaml \
  --input task_hash=<sha256>
```

CAO поддерживает типизированные workflow inputs и проверяет обязательные значения до создания терминалов. Значения сохраняются в журнале и повторно используются при resume, что снижает риск расхождения между первоначальным и возобновлённым запуском.

Я бы добавил `task_hash`, потому что одного пути к файлу недостаточно: содержимое `task.yaml` может измениться после остановки workflow. Workflow должен проверить SHA-256 перед исполнением и отказаться продолжать, если TaskSpec был изменён.

## Agent profiles

В CAO нужно создать фиксированный набор ролей:

```text
context_codex
architect_claude
laravel_codex
laravel_claude
review_grok
review_claude
security_grok
database_claude
test_codex
```

Каждый профиль задаёт:

- provider;
- роль;
- system instructions;
- разрешённые инструменты;
- permission mode;
- модель;
- skills;
- MCP servers;
- Codex-specific или Grok-specific настройки.

Например, логически профили должны выглядеть так:


| Профиль | Provider | Доступ |
| :-- | :-- | :-- |
| `context_codex` | Codex | Read-only |
| `architect_claude` | Claude Code | Read-only или plan |
| `laravel_codex` | Codex | Workspace write |
| `review_grok` | Grok Build | Read-only |
| `security_grok` | Grok Build | Read-only |
| `fix_codex` | Codex | Workspace write |
| `final_claude` | Claude Code | Read-only |

Тогда Task выбирает не «модель», а **роль**. Это лучше, чем в каждой задаче указывать технические CLI-флаги.

## Skills в CAO

У CAO есть собственное хранилище skills:

```text
~/.aws/cli-agent-orchestrator/skills/
└── laravel-review/
    └── SKILL.md
```

Skills загружаются лениво: при запуске агент видит имя и описание, а полный текст получает только при необходимости. Можно подключать проектные каталоги skills, устанавливать отдельные skills командой `cao skills add` и ограничивать рекламируемый каталог через поле `skills` в профиле агента.

Для твоего проекта я бы собрал такой набор:

```text
skills/
├── task-protocol/
├── laravel-architecture/
├── laravel-testing/
├── laravel-security/
├── postgres-transactions/
├── postgres-migrations/
├── code-review/
├── security-review/
├── verification-before-completion/
├── systematic-debugging/
├── repository-context/
└── review-findings-format/
```

Источники:

- Superpowers — TDD, debugging, verification, worktrees, code review.
- ECC — выборочные Laravel, PostgreSQL, security и database skills.
- Твои инструкции — формат Task, архитектурные ограничения, правила проекта.

CAO сам распространяет skills в Claude Code и Codex через runtime prompt и `load_skill`; для Grok профиль и каталог добавляются как rules. Это значительно удобнее, чем отдельно синхронизировать `CLAUDE.md`, `AGENTS.md` и Grok rules.

## Терминальная видимость

Здесь CAO подходит лучше API-фреймворков. Каждый агент работает в отдельном `tmux`-терминале, поэтому можно открыть его и увидеть:

- какой prompt получил агент;
- что он пишет;
- какие команды запускает;
- завис ли он;
- ждёт ли разрешения;
- упёрся ли в лимит подписки;
- закончил ли текущий turn.

Workflow отдельно предоставляет:

```bash
cao workflow status <run-id>
cao workflow events <run-id> --follow
cao workflow wait <run-id>
cao workflow result <run-id>
cao workflow cancel <run-id>
cao workflow resume <run-id>
```

Запуск по умолчанию регистрирует run, печатает его ID и отслеживает состояние; `Ctrl-C` отсоединяет клиент, но не отменяет серверное выполнение. Workflow journal позволяет после перезапуска получить результаты завершённых стадий и продолжить незавершённые.

## Важное ограничение

«100% нормально работает» гарантировать нельзя ни для одного подобного проекта. CAO управляет интерактивными CLI и местами распознаёт состояние по элементам TUI, а интерфейсы Claude Code, Codex и Grok меняются.

Например, Grok provider откалиброван под определённые версии Grok Build и документация прямо предупреждает, что изменение TUI markers или tool names может потребовать обновления интеграции. Codex provider также содержит отдельные распознаватели для разных версий footer, progress spinner и interactive prompt.

Поэтому production-конфигурация должна фиксировать:

```yaml
compatibility:
  cao: exact-version
  tmux: exact-version
  claude-code: exact-version
  codex-cli: exact-version
  grok-build: exact-version
```

Обновление любого CLI:

1. Выполняется на отдельной машине или environment.
2. Прогоняет набор реальных тестовых задач.
3. Проверяет `assign`, `handoff`, timeout и resume.
4. Проверяет extraction последнего ответа.
5. Только после этого переносится в основное окружение.

## Разрешения и sandbox

CAO по умолчанию может запускать Claude Code с `--dangerously-skip-permissions`, а Codex — с `--yolo`, чтобы worker не зависал на approval dialog. Для твоего применения такие defaults лучше заменить явными профилями.

Для Codex:

```toml
[profiles.cao_readonly]
sandbox_mode = "read-only"
approval_policy = "never"

[profiles.cao_writer]
sandbox_mode = "workspace-write"
approval_policy = "never"
```

В CAO agent profile указывается соответствующий `codexProfile`. CAO предупреждает, что интерактивные approval tiers для Codex использовать нельзя: boxed approval UI не обрабатывается автоматически и worker может дождаться timeout.

Для Claude:

- architect: `permissionMode: plan`;
- reviewer: `permissionMode: auto` или ограниченный режим;
- implementer: контролируемый write mode;
- unrestricted bypass — только внутри изолированного worktree.

Для Grok CAO умеет переводить отсутствие capabilities в нативные deny rules для Bash, Read, Write, Grep, Glob и web-инструментов.

## OpenHarness

[OpenHarness](https://github.com/autonomous-ai/openharness) очень хорошо решает задачу **наблюдения и управления терминалами**:

- настоящие терминалы в `tmux`;
- Claude Code, Codex, Grok Build и другие CLIs;
- существующие `~/.claude`, `~/.codex` и другие credentials;
- native hooks и transcripts;
- worktree на harness;
- несколько машин;
- продолжение сессий;
- desktop UI и terminal UI.

Но его модель `harness` — это прежде всего одна запущенная сессия агента. Несколько harnesses можно объединять вкладкой, а экспериментальный `Tab collaboration` позволяет агентам консультироваться друг с другом, но эта функция отключена по умолчанию и пока позиционируется как experimental.

Поэтому OpenHarness подходит для схемы:

```text
Task
    ▼
Ты вручную открываешь вкладку
    ├── Claude architect
    ├── Codex developer
    └── Grok reviewer
```

Но для повторяемого автоматического pipeline:

```text
context → design → implementation → test → review → fix
```

CAO значительно сильнее. У него есть workflow journal, branching, concurrency, resume, recovery policies, structured status и стабильные step IDs.

OpenHarness можно выбрать, если тебе важнее идеальный человеческий control center, чем автоматическая оркестрация. Ставить одновременно OpenHarness и CAO как два слоя управления теми же CLI я бы не советовал: оба управляют `tmux`, сессиями, hooks и состоянием, что создаст конфликт ответственности.

## Варианты системы

| Вариант | Ядро | Плюсы | Минусы | Вердикт |
| :-- | :-- | :-- | :-- | :-- |
| CAO workflow-first | CAO Python workflows | Надёжное переключение провайдеров, resume, события, нативные CLI | Нужно написать несколько workflow scripts | Лучший вариант |
| CAO supervisor-first | Claude/Kiro supervisor внутри CAO | Минимум собственного workflow-кода, динамические subagents | Маршрутизацией снова управляет модель | Для исследований |
| CAO hybrid | Task DAG + CAO workflows + локальные subagents | Баланс надёжности и гибкости | Немного сложнее конфигурация | Оптимальная итоговая схема |
| OpenHarness | OpenHarness workspace | Лучшее визуальное управление живыми терминалами | Collaboration экспериментальный, слабее workflow engine | Для ручной работы |
| Vercel AI SDK | TypeScript API | Хороший программный API и structured output | API-модели, не подписочные coding CLIs | Только при переходе на API |
| Pydantic AI | Python API agents | Типизация и structured workflows | Потребуются собственные CLI adapters | Возвращает к разработке Harness |
| Prime Agent | Собственный agent runtime | Long-running работа, background execution, subagents | Не является координатором трёх нативных CLI | Отдельный worker |
| Hermes Agent | Hermes runtime | Skills и автономный агент | Не универсальный CLI orchestrator | Не ядро |
| Dify | Web/API workflow | UI и готовые LLM workflows | Не terminal-first coding environment | Не подходит |
| Harness.io CLI | Harness Platform | CI/CD и delivery automation | Это другой класс продукта | Исключить |

## JavaScript-вариант

Если принципиально хочется JavaScript/TypeScript API, то архитектура могла бы выглядеть так:

```text
Task
   ▼
TypeScript orchestrator
   ├── Vercel AI SDK provider calls
   ├── execa/node-pty → Claude Code
   ├── execa/node-pty → Codex
   └── execa/node-pty → Grok
```

Но как только ты добавляешь `node-pty`, parsing TUI, status detection, resume, timeouts, terminal attachment и provider-specific authentication, ты снова строишь собственный Harness. Vercel AI SDK унифицирует API-вызовы моделей и tool loops, но не управляет подписочными Claude Code, Codex и Grok CLI как полноценными терминальными агентами.

Поэтому JavaScript-вариант имеет смысл только при условии:

```text
Claude API + OpenAI API + xAI API
```

а не:

```text
Claude Code subscription + ChatGPT/Codex subscription + Grok CLI subscription
```

Для текущих аккаунтов CAO намного ближе к готовому решению.

## Практическая конфигурация

Я бы начал с четырёх profiles:

```text
codex_context
claude_architect
codex_implementer
grok_reviewer
```

И трёх workflows:

```text
small_fix
    Codex implementer
    → tests

normal_feature
    Codex context
    → Claude architecture
    → Codex implementation
    → tests
    → Grok review
    → optional Codex fix
    → tests

high_risk
    parallel context collectors
    → Claude architecture
    → human approval
    → Codex/Claude implementation
    → tests
    → Grok review
    → Claude final review
```

Для `normal_feature`:

```text
Task
  └── создаёт immutable task.yaml

CAO
  ├── context: codex_context
  ├── design: claude_architect
  ├── implement: codex_implementer
  ├── verify: shell commands
  ├── review: grok_reviewer
  ├── condition: blocking findings?
  ├── fix: codex_implementer
  └── final verify
```

В этом варианте твой `Task` отвечает за качество декомпозиции, а вся тяжёлая инфраструктура — сессии, terminals, handoff, providers, skills, resume и наблюдение — переносится в CAO.

## План перехода

1. Заморозить текущий Harness и Artifex, не дорабатывать их.
2. Установить CAO и зафиксировать версию.
3. Авторизовать отдельно `claude`, `codex` и официальный `grok`.
4. Проверить каждый provider обычным интерактивным запуском.
5. Создать четыре минимальных agent profiles.
6. Прогнать CAO E2E для `handoff`, `assign` и supervisor orchestration.
7. Написать один workflow `normal_feature.py`.
8. Научить `Task` создавать immutable `task.yaml` и выбирать workflow preset.
9. Подключить проектные skills через CAO skill store.
10. Добавить worktree и ограниченные permission profiles.
11. Прогнать 20–30 твоих реальных задач.
12. Только после этого добавить автоматический review/fix loop и параллельных context collectors.

Ключевое решение здесь такое: **CAO становится новым готовым движком, Task — внешним планировщиком, а swissknifeman перестаёт владеть orchestration runtime**. OpenHarness имеет смысл оставить кандидатом на ручной terminal cockpit, но не ставить вместо CAO для воспроизводимых многостадийных workflows.

<span style="display:none">[^2_1][^2_10][^2_11][^2_12][^2_13][^2_14][^2_15][^2_2][^2_3][^2_4][^2_5][^2_6][^2_7][^2_8][^2_9]</span>

<div align="center">⁂</div>

[^2_1]: https://vercel.com/docs/ai-sdk

[^2_2]: https://www.mdskills.ai/harnesses

[^2_3]: https://skillsllm.com/skill/munder-difflin

[^2_4]: https://github.com/andyrewlee/awesome-agent-orchestrators

[^2_5]: https://claude-world.com/articles/ai-coding-models-tools-july-2026/

[^2_6]: https://www.scriptbyai.com/codex-resource-list/

[^2_7]: https://www.digitalapplied.com/blog/xai-grok-build-cli-parallel-coding-agents

[^2_8]: https://github.com/topics/grok-build

[^2_9]: https://blog.visionik.com/how-grok-build-the-harness-works/

[^2_10]: https://code.claude.com/docs/en/agents

[^2_11]: https://code.claude.com/docs/en/workflows

[^2_12]: https://github.com/bradagi/awesome-cli-coding-agents

[^2_13]: https://code.visualstudio.com/blogs/2026/02/05/multi-agent-development

[^2_14]: https://pypi.org/project/team-harness/

[^2_15]: https://github.com/topics/pi-coding-agent


---

# [https://github.com/awslabs/aidlc-workflows](https://github.com/awslabs/aidlc-workflows)

а вот еще что есть от aws, пойдет для моей схемы?
и если использовать [https://pydantic.dev/docs/ai/harness/](https://pydantic.dev/docs/ai/harness/) то неполучится настроить как я хочу? и как вообще с ним выглядит работа? он все-такие очень популярный

Коротко: **AI-DLC — да, потенциально очень подходит**, но не как “мульти-CLI оркестратор между Claude/Codex/Grok”, а как **готовый workflow-движок и методология внутри одного выбранного harness за раз**. А **Pydantic AI Harness** наоборот очень гибкий и мощный как конструктор, но он не даст тебе “из коробки” именно тот сценарий, который ты хочешь, с нативными подписочными CLI-агентами и полной терминальной прозрачностью; для этого его придётся уже довольно сильно достраивать самому.[^3_1][^3_2]

## AI-DLC

AI-DLC позиционируется как harness-neutral core, который работает нативно в Claude Code, Codex CLI, Cursor, opencode, Copilot и Kiro, и даёт структурированные workflow, approval gates, persistent state, audit trail и набор предопределённых агентов и профилей. Важный плюс для тебя в том, что там уже есть зрелая **методология lifecycle**, 5 фаз, 33 стадии, 14 агентов, workflow profiles и детерминированный движок, который можно адаптировать под твой `Task` как источник планов и решений.[^3_2]

Но по тому, что видно в документации, AI-DLC выбирает **один harness на проект** через `aidlc config --harness claude|codex|...`, после чего работает уже внутри него, а не как внешний supervisor, который одновременно рулит несколькими разными CLI-провайдерами в одной цепочке.[^3_2] То есть схема “контекст собирает Codex, архитектуру делает Claude, ревью делает Grok” в AI-DLC не выглядит как его основной штатный режим; это скорее единая workflow-система, которую ты запускаешь в конкретной среде исполнения, а не cross-provider terminal orchestrator.[^3_2]

## Подойдёт ли AI-DLC

Если твоя цель — **заменить свой Task/Methodology/Stage engine**, то AI-DLC может подойти очень хорошо: ты можешь встроить своё проектирование задач в его lifecycle, профили и approval gates, вместо того чтобы развивать свой полный engine с нуля. Если же твоя цель — именно **прозрачное переключение между тремя уже залогиненными CLI по подпискам в рамках одной задачи**, то AI-DLC выглядит слабее CAO, потому что из доступного описания он не обещает внешний runtime, который одновременно держит Claude, Codex и Grok как независимые процессы и маршрутизирует работу между ними.[^3_2]

То есть мой вердикт такой:


| Сценарий | AI-DLC |
| :-- | :-- |
| Методология, стадии, approvals, lifecycle | Очень сильный вариант.[^3_2] |
| Подстроить `Task` под готовый процесс | Да, вероятно лучший AWS-вариант после CAO.[^3_2] |
| Multi-provider orchestration Claude ↔ Codex ↔ Grok в одной задаче | Похоже, не основной сценарий.[^3_2] |
| Полная наблюдаемость отдельных CLI-сессий как внешних процессов | В описании это не главное обещание.[^3_2] |
| Grok как участник общей схемы | В списке supported harness его нет.[^3_2] |

Отдельно важно, что в README AI-DLC среди поддержанных harness перечисляет Claude, Codex, Cursor, opencode, Copilot и Kiro, но **Grok там не упомянут**. Для твоей схемы это серьёзный минус.[^3_2]

## Pydantic Harness

С Pydantic AI Harness картина обратная. Он не является готовым terminal-first orchestrator для подписочных coding CLIs, зато это очень сильный **Python-конструктор агентного рантайма**: capabilities, workspaces, memory, skills, subagents, dynamic workflow, guardrails, durable execution, step persistence, observability через OpenTelemetry и Logfire.[^3_1]

Его базовая модель такая:

- ты создаёшь `Agent(...)`;
- подключаешь capabilities;
- выбираешь модель через provider string;
- даёшь workspace;
- добавляешь memory, skills, subagents, workflow logic;
- запускаешь это как Python-агента.[^3_1]

Простейший вид у них прямо такой:

```python
from pydantic_ai import Agent
from pydantic_ai.capabilities import LocalWorkspace
from pydantic_ai_harness.coder import Coder

agent = Agent(
    'anthropic:claude-opus-5-5',
    capabilities=[LocalWorkspace('.'), Coder()],
)
```

Это очень удобно для собственного контролируемого агента, но здесь принципиально нет идеи “запусти мою уже существующую подписочную сессию Claude Code/Codex CLI/Grok CLI в tmux и покажи мне живой терминал”. Вместо этого Pydantic Harness в основном работает через **модельных провайдеров и capability loop**, а не через нативные interactive CLI, которыми ты уже пользуешься.[^3_1]

## Можно ли на Pydantic сделать твою схему

Технически — **да, можно**. Практически — **это будет уже твой собственный harness**, только на хороших кирпичиках.

Потому что для твоей схемы тебе нужно:

- несколько разных моделей и ролей;
- стадийный pipeline;
- смена провайдера на каждой стадии;
- отдельные reviewer/executor/context roles;
- хранение run state;
- retries;
- approvals;
- event log;
- контроль таймаутов;
- наблюдаемость;
- терминальная прозрачность;
- работа именно с твоими CLI-подписками.

Pydantic Harness из этого закрывает:

- capabilities architecture;[^3_1]
- memory;[^3_1]
- skills;[^3_1]
- subagents;[^3_1]
- dynamic workflow;[^3_1]
- durable execution и step persistence;[^3_1]
- observability;[^3_1]
- workspaces/sandboxes.[^3_1]

Но он **не обещает** из коробки:

- orchestration именно между `claude`, `codex`, `grok` как интерактивными CLI-процессами;
- live terminal panes;
- tmux-visible TUI lifecycle;
- provider-specific parsing реальных coding CLIs;
- reuse твоих подписочных CLI-auth состояний как центрального сценария.[^3_1]

То есть с Pydantic ты получаешь очень хорошую базу для своего **Python agent runtime**, но не уходишь от разработки собственной orchestration-системы.

## Как выглядит работа с Pydantic

Работа с ним обычно выглядит так:

### 1. Собираешь capabilities

Например:

- `LocalWorkspace('.')`;
- `Coder()`;
- `Memory(...)`;
- `Skills(...)`;
- `SubAgents(...)`;
- `Dynamic Workflow`;
- `Guardrails`;
- `Step Persistence`;
- `Instrumentation`.[^3_1]


### 2. Пишешь Python-оркестратор

Условно:

```python
context_agent = Agent(...)
architect_agent = Agent(...)
implementer_agent = Agent(...)
reviewer_agent = Agent(...)
```

И дальше сам решаешь:

- кто кого вызывает;
- когда передаётся управление;
- что считается успехом;
- как устроен fix loop;
- как логируются артефакты;
- как работает retry.


### 3. Запускаешь как обычный Python runtime

Можно локально, можно через durable execution, можно с sandbox/backends, можно с CLI/UI-интерфейсом.[^3_1]

Это очень хорошо для контролируемой backend-автоматизации, especially если ты и так любишь Python/Pydantic/Temporal-style durable flows. Но это уже **developer framework**, а не “готовый orchestration cockpit для нескольких coding CLIs”.

## Сравнение под твою задачу

| Критерий | AI-DLC | Pydantic AI Harness |
| :-- | :-- | :-- |
| Готовая методология coding workflow | Да.[^3_2] | Частично, через `Coder` и capabilities.[^3_1] |
| Готовый stage engine | Да.[^3_2] | Нет, собираешь сам.[^3_1] |
| Подстроить `Task` как фазовый планировщик | Да.[^3_2] | Да, но писать самому.[^3_1] |
| Работает с Claude/Codex как harness | Да.[^3_2] | Через model providers, не как terminal-first harness.[^3_1] |
| Grok в списке штатных harness/provider | Не видно.[^3_2] | Можно через xAI provider string/интеграции, но не как готовый CLI harness из этой docs-страницы.[^3_1] |
| Подписочные нативные CLI как основа | Скорее harness-specific, но не multi-CLI orchestration.[^3_2] | Не основной сценарий.[^3_1] |
| Терминальная прозрачность | Не ключевой selling point в доступном описании.[^3_2] | Нет, это не tmux-harness.[^3_1] |
| Durable execution | Есть persistent state/audit trail.[^3_2] | Очень сильная сторона.[^3_1] |
| Skills/memory/guardrails | Да, методологически есть.[^3_2] | Очень развито.[^3_1] |
| Сколько придётся писать самому | Средне | Много |

## Что бы я советовал

Если ты хочешь **минимизировать свою разработку**, то варианты такие:

1. **CAO** — если главное для тебя именно multi-CLI orchestration, видимость в терминале и работа с уже залогиненными Claude/Codex/Grok CLI.
2. **AI-DLC** — если главное для тебя готовая methodology/workflow system и ты готов жить в рамках одного выбранного harness на задачу или проект.[^3_2]
3. **Pydantic AI Harness** — если ты всё-таки хочешь свой runtime, но уже на очень качественном Python-фундаменте, а не с нуля.[^3_1]

То есть:

- **замена твоего полного Harness на готовое orchestration ядро** → CAO;
- **замена твоей lifecycle-методологии и stage logic на готовую систему** → AI-DLC;
- **собрать новый собственный orchestrator-framework в Python** → Pydantic Harness.


## Мой практический вердикт

Для твоей именно формулировки — “есть три CLI по подписке, хочу гибко переключать роли между ними, видеть всё в консоли, легко менять схему по задаче” — **Pydantic AI Harness сам по себе не лучший конечный выбор**, потому что он слишком низкоуровневый для этого конкретного UX и снова толкает тебя к собственной разработке. А **AI-DLC интересен, но скорее как готовая workflow-методология поверх одного harness, чем как универсальный диспетчер Claude/Codex/Grok между собой**.[^3_2][^3_1]

Если выбирать строго между этими двумя:

- для твоей схемы **AI-DLC ближе к готовому продукту**;
- для максимальной гибкости и программируемости **Pydantic Harness сильнее как библиотека**;
- но **ни один из них не выглядит настолько прямым попаданием в multi-subscription CLI orchestration, как CAO**.[^3_2][^3_1]

Хочешь, я следующим сообщением соберу тебе уже **финальную матрицу: CAO vs AI-DLC vs Pydantic Harness vs OpenHarness** именно по твоим критериям — роли, multi-provider, Grok, прозрачность, skills, доработка, риск и объём собственного кода?

<div align="center">⁂</div>

[^3_1]: https://github.com/awslabs/aidlc-workflows

[^3_2]: https://pydantic.dev/docs/ai/harness/


---

# А вот смотри ещё раз: вот. Этот Харнес, который есть, ты вот говоришь, что он действует в рамках одной методологии в workflow системы. А что это значит? То есть, э-э, ну. Для меня это пока не совсем понятно, мне надо простым языком объяснить. Потому что я вот не совсем понимаю до конца возможности. То есть. Вот то, что я сказал: «оркестрация». Настройки, то есть там не получится так нормально сделать?

Простым языком: **AI-DLC — это не диспетчер нескольких разных CLI-агентов. Это готовый “процесс разработки”, который живёт внутри одного выбранного агента.** Он хорошо говорит выбранному Claude Code *как работать по этапам*, но не предназначен для того, чтобы автоматически сказать: «сейчас поручаем контекст Codex, потом Claude делает архитектуру, затем Grok проверяет код».[^4_1]

## Что такое методология

Представь два разных уровня.

### AI-DLC — методология

AI-DLC — это как очень подробный регламент разработки для одного исполнителя:

```text
1. Понять запрос
2. Собрать требования
3. Выявить риски
4. Предложить архитектуру
5. Получить подтверждение человека
6. Реализовать
7. Написать тесты
8. Проверить
9. Провести review
10. Зафиксировать результаты
```

Он хранит план, решения, состояние процесса, знания проекта, результаты проверок и историю workflow. У него есть готовые профили для feature, bug fix, infrastructure, security и других видов работы, плюс approval gates: агент должен остановиться и дождаться подтверждения перед важным этапом.[^4_1]

То есть AI-DLC отвечает на вопрос:

> «Как должен проходить жизненный цикл разработки этой задачи?»

А не на вопрос:

> «Какой конкретно CLI-провайдер должен делать каждую стадию?»

## Что значит «один harness»

Когда ты выполняешь:

```bash
aidlc config --harness claude
```

AI-DLC устанавливает своё runtime-окружение именно для Claude Code: команды, инструкции, hooks, workflow state и способ вызова `/aidlc`. Потом ты запускаешь Claude и говоришь:

```text
/aidlc Добавь идемпотентную генерацию счетов
```

Дальше **Claude Code сам проходит workflow AI-DLC**: изучает код, задаёт вопросы, пишет план, ждёт approvals, вносит изменения, запускает тесты и проводит проверки.[^4_1]

Если вместо этого сделать:

```bash
aidlc config --harness codex
```

То тот же AI-DLC workflow будет исполняться уже внутри Codex CLI через `$aidlc`. Но это не означает, что один запуск автоматически держит рядом и Claude, и Codex, а затем передаёт задачу между ними.[^4_1]

Вот так:

```text
AI-DLC + Claude Code

Task
  ↓
Claude Code
  ↓
AI-DLC stages
  ↓
Claude Code делает все этапы
```

Или так:

```text
AI-DLC + Codex CLI

Task
  ↓
Codex CLI
  ↓
AI-DLC stages
  ↓
Codex делает все этапы
```

Но не так:

```text
Task
  ↓
AI-DLC
  ├── Codex: собрать контекст
  ├── Claude: спроектировать
  ├── Codex: реализовать
  └── Grok: сделать review
```

Именно в последней схеме нужен внешний **оркестратор процессов**, такой как CAO.

## Что AI-DLC умеет вместо этого

AI-DLC может иметь несколько **ролей и агентов** внутри своей методологии — архитектор, разработчик, reviewer, specialist и так далее. Но это не надо автоматически понимать как разные реальные модели или разные CLI.

Упрощённо, внутри одного Claude Code это может выглядеть так:

```text
Claude Code
  ├── мыслит как analyst
  ├── затем как architect
  ├── затем как implementer
  ├── затем как reviewer
  └── сохраняет артефакты стадий
```

То есть это скорее **смена инструкций, ролей, чеклистов, стадий и ожидаемых артефактов**. Это сильно лучше, чем просто написать модели «сделай фичу», потому что она вынуждена идти по дисциплинированному процессу. Но всё ещё один основной agent runtime, выбранный при настройке AI-DLC.[^4_1]

## Можно ли настроить под твою схему

### Вариант 1: Только AI-DLC

Можно сделать такую схему:

```text
Task
  ↓
AI-DLC
  ↓
Claude Code
  ├── исследование
  ├── план
  ├── архитектура
  ├── реализация
  ├── тесты
  └── review
```

Или заменить Claude на Codex:

```text
Task
  ↓
AI-DLC
  ↓
Codex CLI
  ├── исследование
  ├── план
  ├── архитектура
  ├── реализация
  ├── тесты
  └── review
```

Это реально можно нормально настроить. Ты берёшь готовый lifecycle и адаптируешь:

- набор workflow profiles;
- стадии;
- approval gates;
- правила выбора workflow;
- skills;
- project knowledge;
- обязательные тесты;
- Laravel/PostgreSQL conventions;
- формат `TaskSpec`;
- требования к артефактам;
- критерии завершения.

Но это будет стратегия:

> «Для этой задачи я выбираю Claude как основного исполнителя».

А не:

> «На каждой стадии автоматически выбираем любого из Claude, Codex и Grok».

### Вариант 2: AI-DLC как процесс, CAO как оркестратор

Теоретически можно соединить:

```text
Твой Task
  ↓
CAO Workflow
  ├── Codex: собрать контекст
  ├── Claude + AI-DLC: пройти design/implementation workflow
  ├── PHPUnit / PHPStan / Pint
  ├── Grok: независимый review
  └── Codex: исправить findings
```

Но тут есть риск избыточности:

- CAO уже имеет agents, profiles, skills, handoff, workflows, journal, resume;
- AI-DLC уже имеет stages, state, approvals, agents, workflow rules и audit trail;
- оба будут пытаться быть владельцем процесса.

Например, CAO считает, что сейчас идёт стадия `implementation`, а AI-DLC внутри Claude считает, что агент пока находится на стадии `architecture approval`. Или CAO считает Claude завершившим шаг, а AI-DLC намерен продолжить свой внутренний lifecycle.

Поэтому их нельзя бездумно вкладывать друг в друга.

## Где граница

Вот ключевое различие.


| Вопрос | AI-DLC | CAO |
| :-- | :-- | :-- |
| Как правильно реализовать feature? | Да: stages, rules, approvals, evidence | Частично: зависит от profiles/workflow, которые ты задашь |
| Кто из провайдеров работает сейчас? | Обычно один выбранный harness | Да: Claude/Codex/Grok выбираются по шагам |
| Как передать работу между CLI? | Не это основной механизм | Да: `assign`, `handoff`, workflow steps |
| Как наблюдать отдельные терминалы? | Это зависит от выбранного harness | Да: отдельные `tmux` terminals |
| Как восстановить внешний multi-agent run? | Есть state lifecycle | Есть durable workflow journal |
| Что проверять перед завершением? | Встроенная инженерная методология | Ты описываешь правила в workflow |
| Как заставить конкретную модель делать review? | Не основная идея | Нативная задача для workflow |

**AI-DLC — “как правильно работать”.**\
**CAO — “кого сейчас запустить, что ему дать и как дождаться результата”.**

## Почему это важно именно тебе

Ты хочешь именно это:

```text
Task планирует задачу
  ↓
Дешёвый агент читает репозиторий и собирает контекст
  ↓
Сильный агент принимает архитектурные решения
  ↓
Другой агент пишет рутинную реализацию
  ↓
Тесты решают, работает ли код
  ↓
Отдельный агент ревьюит
  ↓
Исполнитель исправляет замечания
```

Это не просто lifecycle. Это **routing и orchestration между разными исполнителями**.

AI-DLC хорошо поможет сделать каждый этап дисциплинированным, но сам по себе не является тем уровнем, который управляет разными CLI по твоим подпискам. В стандартной модели AI-DLC ты один раз выбираешь Claude *или* Codex и получаешь сильный workflow внутри него.[^4_1]

## Когда AI-DLC всё же стоит выбрать

Я бы выбирал AI-DLC вместо CAO, если решишь:

```text
Основной агент: Claude Code
Другие агенты: не обязательны
Главная проблема: Claude часто теряет дисциплину,
не ведёт planning, не соблюдает gates и плохо документирует решения
```

Тогда AI-DLC даст тебе очень много готового:

```text
Claude Code + AI-DLC
  ├── Feature workflow
  ├── Bug-fix workflow
  ├── Security workflow
  ├── Infrastructure workflow
  ├── Approval gates
  ├── Evidence
  ├── Project knowledge
  ├── Persistent state
  └── Audit trail
```

И это будет проще, чем строить CAO-систему с несколькими providers.

## Когда выбирать CAO

CAO остаётся правильным выбором, если важны все три вещи одновременно:

- использовать активные подписки Claude, Codex и Grok;
- выбирать провайдера на уровне каждой стадии;
- видеть отдельные процессы и иметь управляемый multi-agent pipeline.

Тогда AI-DLC может быть источником идей, шаблонов workflow и инженерных правил, но не центральным runtime.

## Практический вывод

Для тебя есть два действительно разных пути.

### Путь A: Простота и дисциплина

```text
Task
  ↓
AI-DLC
  ↓
Claude Code или Codex
```

Ты выбираешь одного главного coding agent на конкретный проект/задачу и получаешь готовый строгий SDLC workflow.

### Путь B: Гибкая мультиагентность

```text
Task
  ↓
CAO
  ├── Claude Code
  ├── Codex CLI
  └── Grok Build CLI
```

Ты платишь большей сложностью настройки, но получаешь то, что описывал с самого начала: маршрутизацию работ между провайдерами, роли, независимое review и отдельные живые терминалы.

<div align="center">⁂</div>

[^4_1]: https://github.com/awslabs/aidlc-workflows


---

# Аудит внедрения AWS CAO в swissknifeman

**Вывод:** внедрение CAO оправдано как замена runtime-части `harness` и `artifex`. Тогда `task` остаётся планировщиком, а CAO берёт на себя запуск процессов, терминалы, handoff, resume и наблюдение. Оговорка: код `academici/swissknifeman` я построчно не разбирал. Инструменты в этом ходе были недоступны, поэтому оценки по репозиторию ниже основаны на твоём описании и на структуре репозитория из прошлых шагов. Всё, что про внутренности репозитория, помечено как «проверить».

## Границы аудита

| Вопрос | Ответ |
| :-- | :-- |
| Что заменяем | Оркестрацию провайдеров, управление сессиями, ожидание ответов, статус и отмену (`harness`, `artifex`) |
| Что сохраняем | Декомпозицию плана, описания задач, критерии приёмки (`task`) |
| Что добавляем | Адаптер `Task → CAO workflow`, agent profiles, skills, проверки |
| Что не делаем | Параллельное развитие старого Harness и CAO |

## Факты о CAO

- CAO запускает Claude Code, Codex и Grok Build как реальные CLI-процессы в `tmux` и использует их нативную авторизацию.
- Workflows пишутся на Python. Они поддерживают условия, циклы и fan-out, имеют журнал и команды `status`, `events`, `wait`, `cancel`, `resume`.
- YAML-режимы `parallel`, `pipeline` и `loop` пока зарезервированы и не исполняются, поэтому критичную логику пишем на Python.
- Skills хранятся в каталоге CAO, загружаются лениво и ограничиваются через профиль агента.
- Для Grok CAO отключает нативные subagents и workflows, чтобы вся делегация шла через `assign` и `handoff`. Интеграция откалибрована под конкретные версии TUI и может сломаться при их обновлении.
- Для Codex нельзя использовать интерактивные approval tiers: worker зависнет на диалоге. Нужны профили с `approval_policy = "never"` и нужным sandbox.
- По умолчанию Claude запускается с `--dangerously-skip-permissions`, а Codex с `--yolo`. Это надо заменить явными профилями.


## Оценка готовности

| Область | Оценка | Комментарий |
| :-- | :-- | :-- |
| Совместимость с тремя подписочными CLI | Высокая | Нативные провайдеры есть для всех трёх |
| Прозрачность работы | Высокая | Каждый агент живёт в своём tmux-терминале |
| Детерминизм маршрутизации | Средняя | Достигается только workflow-first режимом |
| Стабильность при обновлении CLI | Средняя | Парсинг TUI хрупкий, нужна фиксация версий |
| Безопасность по умолчанию | Низкая | Defaults слишком разрешающие |
| Стоимость миграции | Средняя | Основная работа в адаптере и профилях |
| Риск потери данных или кода | Средний | Снижается через worktree и ограниченные профили |

## Риски и меры

| \# | Риск | Серьёзность | Мера |
| :-- | :-- | :-- | :-- |
| 1 | Supervisor-модель неверно делегирует (та же проблема, что с Harness) | Высокая | Порядок стадий задаёт Python-workflow, а не модель |
| 2 | Обновление Claude, Codex или Grok ломает детектор состояния TUI | Высокая | Зафиксировать версии CAO, tmux и трёх CLI, обновлять через тестовый прогон |
| 3 | Worker зависает на approval-диалоге | Высокая | Профили без интерактивных подтверждений, таймауты на стадию |
| 4 | Агент пишет в рабочее дерево вне задачи | Высокая | Один worktree на задачу, reviewer только read-only |
| 5 | `--yolo` и bypass-permissions на основном репозитории | Высокая | Явные профили, запуск только в изолированном worktree |
| 6 | Изменили `task.yaml` после старта | Средняя | Передавать `task_hash`, workflow отказывается продолжать при расхождении |
| 7 | Агент заявляет успех без проверки | Средняя | Итог определяют PHPUnit, PHPStan, Pint, а не текст модели |
| 8 | Бесконечный цикл review → fix | Средняя | Лимит итераций и эскалация человеку |
| 9 | Лимиты подписок и rate limits посреди workflow | Средняя | Политика recovery `manual`, возможность сменить провайдера на стадии |
| 10 | Конфликт скиллов Superpowers/ECC с планом из `Task` | Средняя | Подключать skills по профилям стадий, а не глобально |
| 11 | Дублирование состояния между CAO и остатками Harness | Средняя | Один владелец состояния: журнал CAO |
| 12 | Зависимость от чужого проекта с быстро меняющимся API | Средняя | Версионировать, держать адаптер тонким, иметь выход на ручной запуск |

## Проверки в репозитории

Это нужно сделать на коде, без них аудит неполный:

1. **Контракт `task`**: есть ли стабильная схема вывода (JSON/YAML) или только свободный Markdown. Если схемы нет, начинать надо с неё.
2. **Точки связи `harness` и `artifex`** с `task`: какие функции `task` вызывают runtime. Их заменит адаптер.
3. **Хранилища состояния**: файлы, БД, логи. Определить, что мигрировать, а что отбросить.
4. **Провайдерные обёртки в `artifex`**: промпты и шаблоны, достойные переноса в skills или agent profiles.
5. **Тесты**: что из текущих проверок можно переиспользовать как gate после реализации.
6. **Секреты и конфиги**: где хранятся токены, чтобы не потерять их при переносе. Проверить `run_secret_scanning` на ветке миграции.
7. **CI**: можно ли запускать smoke-прогон workflow на тестовом репозитории.

## План внедрения

**Этап 0. Подготовка (1–2 дня).** Заморозить новые фичи в `harness` и `artifex`. Создать ветку миграции. Зафиксировать версии CAO, tmux, Claude Code, Codex CLI и Grok CLI. Убедиться, что каждый CLI работает вручную с твоей подпиской.

**Этап 1. Пилот CAO без кода swissknifeman (2–3 дня).** Поднять `cao-server`. Создать четыре профиля: `context_codex`, `architect_claude`, `codex_implementer`, `grok_reviewer`. Проверить `handoff`, `assign`, `cancel`, `resume` на одной учебной задаче. Результат: подтверждение, что провайдеры стабильны на твоих версиях.

**Этап 2. Контракт TaskSpec (2–3 дня).** Формализовать вывод `task`: цель, ограничения, критерии приёмки, команды проверки, риск, preset workflow и переопределения по стадиям. Добавить `task_hash`.

**Этап 3. Первый workflow (3–5 дней).** Написать `normal_feature.py`: контекст → архитектура → реализация → проверки → ревью → исправление (не более двух итераций) → финальные проверки. Включить таймауты, worktree и ограниченные permission-профили.

**Этап 4. Адаптер `Task → CAO` (2–3 дня).** Команда запускает `cao workflow run` с входными параметрами и показывает `events` в реальном времени. Адаптер не должен знать флаги конкретных CLI.

**Этап 5. Skills (2–3 дня).** Подключить Superpowers для методологии и выборочно ECC для Laravel, PostgreSQL и безопасности. Добавить свои skills: протокол TaskSpec и формат findings для ревью.

**Этап 6. Приёмка (1 неделя).** Прогнать 20–30 реальных задач разной сложности. Метрики ниже.

**Этап 7. Вывод старого кода.** Пометить `harness` и `artifex` как deprecated, удалять только после стабильной приёмки.

## Критерии приёмки

| Метрика | Целевое значение |
| :-- | :-- |
| Доля workflow, завершённых без ручного вмешательства | не менее 80% |
| Зависания без обнаружения | 0 |
| Случаи, когда «успех» заявлен при красных проверках | 0 |
| Resume после принудительной остановки | работает на всех стадиях |
| Стоимость и время относительно ручной работы | не хуже базового уровня |
| Разворот на новой версии CLI | не более 1 дня, включая тестовый прогон |

Пороги выбраны ориентировочно. Их стоит скорректировать по результатам пилота.

## Критерии остановки

Откатиться или пересмотреть выбор, если на пилоте:

- Codex или Grok регулярно зависают в CAO даже на простых задачах;
- извлечение последнего ответа ненадёжно на твоих версиях CLI;
- без интерактивных подтверждений нельзя безопасно ограничить запись;
- затраты на адаптер и профили сравнимы с доработкой старого Harness.

Тогда запасные варианты такие: OpenHarness как ручная панель управления терминалами, а AI-DLC как методология внутри одного harness.[^5_1]

## Итоговая рекомендация

Идти по схеме **CAO workflow-first с гибридными стадиями**. Порядок стадий задаёт детерминированный Python-код, а supervisor-делегация используется только внутри отдельных стадий, например при параллельном сборе контекста. Первым шагом нужен пилот из этапа 1 на твоих подписках и версиях CLI, а уже потом инвестиции в адаптер. Если хочешь, следующим сообщением могу подготовить шаблон `TaskSpec` и каркас `normal_feature.py`, чтобы ты мог начать этап 2–3.

<div align="center">⁂</div>

[^5_1]: https://pydantic.dev/docs/ai/harness/

