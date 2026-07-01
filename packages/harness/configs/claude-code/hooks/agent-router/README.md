# agent-router — маршрутизатор намерений (свободный текст → оптимальная команда)

Пара **Python-хуков** Claude Code, которые помогают направить любой свободный текст к
оптимальной возможности проекта (`/task:*`, субагенты, локальные скиллы) — вместо того чтобы
помнить и вручную набирать команду. Реализует roadmap `agent-command-router-hook`.

## Как работает (dual-hook)

- **`session-policy.py`** (SessionStart) — один раз за сессию инжектит **статическую политику
  роутинга** в контекст модели (`hookSpecificOutput.additionalContext`). Политика: классифицируй
  каждое сообщение — вопрос → отвечай обычно; задача → проведи через план и предложи одну
  оптимальную `/task:*` строкой в консоль (или, в `auto_dispatch`, вызови сам через SlashCommand).
- **`router.py`** (UserPromptSubmit) — per-turn дёшево скорит текст по keyword-каталогу; если
  лучший кандидат ≥ `THRESHOLD` — эмитит **одну строку** `[intent-router] bias …` (тоже
  `additionalContext`), иначе молчит. Подсказка помечена **non-authoritative** — финальное решение
  за моделью.

Почему два хука: политика статична → место ей в SessionStart (раз за сессию, без per-turn налога и
без stale-replay большого текста); per-turn инжектится лишь крошечный bias. Это и рекомендуют
официальные доки Claude Code (проверено perplexity-web).

## Классификатор — гибрид

Keyword-прескор (`_lib.score_entries`, lowercase-substring, данные не код) даёт **bias**; финальное
«вопрос vs задача / какая команда» решает **модель** по политике. Прескор-brittleness смягчён тем,
что решает модель; keywords стартуют узкими и расширяются по замеренным мисроутам.

## Файлы

| Файл | Роль |
|:--|:--|
| `session-policy.py` | SessionStart-хук (статическая политика) |
| `router.py` | UserPromptSubmit-хук (per-turn bias-подсказка) |
| `_lib.py` | общие примитивы (чтение env, каталога, скоринг) |
| `config.json` | **данные**: тексты политики + hint-шаблон + fallback-каталог (5 `/task:*`) |
| `env.ini` | режим `POLICY` (propose/auto_dispatch/off), `THRESHOLD`, `ESCAPE_PREFIX` |

Per-project каталог возможностей — `<project>/.claude/agent-router.config.json`, генерит
`harness router --generate --target <project>` (сканит `.claude/agents/*.md` + локальные
`.claude/skills/*/SKILL.md` + 5 `/task:*`). При онбординге — провиженер `router-config` в `maind sync`.

## Установка / включение

```bash
harness hooks --global                     # копирует хуки в ~/.claude/hooks/agent-router/
harness hooks --target . --router propose   # включить в проекте (пишет env.ini + settings)
harness router --generate --target .        # сгенерить каталог возможностей проекта
```

## I/O-контракт (для отладки)

Оба хука читают JSON payload на stdin (`user_input`/`cwd`), пишут на stdout
`{"hookSpecificOutput": {"hookEventName": …, "additionalContext": …}}` (или пусто).

```bash
echo '{"user_input":"добавь эндпоинт заказа с тестами","cwd":"/proj"}' \
  | python3 router.py         # → JSON с подсказкой /task:dev
echo '{"user_input":"что такое CAP-теорема?","cwd":"/proj"}' \
  | python3 router.py         # → пусто (вопрос ниже порога)
```

## Честные лимиты (не переобещаем)

- **Хук `/`-команду НЕ запускает** (по контракту Claude Code hooks). В `propose` модель предлагает
  строку — запускаешь ты. В `auto_dispatch` **модель** сама вызывает `/task:*` через инструмент
  `SlashCommand` (это поддерживается, pin модели/effort применяется) — но инициирует модель, не хук.
- **Риск `auto_dispatch` — оверфайр** (модель дёрнет команду там, где не надо). Поэтому дефолт —
  `propose`. Конкретную команду можно закрыть от авто-вызова `disable-model-invocation: true` в её
  frontmatter (пакет `tasks`).
- **«Не наседать» — мягкая инструкция** модели (хук дёшево состояние не трекает).
- **Каталог соседних пакетов из marketplace** — v1 не включает (per-project резолв команд пакетов
  ненадёжен); `/task:*` уже покрывают кросс-пакетный task-интерфейс. Follow-up.
