---
name: dx-design
bucket: oss-dev
version: 0.1.0
description: Developer Experience: README, quick-start (≤ 60 сек), API ergonomics, error messages, типы, CLI UX
risk: draft
persona: oss-dev
tags: [oss]
requires: [oss-development]
produces_for: []
outputs: ["ProjectName/DX_Design.md", "ProjectName/README.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Developer Experience Design

Применять когда: OSS-проект **готовится к публикации** или **получает фидбэк уровня "сложно начать"**. DX — основная причина почему один пакет растёт, а технически равный — нет.

Должен быть **выполнен после `oss-development`** (есть базовая структура и понимание что делает пакет). Часто пара с `release-engineering` (DX-метрики в release notes) и `oss-governance` (CoC / CONTRIBUTING.md — тоже часть DX).

---

## Когда НЕ применять

- Internal-only пакет без внешних потребителей — DX-инвестиция не окупится. Минимальный README достаточен.
- Уже есть зрелое README + примеры + типы — отказать, не переделывать ради переделывания.
- Пакет ещё не делает то, что обещает — сначала функционал, потом DX. Не полировать ничего.

---

## 6 осей DX

### 1. Time-to-First-Success (TTFS)
**Цель:** новый пользователь должен получить **рабочий результат за ≤ 60 секунд** от посадки на README.

Засекать пошагово:
- Прочитать первый параграф README → понять что это
- Найти install-команду → выполнить
- Найти minimal example → скопировать → запустить
- Увидеть успех

**Если хоть один шаг > 15 сек** — DX-проблема. Типичные причины:
- README длинный, install внизу
- Минимальный пример требует config-файл
- Нужен API-ключ или env-переменная — не объяснено где взять

### 2. README structure (обязательная)

Порядок секций (НЕ менять):

```markdown
# ProjectName

> Одна строка: что это и для кого. **Без маркетинга.**

[![ci](badge)] [![npm](badge)] [![license](badge)]

## Install
```bash
npm install [name]
```

## Quick example
```ts
import { Brain } from '[name]';
const b = new Brain({ apiKey: '...' });
const r = await b.query('hello');
console.log(r);
```

## When to use
- Use case 1
- Use case 2

## When NOT to use
- Anti-case 1
- Anti-case 2

## Features
[список из 5–8 буллетов]

## Documentation
→ [полная документация](link)

## License
MIT (или другая, см. oss-governance)
```

**Что НЕ должно быть в README:**
- Длинная история «как мы пришли к идее»
- Сравнения с конкурентами (это в отдельный `COMPARISON.md`)
- Roadmap внутри README (это в `ROADMAP.md`)
- Полный API reference (это в docs)

### 3. API ergonomics
**Правила:**

| Правило | Пример good | Пример bad |
|:---|:---|:---|
| Один основной entry-point | `import { Brain } from 'brainkit'` | `import { BrainCore, BrainConfig, brainSetup } from 'brainkit/internal/...'` |
| Sensible defaults | `new Brain()` работает | `new Brain({ config: required })` |
| Builder pattern для сложного | `Brain.builder().withCache().build()` | `new Brain(c, t, e, x, t)` |
| Async-first, не sync обёртки | `await b.query()` | `b.queryAsync()` (имя выдаёт sync-наследие) |
| Error throws, не return-null | `throw new BrainError(...)` | `return null /* проверь сам */` |
| Type-safe (не `any`) | `Brain<TResponse>` | `query(): Promise<any>` |

**Тест:** новый пользователь должен написать первую полезную интеграцию **без чтения API reference**. Только README + IntelliSense.

### 4. Error messages
**Структура хорошего error:**

```
[ProjectName] {Что произошло.}
  Why: {Почему — короткое объяснение причины.}
  Fix: {Что сделать пользователю.}
  Docs: {link на raison-d'être этой ошибки или troubleshooting.}
```

Пример good:
```
[Brain] Cannot connect to model endpoint.
  Why: BRAIN_API_KEY env var is missing.
  Fix: export BRAIN_API_KEY=sk-... and retry.
  Docs: https://brainkit.dev/docs/auth#api-key
```

Пример bad: `Error: ECONNREFUSED 127.0.0.1:443`

**Правило:** каждое уникальное error должно иметь URL в документации (даже если это якорь в одном troubleshooting-документе).

### 5. CLI UX (если применимо)

| Правило | Пример |
|:---|:---|
| `<name> --help` показывает useful summary | не только список флагов |
| `<name>` (без аргументов) НЕ падает | показывает hint или launches REPL |
| Цвета только в TTY (NO_COLOR / not piped) | автодетект |
| Прогресс-бар для > 2 сек операций | `███░░░ 42%` |
| `--json` flag для машинного вывода | для скриптов |
| Exit code 0 = ok, 1 = user error, 2 = bug | стандарт |

### 6. Документация (структура)

Минимум для `v1.0+`:

```
docs/
├── README.md           # → ссылается на разделы ниже
├── getting-started.md  # 5-минутный туториал
├── core-concepts.md    # ментальная модель пакета
├── api/                # сгенерированный API reference (TypeDoc / phpDocumentor / dartdoc)
├── guides/             # рецепты под use cases
│   ├── caching.md
│   ├── streaming.md
│   └── ...
├── troubleshooting.md  # частые проблемы (синхронизируется с error messages)
└── migration/          # для каждого MAJOR — migration guide
    ├── 0-to-1.md
    └── 1-to-2.md
```

Документация **рядом с кодом** (в репо), не на отдельном сайте, который умирает.

---

## Что агент добавляет сам

- **DX-метрики.** Считать TTFS на чистой VM. Если пакет имеет npm stats — отслеживать `time-from-install-to-first-import` через telemetry (opt-in).
- **Public dogfooding.** Мейнтейнер сам должен использовать свой пакет в нетривиальном проекте. Без этого DX-баги не видны.
- **Issue templates.** `bug_report.yml`, `feature_request.yml`, `question.yml` — снижают шум, дают структурированные баги. (Пересекается с `oss-governance`).
- **Performance baseline.** В README — одна цифра: «cold start: X ms, query: Y ms». Без deceptive benchmarks с конкурентами, но **своя** baseline честно.
- **TypeScript: source of truth.** Для JS-пакетов типы — публичный API. Любое изменение типа = breaking. См. `release-engineering`.

---

## Структура output-файла

### `ProjectName/DX_Design.md`

```markdown
---
project: [ProjectName]
type: oss-process
based_on: oss-development.md
---

# DX Design — [ProjectName]

## TTFS-цель
- Текущий TTFS на чистой VM: X сек
- Целевой: ≤ 60 сек

## README структура
- [принятый порядок секций]

## API ergonomics
- Главный entry-point: ...
- Defaults: ...
- Error class: ...
- Type-safety: ...

## Error message contract
- Шаблон: [What] / Why / Fix / Docs
- Каталог error codes: [...]

## CLI UX (если есть)
- Help: ...
- Color/TTY: ...
- Exit codes: ...

## Документация
- Структура: ...
- Tooling: TypeDoc / phpDocumentor / dartdoc
- Hosting: GitHub Pages / docs/ in-repo

## DX-метрики и проверки
- [ ] README ≤ 200 строк
- [ ] Quick example работает копипастом
- [ ] Все error messages имеют docs URL
- [ ] CLI `--help` информативен
- [ ] `npm install && import` работает без config
```

### `ProjectName/README.md`

Создаётся / переписывается по структуре выше. Это основной артефакт DX.

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Публиковать `v1.0+` без README со структурой выше
- Error messages без `Fix:` подсказки
- API с `any` типами для публичных функций
- Длинный README (> 300 строк) — выносить в docs/
- Маркетинговые тексты в README («revolutionary», «AI-powered» без сути)
- Quick example, требующий config-файла
- Прятать install за разделом «требования»
