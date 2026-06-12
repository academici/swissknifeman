---
name: security-design
bucket: architect
version: 0.2.0
description: "Классификация данных, auth-стратегия, RBAC/ABAC, OWASP Top 10, GDPR, STRIDE threat modeling, операционный чеклист безопасности"
risk: draft
persona: architect
tags: [security, compliance]
requires: [architecture]
produces_for: []
outputs: ["docs/03_Dev/Security_Design.md"]
snippets: ["stride-threat-model.md", "ops-security-checklist.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Security Design

Применять когда: проектирование системы с пользовательскими данными, финансами, аутентификацией, API. Запускать **параллельно с** `architecture.md`, не после.

---

## Принцип

Security — это не список фич, которые добавят в конце. Это ограничения, которые влияют на архитектуру с самого начала.

Правило: **если продукт работает с PII, деньгами или сторонними интеграциями → этот скилл обязателен.**

---

## Шаг 1. Классификация данных

Определить что хранится и какого класса:

| Класс | Примеры | Требования |
|:---|:---|:---|
| **Public** | Публичный контент, описания | Без ограничений |
| **Internal** | Логи, метрики, агрегаты | Доступ только внутри системы |
| **PII** | Email, имя, телефон, IP | Шифрование at rest, минимальное хранение |
| **Sensitive PII** | Паспорт, адрес, дата рождения | Шифрование + аудит + right-to-delete |
| **Financial** | Карты, банк. счета, транзакции | PCI DSS scope, никогда не хранить raw |
| **Credentials** | Пароли, токены, API keys | Только хэш/vault, никогда в логах |

---

## Шаг 2. Auth-стратегия

Выбрать и аргументировать схему аутентификации:

| Схема | Когда подходит | Когда не подходит |
|:---|:---|:---|
| **JWT (stateless)** | Микросервисы, мобильные клиенты, API | Нужен немедленный revoke токена |
| **Session cookie** | Монолит, web-first, SSR | Масштабирование без sticky session |
| **OAuth2 + OIDC** | "Войти через Google/GitHub", B2B SSO | Простые внутренние инструменты |
| **API Key** | Machine-to-machine, webhooks | Пользовательский доступ с браузера |
| **mTLS** | Сервис-сервис внутри инфраструктуры | Клиентские приложения |

**Правило:** для каждого типа клиента (web, mobile, API, сервис-сервис) — своя схема. Не мешать.

---

## Шаг 3. Авторизация

Определить модель:

- **RBAC** (Role-Based): пользователь имеет роль → роль имеет права. Подходит для большинства SaaS.
- **ABAC** (Attribute-Based): доступ зависит от атрибутов объекта и субъекта. Для сложных multi-tenant сценариев.
- **Ownership-based**: пользователь видит только своё. Простейший вариант, работает для B2C MVP.

Проверить: есть ли сценарии где `User A` может получить данные `User B` через прямой ID в URL или API параметре? → **IDOR** (Insecure Direct Object Reference) — самая частая уязвимость.

---

## Шаг 4. OWASP Top 10 — быстрый чеклист

Применить к конкретному типу продукта:

| # | Угроза | Проверка для этого продукта |
|:---|:---|:---|
| A01 | Broken Access Control | IDOR проверен? Роли покрывают все эндпоинты? |
| A02 | Cryptographic Failures | PII зашифрован at rest? TLS везде? |
| A03 | Injection | SQL через ORM? Input валидируется? |
| A04 | Insecure Design | Threat model сделан до кода? |
| A05 | Security Misconfiguration | Default credentials изменены? Debug off в prod? |
| A06 | Vulnerable Components | Зависимости проверяются (Dependabot/Snyk)? |
| A07 | Auth Failures | Brute-force защита? Password reset безопасен? |
| A08 | Software Integrity | CI подписан? Supply chain проверен? |
| A09 | Logging Failures | Логи не содержат PII/credentials? Есть аудит trail? |
| A10 | SSRF | Внешние URL запросы валидируются? |

---

## Шаг 5. Privacy-by-Design (GDPR minimum)

Обязателен если продукт работает с EU-пользователями или PII:

- [ ] **Consent:** явное согласие перед сбором данных (не pre-checked checkbox)
- [ ] **Data minimization:** собирать только то, что реально нужно для функции
- [ ] **Right to delete:** есть endpoint/flow для удаления аккаунта + всех данных
- [ ] **Data portability:** пользователь может скачать свои данные
- [ ] **Retention policy:** через сколько дней удалять inactive данные?
- [ ] **Third-party sharing:** какие данные идут в аналитику, рекламу, партнёров?
- [ ] **Privacy policy:** честно описывает реальный сбор данных

---

## Шаг 6. Secrets Management

| Где НЕ хранить | Где хранить |
|:---|:---|
| `.env` в git репозитории | `.env` только локально + `.gitignore` |
| Хардкод в коде | Environment variables в deployment |
| CI/CD logs | Secrets manager (Vault, AWS SSM, GitHub Secrets) |
| Клиентский код (JS) | Только серверная сторона |

**API keys третьих сторон:** ротировать минимум раз в год. Scope — минимальные права.

---

## Шаг 7. Threat Modeling (упрощённый STRIDE)

Для каждого критического компонента пройти:

| Угроза | Вопрос |
|:---|:---|
| **S**poofing | Может ли злоумышленник притвориться легитимным пользователем? |
| **T**ampering | Может ли кто-то изменить данные в transit или at rest? |
| **R**epudiation | Можно ли доказать кто сделал действие? (аудит лог) |
| **I**nformation Disclosure | Какие данные могут утечь и через какой канал? |
| **D**enial of Service | Есть ли rate limiting? Защита от flood? |
| **E**levation of Privilege | Может ли User получить Admin-права? |

---

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Прохожу STRIDE по компонентам (Шаг 7) — нужен развёрнутый шаблон | `snippets/stride-threat-model.md` |
| Настройка/ревью приложения, БД, серверов, кредов, бэкапов — операционные правила (по Spatie) | `snippets/ops-security-checklist.md` |

---

## Формат вывода в документе

Создавать в `docs/03_Dev/Security_Design.md`:

```markdown
# Security Design: ProjectName

## Классификация данных
[таблица]

## Auth-схема
[выбранная схема + аргументация]

## Авторизация
[модель + IDOR проверка]

## OWASP чеклист
[таблица со статусами]

## Privacy / GDPR
[чеклист]

## Secrets Management
[правила для данного проекта]

## Threat Model
[STRIDE по ключевым компонентам]

## Открытые вопросы безопасности
[что ещё не решено]
```

---

## Что агент добавляет сам

- IDOR-сценарии, которые не упомянуты, но вытекают из структуры API
- Предупреждение если выбранный auth-метод не соответствует типу клиента
- Флаг если в BRD упомянуты данные, которые попадают под GDPR, но Privacy section отсутствует

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Игнорировать Security Design для продуктов с пользователями
- Предлагать хранить пароли в plaintext или MD5
- Рекомендовать хранить API keys в клиентском коде
- Пропускать IDOR проверку для API с пользовательскими ресурсами
- Смешивать Auth (кто ты?) с Authz (что тебе можно?)
