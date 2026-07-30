---
name: legal-compliance
bucket: architect
version: 0.1.0
description: Используй при проверке регуляторных требований перед запуском: GDPR, CCPA, AI Act, DMCA, COPPA, DSA.
risk: draft
persona: architect
tags: [compliance, gdpr, privacy, ai-act, regulatory]
requires: [architecture]
produces_for: [security-design]
outputs: ["docs/03_Dev/Legal_Compliance.md", "docs/01_Business/Privacy_Policy_Draft.md", "docs/01_Business/Terms_of_Service_Draft.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Legal Compliance

Применять когда: продукт работает с пользовательскими данными, AI-моделями, UGC, детской аудиторией, финансами или платежами — и нужен чеклист регуляторных требований **до** запуска.

**Не заменяет юриста.** Скилл готовит структурированный чеклист и черновики, которые потом проверяет юрист. Без юриста — не релизить.

---

## Когда НЕ применять

- Чистый OSS-пакет без данных и сервиса (BrainKit как библиотека) — не применимо. Для AzGuard если есть телеметрия — применимо.
- B2B-продукт исключительно через подписанные контракты + DPA — все требования закрываются договором, не публичной политикой.
- Внутренний инструмент без внешних пользователей — minimal scope.
- Нет архитектуры → отказать, без знания где хранятся данные нельзя оценить compliance.

---

## 6 регуляторных режимов (рассматривать все)

| Режим | Применим когда | Project примеры |
|:---|:---|:---|
| **GDPR** (EU) | Хоть один пользователь из EU | Все vault-проекты |
| **CCPA / CPRA** (California) | > 100k California-users или > $25M revenue | Memster, Edufy при scale |
| **AI Act** (EU) | AI-система с риск-классификацией | Edufy (high-risk: education), Finbrain (limited-risk: financial advice) |
| **DMCA** (US) | UGC с потенциальным copyright-инфрингментом | Memster (видео-мемы) |
| **COPPA** (US) | Пользователи < 13 лет | Edufy при targeting детей |
| **DSA** (EU) | Платформа с UGC, > 45M EU users или просто платформа | Memster, GetChat |

Дополнительные при необходимости: PSD2 (платежи в EU), PCI-DSS (хранение карт), HIPAA (медицина), SOC 2 (B2B SaaS требование).

---

## Стандартный чеклист GDPR (minimum baseline)

Полный GDPR baseline-чеклист (правовые основания, права субъектов, хранение, DPA) — [references/gdpr-checklist.md](references/gdpr-checklist.md).

## AI Act — классификация (для проектов с AI)

| Класс | Что это | Требования | Project примеры |
|:---|:---|:---|:---|
| **Unacceptable risk** | Social scoring, manipulation | Запрещено | — |
| **High risk** | Education, employment, credit | Conformity assessment, registration, human oversight, transparency | Edufy (если выдаёт оценки), Finbrain (если делает credit scoring) |
| **Limited risk** | Chatbots, deepfakes | Transparency: «вы общаетесь с AI» | Edufy tutor, Memster (caption generator), GetChat |
| **Minimal risk** | Spam-фильтры, рекомендации | Voluntary codes of conduct | большинство фич |

Для high-risk: отдельный документ `docs/03_Dev/AI_Act_Conformity.md` (не покрывается этим скиллом, отдельный сценарий с юристом).

---

## DMCA (для UGC-платформ)

Обязательный минимум:
- **Designated DMCA agent** зарегистрирован в US Copyright Office ($6 fee, обновление раз в 3 года)
- **Takedown notice flow** — UI/email для правообладателей
- **Counter-notice flow** — для пользователей оспорить takedown
- **Repeat infringer policy** — авто-бан после N strikes, опубликовано в ToS
- **Logging** — кто, когда, что снято — на случай судебного процесса

Для Memster это критично (видео-мемы = miner field). Без DMCA-инфры = риск shutdown.

---

## COPPA (если есть пользователи < 13)

Если **не** targeting детей и нет «actual knowledge» о их присутствии — можно блокировать <13 на регистрации.
Если targeting детей:
- Verifiable parental consent (платёжная карта родителя, скан ID, video-call — варианты ограничены)
- Минимизация данных детей
- Отказ от behavioural ads на детей
- Specific Privacy Policy для детской аудитории

Для Edufy: если ICP включает школьников < 13 — серьёзный compliance overhead. Альтернатива: возрастной gate на 13+.

---

## Что агент добавляет сам

- **Risk-rating per проект.** Для каждого vault-проекта оценить overall risk: low / medium / high / critical. Пример: Finbrain = high (PSD2 + AI Act + GDPR), TcenZor = medium (GDPR + affiliate disclosure), BrainKit = low (OSS-пакет).
- **Data flow diagram.** На основе архитектуры — нарисовать (Mermaid) как данные движутся через систему, отметить EU/US-границы.
- **Sub-processor list.** Из архитектуры извлечь всех external vendors (AWS, Stripe, OpenAI, Twilio) — это будущий public list для GDPR.
- **Cross-border transfer mechanism.** Если данные текут EU → US — указать механизм (SCC / EU-US Data Privacy Framework).
- **Чеклист для country-specific** — РФ (152-ФЗ, локализация ПДн), Бразилия (LGPD), UK (UK GDPR + ICO) — если ICP включает.

---

## Структура output-файлов

### `docs/03_Dev/Legal_Compliance.md`

```markdown
---
project: [ProjectName]
stage: legal-compliance
based_on: docs/03_Dev/Architecture_[Name].md
overall_risk: low | medium | high | critical
requires_lawyer_review: true
---

# Legal Compliance — [ProjectName]

## Применимые режимы (агент)
- GDPR: [yes/no/conditional] — обоснование
- CCPA: ...
- AI Act: [класс]
- DMCA: ...
- COPPA: ...
- DSA: ...
- Country-specific: [список]

## Overall risk: [уровень] (агент)

## Data inventory (Article 30)
[таблица]

## Data flow diagram
```mermaid
[диаграмма потоков данных с EU/US границами]
```

## Sub-processors
[список с DPA-статусом]

## GDPR-чеклист
- [ ] Legal basis для каждой категории данных
- [ ] User rights: access / rectification / erasure / portability / objection
- [ ] Consent management
- [ ] Privacy Policy (draft)
- [ ] ToS (draft)
- [ ] DPA подписаны со всеми sub-processors
- [ ] Breach response plan

## AI Act (если применимо)
- Классификация: ...
- Transparency обязательства: ...
- Human oversight: ...

## DMCA (если UGC)
- Designated agent registered: yes/no
- Takedown flow: ...
- Counter-notice flow: ...
- Repeat infringer policy: ...

## COPPA (если <13 users)
- Возрастной gate / verifiable parental consent: ...

## Открытые вопросы для юриста
- ...

## Следующие шаги
1. Передать draft Privacy Policy и ToS юристу
2. Подписать DPA с [список процессоров]
3. Зарегистрировать DMCA agent (если применимо)
4. AI Act conformity assessment для high-risk компонентов
```

### `docs/01_Business/Privacy_Policy_Draft.md`
Стандартный шаблон GDPR-compliant Privacy Policy с placeholder'ами для контактов и юрисдикции. **Помечен как DRAFT** — без юриста не публиковать.

### `docs/01_Business/Terms_of_Service_Draft.md`
Базовый ToS draft. Аналогично — DRAFT до юриста.

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Публиковать Privacy Policy / ToS без юриста
- Запускать high-risk AI без conformity assessment
- Игнорировать GDPR «потому что мы только начали» — штраф €20M / 4% оборота
- Заявлять «no PII» если собираем email или IP — это уже PII в EU
- Запускать UGC без DMCA-flow в US
- Хранить данные детей < 13 без COPPA-flow в US
- Делать crypto/fintech без юр-консультации по AML/KYC
- "Compliance потом" — retrofit обычно стоит в 10× дороже design-time

---

## Связанные скиллы

- `architect/architecture` — карта хранения данных и vendors как основа для compliance (предусловие).
- `architect/security-design` — GDPR privacy-by-design, классификация данных, retention; этот чеклист кормит её требованиями.
- `architect/eval-design` — для AI Act high/limited-risk: eval-харнес как часть conformity и transparency.
- `architect/observability-design` — audit trail и retention логов под Article 30 / breach-response.
- `legal/legal` — внешний свод по контрактам/NDA/compliance (анализ, не зеркало).
