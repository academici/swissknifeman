# P3.1 — Аудит Opus-пинов task-команд (оправданность vs Sonnet 5 / Fable 5)

Систематический аудит 7 Opus-пинованных `/task:*`-команд на оправданность дорогого тира.
Гранулярность — **Вариант A OQ-1 (D8): по task-командам** (frontmatter + `analyst token-report
--by model`), не по phase-токенам (`--by phase` не реализован, `token_report.py:38-41`).
Вход-факты: тело промпта каждой команды (когнитивный класс, repo-grounded), фактическая
токен-телеметрия (прогон ниже), возможности моделей на 2026-07 (RAG-верифицировано).

## 1. Фактическая токен-телеметрия — `analyst token-report --by model`

Прогон в этой сессии (tree-anchor **5ae6488**, `git rev-parse --short HEAD`), рабочий каталог —
корень монорепо `swissknifeman`:

```
$ analyst token-report --by model
analyst token-report — /home/vostrikov/projects/packages/swissknifeman  ·  срез: model
  окно: 20/121 сессий (запрошено 20)
  rolling baseline (K=20, N=20): медиана out 57k · p90 out 163k

  срез                          сессий   out (сумма)  out (сред.)  vs медиана  флаг
  claude-haiku-4-5-20251001          2            2k          932        0.0×
  claude-opus-4-8                    8         1029k         129k        2.3×  ⚠ РЕГРЕСС
  claude-sonnet-5                   13          499k          38k        0.7×
```

Кросс-проектный срез (`analyst token-report --by model --all-projects`, tree-anchor **5ae6488**,
25 проектов) — Opus-паттерн **воспроизводится**: `claude-opus-4-8` на сессию даёт 1.8–2.6× медианы
out и флагается РЕГРЕССом в agelto (227k, 1.8×), swissknifeman (129k, 2.3×), corex (284k, 2.6×),
dterema (151k, 2.3×); `claude-sonnet-5` держится 0.7–1.2× медианы почти везде; `claude-fable-5`
встретился ОДИН раз (agelto, 739k, 5.9× — единичный тяжёлый прогон, не паттерн).

**Вывод (repo-grounded):** доминирование Opus по out (baseline: 8.1M vs Sonnet 5.4M) подтверждено
на уровне `--by model` — Opus-сессия стоит ~2–2.6× out-токенов Sonnet-сессии **и** 1.67× цену
за токен → Opus-сессия ≈ **3–4× стоимости** Sonnet-сессии. Самый дорогой рычаг экосистемы —
подтверждён свежими данными, не пересказом baseline.
**Ограничение (D8, вынести в P3.2):** `--by model` НЕ атрибутирует эти 8.1M к конкретным
командам — какая из 7 Opus-команд реально жжёт, телеметрия текущей схемы не показывает
(`workflows[]` без токенов, `token_report.py:38-41`, ESCALATION-REQUIRED). ROI downgrade
конкретного пина поэтому **не квантифицируется** — приоритет trial'ов ниже качественный.

## 2. RAG-факты о возможностях моделей (2026-07)

Источник-1 (первичный, canonical Anthropic reference): скилл `claude-api` (`shared/models.md`,
`shared/model-migration.md`, кэш 2026-06-24 + live-source backing). Источник-2 (внешняя сверка):
`perplexity-web` 2026-07-15 (Anthropic docs/blog + независимые бенчмарки; см. footer).

| Модель | out $/1M | Позиционирование (RAG:✅ 2026-07) |
|:--|:--|:--|
| Claude Fable 5 | **$50** | Самая мощная широко-доступная; «frontier / для самых тяжёлых». Thinking always-on. **Дороже Opus** (2× out). «Call only when it really matters» — 3–5× счёт. **НЕ дефолт-апгрейд.** |
| Claude Opus 4.8 | **$25** | Флагман coding/enterprise; SOTA long-horizon agentic, knowledge-work, memory, **bug-finding** («stronger real-bug finding», ловит intermittent flakes). Лидирует на SWE-bench Pro (69.2) над Sonnet (63.2). |
| Claude Sonnet 5 | **$15** ($10 intro→2026-08-31) | «Best speed+intelligence»; near-Opus на coding/agentic. **≈93% способностей Opus 4.8 при ~60% цены** (40% на intro). Поддерживает effort `low..xhigh/max`. На автономном agentic/terminal-бенче **обгоняет** Opus 4.8 (80.4 vs 74.6). |

**Ключевые следствия для аудита (RAG:✅):**
- **Ось downgrade — только Opus → Sonnet 5.** Fable 5 дороже Opus (2× out) → как цель-даунгрейда
  ИСКЛЮЧЁН; релевантен лишь как up-tier для экстремальной сложности (ни одной команде не нужен).
