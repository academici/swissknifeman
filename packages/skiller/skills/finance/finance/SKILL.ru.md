> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: finance-super-skill
bucket: finance
version: 1.0.0
description: Finance and accounting: financial statements, journal entries, reconciliation, close management, audit support, variance analysis, market data, investment research, ML forecasting, invoice processing. Use for financial reporting, month-end close, audit prep, variance analysis, market research, investment thesis, or finance data work.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Супер-скилл «Финансы и бухучёт» — навигатор

Тонкий навигатор над вендоренным **get-zeked/finance-super-skill**. Полный справочник
(13 разделов + 2 приложения: шаблоны, чек-листы, код) — в
[`references/full.md`](references/full.md). **Открывай точечно под конкретный вопрос —
переходи к нужному разделу по карте, не грузи файл целиком.**

## Карта разделов (`references/full.md`)

| Задача | Раздел |
|:--|:--|
| Обзор возможностей: какой суб-скилл что покрывает | §0 Gap Analysis |
| Шаблоны IS/BS/CF, коэффициенты, DCF, отраслевые KPI | §1 Financial Statements |
| Дебет/кредит, шаблоны проводок, чек-лист начислений | §2 Journal Entries |
| Банковские/GL/внутригрупповые сверки, обоснование баланса | §3 Reconciliation |
| Календарь закрытия, трекер задач, зависимости | §4 Month-End Close |
| Waterfall, комментарий по драйверам отклонений | §5 Variance Analysis |
| PBC-списки, тестирование контролей, выборки, SOX | §6 Audit Support |
| Котировки, история, данные SEC, инвестиционный тезис | §7 Markets & Research |
| ETL/ELT-пайплайны, модели хранилища, dbt/Airflow | §8 Data Engineering |
| Прогнозирование, поиск аномалий, ML-модели | §9 ML & Forecasting |
| Извлечение инвойсов, нейминг, таксономии папок | §10 Invoices & Documents |
| Инструментарий только Perplexity Computer | §11 Unique Capabilities |
| Быстрый роутер «какой раздел мне нужен» | §12 Quick-Start Guide |
| План счетов, нормальные сальдо | Приложение A |
| Аббревиатуры (GAAP, EBITDA, DSO, …) | Приложение B |

## Сопровождение

Отслеживается по апстриму (`strategy: notify`, `body_path: references/full.md`): SKILL.md —
рукописный навигатор, скрипты его не перезаписывают; при дрейфе апстрима
(`scripts/update-upstreams.sh --check`) изменения переносятся в `references/full.md` вручную.
