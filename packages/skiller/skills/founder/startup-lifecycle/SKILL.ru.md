---
name: startup-lifecycle
bucket: founder
version: 0.1.0
description: 4 стадии AI-native стартапа (Idea→MVP→Launch→Scale) с exit-criteria, failure modes и антидотами + метод stage-gate review
risk: draft
persona: founder
tags: [validation, requirements, market]
requires: []
produces_for: [new-project, customer-discovery, pmf-diagnostics, defensibility]
outputs: ["docs/01_Business/Stage_Gate_Review.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Startup Lifecycle

Применять когда: нужно понять, **на какой стадии** находится проект, какие скиллы релевантны сейчас, и **готов ли он перейти** в следующую стадию (stage-gate review). Каноническая рамка из Founder's Playbook (Anthropic 2026) — спина, на которую опираются все остальные founder/pm-скиллы.

Базовый принцип эпохи agentic coding: **бутылочное горлышко больше не «что можешь построить», а «что выбираешь строить».** AI стёр стоимость строительства → дисциплина валидации важнее, чем когда-либо.

---

## Когда НЕ применять

- Нужен конкретный артефакт (BRD, GTM, риски) — грузить целевой скилл, не рамку.
- Чисто технический вопрос по коду — это не lifecycle-решение.
- Проект — не стартап (OSS-пакет, агентство) — стадии валидации к нему не применяются.

---

## 4 стадии

### 1. Idea — `stage: idea`
**Goal:** research-oriented validation → **problem-solution fit**. Собрать качественные доказательства (прежде всего из живых разговоров), что реальная проблема существует и решение её адресует — **до** первой строки production-кода.

**Exit (3 «да»):**
1. Проблема реальна, специфична и достаточно частотна? (кто именно сталкивается, как часто, насколько больно, что делают сейчас)
2. Решение бьёт по **реальной** проблеме, которую вскрыла валидация (а не по той, что предполагали на входе)?
3. Сигнала достаточно, чтобы оправдать MVP? (не сертификат, а обоснованное решение vs акт веры)

**Failure modes:** mistaking building for validating · premature scaling · loss of objectivity (confirmation bias × AI).
**Скиллы:** `idea-discovery` → `adversarial-check` → `customer-discovery` → `competitive-analysis` → `risk-assessment`.

### 2. MVP — `stage: mvp`
**Goal:** превратить валидированную проблему в **работающий продукт** (наименьшая сфокусированная итерация, не полный roadmap); двигаться быстро **без** накопления tech debt; инвестировать в persistent context (CLAUDE.md) с первого дня.

**Exit:** genuine PMF — доказательство, что конкретная идентифицируемая группа достаточно ценит продукт, чтобы **возвращаться** (retention), **платить** (revenue) или **рассказывать** (referral). Паттерн через несколько итераций, не одна точка.

**Failure modes:** agentic technical debt · false PMF · zero-friction scope creep · insecure by inexperience.
**Скиллы:** `architecture` (+CLAUDE.md) → `product-roadmap` (scope + amendment-criteria) → `security-design` (gate до первого юзера) → `pmf-diagnostics` → `tech-debt-audit`.

### 3. Launch — `stage: launch`
**Goal:** превратить early traction в **повторяемый устойчивый growth engine**; закалить инфраструктуру; построить компанию вокруг продукта.

**Exit (3 части):**
1. Рост повторяем и channel-driven (известные CAC, LTV, payback).
2. Продукт держит production-нагрузку (hardened, security, compliance, reliability — не только тестовые условия).
3. Операции идут **без** founder-bottleneck (процессы и автоматизация на месте).

**Failure modes:** technical debt comes due · founder = bottleneck · security/compliance не отложить · expansion раньше готовности.
**Скиллы:** `go-to-market` (как функция) · `tech-debt-audit` (architectural audit) · `security-design` (SOC2/GDPR/HIPAA workstream) · `capacity-planning` · `oncall-rotation`.

### 4. Scale — `stage: scale`
**Goal:** systematic growth + **defensible moat через accumulated depth**; роль фаундера → public-facing executive.

**Exit (threshold, не milestone):** sustainable profitability (без внешнего капитала) / IPO-readiness / acquisition. Лакмус: *«Если бы well-funded incumbent скопировал продукт сегодня — пользователи остались бы?»*

**Failure modes:** delegating the operational layer (психологически и структурно) · scaling org functions · нет GTM-функции.
**Скиллы:** `defensibility` (data flywheel, workflow lock-in, domain-as-context) · `capacity-planning` · `go-to-market` (analyst/investor/enterprise voice).

---

## Метод: stage-gate review

При запросе «готов ли перейти дальше?» — прогнать exit-criteria текущей стадии как чеклист:

1. Определить текущую `stage:` из frontmatter control tower.
2. Взять exit-condition этой стадии (выше) → разложить на проверяемые пункты.
3. По каждому: ✅ выполнено / ⚠️ частично (чего не хватает) / ❌ нет (что сделать).
   **Гейт доказательности:** каждый ✅ обязан опираться минимум на **1 внешний сигнал** — рыночные
   данные / живой разговор / эксперимент (не внутреннее мнение и не вывод AI). Нет внешнего сигнала →
   статус максимум ⚠️, не ✅.
4. **Перед вердиктом «готов» — обязательный [[adversarial-check]]:** «что в этих данных — реальный сигнал, а что wishful thinking?» (см. failure mode loss-of-objectivity).
5. Вердикт: `PROCEED` (все ✅) / `HOLD` (есть ⚠️/❌ + список действий) / `PIVOT` (exit недостижим на текущей гипотезе).

При вердикте `PROCEED` — поднять `stage:` в frontmatter проекта.

---

## Что агент добавляет сам

- **Несоответствие activity↔stage.** Если на `stage: idea` уже пишут production-код — назвать прямо: «это building раньше validating».
- **Stage-aware маршрутизация.** По стадии назвать релевантную персону и набор скиллов (idea→Founder, mvp→Architect+Quality, launch→PM+Operator, scale→Operator+PM).
- **Портфельный контекст.** Если в реестре проектов много `idea` — напомнить о портфельном риске «строим непроверенное».

---

## Структура output-файла

`docs/01_Business/Stage_Gate_Review.md`:

```markdown
---
project: [ProjectName]
stage_from: idea
review_date: YYYY-MM-DD
verdict: PROCEED | HOLD | PIVOT
---

# Stage-Gate Review — [ProjectName]: idea → mvp

## Exit-criteria
| Критерий | Статус | Внешний сигнал (источник) | Чего не хватает / действие |
|---|---|---|---|
| 1. Проблема реальна+специфична+частотна | ✅/⚠️/❌ | [данные/разговор/эксперимент] | ... |
| 2. Решение бьёт по реальной проблеме | ... | ... | ... |
| 3. Сигнала достаточно для MVP | ... | ... | ... |

## Adversarial check (обязательно)
- Что здесь реальный сигнал vs wishful thinking: ...

## Вердикт
PROCEED / HOLD / PIVOT — обоснование.
```

---

## Связанные скиллы

- `founder/new-project` — выставляет `stage: idea` и прогоняет idea-gate при заведении проекта
- `founder/idea-discovery`, `founder/customer-discovery`, `founder/adversarial-check` — инструменты Idea-стадии
- `pm/pmf-diagnostics` — измеряет MVP-exit (PMF)
- `founder/defensibility` — moat-работа Scale-стадии
- `quality/tech-debt-audit` — agentic debt (MVP/Launch failure mode)
