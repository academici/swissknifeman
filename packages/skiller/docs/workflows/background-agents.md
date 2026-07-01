# Фоновые агенты

Фоновый агент — это агент в CI, работающий параллельно с разработкой:
аналог CI/CD, но для качества кода, а не только тестов. Он не прерывает
разработчика — работает в изолированном окружении и отдаёт результат как
PR-комментарий или Issue.

**Ключевое ограничение:** фоновый агент **предлагает** изменения, но никогда
не применяет их без code review. Никаких авто-мержей.

Документ покрывает два вида фоновой работы: **CI-агенты** (GitHub Actions, ниже) и
**Workflow-оркестрацию** (`dev-loop` из agent-packs — длинные автономные прогоны).
Раздел [«Устойчивость»](#устойчивость-workflow-оркестрации) — про то, как не получить
«многочасовой молчаливый грайндинг» под rate-limit (реальный инцидент 2026-07-01).

## Готовые шаблоны

Шаблоны GitHub Actions лежат как сниппеты соответствующих скиллов —
скопируйте нужный в `.github/workflows/` целевого проекта:

| Шаблон | Скилл-носитель | Триггер | Результат |
|---|---|---|---|
| `simplify-on-push.yml` | `quality/code-simplifier` | pull_request (PHP-файлы) | Предложения по упрощению комментарием к PR |
| `security-audit-scheduled.yml` | `laravel-auth/laravel-security-audit` | cron (еженедельно) + ручной | Issue с находками по severity |

После установки скиллов через `skiller vendor` сниппеты лежат в
`<skills-path>/<skill>/snippets/`; в самом реестре swissknifeman эти
workflow не настраиваются.

## Требования

1. **Secret `ANTHROPIC_API_KEY`** в настройках репозитория — фоновые агенты
   расходуют платные токены.
2. **Установленный скилл** в целевом проекте (`skiller vendor` или
   plugin marketplace через `skiller connect`) — промпт workflow
   ссылается на протокол скилла.
3. **Permissions** заданы в шаблонах минимально необходимые:
   `contents: read` + `pull-requests: write` или `issues: write`.

## Ограничение стоимости

- `concurrency` с `cancel-in-progress` — не платить за устаревшие прогоны
  при серии пушей (уже в шаблонах).
- `paths`-фильтры — запускать только на релевантных файлах.
- Расписание — не чаще, чем результаты реально читаются: еженедельный
  аудит, который никто не смотрит, — это только расходы.
- Для разовых проверок предпочитайте локальный запуск скилла в сессии —
  он бесплатен в рамках подписки.

## Анти-дрифт правила для фоновых агентов

Разрешено: предложения по упрощению, отчёты об уязвимостях, обновление
PHPDoc/комментариев в предложениях.

Запрещено: менять бизнес-логику, добавлять зависимости, менять схему БД,
мержить без ревью, править тесты. Эти ограничения зашиты в промпты
шаблонов — при адаптации под свой проект сохраняйте их.

## Устойчивость Workflow-оркестрации

Инцидент 2026-07-01 (проект chatom): `dev-loop`-прогон под server-side rate-limit
Anthropic авто-ретраил `agent()`-вызовы ~10 часов → 0 коммитов, без раннего сигнала.
Причина: рантайм Workflow сам ретраит транзиентные ошибки (включая rate-limit) до
высокого капа; при устойчивом throttling это часы wall-clock без durable-прогресса.
Разбор — `packages/skiller/docs/audits/2026-07-01-workflow-resilience-ratelimit.md`.

Верифицировано индустрийными паттернами 2025–2026 (RAG): 429 — это сигнал
backpressure, не глюк одного запроса; unbounded auto-retry = self-DoS; надёжный
слой — модель **job / worker / supervisor**, где supervisor детектит зависших извне.

### Что скрипт МОЖЕТ надёжно (в песочнице)

- **Честные статусы `green | deferred | infra-failed`.** `deferred` — тест честно не
  зелёный (реальный дефект); `infra-failed` — инфра-отказ (rate-limit/timeout/`agent()`
  вернул `null`). **Не маскировать инфра-отказ под `deferred`** — это и была ложь
  инцидента (срезы помечены `deferred`, хотя причина — throttling).
- **Fail-fast на терминальный `agent()===null`.** Рантайм исчерпал ретраи → срез
  `infra-failed`, СТОП всего прогона (не следующий срез: throttling сам не пройдёт).
- **Меньший батч (дефолт 2, не 3+).** Батч N срезов × (impl+test+review) множит
  retry-поверхность под throttling.
- **Heartbeat `log()`** на каждом шаге — сигнал живости для supervisor и человека.
- **Текст-маркер как запасной путь возврата.** Строгая StructuredOutput-схема на
  длинном/сложном возврате хрупка (retry-cap рантайма = 5 → обрывала весь прогон).
  Разрешаем последней строкой `===SLICE-RESULT=== status=green|deferred` — парсится
  регуляркой, прогон не срывается.

### Чего скрипт НЕ может — и почему это НЕ костыль, а эскалация

`Date.now()`/`Math.random()`/`setTimeout` в песочнице Workflow недоступны/ненадёжны, а
`agent()` не отменяем (`AbortController` нет). Поэтому **затяжной hang** (agent ретраит
часами, управление в цикл не вернулось) в скрипте не ловится. Не имитируем защиту —
переносим её на **внешний supervisor**:

- **Доклад оркестратора каждые ~30 мин (главный слой).** Основная сессия после запуска
  фонового dev-loop ставит `Monitor`/`ScheduleWakeup` на `git log <base>..HEAD`; каждый
  тик — короткий доклад статуса; нет коммита за тик ИЛИ виден `<failures>` →
  `PushNotification` («dev-loop застрял: … срез Y — нужно вмешательство») + при нужде
  `TaskStop`. Никогда не ждать completion «вслепую». Живёт вне песочницы → надёжно.
- **Опционально — автономный GitHub Actions cron-watchdog** (для прогонов без живого
  оркестратора, напр. ночных). Переживает завершение сессии:

  ```yaml
  # .github/workflows/dev-loop-watchdog.yml
  on:
    schedule: [{ cron: "*/20 * * * *" }]   # каждые 20 мин
    workflow_dispatch:
  jobs:
    liveness:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
          with: { fetch-depth: 50 }
        - id: check
          run: echo "recent=$(git rev-list --count --after='25 minutes ago' HEAD)" >> "$GITHUB_OUTPUT"
        - if: steps.check.outputs.recent == '0'
          env: { GH_TOKEN: "${{ secrets.GITHUB_TOKEN }}" }
          run: gh issue create --title "🔴 dev-loop STALE: нет коммитов 25+ мин"
               --body "Watchdog: git log base..HEAD пуст — возможен in-flight hang. Диагностировать/остановить." --label infra,watchdog
  ```

  Порог 25 мин ≈ 2× impl-бюджета (~12 мин) + буфер на опоздание GHA-cron под нагрузкой.

### Инструмент → parallel-safe?

| Инструмент | Параллелить? |
|---|---|
| `agent()` dev-loop | по срезам — **последовательно** (канон «parallel-in-layer, sequential-across-layer»); fan-out только на research-фазе |
| `perplexity-web` | **bounded concurrency** — ≤ `maxConcurrency` в одном pool/daemon (v1.3.0), НИКОГДА не 13-way fan-out независимыми процессами (один профиль = один процесс → `SingletonLock`). Детали и recovery (`pkill` stale lock) — скилл `research/query-craft` |
| `context7`, `WebSearch`/`WebFetch` | да (stateless) |

### Восстановление после застоя

Владелец по сигналу (push или GHA-issue) просит Claude: читает `<failures>`/`git log`,
`TaskStop`, чинит корень (throttling → подождать/solo-fallback; schema-cap → маркер;
env → префлайт), перезапуск с resume. Остановка прогона важна и как обрыв
**orphaned-agent** (зависший `agent()` продолжает жечь токены — извне это единственный
способ его прекратить).