- Sonnet 5 закрыл разрыв на **coding/agentic** (par/выше Opus), но Opus 4.8 всё ещё лидирует на
  **hardest reasoning / глубоком bug-finding** (SWE-bench Pro, adversarial-разбор).
- `xhigh` доступен и на Sonnet 5, и на Opus 4.8 — effort сам по себе тир не блокирует.

## 3. Per-command вердикт-таблица (7 Opus-команд)

Вердикт-таксономия: **keep-Opus** (пин оправдан) · **downgrade-candidate** (рекомендую
Owner-gated trial → Sonnet 5) · **needs-Owner** (плавно-спорно, Owner решает A/B). Каждый вердикт
несёт явный tradeoff: что ломается при downgrade.

| Команда (пин) | Когнитивный класс (repo-grounded) | Вердикт | Обоснование + tradeoff | RAG |
|:--|:--|:--|:--|:--|
| **design** `opus/high` | Синтез research-fanout → durable план/ADR; кросс-источниковое reasoning; SSOT архитектуры, propagates во ВСЕ проекты | **keep-Opus** | Correctness-critical: плохой дизайн-план тиражируется ecosystem-wide (D8 pre-mortem). Синтез = knowledge-work/reasoning, где Opus 4.8 лидирует. Fanout уже Sonnet. Downgrade-risk **HIGH**, quality-телеметрии нет → тихая деградация. Sonnet 5 (~93%) — *плаузибельный* Owner-A/B, не слепой downgrade. | ✅ |
| **dev** `opus/high` | Opus ТОЛЬКО для планирования (нарезка вертикальных срезов + risk/blast-radius); impl-субагенты уже Lean-tiered (Sonnet impl / Opus xhigh на HIGH-review / Haiku тривиал) | **downgrade-candidate** | Opus-пин — тонкий планировочный слой (не bulk-токены: impl на Sonnet). Планирование = coding-agentic домен, где Sonnet 5 **par/обгоняет** Opus (80.4 vs 74.6 на agentic-бенче). Tradeoff: плохая нарезка → плохой dispatch, но recoverable per-slice через review-gate → risk **MODERATE**. Рекомендую Owner-gated trial `sonnet/high`. | ✅ |
| **make-workflow** `opus/high` | Процедурный контур: матчинг 1/4 шаблонов → slot-fill → статический выходной ревьюер (RED блокирует). Низкий open-ended синтез; гейт ловит выпиленные обязательные стадии | **downgrade-candidate** | Задача = «копия шаблона + слоты + чеклист-гейт», не свободный синтез; статический ревьюер — safety-net. Tradeoff: судьба матчинга шаблона (не форкать логику) требует reasoning, но гейт ловит промахи → risk **LOW-MODERATE**. Рекомендую Owner-gated trial `sonnet/high`. | ✅ |
| **plan-design** `opus/high` | Авторинг мастер-плана; тяжёлая схема/RAG-маркеры/DoR/pre-mortem; SSOT, дешёвая модель исполнит БЕЗ чата | **keep-Opus** | Наивысший рычаг: плохой план → cheap-исполнители падают без чата. Явно Owner-blessed (D1: «дизайн-синтез — Opus 4.8/high», подтверждено). Downgrade-risk **HIGH**. Не трогать. | ✅ |
| **research** `opus/high` | Многоисточниковый retrieval + верификация + синтез с цитатами; fanout Sonnet, Opus синтезирует/reduce | **needs-Owner** | Opus-пин = reduce/синтез-мозг. Sonnet 5 near-par на retrieval+синтез, но fidelity цитат + кросс-источниковое reasoning — зона, где Opus чуть впереди. Tradeoff: плохой синтез → плохие входы design (но ловится downstream) → risk **MODERATE**. Owner A/B `sonnet/high`, низкий приоритет. | ✅ |
| **plan-audit** `opus/xhigh` | Adversarial-аудит закрытой фазы; ~15 finding-типов, no-op-детект, scope-drift, re-run Validation, RAG-маркеры | **keep-Opus/xhigh** | Bug-finding/defect-detection — **сильнейшая** документированная зона Opus 4.8 («stronger real-bug finding», ловит flakes). xhigh оправдан для adversarial-глубины. Downgrade-risk **HIGH**: недо-аудит пропускает дефекты, quality-gap → тихо. Именно здесь НЕ даунгрейдим. | ✅ |
| **review** `opus/xhigh` | Read-only adversarial code/doc-ревью; Stage A стек→скиллы, B классика+conformance, C adversarial verify | **keep-Opus/xhigh** | Тот же класс — adversarial bug-finding, Opus 4.8 best-in-class. Команда уже coverage-first («репортишь ВСЕ, при сомнении ВЫШЕ») — совпадает с рекоменд. промптом миграционного гайда (Opus 4.8 буквально следует «only high-severity» → recall падает; здесь снято). xhigh оправдан. Не трогать. | ✅ |

