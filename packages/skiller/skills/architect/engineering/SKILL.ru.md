> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: dev-engineering-super-skill
bucket: architect
version: 0.1.0
description: Comprehensive full-stack development and engineering skill merging Perplexity Computer's built-in dev tools with Claude Code's engineering team skills. Covers architecture, frontend, backend, fullstack, QA/testing, DevOps/CI-CD, security, debugging, TDD, code review, and more. Use when writing code, debugging, architecting systems, reviewing code, writing tests, deploying, or doing any software engineering work.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Супер-скилл разработки и инженерии

Исчерпывающее операционное руководство по инженерии, объединяющее встроенные возможности Perplexity Computer для работы с данными и веб-ресурсами с полным набором скиллов инженерной команды Claude Code. Охватывает каждую фазу жизненного цикла разработки ПО.

---

## Оглавление

1. [Анализ пробелов — Perplexity против скиллов Claude Code](#section-1-gap-analysis)
2. [Архитектура и проектирование систем](#section-2-architecture--system-design)
3. [Фронтенд-инженерия](#section-3-frontend-engineering)
4. [Бэкенд-инженерия](#section-4-backend-engineering)
5. [Фулстек-разработка](#section-5-fullstack-development)
6. [Тестирование и контроль качества](#section-6-testing--quality-assurance)
7. [Отладка и код-ревью](#section-7-debugging--code-review)
8. [DevOps и CI/CD](#section-8-devops--cicd)
9. [Инженерия безопасности](#section-9-security-engineering)
10. [Инженерия данных и анализ](#section-10-data-engineering--analysis)
11. [Чейнджлог и документация](#section-11-changelog--documentation)
12. [Уникальные возможности Perplexity Computer](#section-12-unique-perplexity-computer-capabilities)

---

## Раздел 1: Анализ пробелов

### Матрица сравнения возможностей

| Возможность | Встроено в Perplexity Computer | Claude Code (инженерные скиллы) | Покрытие объединённого супер-скилла |
|------------|------------------------------|-----------------------------------|-----------------------------|
| SQL (Snowflake, BigQuery, PG, Databricks) | скилл `sql-queries` | Бэкенд-паттерны SQL | **Полностью: мультидиалектный SQL + оптимизация** |
| Профилирование и исследование данных | скилл `data-exploration` | — | **Полностью: профилирование, NULL'ы, выбросы, качество** |
| Валидация данных и методология QA | скилл `data-validation` | QA/Тестирование-паттерны | **Полностью: валидация и кода, и данных** |
| Визуализация (matplotlib, seaborn, plotly) | скилл `data-visualization` | — | **Полностью: выбор графика + доступность** |
| Статистический анализ | скилл `statistical-analysis` | — | **Полностью: проверка гипотез, распределения** |
| Создание сайтов/веб-приложений/веб-игр | скилл `website-building` | Фронтенд/Фулстек | **Полностью: дизайн-система + React + Next.js** |
| Серверная логика, CGI, вебхуки | скилл `webserver` | Бэкенд-инженер | **Полностью: CGI + FastAPI + Express** |
| Архитектурные диаграммы (Mermaid, PlantUML) | — | `senior-architect` | **Полностью: C4, sequence, компонентные, слоевые** |
| Анализ зависимостей | — | `senior-architect` | **Полностью: циклические зависимости, оценка связанности** |
| Создание ADR | — | `senior-architect` | **Полностью: записи решений + рабочие процессы** |
| React/Next.js фронтенд | — | `senior-frontend` | **Полностью: хуки, серверные компоненты, бандлы** |
| Оптимизация бандла | — | `senior-frontend` | **Полностью: обнаружение тяжёлых зависимостей + альтернативы** |
| Дизайн REST/GraphQL API | — | `senior-backend` | **Полностью: OpenAPI, скаффолдинг, нагрузочное тестирование** |
| Инструменты миграции БД | — | `senior-backend` | **Полностью: diff схемы + откат** |
| Генерация набора тестов | — | `senior-qa` | **Полностью: RTL, Playwright, пробелы покрытия** |
| E2E-тестирование (Playwright/Cypress) | — | `senior-qa` | **Полностью: скаффолдинг по маршрутам + Page Objects** |
| Методология TDD | — | `tdd-guide` + obra TDD | **Полностью: Red-Green-Refactor + Железный закон** |
| Генерация CI/CD-пайплайнов | — | `senior-devops` | **Полностью: GitHub Actions, CircleCI, Terraform** |
| Сканирование безопасности (SAST/секреты) | — | `senior-secops` | **Полностью: скан кода + оценка CVE** |
| Проверка соответствия (SOC2, GDPR, HIPAA) | — | `senior-secops` | **Полностью: автоматизированная проверка соответствия** |
| Моделирование угроз (STRIDE) | — | `senior-security` | **Полностью: оценка DREAD + анализ DFD** |
| Автоматизация код-ревью | — | `code-reviewer` | **Полностью: анализ PR + проверка качества** |
| Систематическая отладка | — | obra systematic-debugging | **Полностью: 4-фазный анализ первопричины** |
| Чейнджлог из git-коммитов | — | `changelog-generator` | **Полностью: пайплайн «коммит → release notes»** |
| Живой веб-ресёрч для документации | **Да — в реальном времени** | Нет обхода обучающего отсечения | **Эксклюзив Perplexity** |
| Генерация изображений ИИ (мокапы) | **Да** | Нет | **Эксклюзив Perplexity** |
| 400+ интеграций приложений | **Да** | Нет | **Эксклюзив Perplexity** |
| Деплой сайтов вживую | **Да** | Нет | **Эксклюзив Perplexity** |

### Уникально для Perplexity Computer
- Поиск документации библиотек/API в реальном времени
- Деплой сайта за минуты
- Сгенерированные ИИ UI-мокапы и дизайн-ассеты
- Мониторинг деплоев по расписанию
- 400+ интеграций со сторонними сервисами

### Уникально для инженерных скиллов Claude Code
- Многофазная систематическая отладка (obra)
- Принудительный TDD по «железному закону»
- Оценка сложности и риска PR
- Моделирование угроз STRIDE/DREAD
- Автоматизация соответствия (SOC2, PCI-DSS, HIPAA, GDPR)

### Объединённые дополнения (только в супер-скилле)
- Инженерия данных + бэкенд-SQL в едином рабочем процессе
- Дизайн-система создания сайтов, объединённая с паттернами React/Next.js
- Веб-ресёрч Perplexity, применённый к решениям по пакетам/библиотекам
- Статистический анализ, информирующий выбор проектирования слоя данных

---

## Раздел 2: Архитектура и проектирование систем

### Когда использовать этот раздел
- Проектирование новых систем или рефакторинг существующей архитектуры
- Принятие решений по технологическому стеку
- Создание технической документации, ADR
- Оценка компромиссов «микросервисы против монолита»

### Генератор архитектурных диаграмм

Генерирует диаграммы из структуры вашего проекта в нескольких форматах.

```bash
# Mermaid (по умолчанию, рендерится в GitHub/Notion)
python scripts/architecture_diagram_generator.py ./project --format mermaid --type component

# PlantUML (корпоративная документация)
python scripts/architecture_diagram_generator.py ./project --format plantuml --type layer

# ASCII (удобно для терминала)
python scripts/architecture_diagram_generator.py ./project --format ascii

# Сохранить в файл
python scripts/architecture_diagram_generator.py ./project -o architecture.md
```

**Типы диаграмм:**
| Тип | Назначение |
|------|----------|
| `component` | Модули и их взаимосвязи |
| `layer` | Слои Presentation / Business / Data |
| `deployment` | Физическая/облачная топология развёртывания |
| `sequence` | Поток запроса между сервисами |

**Пример вывода Mermaid:**
```mermaid
graph TD
    A[API Gateway] --> B[Auth Service]
    A --> C[User Service]
    B --> D[(PostgreSQL)]
    C --> D
    C --> E[Redis Cache]
```

### Диаграммы модели C4

```mermaid
C4Context
    title System Context — E-Commerce Platform
    Person(customer, "Customer", "Browses and purchases products")
    System(ecommerce, "E-Commerce Platform", "Handles orders, payments, inventory")
    System_Ext(payment, "Stripe", "Payment processing")
    System_Ext(email, "SendGrid", "Transactional email")
    Rel(customer, ecommerce, "Uses", "HTTPS")
    Rel(ecommerce, payment, "Charges", "HTTPS/API")
    Rel(ecommerce, email, "Sends via", "HTTPS/API")
```

### Анализатор зависимостей

```bash
# Полный отчёт по зависимостям
python scripts/dependency_analyzer.py ./project --verbose

# Вывод JSON для интеграции с CI/CD
python scripts/dependency_analyzer.py ./project --output json

# Проверить только циклические зависимости
python scripts/dependency_analyzer.py ./project --check circular

# Поддерживаемые пакетные менеджеры: npm/yarn, pip/pyproject, go.mod, Cargo.toml
```

**Пример вывода:**
```
Dependency Analysis Report
==========================
Total dependencies: 47 (32 direct, 15 transitive)
Coupling score: 72/100 (moderate)

Issues found:
- CIRCULAR: auth → user → permissions → auth
- OUTDATED: lodash 4.17.15 → 4.17.21 (security)

Recommendations:
1. Extract shared interface to break circular dependency
2. Update lodash to fix CVE-2020-8203
```

### Записи архитектурных решений (ADR)

Используйте ADR для документирования значимых технических решений. Храните в `docs/adr/`.

**Шаблон ADR:**
```markdown
# ADR-001: Choose PostgreSQL as Primary Database

**Status:** Accepted
**Date:** 2026-03-03
**Deciders:** Engineering Team

## Context
We need a database for our SaaS application handling 500K users.

## Decision
Use PostgreSQL 16 as the primary relational database.

## Consequences
- Strong ACID compliance for financial data
- Excellent full-text search with pg_trgm
- Requires DBA knowledge for tuning at scale
- Well-supported by Prisma, Drizzle, SQLAlchemy
```

### Выбор архитектурного паттерна

**Шаг 1 — оцените размер команды и проекта:**

| Размер команды | Рекомендуемая отправная точка |
|-----------|---------------------------|
| 1–3 разработчика | Модульный монолит |
| 4–10 разработчиков | Модульный монолит или сервис-ориентированная архитектура |
| 10+ разработчиков | Рассмотреть микросервисы |

**Шаг 2 — сопоставьте паттерн с требованиями:**

| Требование | Рекомендуемый паттерн |
|-------------|-------------------|
| Быстрый MVP | Модульный монолит |
| Независимый деплой команд | Микросервисы |
| Сложная доменная логика | Domain-Driven Design |
| Большая разница соотношения чтение/запись | CQRS |
| Требуется аудиторский след | Event Sourcing |
| Сторонние интеграции | Hexagonal/Ports & Adapters |

**Шаг 3 — выбор базы данных:**

```
PostgreSQL → Выбор по умолчанию для большинства приложений
MongoDB    → Хранилище документов, гибкая схема
Redis      → Кэширование, сессии, real-time-функции
DynamoDB   → Бессерверная, авто-масштабирование, нативная для AWS
TimescaleDB → Временные ряды с SQL-интерфейсом
```

**Пороги масштаба:**
- < 1M записей, один регион → PostgreSQL или MySQL
- 1M–100M записей, преобладание чтения → PostgreSQL с read-репликами
- > 100M записей, глобально → CockroachDB, Spanner или DynamoDB
- Высокая пропускная способность записи (> 10K/сек) → Cassandra или ScyllaDB

### Решение «Монолит против микросервисов»

**Выбирайте монолит, когда:**
- [ ] Команда небольшая (< 10 разработчиков)
- [ ] Границы доменов неясны
- [ ] Приоритет — быстрая итерация
- [ ] Общая база данных приемлема

**Выбирайте микросервисы, когда:**
- [ ] Команды могут владеть сервисами от и до
- [ ] Независимый деплой критичен
- [ ] Разные требования к масштабированию по компонентам
- [ ] Границы доменов хорошо поняты

**Гибридный подход:** начните с модульного монолита. Извлекайте сервисы только когда у модуля существенно иные потребности в масштабировании, команде нужен независимый деплой или технологические ограничения требуют разделения.

### Инструмент оценки архитектуры

```bash
# Полная оценка
python scripts/project_architect.py ./project --verbose

# Вывод JSON
python scripts/project_architect.py ./project --output json

# Проверить конкретный аспект
python scripts/project_architect.py ./project --check layers
```

**Пример вывода:**
```
Architecture Assessment
=======================
Detected pattern: Layered Architecture (confidence: 85%)

  ✓ controllers/  - Presentation layer detected
  ✓ services/     - Business logic layer detected
  ✓ repositories/ - Data access layer detected
  ⚠ models/       - Mixed domain and DTOs

Issues:
- LARGE FILE: UserService.ts (1,847 lines) - consider splitting
- MIXED CONCERNS: PaymentController contains business logic

Recommendations:
1. Split UserService into focused services
2. Move business logic from controllers to services
3. Separate domain models from DTOs
```

### Рабочие процессы проектирования систем

**Чеклист планирования ёмкости:**
- [ ] Оценить дневную аудиторию и пиковую конкурентность
- [ ] Рассчитать темп роста хранилища (12 месяцев)
- [ ] Определить соотношение чтение/запись по каждому сервису
- [ ] Определить SLA (целевые задержки p50/p95/p99)
- [ ] Заложить 3-кратный запас над ожидаемым пиком

**Чеклист проектирования API:**
- [ ] Определить ресурсы и операции (сначала OpenAPI)
- [ ] Установить стратегию версионирования (`/v1/`, через заголовки)
- [ ] Определить формат ответа с ошибкой (единый для всех эндпоинтов)
- [ ] Спроектировать пагинацию (курсорная для больших датасетов)
- [ ] Задокументировать модель аутентификации/авторизации

---

## Раздел 3: Фронтенд-инженерия

### Когда использовать этот раздел
- Построение React/Next.js компонентов или страниц
- Оптимизация размера бандла или Core Web Vitals
- Реализация доступности и адаптивного дизайна
- Настройка нового фронтенд-проекта

### Скаффолдинг проекта

```bash
# Next.js 14+ с App Router
python scripts/frontend_scaffolder.py my-app --template nextjs

# React + Vite
python scripts/frontend_scaffolder.py my-app --template react

# С фичами
python scripts/frontend_scaffolder.py dashboard --template nextjs --features auth,api,forms,testing

# Предпросмотр без создания файлов
python scripts/frontend_scaffolder.py my-app --template nextjs --dry-run
```

**Сгенерированная структура Next.js:**
```
my-app/
├── app/
│   ├── layout.tsx        # Root layout with fonts
│   ├── page.tsx          # Home page
│   ├── globals.css       # Tailwind + CSS variables
│   └── api/health/route.ts
├── components/
│   ├── ui/               # Button, Input, Card
│   └── layout/           # Header, Footer, Sidebar
├── hooks/                # useDebounce, useLocalStorage
├── lib/                  # utils (cn), constants
├── types/                # TypeScript interfaces
├── tailwind.config.ts
├── next.config.js
└── package.json
```

### Генерация компонентов

```bash
# Клиентский компонент (по умолчанию)
python scripts/component_generator.py Button --dir src/components/ui

# Серверный компонент
python scripts/component_generator.py ProductCard --type server

# С тестом и Storybook-историей
python scripts/component_generator.py UserProfile --with-test --with-story

# Кастомный хук
python scripts/component_generator.py FormValidation --type hook

# Предпросмотр без создания
python scripts/component_generator.py Button --dry-run
```

**Сгенерированный паттерн компонента:**
```tsx
'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';

interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost';
  disabled?: boolean;
  className?: string;
  children: React.ReactNode;
  onClick?: () => void;
}

export function Button({ variant = 'primary', disabled, className, children, onClick }: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'px-4 py-2 rounded font-medium transition-colors',
        variant === 'primary' && 'bg-blue-600 text-white hover:bg-blue-700',
        variant === 'secondary' && 'bg-gray-100 text-gray-900 hover:bg-gray-200',
        variant === 'ghost' && 'text-gray-700 hover:bg-gray-100',
        disabled && 'opacity-50 cursor-not-allowed',
        className
      )}
    >
      {children}
    </button>
  );
}
```

### Паттерны React

**Составные компоненты (Compound Components) — разделяют состояние между связанными компонентами:**
```tsx
const Tabs = ({ children, defaultTab = 0 }) => {
  const [active, setActive] = useState(defaultTab);
  return (
    <TabsContext.Provider value={{ active, setActive }}>
      {children}
    </TabsContext.Provider>
  );
};

Tabs.List = TabList;
Tabs.Tab = Tab;
Tabs.Panel = TabPanel;

// Usage
<Tabs>
  <Tabs.List>
    <Tabs.Tab>Overview</Tabs.Tab>
    <Tabs.Tab>Details</Tabs.Tab>
  </Tabs.List>
  <Tabs.Panel>Overview content</Tabs.Panel>
  <Tabs.Panel>Details content</Tabs.Panel>
</Tabs>
```

**Кастомные хуки — извлекают переиспользуемую логику:**
```tsx
function useDebounce<T>(value: T, delay = 500): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

// Usage
const debouncedSearch = useDebounce(searchTerm, 300);
```

**Дженерик-компоненты с TypeScript:**
```tsx
interface ListProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  keyExtractor: (item: T) => string;
  emptyState?: React.ReactNode;
}

function List<T>({ items, renderItem, keyExtractor, emptyState }: ListProps<T>) {
  if (items.length === 0) return <>{emptyState}</>;
  return (
    <ul>
      {items.map((item, i) => (
        <li key={keyExtractor(item)}>{renderItem(item, i)}</li>
      ))}
    </ul>
  );
}
```

### Оптимизация Next.js

**Решение «серверные против клиентских компонентов»:**

По умолчанию используйте серверные компоненты. Добавляйте `'use client'` только когда нужны:
- Обработчики событий (onClick, onChange)
- Состояние (useState, useReducer)
- Эффекты (useEffect)
- Браузерные API (window, localStorage)

```tsx
// Server Component (default) — no 'use client'
async function ProductPage({ params }: { params: { id: string } }) {
  const product = await getProduct(params.id);  // Server-side fetch, no waterfall

  return (
    <div>
      <h1>{product.name}</h1>
      <AddToCartButton productId={product.id} />  {/* Client island */}
    </div>
  );
}

// Client Component
'use client';
function AddToCartButton({ productId }: { productId: string }) {
  const [adding, setAdding] = useState(false);
  return (
    <button
      onClick={async () => {
        setAdding(true);
        await addToCart(productId);
        setAdding(false);
      }}
      disabled={adding}
    >
      {adding ? 'Adding...' : 'Add to Cart'}
    </button>
  );
}
```

**Параллельная загрузка данных:**
```tsx
async function Dashboard() {
  // Fetch in parallel, not waterfall
  const [user, stats, notifications] = await Promise.all([
    getUser(),
    getStats(),
    getNotifications(),
  ]);
  return <div>...</div>;
}
```

**Стриминг с Suspense:**
```tsx
async function ProductPage({ params }: { params: { id: string } }) {
  return (
    <div>
      <ProductDetails id={params.id} />  {/* Loads first */}
      <Suspense fallback={<ReviewsSkeleton />}>
        <Reviews productId={params.id} />  {/* Streams in */}
      </Suspense>
    </div>
  );
}
```

**Конфигурация Next.js:**
```js
// next.config.js
const nextConfig = {
  images: {
    remotePatterns: [{ hostname: 'cdn.example.com' }],
    formats: ['image/avif', 'image/webp'],
  },
  experimental: {
    optimizePackageImports: ['lucide-react', '@heroicons/react'],
  },
};
```

### Анализ бандла

```bash
# Анализ бандла
python scripts/bundle_analyzer.py /path/to/project

# Подробно — проверка паттернов импорта
python scripts/bundle_analyzer.py . --verbose
```

**Интерпретация оценки бандла:**

| Оценка | Грейд | Действие |
|-------|-------|--------|
| 90–100 | A | Хорошо оптимизирован |
| 80–89 | B | Доступны мелкие оптимизации |
| 70–79 | C | Заменить тяжёлые зависимости |
| 60–69 | D | Несколько проблем требуют внимания |
| < 60 | F | Критические проблемы размера бандла |

**Замены тяжёлых зависимостей:**

| Пакет | Размер | Альтернатива |
|---------|------|-------------|
| moment | 290KB | date-fns (12KB) или dayjs (2KB) |
| lodash | 71KB | lodash-es с tree-shaking |
| axios | 14KB | Нативный fetch или ky (3KB) |
| jquery | 87KB | Нативные DOM API |
| @mui/material | Большой | shadcn/ui или Radix UI |

### Дизайн-система CSS/Tailwind

```tsx
// Conditional classes with cn() utility
import { cn } from '@/lib/utils';

// CSS variables for theming
:root {
  --color-primary: #3B82F6;
  --color-surface: #FFFFFF;
  --color-text: #1F2937;
  --spacing-base: 0.25rem;
  --radius-base: 0.375rem;
}

// Tailwind component
<button className={cn(
  // Base
  'inline-flex items-center justify-center rounded-md font-medium transition-colors',
  // Size
  size === 'sm' && 'h-8 px-3 text-xs',
  size === 'md' && 'h-10 px-4 text-sm',
  size === 'lg' && 'h-12 px-6 text-base',
  // Variant
  variant === 'primary' && 'bg-blue-600 text-white hover:bg-blue-700',
  variant === 'outline' && 'border border-gray-200 hover:bg-gray-50',
  // State
  disabled && 'pointer-events-none opacity-50'
)} />
```

**Типографическая шкала:**
```css
/* Fluid type scale */
--font-xs:   clamp(0.75rem, 0.7rem + 0.25vw, 0.875rem);
--font-sm:   clamp(0.875rem, 0.8rem + 0.375vw, 1rem);
--font-base: clamp(1rem, 0.9rem + 0.5vw, 1.125rem);
--font-lg:   clamp(1.125rem, 1rem + 0.625vw, 1.25rem);
--font-xl:   clamp(1.25rem, 1.1rem + 0.75vw, 1.5rem);
--font-2xl:  clamp(1.5rem, 1.3rem + 1vw, 2rem);
```

### Чеклист доступности

- [ ] Семантический HTML: используйте `<button>`, `<nav>`, `<main>`, `<article>`, `<section>`
- [ ] Навигация с клавиатуры: все интерактивные элементы достижимы клавиатурой
- [ ] ARIA-метки: предоставляйте метки для иконок и сложных виджетов
- [ ] Контраст цвета: минимум 4.5:1 для обычного текста, 3:1 для крупного
- [ ] Индикаторы фокуса: видимые, высококонтрастные кольца фокуса
- [ ] Skip-ссылки: «Перейти к основному содержимому» для пользователей клавиатуры
- [ ] Alt-текст: осмысленные описания для всех изображений
- [ ] Метки форм: все поля имеют связанные элементы `<label>`

```tsx
// Accessible icon button
<button
  type="button"
  aria-label="Close dialog"
  onClick={onClose}
  className="focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none rounded"
>
  <XIcon aria-hidden="true" />
</button>

// Skip link
<a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4">
  Skip to main content
</a>
```

### SEO-оптимизация

```tsx
// app/layout.tsx — root metadata
export const metadata: Metadata = {
  title: { template: '%s | My App', default: 'My App' },
  description: 'Application description for SEO',
  openGraph: {
    type: 'website',
    url: 'https://example.com',
    images: [{ url: '/og-image.png', width: 1200, height: 630 }],
  },
};

// Per-page metadata
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const product = await getProduct(params.id);
  return {
    title: product.name,
    description: product.description,
  };
}
```

---

## Раздел 4: Бэкенд-инженерия

### Когда использовать этот раздел
- Проектирование REST или GraphQL API
- Оптимизация запросов к БД и миграций
- Реализация аутентификации и авторизации
- Нагрузочное тестирование и настройка производительности

### Скаффолдинг API

```bash
# Генерация маршрутов Express из спецификации OpenAPI
python scripts/api_scaffolder.py openapi.yaml --framework express --output src/routes/

# Генерация из схемы базы данных
python scripts/api_scaffolder.py --from-db postgres://localhost/mydb --output src/routes/

# Генерация спецификации OpenAPI из существующих маршрутов
python scripts/api_scaffolder.py src/routes/ --generate-spec --output openapi.yaml

# Фреймворки: express, fastify, koa
```

### Паттерны проектирования API

**Рабочий процесс «сначала OpenAPI»:**
```yaml
# openapi.yaml
openapi: 3.0.3
info:
  title: User Service API
  version: 1.0.0
paths:
  /users:
    get:
      summary: List users
      parameters:
        - name: cursor
          in: query
          schema: { type: string }
        - name: limit
          in: query
          schema: { type: integer, default: 20, maximum: 100 }
      responses:
        '200':
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/UserListResponse'
    post:
      summary: Create user
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateUserRequest'
```

**Стандартный формат ответа:**
```json
{
  "data": { "id": "usr_123", "email": "user@example.com" },
  "meta": { "requestId": "req_abc123", "timestamp": "2026-03-03T09:00:00Z" }
}
```

**Стандартный формат ошибки:**
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid email format",
    "details": [{ "field": "email", "message": "must be a valid email address" }]
  },
  "meta": { "requestId": "req_abc123" }
}
```

**HTTP-коды состояния:**
| Код | Назначение |
|------|----------|
| 200 | Успех (GET, PUT, PATCH) |
| 201 | Создано (POST) |
| 204 | Нет содержимого (DELETE) |
| 400 | Ошибка валидации |
| 401 | Требуется аутентификация |
| 403 | Доступ запрещён |
| 404 | Ресурс не найден |
| 429 | Превышен лимит запросов |
| 500 | Внутренняя ошибка сервера |

### Проектирование и оптимизация БД

```bash
# Анализ производительности схемы
python scripts/database_migration_tool.py --connection $DATABASE_URL --analyze

# Генерация миграции из diff схемы
python scripts/database_migration_tool.py --connection $DATABASE_URL \
  --compare schema/v2.sql --output migrations/

# Сухой прогон миграции
python scripts/database_migration_tool.py --connection $DATABASE_URL \
  --migrate migrations/20260303_add_indexes.sql --dry-run

# Применить миграцию
python scripts/database_migration_tool.py --connection $DATABASE_URL \
  --migrate migrations/20260303_add_indexes.sql
```

**Стратегия индексов БД:**
```sql
-- Single column (equality lookups)
CREATE INDEX idx_users_email ON users(email);

-- Composite (multi-column queries — order matters)
CREATE INDEX idx_orders_user_status ON orders(user_id, status);

-- Partial (filtered subsets)
CREATE INDEX idx_orders_active ON orders(created_at) WHERE status = 'active';

-- Covering (avoid table lookup entirely)
CREATE INDEX idx_users_email_name ON users(email) INCLUDE (name);

-- Explain a slow query
EXPLAIN ANALYZE SELECT * FROM orders
WHERE user_id = 123
ORDER BY created_at DESC
LIMIT 10;
-- Look for: "Seq Scan" (bad), "Index Scan" (good)
```

**Предотвращение запросов N+1:**
```typescript
// BAD: N+1
const users = await db.user.findMany();
for (const user of users) {
  const orders = await db.order.findMany({ where: { userId: user.id } });
}

// GOOD: Eager loading with Prisma
const users = await db.user.findMany({
  include: {
    orders: {
      where: { status: 'active' },
      orderBy: { createdAt: 'desc' },
      take: 10,
    },
  },
});
```

**Пулинг соединений:**
```typescript
// PgBouncer or Prisma connection pool
const prisma = new PrismaClient({
  datasources: {
    db: { url: process.env.DATABASE_URL },
  },
  // Connection pool size: (2 * CPU cores) + 1
});

// Supabase / NeonDB pooled connection
DATABASE_URL="postgresql://user:pass@host:6543/db?pgbouncer=true&connection_limit=10"
```

### Аутентификация и авторизация

```typescript
// JWT configuration
const jwtConfig = {
  secret: process.env.JWT_SECRET,   // Must be from env, never hardcoded
  expiresIn: '15m',                 // Short-lived access tokens
  algorithm: 'RS256' as const,      // Prefer asymmetric
};

// Password hashing
import bcrypt from 'bcrypt';
const SALT_ROUNDS = 12;
const hash = await bcrypt.hash(password, SALT_ROUNDS);
const match = await bcrypt.compare(password, hash);

// Rate limiting
import rateLimit from 'express-rate-limit';
const apiLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,  // 15 minutes
  max: 100,
  standardHeaders: true,
  legacyHeaders: false,
});
app.use('/api/', apiLimiter);

// Input validation with Zod
import { z } from 'zod';
const CreateUserSchema = z.object({
  email: z.string().email().max(255),
  name: z.string().min(1).max(100),
  password: z.string().min(12).regex(/[A-Z]/).regex(/[0-9]/),
});
const data = CreateUserSchema.parse(req.body);
```

### Нагрузочное тестирование API

```bash
# Базовый нагрузочный тест
python scripts/api_load_tester.py https://api.example.com/users \
  --concurrency 50 --duration 30

# POST с телом и заголовками
python scripts/api_load_tester.py https://api.example.com/orders \
  --method POST \
  --header "Authorization: Bearer token123" \
  --body '{"product_id": 1, "quantity": 2}' \
  --concurrency 100 --duration 60

# Сравнить две версии API
python scripts/api_load_tester.py \
  https://api.example.com/v1/users \
  https://api.example.com/v2/users \
  --compare --concurrency 50 --duration 30
```

**Целевые показатели производительности:**
| Метрика | Цель |
|--------|------|
| Задержка P50 | < 50ms |
| Задержка P95 | < 200ms |
| Задержка P99 | < 500ms |
| Доля ошибок | < 0.1% |
| Пропускная способность | > 500 req/s на инстанс |

### Серверная логика: CGI, вебхуки, SQLite

Для лёгких серверных сценариев (вебхуки, бэкенды форм, персистентность данных):

```python
# Simple webhook receiver (CGI)
#!/usr/bin/env python3
import sys, json, hmac, hashlib, os

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = 'sha256=' + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

# SQLite backend for lightweight persistence
import sqlite3

def get_db():
    db = sqlite3.connect('data.db')
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with get_db() as db:
        db.execute('''
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
```

### Рабочий процесс усиления безопасности

```typescript
// Security headers with Helmet
import helmet from 'helmet';
app.use(helmet({
  contentSecurityPolicy: true,
  crossOriginEmbedderPolicy: true,
  hsts: { maxAge: 31536000, includeSubDomains: true },
}));

// CORS configuration
import cors from 'cors';
app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || [],
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
}));
```

---

## Раздел 5: Фулстек-разработка

### Когда использовать этот раздел
- Старт нового фулстек-проекта с нуля
- Аудит существующей кодовой базы на проблемы качества
- Выбор между технологическими стеками
- Настройка рабочих процессов разработки

### Скаффолдинг проекта

```bash
# Список доступных шаблонов
python scripts/project_scaffolder.py --list-templates

# Next.js 14+ (App Router, TypeScript, Tailwind)
python scripts/project_scaffolder.py nextjs my-saas-app

# FastAPI + React + PostgreSQL
python scripts/project_scaffolder.py fastapi-react my-api

# Стек MERN
python scripts/project_scaffolder.py mern my-project

# Django + React
python scripts/project_scaffolder.py django-react my-app

# Вывод JSON для интеграции с CI
python scripts/project_scaffolder.py nextjs my-app --json
```

**Сгенерированные файлы включают:**
- Структуру проекта со всеми необходимыми файлами
- `package.json` / `requirements.txt`
- Конфигурацию TypeScript (`tsconfig.json`)
- Docker и `docker-compose.yml`
- Шаблоны файлов окружения (`.env.example`)
- Следующие шаги для запуска проекта

### Анализ качества кода

```bash
# Анализ текущей директории
python scripts/code_quality_analyzer.py .

# Подробный вывод с детальными находками
python scripts/code_quality_analyzer.py . --verbose

# Вывод JSON
python scripts/code_quality_analyzer.py . --json

# Сохранить отчёт в файл
python scripts/code_quality_analyzer.py . --output report.json
```

**Пример вывода:**
```
CODE QUALITY ANALYSIS REPORT
============================================================
Overall Score: 75/100 (Grade: C)
Files Analyzed: 45
Total Lines: 12,500

--- SECURITY ---
  Critical: 1
  High: 2
  Medium: 5

--- COMPLEXITY ---
  Average Complexity: 8.5
  High Complexity Files: 3

--- RECOMMENDATIONS ---
1. [P0] SECURITY
   Issue: Potential hardcoded secret detected
   Action: Remove or secure sensitive data at line 42
```

### Матрица выбора стека

| Требование | Рекомендация |
|-------------|---------------|
| SEO-критичный сайт | Next.js с SSR |
| Внутренний дашборд | React + Vite |
| API-first бэкенд | FastAPI или Fastify |
| Корпоративный масштаб | NestJS + PostgreSQL |
| Быстрый прототип | API-маршруты Next.js |
| Данные с обилием документов | MongoDB |
| Сложные запросы | PostgreSQL |
| Real-time-функции | WebSockets + Redis Pub/Sub |
| Мобильное приложение | React Native или Flutter |

### Рабочий процесс разработки

**Git-процесс (Trunk-Based Development):**
```bash
# Create feature branch
git checkout -b feat/add-user-authentication

# Conventional commits
git commit -m "feat(auth): add JWT refresh token rotation"
git commit -m "fix(api): handle expired token edge case"
git commit -m "test(auth): add refresh token tests"
git commit -m "docs: update authentication API reference"

# Squash merge to main
git checkout main
git merge --squash feat/add-user-authentication
git commit -m "feat(auth): add JWT refresh token rotation (#123)"
```

**Локальная разработка:**
```bash
# Docker Compose for all services
docker-compose up -d postgres redis

# Install and run
npm install
cp .env.example .env.local
npm run dev

# Database setup
npx prisma migrate dev
npx prisma db seed
```

**Частые проблемы:**
| Проблема | Решение |
|-------|----------|
| Запросы N+1 | Использовать DataLoader или жадную загрузку |
| Медленные сборки | Проверить размер бандла, ленивая загрузка |
| Сложность аутентификации | Использовать Auth.js или Clerk |
| Ошибки типов | Включить strict-режим в tsconfig |
| Проблемы CORS | Корректно настроить middleware |

---

## Раздел 6: Тестирование и контроль качества

### Когда использовать этот раздел
- Настройка инфраструктуры тестирования для нового проекта
- Генерация наборов тестов для существующих компонентов
- Анализ пробелов покрытия
- Установление рабочих процессов TDD

### Железный закон TDD

```
НЕТ ПРОДАКШН-КОДА БЕЗ ПАДАЮЩЕГО ТЕСТА ПЕРВЫМ
```

Написали код раньше теста? Удалите его. Начните заново с TDD. Никаких исключений без явного разрешения вашего человека-партнёра.

### Цикл Red-Green-Refactor

**RED — напишите падающий тест:**
```typescript
// One behavior, clear name, tests real code (not mocks)
test('retries failed operations 3 times', async () => {
  let attempts = 0;
  const operation = () => {
    attempts++;
    if (attempts < 3) throw new Error('fail');
    return 'success';
  };

  const result = await retryOperation(operation);

  expect(result).toBe('success');
  expect(attempts).toBe(3);
});
```

**Проверьте RED — ОБЯЗАТЕЛЬНО, никогда не пропускайте:**
```bash
npm test path/to/test.test.ts
# FAIL: retryOperation is not defined
# ✓ Test fails for the RIGHT reason (feature missing, not a typo)
```

**GREEN — минимальный код, чтобы пройти:**
```typescript
// Simplest code that passes the test — no over-engineering
async function retryOperation<T>(fn: () => T | Promise<T>): Promise<T> {
  for (let i = 0; i < 3; i++) {
    try {
      return await fn();
    } catch (e) {
      if (i === 2) throw e;
    }
  }
  throw new Error('unreachable');
}
```

**Проверьте GREEN:**
```bash
npm test path/to/test.test.ts
# PASS ✓
```

**REFACTOR — приведите в порядок, оставаясь зелёным:**
- Удалите дублирование
- Улучшите имена
- Извлеките хелперы
- НЕ добавляйте поведение

**Чеклист проверки TDD — перед тем как отметить работу завершённой:**
- [ ] У каждой новой функции/метода есть тест
- [ ] Наблюдали падение каждого теста перед реализацией
- [ ] Каждый тест упал по ожидаемой причине
- [ ] Написали минимальный код, чтобы пройти каждый тест
- [ ] Все тесты проходят
- [ ] Нет ошибок или предупреждений в консоли
- [ ] Тесты используют реальный код (моки только если неизбежно)
- [ ] Покрыты граничные случаи и ошибки

**Частые рационализации — все неверны:**
| Отговорка | Реальность |
|--------|---------|
| «Слишком просто, чтобы тестировать» | Простой код ломается. Тест занимает 30 секунд. |
| «Напишу тесты потом» | Тесты, проходящие сразу, ничего не доказывают. |
| «Уже проверил вручную» | Ad-hoc ≠ систематически. Нет записи, нельзя повторить. |
| «TDD меня замедляет» | TDD быстрее, чем отладка продакшена. |

### Пирамида тестирования

```
        /\
       /E2E\          10% — мало, медленно, высокая уверенность
      /------\
     / Integ. \       20% — границы сервисов, запросы к БД
    /----------\
   /    Unit    \     70% — быстрые, изолированные, много
  /--------------\
```

**Целевые показатели покрытия:**
- Инструкции (Statements): ≥ 80%
- Ветви (Branches): ≥ 80%
- Функции: ≥ 80%
- Строки: ≥ 80%
- Критическая бизнес-логика: 100%

### Генерация набора тестов

```bash
# Генерация Jest + RTL тестов для React-компонентов
python scripts/test_suite_generator.py src/components/ --output __tests__/

# Включить тесты доступности
python scripts/test_suite_generator.py src/ --output __tests__/ --include-a11y

# Генерировать только для непокрытых файлов
python scripts/test_suite_generator.py src/ --uncovered-only --output __tests__/

# Сканировать без генерации
python scripts/test_suite_generator.py src/ --scan-only
```

**Сгенерированный паттерн теста:**
```typescript
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from '../src/components/Button';

describe('Button', () => {
  it('renders with label', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button', { name: /click me/i })).toBeInTheDocument();
  });

  it('calls onClick when clicked', async () => {
    const user = userEvent.setup();
    const handleClick = jest.fn();
    render(<Button onClick={handleClick}>Click</Button>);

    await user.click(screen.getByRole('button'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('is disabled when disabled prop passed', () => {
    render(<Button disabled>Click</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
```

### Анализ покрытия

```bash
# Генерация отчёта о покрытии
npm test -- --coverage --coverageReporters=json

# Анализ пробелов покрытия
python scripts/coverage_analyzer.py coverage/coverage-final.json --threshold 80

# Принудительное соблюдение порога (выход 1, если ниже)
python scripts/coverage_analyzer.py coverage/ --threshold 80 --strict

# Генерация HTML-отчёта
python scripts/coverage_analyzer.py coverage/ --format html --output report.html
```

### E2E-тестирование с Playwright

```bash
# Скаффолдинг E2E-тестов из маршрутов Next.js
python scripts/e2e_test_scaffolder.py src/app/ --output e2e/

# Включить классы Page Object Model
python scripts/e2e_test_scaffolder.py src/app/ --output e2e/ --include-pom

# Только определённые маршруты
python scripts/e2e_test_scaffolder.py src/app/ --routes "/login,/dashboard,/checkout"
```

**Сгенерированный тест Playwright:**
```typescript
import { test, expect } from '@playwright/test';

test.describe('Login page', () => {
  test('allows user to log in with valid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.getByLabel('Email').fill('user@example.com');
    await page.getByLabel('Password').fill('password123');
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page).toHaveURL('/dashboard');
    await expect(page.getByText('Welcome back')).toBeVisible();
  });

  test('shows error with invalid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.getByLabel('Email').fill('wrong@example.com');
    await page.getByLabel('Password').fill('wrongpassword');
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.getByRole('alert')).toContainText('Invalid credentials');
  });
});
```

**Фикстура аутентификации:**
```typescript
// e2e/fixtures/auth.ts
import { test as base } from '@playwright/test';

export const test = base.extend({
  authenticatedPage: async ({ page }, use) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill('test@example.com');
    await page.getByLabel('Password').fill('password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL('/dashboard');
    await use(page);
  },
});
```

### Поддержка нескольких фреймворков тестирования

```bash
# Генерация тестов Pytest
python scripts/test_generator.py --input source.py --framework pytest

# Генерация тестов JUnit
python scripts/test_generator.py --input UserService.java --framework junit

# Конвертация из Jest в Pytest
python scripts/framework_adapter.py --from jest --to pytest

# Генерация фикстур тестов
python scripts/fixture_generator.py --entity User --count 10 --format json
```

### Частые паттерны тестирования

**Запросы React Testing Library (в порядке предпочтения):**
```typescript
// 1. Accessible role (best)
screen.getByRole('button', { name: /submit/i })

// 2. Label text
screen.getByLabelText(/email address/i)

// 3. Placeholder
screen.getByPlaceholderText(/search/i)

// 4. Text content
screen.getByText(/welcome/i)

// 5. Test ID (last resort)
screen.getByTestId('custom-element')
```

**Асинхронное тестирование:**
```typescript
// Wait for element to appear
await screen.findByText(/loaded successfully/i);

// Wait for element to disappear
await waitForElementToBeRemoved(() => screen.queryByText(/loading/i));

// Wait for condition
await waitFor(() => {
  expect(mockFn).toHaveBeenCalledWith(expect.objectContaining({ id: '123' }));
});
```

**Мокинг API с MSW:**
```typescript
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

const server = setupServer(
  http.get('/api/users', () => {
    return HttpResponse.json([{ id: 1, name: 'John' }]);
  }),
  http.post('/api/users', async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({ id: 2, ...body }, { status: 201 });
  })
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

**Конфигурация Jest:**
```javascript
// jest.config.js
module.exports = {
  testEnvironment: 'jsdom',
  setupFilesAfterFramework: ['@testing-library/jest-dom'],
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
  },
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
};
```

### Анти-паттерны тестирования, которых следует избегать

| Анти-паттерн | Проблема | Исправление |
|-------------|---------|-----|
| Тестирование поведения моков | Тестирует моки, а не реальный код | Используйте реальные реализации |
| Тестирование деталей реализации | Хрупкие, ломаются при рефакторинге | Тестируйте наблюдаемое поведение |
| `test('it works')` | Расплывчатое имя теста | Опишите поведение: `test('returns 401 for expired token')` |
| Несколько утверждений без контекста | Трудно диагностировать падения | Используйте блоки `describe`, одно поведение на тест |
| Жёстко заданные паузы (`setTimeout`) | Нестабильные (flaky) тесты | Используйте `waitFor` / опрос условия |
| Общее изменяемое состояние тестов | Баги порядка тестов | Сбрасывайте состояние в `beforeEach` |

---

## Раздел 7: Отладка и код-ревью

### Когда использовать этот раздел
- Столкнулись с любым багом, падением теста или неожиданным поведением
- Ревью pull-реквестов
- Оценка качества кода перед мёрджем

### Железный закон систематической отладки

```
НЕТ ИСПРАВЛЕНИЙ БЕЗ РАССЛЕДОВАНИЯ ПЕРВОПРИЧИНЫ
```

Если вы не завершили Фазу 1, вы не можете предлагать исправления.

### Четыре фазы

**Фаза 1: Расследование первопричины**

1. **Внимательно читайте сообщения об ошибках** — они часто содержат точное решение
2. **Воспроизводите стабильно** — точные шаги, каждый раз
3. **Проверьте недавние изменения** — git diff, новые зависимости, изменения конфига
4. **Собирайте улики в многокомпонентных системах:**
   ```bash
   # Layer 1: Check environment propagation
   echo "=== Env vars: ===" && env | grep MY_VAR || echo "NOT SET"
   
   # Layer 2: Add diagnostic logging at each boundary
   console.log('[auth] Input:', { userId, scope })
   console.log('[auth] Token:', token ? 'SET' : 'UNSET')
   
   # Layer 3: Trace actual data flow
   console.log('[db] Query result:', JSON.stringify(result, null, 2))
   ```
5. **Трассируйте поток данных** — где возникает плохое значение? Трассируйте назад.

**Фаза 2: Анализ паттернов**

- Найдите рабочие примеры похожего кода в кодовой базе
- Сравните рабочий и сломанный код — перечислите каждое различие
- Поймите зависимости (конфиг, окружение, предположения)

**Фаза 3: Гипотеза и проверка**

- Сформулируйте гипотезу: *«Я думаю, X — первопричина, потому что Y»*
- Сделайте наименьшее возможное изменение, чтобы её проверить
- По одной переменной за раз — никогда не несколько исправлений сразу
- Если не сработало, сформируйте НОВУЮ гипотезу

**Фаза 4: Реализация**

- Сначала создайте падающий тестовый случай (см. раздел TDD)
- Реализуйте единственное исправление, устраняющее первопричину
- Проверьте исправление (тесты проходят, проблема решена, нет регрессий)
- Если провалились 3+ исправления: **подвергните сомнению архитектуру**, а не симптомы

### Красные флаги отладки — СТОП и возврат к Фазе 1

- «Быстрый фикс сейчас, разберусь потом»
- «Просто попробуй поменять X и посмотри, сработает ли»
- «Добавь несколько изменений, прогони тесты»
- «Это, наверное, X, дай починю»
- «Ещё одна попытка фикса» (после уже 2+ попыток)
- Каждое исправление вскрывает новую проблему в другом месте

**Если провалились 3+ исправления:** архитектура может быть неправильной. Обсудите с командой перед новыми попытками исправления.

### Краткий справочник по отладке

| Фаза | Ключевые активности | Критерий успеха |
|-------|---------------|------------------|
| Первопричина | Читать ошибки, воспроизводить, собирать улики | Понять ЧТО и ПОЧЕМУ |
| Паттерн | Найти рабочие примеры, сравнить | Выявить различия |
| Гипотеза | Сформировать теорию, минимально проверить | Подтверждено или новая гипотеза |
| Реализация | Написать тест, исправить, проверить | Баг устранён, тесты проходят |

### Автоматизация код-ревью

```bash
# Анализ сложности и риска PR
python scripts/pr_analyzer.py /path/to/repo

# Сравнить конкретные ветки
python scripts/pr_analyzer.py . --base main --head feature-branch

# Проверить качество кода
python scripts/code_quality_checker.py /path/to/code

# Проверить конкретный язык
python scripts/code_quality_checker.py . --language python

# Сгенерировать полный отчёт ревью
python scripts/review_report_generator.py /path/to/repo

# Вывод Markdown
python scripts/review_report_generator.py . --format markdown --output review.md
```

**Вердикты ревью:**
| Оценка | Вердикт |
|-------|---------|
| 90+ без high-проблем | Одобрить |
| 75+ с ≤2 high-проблемами | Одобрить с предложениями |
| 50–74 | Запросить изменения |
| < 50 или критические проблемы | Блокировать |

### Пороги качества кода

| Проблема | Порог | Действие |
|-------|-----------|--------|
| Длинная функция | > 50 строк | Извлечь в меньшие функции |
| Большой файл | > 500 строк | Разбить на модули |
| Божественный класс | > 20 методов | Применить единую ответственность |
| Слишком много параметров | > 5 | Использовать объект-опции или билдер |
| Глубокая вложенность | > 4 уровней | Извлечь в функции, guard-условия |
| Высокая сложность | > 10 ветвей | Извлечь в паттерн «стратегия» |

### Чеклист код-ревью

**Перед ревью:**
- [ ] Сборка проходит
- [ ] Все тесты проходят
- [ ] Описание PR объясняет что и почему
- [ ] Нет несвязанных изменений

**Корректность:**
- [ ] Логика обрабатывает граничные случаи
- [ ] Обработка ошибок присутствует и корректна
- [ ] Нет гонок данных или проблем конкурентности

**Безопасность:**
- [ ] Нет жёстко заданных секретов или API-ключей
- [ ] Валидация ввода на всех данных, управляемых пользователем
- [ ] Нет уязвимостей SQL-инъекций
- [ ] Проверки авторизации на всех защищённых эндпоинтах

**Производительность:**
- [ ] Нет запросов N+1
- [ ] Нет неограниченных операций над коллекциями
- [ ] Уместное использование кэширования

**Сопровождаемость:**
- [ ] Чёткие, описательные имена переменных и функций
- [ ] Нет магических чисел (используйте именованные константы)
- [ ] Нет TODO/FIXME без отслеживающих задач
- [ ] Нет типов `any` в TypeScript

**Тестирование:**
- [ ] У нового кода есть тесты
- [ ] Тесты покрывают случаи ошибок и граничные случаи
- [ ] Нет тестов деталей реализации

### Языко-специфичные стандарты кода

**TypeScript:**
```typescript
// Type annotations on all public functions
function processUser(userId: string, options: ProcessOptions): Promise<User>

// Avoid `any` — use `unknown` + type guards
function parseJSON(input: unknown): Record<string, unknown> {
  if (typeof input !== 'string') throw new TypeError('Expected string');
  return JSON.parse(input);
}

// Prefer const assertions
const ROLES = ['admin', 'user', 'guest'] as const;
type Role = typeof ROLES[number];
```

**Python:**
```python
# Type hints on all functions
def process_user(user_id: str, *, dry_run: bool = False) -> User:
    ...

# Use dataclasses for data containers
from dataclasses import dataclass, field
@dataclass
class ProcessOptions:
    dry_run: bool = False
    timeout: float = 30.0

# Context managers for resources
with open(file_path) as f:
    content = f.read()
```

---

## Раздел 8: DevOps и CI/CD

### Когда использовать этот раздел
- Настройка CI/CD-пайплайнов для проекта
- Развёртывание приложений в облачной инфраструктуре
- Контейнеризация приложений с Docker/Kubernetes
- Управление инфраструктурой как кодом

### Генерация пайплайна

```bash
# Генерация пайплайна GitHub Actions
python scripts/pipeline_generator.py ./my-project --platform github

# Генерация пайплайна CircleCI
python scripts/pipeline_generator.py ./my-project --platform circleci

# Анализ существующего пайплайна
python scripts/deployment_manager.py --analyze
```

### Паттерны GitHub Actions

**Полный CI/CD-пайплайн:**
```yaml
# .github/workflows/ci-cd.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  NODE_VERSION: '20'
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: 'npm'

      - run: npm ci
      - run: npm run lint
      - run: npm test -- --coverage

      - name: Upload coverage
        uses: codecov/codecov-action@v4

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Security Scan
        run: python scripts/security_scanner.py . --severity high
      - name: Vulnerability Assessment
        run: python scripts/vulnerability_assessor.py . --severity critical

  build:
    needs: [test, security]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    outputs:
      image-digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v4
      - name: Login to Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and Push
        id: build
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Deploy to Kubernetes
        run: |
          kubectl set image deployment/app \
            app=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build.outputs.image-digest }}
          kubectl rollout status deployment/app
```

**Гейт сканирования безопасности:**
```yaml
# .github/workflows/security.yml
name: Security Scan
on:
  pull_request:
    branches: [main, develop]

jobs:
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Security Scanner
        run: python scripts/security_scanner.py . --severity high
      - name: Vulnerability Assessment
        run: python scripts/vulnerability_assessor.py . --severity critical
      - name: Compliance Check
        run: python scripts/compliance_checker.py . --framework soc2
```

### Инфраструктура как код (Terraform)

```bash
# Скаффолдинг модулей Terraform
python scripts/terraform_scaffolder.py ./infrastructure --cloud aws

# Анализ существующего Terraform
python scripts/terraform_scaffolder.py ./infrastructure --verbose
```

**Структура модуля Terraform:**
```
infrastructure/
├── main.tf
├── variables.tf
├── outputs.tf
├── versions.tf
├── modules/
│   ├── vpc/
│   ├── eks/
│   └── rds/
└── environments/
    ├── staging/
    └── production/
```

**Пример модуля EKS:**
```hcl
# modules/eks/main.tf
resource "aws_eks_cluster" "main" {
  name     = var.cluster_name
  role_arn = aws_iam_role.eks.arn
  version  = var.kubernetes_version

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.eks.id]
  }

  encryption_config {
    provider {
      key_arn = var.kms_key_arn
    }
    resources = ["secrets"]
  }

  depends_on = [aws_iam_role_policy_attachment.eks]
}
```

### Стратегии развёртывания

**Сине-зелёное развёртывание (Blue-Green):**
```bash
# Deploy to green environment
kubectl apply -f k8s/green/

# Run smoke tests
./scripts/smoke-test.sh https://green.example.com

# Switch traffic
kubectl patch service app -p '{"spec":{"selector":{"slot":"green"}}}'

# Keep blue for rollback
# kubectl patch service app -p '{"spec":{"selector":{"slot":"blue"}}}'
```

**Канареечное развёртывание (Canary):**
```yaml
# k8s/canary.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations:
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-weight: "10"  # 10% to canary
spec:
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: app-canary
                port: { number: 80 }
```

**Скользящее обновление (Rolling Update):**
```yaml
# k8s/deployment.yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1        # Create 1 new pod before removing old
      maxUnavailable: 0  # Zero downtime
```

### Лучшие практики контейнеров

```dockerfile
# Multi-stage build for Node.js
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

FROM node:20-alpine AS runner
WORKDIR /app
# Run as non-root
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs
COPY --from=builder /app/node_modules ./node_modules
COPY --chown=nextjs:nodejs . .
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
```

### Операции Kubernetes

```bash
# Apply manifests
kubectl apply -f k8s/

# Check rollout status
kubectl rollout status deployment/app

# Rollback if needed
kubectl rollout undo deployment/app

# View logs
kubectl logs -f deployment/app --tail=100

# Scale
kubectl scale deployment/app --replicas=5

# Resource usage
kubectl top pods
kubectl top nodes
```

### Мониторинг и оповещения

**Эндпоинт проверки здоровья (health check):**
```typescript
// GET /health
app.get('/health', async (req, res) => {
  const checks = await Promise.allSettled([
    db.$queryRaw`SELECT 1`,
    redis.ping(),
  ]);

  const status = checks.every(c => c.status === 'fulfilled') ? 200 : 503;

  res.status(status).json({
    status: status === 200 ? 'healthy' : 'degraded',
    timestamp: new Date().toISOString(),
    checks: {
      database: checks[0].status,
      redis: checks[1].status,
    },
  });
});
```

**Структурированное логирование:**
```typescript
import pino from 'pino';

const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  redact: ['req.headers.authorization', 'body.password'],
});

// Request logging
logger.info({ userId, action: 'createOrder', orderId }, 'Order created');

// Error logging
logger.error({ err, userId, path: req.path }, 'Request failed');
```

---

## Раздел 9: Инженерия безопасности

### Когда использовать этот раздел
- Реализация средств контроля безопасности на новом проекте
- Проведение аудитов безопасности или код-ревью
- Реагирование на отчёты об уязвимостях
- Проектирование безопасных архитектур

### Набор инструментов сканирования безопасности

```bash
# Сканировать исходный код на уязвимости
python scripts/security_scanner.py /path/to/project

# Фильтр по серьёзности
python scripts/security_scanner.py /path/to/project --severity high

# Вывод JSON для CI/CD
python scripts/security_scanner.py /path/to/project --json --output report.json

# Оценить CVE зависимостей
python scripts/vulnerability_assessor.py /path/to/project --severity high

# Проверить соответствие
python scripts/compliance_checker.py /path/to/project --framework soc2
python scripts/compliance_checker.py /path/to/project --framework gdpr
python scripts/compliance_checker.py /path/to/project --framework pci-dss
python scripts/compliance_checker.py /path/to/project --framework hipaa
```

**Сканер безопасности обнаруживает:**
- Жёстко заданные секреты (API-ключи, пароли, AWS-креды, приватные ключи)
- SQL-инъекции (конкатенация строк, f-строки в запросах)
- XSS (присваивание innerHTML, небезопасная манипуляция DOM)
- Инъекции команд (shell=True, exec/eval с пользовательским вводом)
- Обход путей (операции с файлами с пользовательским вводом)

### Предотвращение OWASP Top 10

| Уязвимость | Предотвращение |
|--------------|------------|
| A01: Нарушение контроля доступа | RBAC, запрет по умолчанию, валидация прав на сервере |
| A02: Криптографические сбои | TLS 1.3+, AES-256-GCM, безопасное управление ключами |
| A03: Инъекции | Параметризованные запросы, валидация ввода, экранирование вывода |
| A04: Небезопасный дизайн | Моделирование угроз, безопасные паттерны проектирования, эшелонированная защита |
| A05: Неверная конфигурация безопасности | Руководства по усилению, удаление дефолтов, отключение неиспользуемых функций |
| A06: Уязвимые компоненты | Сканирование зависимостей, автообновления, SBOM |
| A07: Сбои аутентификации | MFA, ограничение скорости, безопасное хранение паролей |
| A08: Сбои целостности данных | Подписывание кода, проверки целостности, безопасный CI/CD |
| A09: Сбои логирования безопасности | Исчерпывающие аудиторские логи, интеграция с SIEM |
| A10: SSRF | Валидация URL, allowlist назначений, сегментация сети |

### Чеклист безопасного кодирования

**Валидация ввода:**
- [ ] Весь пользовательский ввод валидируется на сервере
- [ ] Allowlist предпочтительнее denylist
- [ ] Контекстно-уместная санитизация (HTML, SQL, shell)

**Аутентификация:**
- [ ] Пароли хешируются bcrypt/Argon2 (минимум раундов: 12)
- [ ] MFA для чувствительных операций
- [ ] Строгая парольная политика (минимум 12 символов, сложность)
- [ ] Короткоживущие access-токены (15 мин), более долгие refresh-токены (7 дней)

**Управление сессиями:**
- [ ] Безопасные случайные ID сессий
- [ ] Флаги cookie HttpOnly, Secure, SameSite=Strict
- [ ] Тайм-аут сессии (15 мин простоя)
- [ ] Ротация токена при повышении привилегий

**Управление секретами:**
- [ ] Переменные окружения или выделенный менеджер секретов
- [ ] Никогда не коммитьте секреты в систему контроля версий
- [ ] Ротация кредов при уходе члена команды
- [ ] Используйте `.env.example` с плейсхолдерами

**Обработка ошибок:**
- [ ] Логируйте ошибки с контекстом (никогда не логируйте секреты)
- [ ] Возвращайте обобщённые сообщения пользователям
- [ ] Никогда не раскрывайте стек-трейсы в продакшене

### Моделирование угроз (STRIDE)

**Рабочий процесс:**
1. Определите границы системы (активы, границы доверия, потоки данных)
2. Создайте диаграмму потоков данных (DFD)
3. Примените STRIDE к каждому элементу DFD
4. Оцените риски с помощью DREAD
5. Приоритизируйте и определите меры смягчения

**Категории STRIDE:**
| Категория | Свойство безопасности | Фокус смягчения |
|----------|-------------------|------------------|
| Spoofing (подмена) | Аутентификация | MFA, сертификаты, сильная аутентификация |
| Tampering (подделка) | Целостность | Подписывание, контрольные суммы, валидация |
| Repudiation (отказ) | Неотказуемость | Аудиторские логи, цифровые подписи |
| Information Disclosure (раскрытие информации) | Конфиденциальность | Шифрование, контроль доступа |
| Denial of Service (отказ в обслуживании) | Доступность | Ограничение скорости, избыточность |
| Elevation of Privilege (повышение привилегий) | Авторизация | RBAC, наименьшие привилегии |

**STRIDE по элементу DFD:**
| Элемент | S | T | R | I | D | E |
|---------|---|---|---|---|---|---|
| Внешняя сущность | X | | X | | | |
| Процесс | X | X | X | X | X | X |
| Хранилище данных | | X | X | X | X | |
| Поток данных | | X | | X | X | |

```bash
# Run STRIDE threat modeling
python scripts/threat_modeler.py --component "Authentication Service"

# Scan for hardcoded secrets
python scripts/secret_scanner.py /path/to/project
```

### Архитектура безопасности: эшелонированная защита (Defense in Depth)

```
Layer 1: PERIMETER
  WAF, DDoS mitigation, DNS filtering, rate limiting

Layer 2: NETWORK
  Segmentation, IDS/IPS, network monitoring, VPN, mTLS

Layer 3: HOST
  Endpoint protection, OS hardening, patching, EDR

Layer 4: APPLICATION
  Input validation, authentication, secure coding, SAST

Layer 5: DATA
  Encryption at rest/transit, access controls, DLP, backup
```

**Принципы Zero Trust:**
- Проверяйте явно (аутентифицируйте/авторизуйте каждый запрос)
- Наименьшие привилегии доступа (just-in-time, just-enough access)
- Предполагайте взлом (сегментируйте, мониторьте, обнаруживайте боковое перемещение)

### Выбор паттерна аутентификации

| Сценарий | Рекомендуемый паттерн |
|----------|---------------------|
| Веб-приложение | OAuth 2.0 + PKCE с OIDC |
| Аутентификация API | JWT (RS256) + короткий срок действия + refresh-токены |
| Сервис-сервис | mTLS с ротацией сертификатов |
| CLI/Автоматизация | API-ключи с allowlist по IP |
| Высокая безопасность | Аппаратные ключи FIDO2/WebAuthn |

### Выбор криптографического алгоритма

| Сценарий | Алгоритм | Размер ключа |
|----------|-----------|----------|
| Симметричное шифрование | AES-256-GCM | 256 бит |
| Хеширование паролей | Argon2id | Используйте дефолты |
| Аутентификация сообщений | HMAC-SHA256 | 256 бит |
| Цифровые подписи | Ed25519 | 256 бит |
| Обмен ключами | X25519 | 256 бит |
| TLS | TLS 1.3 | Н/Д |

**Паттерны кода:**
```javascript
// Password hashing (bcrypt)
const bcrypt = require('bcrypt');
const hash = await bcrypt.hash(password, 12);
const valid = await bcrypt.compare(password, hash);

// Random tokens (cryptographically secure)
import { randomBytes } from 'crypto';
const token = randomBytes(32).toString('hex');

// BAD: Math.random()
// GOOD: crypto.getRandomValues()
const array = new Uint32Array(10);
crypto.getRandomValues(array);
```

### Фреймворки соответствия (Compliance)

**Средства контроля SOC 2 Type II:**
| Контроль | Категория | Описание |
|---------|----------|-------------|
| CC1 | Среда контроля | Политики безопасности, оргструктура |
| CC3 | Оценка рисков | Сканирование уязвимостей, моделирование угроз |
| CC6 | Логический доступ | Аутентификация, авторизация, MFA |
| CC7 | Операции системы | Мониторинг, логирование, реагирование на инциденты |
| CC8 | Управление изменениями | CI/CD, код-ревью, контроль деплоев |

**Требования GDPR:**
| Статья | Требование |
|---------|-------------|
| Ст. 25 | Конфиденциальность по дизайну, минимизация данных |
| Ст. 32 | Меры безопасности, шифрование, псевдонимизация |
| Ст. 33 | Уведомление об утечке (72 часа) |
| Ст. 17 | Право на удаление (стирание данных) |
| Ст. 20 | Переносимость данных (возможность экспорта) |

### Реагирование на инциденты безопасности

```
PHASE 1: DETECT & IDENTIFY (0–15 min)
- Alert received and acknowledged
- Initial severity assessment (SEV-1 to SEV-4)
- Incident commander assigned
- Communication channel established

PHASE 2: CONTAIN (15–60 min)
- Affected systems identified
- Network isolation if needed
- Credentials rotated if compromised
- Evidence preserved (logs, memory dumps)

PHASE 3: ERADICATE (1–4 hours)
- Root cause identified
- Malware/backdoors removed
- Vulnerabilities patched
- Systems hardened

PHASE 4: RECOVER (4–24 hours)
- Systems restored from clean backup
- Services brought back online
- Enhanced monitoring enabled

PHASE 5: POST-INCIDENT (24–72 hours)
- Timeline documented
- Root cause analysis complete
- Lessons learned documented
- Stakeholder report delivered
```

**Уровни серьёзности инцидента:**
| Уровень | Описание | Время реагирования |
|-------|-------------|---------------|
| P1 – Критический | Активный взлом, эксфильтрация данных | Немедленно |
| P2 – Высокий | Подтверждённая компрометация, локализована | 1 час |
| P3 – Средний | Потенциальная компрометация, расследуется | 4 часа |
| P4 – Низкий | Подозрительная активность, низкое влияние | 24 часа |

---

## Раздел 10: Инженерия данных и анализ

### Когда использовать этот раздел
- Профилирование и исследование датасетов на проблемы качества
- Написание SQL-запросов на нескольких диалектах хранилищ
- Создание графиков и визуализаций
- Применение статистических методов к данным
- Валидация пайплайнов данных и методологии анализа

### Профилирование датасета

```python
import pandas as pd
import numpy as np

def profile_dataset(df: pd.DataFrame) -> dict:
    """Profile a dataset for quality issues."""
    profile = {
        'shape': df.shape,
        'dtypes': df.dtypes.to_dict(),
        'null_counts': df.isnull().sum().to_dict(),
        'null_pct': (df.isnull().mean() * 100).round(2).to_dict(),
        'duplicates': df.duplicated().sum(),
    }

    # Numeric column stats
    numeric_cols = df.select_dtypes(include=np.number).columns
    profile['numeric_stats'] = df[numeric_cols].describe().to_dict()

    # Outlier detection (IQR method)
    outliers = {}
    for col in numeric_cols:
        Q1, Q3 = df[col].quantile([0.25, 0.75])
        IQR = Q3 - Q1
        n_outliers = ((df[col] < Q1 - 1.5 * IQR) | (df[col] > Q3 + 1.5 * IQR)).sum()
        if n_outliers > 0:
            outliers[col] = int(n_outliers)
    profile['outliers'] = outliers

    return profile
```

**Чеклист качества данных:**
- [ ] Количество строк соответствует ожидаемому объёму
- [ ] Нет неожиданных NULL-значений в обязательных колонках
- [ ] Уникальность первичного ключа проверена
- [ ] Диапазоны дат в ожидаемых границах
- [ ] Категориальные значения соответствуют известному домену значений
- [ ] Числовые значения в бизнес-допустимых диапазонах
- [ ] Нет дублирующихся записей

### SQL на основных диалектах

**PostgreSQL:**
```sql
-- Window functions
SELECT
  user_id,
  order_date,
  amount,
  SUM(amount) OVER (
    PARTITION BY user_id
    ORDER BY order_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
  ) AS running_total,
  ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY order_date DESC) AS rn
FROM orders;

-- CTEs for readability
WITH monthly_revenue AS (
  SELECT
    DATE_TRUNC('month', order_date) AS month,
    SUM(amount) AS revenue
  FROM orders
  WHERE status = 'completed'
  GROUP BY 1
),
growth AS (
  SELECT
    month,
    revenue,
    LAG(revenue) OVER (ORDER BY month) AS prev_revenue,
    ROUND(
      100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
      / NULLIF(LAG(revenue) OVER (ORDER BY month), 0), 2
    ) AS growth_pct
  FROM monthly_revenue
)
SELECT * FROM growth ORDER BY month;
```

**Snowflake:**
```sql
-- Semi-structured data with VARIANT
SELECT
  user_id,
  event_data:event_type::STRING AS event_type,
  event_data:properties:page::STRING AS page,
  event_data:timestamp::TIMESTAMP AS ts
FROM events
WHERE event_data:event_type = 'page_view';

-- Clustering and partitioning
CREATE TABLE orders
  CLUSTER BY (DATE_TRUNC('month', order_date))
AS SELECT * FROM source_orders;
```

**BigQuery:**
```sql
-- Array aggregation
SELECT
  user_id,
  ARRAY_AGG(
    STRUCT(product_id, quantity, unit_price)
    ORDER BY created_at
  ) AS order_items
FROM order_items
GROUP BY user_id;

-- Approximate aggregations (fast on large tables)
SELECT
  country,
  APPROX_COUNT_DISTINCT(user_id) AS approx_users,
  APPROX_QUANTILES(revenue, 100)[OFFSET(50)] AS median_revenue
FROM sessions
GROUP BY country;
```

**Databricks / Spark SQL:**
```sql
-- Delta Lake time travel
SELECT * FROM orders VERSION AS OF 5;
SELECT * FROM orders TIMESTAMP AS OF '2026-01-01';

-- Optimize and Z-order
OPTIMIZE orders ZORDER BY (user_id, order_date);

-- Merge (upsert)
MERGE INTO orders AS target
USING updates AS source
ON target.order_id = source.order_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

**Паттерны оптимизации запросов:**
```sql
-- Use EXISTS instead of IN for large subqueries
-- SLOW:
SELECT * FROM users WHERE id IN (SELECT user_id FROM orders WHERE amount > 100);

-- FAST:
SELECT u.* FROM users u WHERE EXISTS (
  SELECT 1 FROM orders o WHERE o.user_id = u.id AND o.amount > 100
);

-- Index-friendly date filtering
-- SLOW (function on indexed column):
WHERE YEAR(created_at) = 2026

-- FAST (range on indexed column):
WHERE created_at >= '2026-01-01' AND created_at < '2027-01-01'

-- Covering index for common queries
CREATE INDEX idx_orders_user_date_amount
ON orders(user_id, order_date)
INCLUDE (amount, status);
```

### Визуализация данных

```python
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px

# Seaborn theme
sns.set_theme(style='whitegrid', palette='muted', font_scale=1.2)

# Distribution plot with annotations
fig, ax = plt.subplots(figsize=(10, 6))
sns.histplot(data=df, x='revenue', bins=50, kde=True, ax=ax)
ax.set_title('Revenue Distribution', fontsize=14, fontweight='bold')
ax.set_xlabel('Revenue ($)')
ax.set_ylabel('Count')
plt.tight_layout()
plt.savefig('revenue_dist.png', dpi=150, bbox_inches='tight')

# Interactive Plotly chart
fig = px.scatter(
    df,
    x='customer_age',
    y='lifetime_value',
    color='segment',
    size='order_count',
    hover_data=['customer_id'],
    title='Customer Lifetime Value by Segment',
    labels={'customer_age': 'Age', 'lifetime_value': 'LTV ($)'},
)
fig.update_layout(template='plotly_white')
fig.write_html('ltv_scatter.html')
```

**Руководство по выбору типа графика:**
| Тип данных | Сравнение | Используйте график |
|-----------|-----------|-----------|
| Числовые во времени | Тренд | Линейный график |
| Числовые категории | Ранжирование | Столбчатый (горизонтальный для длинных меток) |
| Часть к целому | Композиция | Стек столбцов, treemap |
| Две числовые переменные | Корреляция | Точечная диаграмма (scatter) |
| Распределение | Форма | Гистограмма, скрипка (violin), ящик (box plot) |
| Географические | Пространственные | Хороплет, пузырьковая карта |
| Пропорции (≤5 частей) | Композиция | Круговая/кольцевая (используйте умеренно) |

**Доступность в графиках:**
```python
# Use colorblind-safe palettes
PALETTE = ['#0072B2', '#E69F00', '#009E73', '#CC79A7', '#56B4E9']

# Add pattern fill for black-and-white printing
ax.bar(x, height, hatch='///', color=PALETTE[0])

# Always include alt text metadata
fig.update_layout(
    title=dict(text='<b>Revenue by Quarter</b>'),
    annotations=[dict(
        text='<i>Accessible description: Bar chart showing Q1-Q4 revenue...</i>',
        visible=False,  # For screen readers via aria
    )],
)
```

### Статистический анализ

```python
from scipy import stats
import numpy as np

# Descriptive statistics
def describe_column(series: pd.Series) -> dict:
    return {
        'n': len(series.dropna()),
        'mean': series.mean(),
        'median': series.median(),
        'std': series.std(),
        'skewness': series.skew(),
        'kurtosis': series.kurtosis(),
        'q1': series.quantile(0.25),
        'q3': series.quantile(0.75),
        'iqr': series.quantile(0.75) - series.quantile(0.25),
    }

# Hypothesis testing — t-test
def ab_test(control: np.ndarray, treatment: np.ndarray, alpha: float = 0.05) -> dict:
    t_stat, p_value = stats.ttest_ind(control, treatment)
    effect_size = (treatment.mean() - control.mean()) / np.sqrt(
        ((len(control) - 1) * control.std()**2 + (len(treatment) - 1) * treatment.std()**2)
        / (len(control) + len(treatment) - 2)
    )
    return {
        't_statistic': t_stat,
        'p_value': p_value,
        'significant': p_value < alpha,
        'cohens_d': effect_size,
        'control_mean': control.mean(),
        'treatment_mean': treatment.mean(),
        'lift_pct': 100 * (treatment.mean() - control.mean()) / control.mean(),
    }

# Outlier detection — Z-score method
def detect_outliers_zscore(series: pd.Series, threshold: float = 3.0) -> pd.Series:
    z_scores = np.abs(stats.zscore(series.dropna()))
    return series[z_scores > threshold]

# Correlation matrix
def correlation_analysis(df: pd.DataFrame, method: str = 'spearman') -> pd.DataFrame:
    corr = df.select_dtypes(include=np.number).corr(method=method)
    return corr
```

### Методология валидации данных

```python
import great_expectations as gx

# Define expectations
context = gx.get_context()
suite = context.add_expectation_suite('orders.critical')

# Validate
validator = context.get_validator(
    datasource_name='my_db',
    data_asset_name='orders',
    expectation_suite=suite,
)

# Required validations for any dataset
validator.expect_column_to_exist('order_id')
validator.expect_column_values_to_not_be_null('order_id')
validator.expect_column_values_to_be_unique('order_id')
validator.expect_column_values_to_be_between('amount', 0, 100_000)
validator.expect_column_values_to_be_in_set('status', ['pending', 'completed', 'cancelled'])
validator.expect_column_values_to_match_regex('email', r'^[^@]+@[^@]+\.[^@]+$')

results = validator.validate()
assert results.success, f"Validation failed: {results}"
```

**Чеклист валидации данных:**
- [ ] Схема соответствует ожидаемой структуре (имена колонок, типы)
- [ ] Нет NULL в обязательных колонках
- [ ] Уникальность первичного ключа
- [ ] Ссылочная целостность внешнего ключа
- [ ] Бизнес-правила (положительные суммы, допустимые статусы)
- [ ] Количество строк в ожидаемом диапазоне
- [ ] Нет дублирующихся записей
- [ ] Темпоральная согласованность (end_date > start_date)
- [ ] Проверка ошибки выжившего (survivorship bias) (не упускаете ли вы неактивные записи?)

---

## Раздел 11: Чейнджлог и документация

### Когда использовать этот раздел
- Подготовка release notes для новой версии
- Создание еженедельных сводок обновлений продукта
- Генерация README или документации API

### Генерация чейнджлога из Git

**Базовое использование:**
```
Create a changelog from commits since last release
Generate changelog for all commits from the past week
Create release notes for version 2.5.0
Create a changelog for commits between March 1 and March 15
```

**С кастомными гайдлайнами:**
```
Create a changelog for commits since v2.4.0, using my changelog
guidelines from CHANGELOG_STYLE.md
```

**Рабочий процесс:**
1. Проверьте файлы зависимостей на точные версии (`package.json`, `requirements.txt`)
2. Найдите чейнджлоги библиотек для любых упомянутых обновлений
3. Переведите технические коммиты на язык, обращённый к пользователю
4. Отфильтруйте внутренние коммиты (рефакторинг, CI, тесты)
5. Сгруппируйте по категориям: Фичи, Улучшения, Исправления, Безопасность

**Формат вывода:**
```markdown
# Updates — Week of March 3, 2026

## New Features

- **Team Workspaces**: Create separate workspaces for different projects.
  Invite team members and keep everything organized.

- **Keyboard Shortcuts**: Press ? to see all available shortcuts.
  Navigate faster without touching your mouse.

## Improvements

- **Faster Sync**: Files now sync 2x faster across devices
- **Better Search**: Search now includes file contents, not just titles

## Bug Fixes

- Fixed issue where large images would not upload
- Resolved timezone confusion in scheduled posts
- Corrected notification badge count

## Security

- Updated dependency to resolve CVE-2026-1234 (high severity)
```

**Категории коммитов:**
| Префикс Conventional Commit | Раздел чейнджлога |
|---------------------------|-------------------|
| `feat:`, `feature:` | New Features |
| `perf:`, `improve:` | Improvements |
| `fix:`, `bugfix:` | Bug Fixes |
| `security:`, `vuln:` | Security |
| `break:`, `BREAKING:` | Breaking Changes |
| `refactor:`, `test:`, `ci:` | (отфильтровано) |

### Генерация README

**Обязательные разделы README:**
```markdown
# Project Name

One-line description of what this does.

## Quick Start

```bash
npm install
cp .env.example .env
npm run dev
```

## Features

- Feature 1 with brief description
- Feature 2 with brief description

## Architecture

Brief description + link to architecture docs

## Development

Prerequisites, setup instructions, commands

## Testing

How to run tests, coverage requirements

## Deployment

How to deploy to production

## Contributing

Branch conventions, PR process, code standards

## License

MIT / Apache 2.0 / etc.
```

### Документация API

```typescript
/**
 * @openapi
 * /users/{id}:
 *   get:
 *     summary: Get user by ID
 *     tags: [Users]
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *         description: The user's unique identifier
 *     responses:
 *       200:
 *         description: User found
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/User'
 *       404:
 *         description: User not found
 *       401:
 *         description: Authentication required
 */
app.get('/users/:id', authenticate, async (req, res) => {
  // ...
});
```

**Лучшие практики документации:**
- [ ] У каждой публичной функции/метода есть docstring
- [ ] Все параметры задокументированы с типами и ограничениями
- [ ] Описаны возвращаемые значения и случаи ошибок
- [ ] Приведены примеры кода для сложных функций
- [ ] CHANGELOG.md обновляется с каждым релизом
- [ ] `CONTRIBUTING.md` описывает рабочий процесс разработки
- [ ] Записи архитектурных решений (ADR) в `docs/adr/`
- [ ] Раннбуки операционных задач в `docs/runbooks/`

---

## Раздел 12: Уникальные возможности Perplexity Computer

Эти возможности эксклюзивны для Perplexity Computer и дополняют инженерные рабочие процессы выше.

### Живой веб-ресёрч для инженерных решений

При оценке библиотек, фреймворков или пакетов Perplexity Computer может получать информацию в реальном времени, выходящую за пределы любого обучающего отсечения:

**Сценарии использования:**
- «Какая последняя стабильная версия Next.js и что изменилось?»
- «Есть ли известные проблемы безопасности с lodash 4.17.20?»
- «Как Bun сравнивается с Node.js для нашего сценария API в 2026 году?»
- «Что официальная документация Prisma говорит о пулинге соединений с бессерверными функциями?»
- «Найди ломающие изменения в React 19 перед тем, как я обновлюсь»

Это заполняет пробел, где у скиллов Claude Code есть даты обучающего отсечения — Perplexity может проверять документацию пакетов, чейнджлоги, CVE и ответы Stack Overflow в реальном времени.

### Деплой сайтов за минуты

Perplexity Computer может собирать и развёртывать полноценные сайты без отдельной настройки инфраструктуры:

**Рабочий процесс:**
1. Опишите требования к вашему сайту
2. Perplexity генерирует полный сайт (HTML/CSS/JS или React)
3. Сайт развёрнут и доступен по ссылке для шеринга
4. Итерируйте дизайн с помощью обновлений при содействии ИИ

**Лучше всего для:**
- Лендингов, сайтов документации, маркетинговых микросайтов
- Деплоев прототипов/MVP для пользовательского тестирования
- Статических сайтов из markdown-контента
- Внутренних инструментов и дашбордов

### Генерация изображений ИИ для UI-мокапов

Генерируйте визуальные ассеты прямо в вашем инженерном рабочем процессе:

**Сценарии использования:**
- «Сгенерируй hero-баннер для лендинга продукта»
- «Создай плейсхолдер для аватаров пользователей (512x512, стиль профессионального портрета)»
- «Спроектируй иконку для функции уведомлений»
- «Сгенерируй мокап того, как мог бы выглядеть дашборд, прежде чем я закодирую его»

**Поддерживаемые соотношения сторон:** 1:1, 16:9, 9:16, 4:3, 3:4

### 400+ интеграций приложений

Perplexity Computer интегрируется с внешними сервисами, которые ваш инженерный рабочий процесс уже использует:

| Категория | Примеры |
|----------|---------|
| Контроль версий | GitHub, GitLab, Bitbucket |
| Управление проектами | Jira, Linear, Asana, Trello |
| Коммуникации | Slack, Microsoft Teams |
| Облачные платформы | AWS, GCP, Azure |
| Базы данных | Supabase, PlanetScale, Neon |
| Мониторинг | Datadog, PagerDuty, Grafana |
| CI/CD | GitHub Actions, CircleCI, Vercel |
| Аналитика | Mixpanel, Amplitude, PostHog |

### Мониторинг деплоев по расписанию

Настройте автоматизированные проверки, выполняющиеся по расписанию:

**Примеры:**
- Мониторинг URL на доступность каждые 5 минут
- Проверка, что деплой успешен после прогона CI
- Оповещение, если время ответа API превышает 500ms
- Проверка, что резервное копирование БД завершилось успешно

### Информация о пакетах и библиотеках в реальном времени

В отличие от статичных обучающих данных, Perplexity может искать:
- Последние версии пакетов на npm, PyPI, crates.io
- Известные CVE и рекомендации по безопасности
- Руководства по миграции между мажорными версиями
- Сообщённые сообществом проблемы и обходные пути
- Сравнения бенчмарков, опубликованные после обучающего отсечения

### Исследование сравнения технологий

Для архитектурных решений Perplexity может синтезировать актуальные знания сообщества:

**Примеры:**
- «Сравни Prisma и Drizzle для нашего стека Next.js + PostgreSQL на 2026 год»
- «Что разработчики говорят о переходе с REST на tRPC?»
- «Остаётся ли Redis рекомендуемым выбором для ограничения скорости, или есть варианты лучше?»
- «Каковы текущие показатели продакшен-адопшена Bun против Node.js?»

---

## Краткий справочник: когда какой раздел скилла использовать

| Задача | Раздел | Ключевые команды/паттерны |
|------|---------|----------------------|
| Спроектировать новую систему | §2 Архитектура | `project_architect.py`, шаблон ADR |
| Собрать React-компонент | §3 Фронтенд | `component_generator.py`, паттерны |
| Спроектировать REST API | §4 Бэкенд | `api_scaffolder.py`, OpenAPI |
| Стартовать новый фулстек-проект | §5 Фулстек | `project_scaffolder.py` |
| Написать тесты для существующего кода | §6 Тестирование | `test_suite_generator.py`, цикл TDD |
| Отладить падающий тест/баг | §7 Отладка | Четырёхфазный анализ первопричины |
| Отревьюить pull-реквест | §7 Код-ревью | `pr_analyzer.py`, чеклист |
| Настроить CI/CD | §8 DevOps | Шаблоны GitHub Actions |
| Аудит безопасности | §9 Безопасность | `security_scanner.py`, чеклист OWASP |
| Написать сложный SQL | §10 Данные | Диалект-специфичные паттерны |
| Визуализировать данные | §10 Данные | Руководство по выбору типа графика |
| Написать release notes | §11 Чейнджлог | Рабочий процесс «git → чейнджлог» |
| Найти актуальную документацию библиотеки | §12 Perplexity | Живой веб-ресёрч |
| Развернуть сайт | §12 Perplexity | Деплой через Perplexity |

---

## Рабочие процессы комбинирования скиллов

### Процесс A: старт нового SaaS-продукта

1. **§2 Архитектура** — создайте диаграмму системы + ADR для ключевых решений
2. **§5 Фулстек** — заскаффолдьте проект через `project_scaffolder.py nextjs my-saas`
3. **§8 DevOps** — сгенерируйте CI/CD-пайплайн с гейтами безопасности
4. **§9 Безопасность** — запустите начальный скан безопасности, установите базовую линию соответствия
5. **§6 Тестирование** — настройте Jest + Playwright, установите цель покрытия 80%
6. **§12 Perplexity** — исследуйте актуальные версии библиотек и разверните предпросмотр

### Процесс B: исправление бага в продакшене

1. **§7 Отладка** — Фаза 1, расследование первопричины (читать ошибки, воспроизвести)
2. **§6 Тестирование** — напишите падающий тест, воспроизводящий баг
3. **§7 Отладка** — реализуйте единственное исправление, проверьте, что тесты проходят
4. **§8 DevOps** — задеплойте через CI/CD-пайплайн, мониторьте

### Процесс C: аудит безопасности перед запуском

1. **§9 Безопасность** — `security_scanner.py` + `vulnerability_assessor.py`
2. **§9 Безопасность** — `compliance_checker.py --framework soc2`
3. **§9 Безопасность** — модель угроз STRIDE для критических компонентов
4. **§7 Код-ревью** — `review_report_generator.py` для всего нового кода
5. **§12 Perplexity** — исследуйте любые CVE в зависимостях, появившиеся после обучения

### Процесс D: пайплайн анализа данных

1. **§10 Данные** — профилируйте датасет на проблемы качества
2. **§10 Данные** — напишите SQL-запросы (с учётом диалекта)
3. **§10 Данные** — провалидируйте данные с Great Expectations
4. **§10 Данные** — визуализируйте результаты подходящими типами графиков
5. **§6 Тестирование** — напишите тесты для логики трансформации данных
6. **§11 Документация** — задокументируйте методологию анализа и находки