## 4. Сводная рекомендация для P3.2

**Применить безопасно (без правки пинов):**
- Секция «Model-routing пинов task-команд» в `docs/routing.md` — рационал КАЖДОГО из 7 пинов +
  вердикт этого аудита (провенанс, останавливает повторное second-guessing).

**Owner-gated downgrade-trials (правка пина ТОЛЬКО после явного одобрения, гейт `AskUserQuestion`):**
- `dev` `opus/high` → `sonnet/high` — сильнейший кандидат (планировочный слой, coding-agentic домен
  Sonnet-par/выше; risk MODERATE, recoverable через review-gate).
- `make-workflow` `opus/high` → `sonnet/high` — второй кандидат (процедурный контур + статический
  гейт-safety-net; risk LOW-MODERATE).
- (при правке пина — синхронно строка «Пинит …» в `description` того же файла + `skiller registry`.)

**Оставить подтверждёнными (Opus оправдан, правок пинов НЕТ — легальный исход):**
- `design` `opus/high`, `plan-design` `opus/high` (Owner-blessed D1), `plan-audit` `opus/xhigh`,
  `review` `opus/xhigh` — correctness-critical, downgrade-risk HIGH, quality-телеметрии нет.

**Эскалировать Owner (спорное → `open-questions.md`):**
- `research` `opus/high` → возможный A/B `sonnet/high` (needs-Owner, низкий приоритет, MODERATE-risk).

**Fable 5:** ни для одной команды не рекомендуется (дороже Opus, up-tier для frontier-сложности —
вне цели токен-экономии P3).

**Не трогать effort xhigh** на plan-audit/review: correctness-critical adversarial-глубина; `high`
теоретически мог бы хватить, но снижать не рекомендую без quality-телеметрии.

**Перенести в P3.2 как ограничение:** ROI конкретного downgrade не квантифицируется, пока нет
`--by phase` (D8, deferred) — какая Opus-команда реально жжёт 8.1M, неизвестно; приоритет trial'ов
качественный (по downgrade-risk), не по измеренной экономии.

---

## Проверка

- **Проверено (RAG:✅ 2026-07-15):** цены out $/1M (Fable $50 / Opus 4.8 $25 / Sonnet 5 $15,
  intro $10) · позиционирование тиров (Fable frontier-only/дороже Opus; Opus 4.8 SOTA
  bug-finding+long-horizon, лидер SWE-bench Pro; Sonnet 5 ≈93% Opus@~60%, par/выше на
  autonomous-agentic, поддержка xhigh). Источник-1 (первичный) — скилл `claude-api`
  (`shared/models.md`+`shared/model-migration.md`, canonical Anthropic reference). Источник-2
  (сверка) — `perplexity-web` (Anthropic pricing/blog + независимые бенчмарки SWE-bench Pro
  69.2/63.2, agentic 80.4/74.6). Оба источника согласованы, противоречий нет.
- **Проверено (repo-grounded):** токен-числа §1 — ФАКТИЧЕСКИЙ прогон `analyst token-report --by
  model` (+`--all-projects`) на tree-anchor `5ae6488`, не пересказ baseline · когнитивный класс
  каждой команды — чтение тела `packages/task/commands/*.md` · `--by phase` недоступен —
  `token_report.py:38-41`.
- **Ноты честности:** ось downgrade сведена к Opus→Sonnet 5 осознанно (Fable дороже — не цель);
  ROI пер-команды НЕ измерен (telemetry-gap `--by phase`, D8) — это костыль гранулярности Варианта
  A, назван костылём, не выдан за точную атрибуцию; вердикты design/research помечены как
  плаузибельные-A/B, а не форсированный downgrade — анти-самообман в ОБЕ стороны (не штампуем «всё
  Opus оправдано» и не гоним blanket-downgrade ради 8.1M).
- **RAG-движок:** `perplexity-web` доступен, отработал с первого запроса (без lock/timeout).
  `context7` НЕ применялся — он для API-доков библиотек, не для capability-позиционирования моделей
  (правильная ступень здесь — canonical `claude-api` reference → perplexity-web, по CLAUDE.md
  «Методология решений»). ПОВТОРНЫЙ ПРОХОД не требуется — все несущие факты верифицированы.
