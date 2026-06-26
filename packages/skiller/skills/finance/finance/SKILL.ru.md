> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: finance-super-skill
bucket: finance
version: 1.0.0
description: Comprehensive finance and accounting skill merging Perplexity Computer's 7 finance skills plus investment research with Claude Code's data science, data engineering, financial analysis, and invoice management skills. Covers financial statements, journal entries, reconciliation, close management, audit support, variance analysis, market data, investment research, data pipelines, ML forecasting, and invoice processing. Use for financial reporting, month-end close, audit prep, variance analysis, market research, investment thesis, data engineering, or any finance and accounting work.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Супер-скилл «Финансы и бухучёт»

Единый справочник, объединяющий 8 финансово-инвестиционных скиллов Perplexity Computer со скиллами Claude Code: Financial Analyst, Senior Data Engineer, Senior Data Scientist, Senior ML Engineer и Invoice Organizer. Покрывает весь спектр — от журнальных проводок и закрытия месяца до DCF-оценки, ETL-пайплайнов и прогнозирования на базе ML.

---

## 0. Анализ пробелов: финансовые скиллы Perplexity Computer против Claude Code

| Возможность | Perplexity Computer | Claude Code | Совокупное покрытие |
|---|---|---|---|
| Финансовая отчётность (ОПУ/баланс/ОДДС) | finance-financial-statements | financial-analyst | Полный GAAP + анализ коэффициентов |
| Журнальные проводки и начисления | finance-journal-entry-prep | — | Дебеты/кредиты, шаблоны |
| Сверка счетов | finance-reconciliation | — | ГК, банк, внутригрупповые |
| Закрытие месяца | finance-close-management | — | Календарь, зависимости, отслеживание |
| Анализ отклонений | finance-variance-analysis | financial-analyst | Водопад + нарратив по драйверам |
| Аудит и соответствие SOX | finance-audit-support | — | Тестирование контролей, выборка |
| Рыночные данные и цены | finance-markets | — | Реал-тайм, исторические, SEC |
| Инвестиционный анализ | investment-research | financial-analyst (DCF) | Тезис, аналоги, известные инвесторы |
| ETL / дата-пайплайны | — | senior-data-engineer | Airflow, dbt, Spark, Kafka |
| Качество данных и контракты | — | senior-data-engineer | Great Expectations, dbt-тесты |
| Статистическое моделирование | — | senior-data-scientist | A/B-тесты, временные ряды, ML |
| ML-прогнозирование и MLOps | — | senior-ml-engineer | Прогноз выручки, детекция аномалий |
| Управление счетами и документами | — | invoice-organizer | Извлечение из PDF, экспорт в CSV |
| Финансы с помощью LLM | — | senior-ml-engineer | RAG по финансовым документам |

**Ключевые пробелы, закрываемые объединением обоих источников:**
- Скиллы Perplexity глубоко покрывают бухгалтерские процессы; Claude Code добавляет дата-инфраструктуру.
- Claude Code покрывает ML/инжиниринг; Perplexity добавляет рыночные данные в реальном времени и отчётность SEC.
- Ни один источник по отдельности не покрывает автоматизацию счетов + финансовое закрытие + рыночный анализ вместе.

---

## 1. Финансовая отчётность и составление отчётов

### Когда использовать
- Подготовка отчёта о прибылях и убытках, балансов или отчётов о движении денежных средств
- Сравнения «период к периоду» (квартал к кварталу, год к году)
- Расчёт финансовых коэффициентов для управленческой или инвесторской отчётности
- Построение DCF-модели или анализа сопоставимых компаний
- Отраслевая отчётность (SaaS, ритейл, производство, здравоохранение)

### Шаблоны финансовой отчётности по GAAP

#### Шаблон отчёта о прибылях и убытках
```
[Company Name]
Consolidated Statements of Operations
For the [Quarter/Year] Ended [Date]
(in thousands, except per share data)

                                    Current Period    Prior Period    Change $    Change %
Revenue
  Product Revenue                   $             $             $           %
  Service Revenue                   $             $             $           %
  Total Revenue                     $             $             $           %

Cost of Revenue
  Cost of Products                  $             $             $           %
  Cost of Services                  $             $             $           %
  Total Cost of Revenue             $             $             $           %

Gross Profit                        $             $             $           %
Gross Margin                                    %               %

Operating Expenses
  Research & Development            $             $             $           %
  Sales & Marketing                 $             $             $           %
  General & Administrative          $             $             $           %
  Total Operating Expenses          $             $             $           %

Operating Income (Loss)             $             $             $           %
Operating Margin                               %               %

Other Income (Expense)
  Interest Income                   $             $
  Interest Expense                  ($            ) ($            )
  Other, net                        $             $
  Total Other Income (Expense)      $             $

Income Before Income Taxes          $             $
Income Tax Expense (Benefit)        $             $
Effective Tax Rate                             %               %

Net Income (Loss)                   $             $             $           %
Net Margin                                     %               %

Earnings Per Share
  Basic EPS                         $             $
  Diluted EPS                       $             $
  Weighted Avg Shares (Basic)
  Weighted Avg Shares (Diluted)
```

#### Шаблон баланса
```
[Company Name]
Consolidated Balance Sheets
As of [Date] and [Prior Period Date]
(in thousands)

                                    Current         Prior Period
ASSETS
Current Assets
  Cash and Cash Equivalents         $               $
  Short-term Investments            $               $
  Accounts Receivable, net          $               $
  Inventories                       $               $
  Prepaid Expenses                  $               $
  Other Current Assets              $               $
  Total Current Assets              $               $

Non-Current Assets
  Property, Plant & Equipment, net  $               $
  Right-of-Use Assets               $               $
  Goodwill                          $               $
  Intangible Assets, net            $               $
  Deferred Tax Assets               $               $
  Other Non-Current Assets          $               $
  Total Non-Current Assets          $               $

TOTAL ASSETS                        $               $

LIABILITIES & STOCKHOLDERS' EQUITY
Current Liabilities
  Accounts Payable                  $               $
  Accrued Liabilities               $               $
  Deferred Revenue (Current)        $               $
  Short-term Debt                   $               $
  Other Current Liabilities         $               $
  Total Current Liabilities         $               $

Non-Current Liabilities
  Long-term Debt                    $               $
  Operating Lease Liabilities       $               $
  Deferred Revenue (LT)             $               $
  Deferred Tax Liabilities          $               $
  Other Non-Current Liabilities     $               $
  Total Non-Current Liabilities     $               $

TOTAL LIABILITIES                   $               $

Stockholders' Equity
  Common Stock                      $               $
  Additional Paid-in Capital        $               $
  Retained Earnings (Deficit)       $               $
  Accumulated OCI                   $               $
  Treasury Stock                    ($              ) ($              )
  Total Stockholders' Equity        $               $

TOTAL LIABILITIES & EQUITY         $               $
```

#### Шаблон отчёта о движении денежных средств
```
[Company Name]
Consolidated Statements of Cash Flows
For the [Period] Ended [Date]
(in thousands)

                                            Current Period    Prior Period
OPERATING ACTIVITIES
Net Income (Loss)                           $                 $
Adjustments to reconcile net income:
  Depreciation & Amortization              $                 $
  Stock-Based Compensation                 $                 $
  Deferred Income Taxes                    $                 $
  Changes in operating assets/liabilities:
    Accounts Receivable                    ($                ) ($                )
    Inventories                            ($                ) ($                )
    Prepaid Expenses & Other               ($                ) ($                )
    Accounts Payable                       $                 $
    Accrued Liabilities                    $                 $
    Deferred Revenue                       $                 $
Net Cash from Operating Activities         $                 $

INVESTING ACTIVITIES
  Capital Expenditures                     ($                ) ($                )
  Acquisitions, net of cash                ($                ) ($                )
  Purchases of Investments                 ($                ) ($                )
  Proceeds from Sales of Investments       $                 $
Net Cash used in Investing Activities      ($                ) ($                )

FINANCING ACTIVITIES
  Proceeds from Stock Issuance             $                 $
  Repurchase of Common Stock               ($                ) ($                )
  Proceeds from Debt Issuance              $                 $
  Repayment of Debt                        ($                ) ($                )
  Payment of Dividends                     ($                ) ($                )
Net Cash from (used in) Financing          $                 $

Net Increase (Decrease) in Cash            $                 $
Cash at Beginning of Period                $                 $
Cash at End of Period                      $                 $

Free Cash Flow = Operating CF - CapEx      $                 $
```

### Справочник финансовых коэффициентов

#### Коэффициенты прибыльности
| Коэффициент | Формула | Бенчмарк (среднее по S&P 500) |
|---|---|---|
| Валовая маржа (Gross Margin) | Gross Profit / Revenue | ~50% (сильно зависит от отрасли) |
| Операционная маржа (Operating Margin) | Operating Income / Revenue | ~15% |
| Чистая маржа (Net Margin) | Net Income / Revenue | ~10% |
| ROE | Net Income / Avg Shareholders' Equity | ~15% |
| ROA | Net Income / Avg Total Assets | ~6% |
| ROIC | NOPAT / Invested Capital | Сравнивать с WACC |
| Маржа EBITDA (EBITDA Margin) | EBITDA / Revenue | ~20% |

#### Коэффициенты ликвидности
| Коэффициент | Формула | Здоровый диапазон |
|---|---|---|
| Текущая ликвидность (Current Ratio) | Current Assets / Current Liabilities | 1.5x–3.0x |
| Быстрая ликвидность (Quick Ratio) | (Cash + AR) / Current Liabilities | 1.0x–2.0x |
| Денежная ликвидность (Cash Ratio) | Cash / Current Liabilities | > 0.5x |
| Коэффициент операционного CF (Operating CF Ratio) | Operating CF / Current Liabilities | > 1.0x |

#### Коэффициенты финансового рычага
| Коэффициент | Формула | Здоровый диапазон |
|---|---|---|
| Долг к собственному капиталу (Debt-to-Equity) | Total Debt / Equity | < 2.0x |
| Чистый долг / EBITDA (Net Debt / EBITDA) | (Total Debt − Cash) / EBITDA | < 3.0x |
| Покрытие процентов (Interest Coverage) | EBIT / Interest Expense | > 3.0x |
| Покрытие обслуживания долга (Debt Service Coverage) | Net Operating Income / Debt Service | > 1.25x |

#### Коэффициенты эффективности
| Коэффициент | Формула | Примечание |
|---|---|---|
| Оборачиваемость активов (Asset Turnover) | Revenue / Avg Total Assets | Выше = эффективнее |
| Оборачиваемость запасов (Inventory Turnover) | COGS / Avg Inventory | Выше = быстрее продаются |
| Период оборота дебиторки (Days Sales Outstanding) | AR / (Revenue / 365) | Ниже = быстрее собираемость |
| Период оборота кредиторки (Days Payable Outstanding) | AP / (COGS / 365) | Выше = лучше управление деньгами |
| Денежный цикл (Cash Conversion Cycle) | DIO + DSO − DPO | Ниже = лучше оборотный капитал |

#### Оценочные мультипликаторы
| Мультипликатор | Формула | Когда использовать |
|---|---|---|
| P/E | Share Price / EPS | Прибыльные компании |
| EV/EBITDA | Enterprise Value / EBITDA | Сравнение при разной структуре капитала |
| EV/Revenue | Enterprise Value / Revenue | Быстрорастущие, до выхода в прибыль |
| P/B | Share Price / Book Value per Share | Банки, капиталоёмкие бизнесы |
| P/FCF | Share Price / FCF per Share | Оценка с фокусом на денежный поток |
| PEG | P/E / Earnings Growth Rate | Оценка с поправкой на рост |

### Рабочий процесс DCF-оценки

```
Step 1: Forecast Free Cash Flow (5–10 years)
  FCF = EBIT × (1 - Tax Rate) + D&A − CapEx − ΔNWC

Step 2: Calculate WACC
  WACC = (E/V) × Ke + (D/V) × Kd × (1 - Tax Rate)
  Ke = Rf + β × (Rm − Rf)           [CAPM]

Step 3: Terminal Value
  Perpetuity Growth: TV = FCF(n+1) / (WACC − g)
  Exit Multiple:     TV = EBITDA(n) × EV/EBITDA Multiple

Step 4: Discount to Present Value
  PV = Σ FCFt / (1 + WACC)^t  +  TV / (1 + WACC)^n

Step 5: Bridge to Equity Value
  Enterprise Value = PV of FCFs + PV of Terminal Value
  Equity Value = Enterprise Value − Net Debt + Cash
  Share Price = Equity Value / Diluted Shares Outstanding

Step 6: Sensitivity Analysis
  Vary WACC ±1% and Terminal Growth ±0.5%
  Create 5×5 table of implied share prices
```

### Отраслевые KPI

| Отрасль | Ключевые метрики |
|---|---|
| SaaS | ARR, MRR, Churn Rate, Net Revenue Retention, CAC, LTV, CAC Payback |
| Ритейл | Same-Store Sales Growth, Revenue/Sq Ft, Inventory Turnover, Shrink % |
| Производство | Capacity Utilization, Gross Margin by Product Line, CapEx/Revenue |
| Финансовые услуги | NIM, Efficiency Ratio, Tier 1 Capital Ratio, ROA, NPL Ratio |
| Здравоохранение | Revenue/Patient, Payer Mix, Days in A/R, Operating Margin |
| E-Commerce | GMV, Take Rate, Conversion Rate, Average Order Value, CAC |

---

## 2. Журнальные проводки и обработка транзакций

### Когда использовать
- Запись любой бухгалтерской операции в главную книгу
- Начисления и сторно на конец месяца
- Амортизация расходов будущих периодов, амортизация основных средств
- Зарплатные проводки
- Признание выручки по ASC 606
- Корректировки доходов будущих периодов
- Учёт аренды по ASC 842

### Основы журнальных проводок

**Правила:**
- Каждая проводка должна балансироваться: сумма дебетов = сумме кредитов
- Указывайте номер счёта, описание и ссылку на подтверждающий документ
- Включайте чёткий мемо, объясняющий деловую цель
- Получайте необходимые согласования до проведения

**Нормальные сальдо:**
| Тип счёта | Нормальное сальдо | Увеличивается на | Уменьшается на |
|---|---|---|---|
| Активы | Дебет | Дебет | Кредит |
| Обязательства | Кредит | Кредит | Дебет |
| Капитал | Кредит | Кредит | Дебет |
| Выручка | Кредит | Кредит | Дебет |
| Расходы | Дебет | Дебет | Кредит |

### Шаблоны журнальных проводок

#### Начисление на конец месяца (расход)
```
Date: [Last day of month]
Reference: JE-[YYYY-MM]-[###]
Prepared by: [Name]    Approved by: [Name]
Description: Accrue [vendor/service] for [month] services

  Account                    Account #    Debit        Credit
  [Expense Account]          [XXXXX]      $X,XXX.XX
    Accrued Liabilities      [XXXXX]                   $X,XXX.XX

Supporting: Vendor estimate / Contract / Invoice received [date]
Reversal: Auto-reverse [first day of next month]
```

#### Амортизация расходов будущих периодов
```
Date: [Last day of month]
Reference: JE-[YYYY-MM]-[###]
Description: Amortize prepaid [insurance/software/etc.] – Month [X] of [Y]

  Account                    Account #    Debit        Credit
  [Expense Account]          [XXXXX]      $X,XXX.XX
    Prepaid Expenses         [XXXXX]                   $X,XXX.XX

Original prepaid amount: $[Total]
Monthly amortization: $[Amount] = $[Total] / [Months]
Remaining balance after entry: $[Remaining]
Supporting: Original invoice [date], prepaid schedule
```

#### Амортизация основных средств
```
Date: [Last day of month]
Reference: JE-[YYYY-MM]-[###]
Description: Record depreciation – [Asset Class] – [Month Year]

  Account                    Account #    Debit        Credit
  Depreciation Expense       [XXXXX]      $X,XXX.XX
    Accumulated Depreciation [XXXXX]                   $X,XXX.XX

Asset: [Asset Name / FA #]
Acquisition cost: $[Cost]     Salvage value: $[Value]
Useful life: [X] years         Method: [Straight-line / DDB / Units]
Monthly depreciation: $[Cost - Salvage] / ([Life] × 12)
Supporting: Fixed asset register
```

#### Зарплатная проводка
```
Date: [Pay date]
Reference: JE-[YYYY-MM]-[###]
Description: Payroll – Period ending [date]

  Account                    Account #    Debit        Credit
  Salaries & Wages Expense   [XXXXX]      $XX,XXX.XX
  Payroll Tax Expense        [XXXXX]      $X,XXX.XX
    Salaries Payable                                   $XX,XXX.XX
    Federal Income Tax W/H                             $X,XXX.XX
    State Income Tax W/H                               $X,XXX.XX
    FICA – Employee (SS)                               $X,XXX.XX
    FICA – Employee (Medicare)                         $X,XXX.XX
    FICA – Employer (SS)                               $X,XXX.XX
    FICA – Employer (Medicare)                         $X,XXX.XX
    401(k) Payable                                     $X,XXX.XX
    Health Insurance Payable                           $X,XXX.XX

Supporting: Payroll register, HR approval
```

#### Признание выручки (ASC 606) — в момент времени
```
Date: [Revenue recognition date]
Reference: JE-[YYYY-MM]-[###]
Description: Recognize revenue – [Customer] – [Contract/Order #]

  Account                    Account #    Debit        Credit
  Accounts Receivable        [XXXXX]      $X,XXX.XX
    Revenue                  [XXXXX]                   $X,XXX.XX

5-step model confirmation:
  Step 1 – Contract identified: [Yes/Contract #]
  Step 2 – Performance obligations: [Description]
  Step 3 – Transaction price: $[Amount]
  Step 4 – Allocation: [100% to single PO / Split: X%/Y%]
  Step 5 – Satisfied: [Date/Event that triggered recognition]
Supporting: Sales order, delivery confirmation, contract
```

#### Признание доходов будущих периодов (подписка)
```
Date: [Date of recognition]
Reference: JE-[YYYY-MM]-[###]
Description: Recognize deferred revenue – [Customer] – Month [X] of [Y]

  Account                    Account #    Debit        Credit
  Deferred Revenue           [XXXXX]      $X,XXX.XX
    Revenue                  [XXXXX]                   $X,XXX.XX

Original invoice: $[Total]     Contract term: [X] months
Monthly recognition: $[Total] / [Months]
Remaining deferred balance: $[Amount]
Supporting: Customer contract, billing schedule
```

#### Внутригрупповое элиминирование
```
Date: [Consolidation date]
Reference: JE-CONSOL-[YYYY-MM]-[###]
Description: Eliminate intercompany [sale/loan/dividend] – [Sub A] to [Sub B]

  Elimination Entry – Selling Entity
  Account                    Account #    Debit        Credit
  Intercompany Revenue       [XXXXX]      $X,XXX.XX
    Intercompany Receivable  [XXXXX]                   $X,XXX.XX

  Elimination Entry – Buying Entity
  Account                    Account #    Debit        Credit
  Intercompany Payable       [XXXXX]      $X,XXX.XX
    Intercompany Expense     [XXXXX]                   $X,XXX.XX

Confirmation: Both legs balance to zero on consolidation
Supporting: Intercompany agreement, transfer pricing documentation
```

### Типовой чеклист начислений (на конец месяца)
```
□ Payroll accrual (days worked but not yet paid)
□ Benefits accrual (health, dental, 401k employer match)
□ Bonus accrual (% of annual target × months elapsed)
□ Commission accrual (sales team earned but unpaid)
□ Vendor invoice accruals (services received, invoice not yet in)
□ Utility accruals (service period vs billing period)
□ Interest accrual (on outstanding debt)
□ Depreciation (fixed assets)
□ Amortization (intangibles, prepaid schedules)
□ Deferred revenue recognition (subscription, milestone)
□ Revenue accruals (shipped/delivered but not yet invoiced)
□ Income tax provision (current + deferred)
□ Lease ROU amortization (ASC 842)
```

---

## 3. Сверка счетов

### Когда использовать
- Ежемесячная банковская сверка
- Сверка главной книги с субреестрами (AR, AP, основные средства)
- Сверка внутригрупповых сальдо
- Подтверждение остатков по балансовым счетам
- Подготовка к аудиту

### Шаблон банковской сверки
```
[Company Name]
Bank Reconciliation – [Bank / Account #]
As of [Date]

BOOK BALANCE
  Balance per general ledger                          $XX,XXX.XX
  Add: Deposits in transit
    [Date] Deposit – [Description]                    $X,XXX.XX
    [Date] Deposit – [Description]                    $X,XXX.XX
  Less: Outstanding checks
    Check #[####] – [Payee] – [Date]                 ($X,XXX.XX)
    Check #[####] – [Payee] – [Date]                 ($X,XXX.XX)
  Add/Less: Book errors
    [Describe error and correction]                   $X,XXX.XX
ADJUSTED BOOK BALANCE                                $XX,XXX.XX

BANK BALANCE
  Balance per bank statement                         $XX,XXX.XX
  Add: Deposits in transit (same list above)         $X,XXX.XX
  Less: Outstanding checks (same list above)        ($X,XXX.XX)
  Add/Less: Bank errors
    [Describe error and correction]                   $X,XXX.XX
ADJUSTED BANK BALANCE                               $XX,XXX.XX

RECONCILING DIFFERENCE                               $       —

Prepared by: ____________   Date: ____________
Reviewed by: ____________   Date: ____________
```

### Сверка главной книги с субреестром

**Сверка дебиторской задолженности:**
```
[Company Name]
AR Reconciliation
As of [Date]

  GL Balance – Accounts Receivable                   $XX,XXX.XX

  AR Subledger by Customer:
  Customer                   Invoice #    Amount
  [Customer A]               [INV-###]    $X,XXX.XX
  [Customer B]               [INV-###]    $X,XXX.XX
  ...
  Total AR Subledger                                  $XX,XXX.XX

  DIFFERENCE                                         $       —

  Items in GL not in Subledger:
  [Description]                                      $X,XXX.XX

  Items in Subledger not in GL:
  [Description]                                      $X,XXX.XX

  Resolution / JE Required:
  [Describe correcting entry]
```

### Категории сверочных расхождений
| Категория | Описание | Решение |
|---|---|---|
| Временны́е разницы | Транзакции учтены в разных периодах | Проверить последующее закрытие; без проводки, если это законная разница во времени |
| Ошибки банка | Банк провёл неверную сумму | Связаться с банком; скорректировать банковскую сторону сверки |
| Ошибки учёта | Ошибка ввода, неверный счёт | Подготовить корректирующую проводку |
| Неучтённые позиции | Чеки NSF, банковские комиссии, проценты | Отразить в ГК согласно банковской выписке |
| Дублирующие проводки | Одна транзакция проведена дважды | Аннулировать/сторнировать дубль |
| Пропущенные транзакции | Корректная транзакция не учтена | Отразить с подтверждающими документами |

### Чеклист подтверждения балансовых счетов
```
For each balance sheet account:
□ Balance agrees to GL trial balance
□ Activity roll (beginning balance + additions - reductions = ending)
□ All items have valid supporting documentation
□ Aging analysis for AR / AP (identify items > 90 days)
□ Subsequent clearing confirmed for significant items
□ Reconciling items < materiality threshold or explained
□ Prior period items resolved
□ Approvals documented
```

---

## 4. Управление закрытием месяца

### Когда использовать
- Планирование календаря ежемесячного или квартального закрытия
- Отслеживание статуса задач закрытия и ответственных
- Выявление блокеров и зависимостей
- Коммуникация статуса закрытия руководству

### Шаблон календаря закрытия (закрытие за 15 рабочих дней)

```
PRE-CLOSE (Days -3 to 0)
Day -3:  Confirm subledger cutoff with AR/AP teams
Day -3:  Distribute close checklist to all controllers
Day -2:  Process final customer invoices for the period
Day -2:  Complete final AP invoice entry cutoff
Day -1:  Process final payroll; confirm payroll accruals
Day 0:   Period closes at end of business

CLOSE WEEK 1 (Days 1–5)
Day 1:   Open period in ERP; run preliminary trial balance
Day 1:   Bank statements received; begin bank reconciliations
Day 1:   AR team: complete AR subledger reconciliation
Day 2:   AP team: complete AP subledger reconciliation
Day 2:   Fixed assets: run depreciation; reconcile FA subledger
Day 2:   Inventory: confirm physical counts; post inventory JEs
Day 3:   Payroll JEs posted and reviewed
Day 3:   Standard recurring entries posted (amortization, D&A)
Day 4:   Accruals: all department accruals submitted and posted
Day 4:   Intercompany: confirm IC balances with counterparts
Day 5:   Elimination JEs posted; preliminary consolidation run

CLOSE WEEK 2 (Days 6–10)
Day 6:   Management review: preliminary P&L distributed
Day 6:   Flux analysis: identify variances > materiality threshold
Day 7:   Tax provision calculated; deferred tax JEs posted
Day 7:   Revenue recognition review; deferred revenue JEs
Day 8:   Controller review: all reconciliations signed off
Day 9:   Final consolidation; segment reporting prepared
Day 9:   Board/management package drafted
Day 10:  CFO review; final adjustments made

REPORTING (Days 11–15)
Day 11:  Final financial statements issued internally
Day 12:  Management commentary finalized
Day 13:  Board package distributed
Day 14:  External auditor review (if applicable)
Day 15:  Period locked in ERP
```

### Трекер статуса задач закрытия

```markdown
| Task | Owner | Due | Status | Blocker |
|---|---|---|---|---|
| Bank Reconciliations | Controller | Day 3 | In Progress | — |
| AR Subledger Rec | AR Manager | Day 2 | Complete | — |
| AP Subledger Rec | AP Manager | Day 2 | Not Started | Waiting on statements |
| Payroll JEs | Payroll | Day 3 | Complete | — |
| Fixed Asset D&A | Fixed Asset Acct | Day 2 | In Progress | — |
| Accruals – Mktg | Mktg Controller | Day 4 | Not Started | Pending vendor quotes |
| Accruals – IT | IT Controller | Day 4 | Complete | — |
| IC Reconciliation | Corporate Acct | Day 5 | Not Started | — |
| Tax Provision | Tax Director | Day 7 | Not Started | Waiting prelim P&L |
| Consolidation | Corporate | Day 9 | Not Started | — |
| Management Package | FP&A | Day 10 | Not Started | — |
```

### Карта зависимостей закрытия
```
Bank Recs ------------------------------------------► Controller Review
AR Rec ----------------------------------------------► Consolidation
AP Rec ----------------------------------------------► Consolidation
Payroll JEs -----------------------------------------► Accrual Review
Fixed Asset D&A -------------------------------------► Balance Sheet
Accruals (all) --------------------------------------► Prelim P&L
                                                              │
                                                              ▼
Revenue Recognition ---------------------------------► Prelim P&L
                                                              │
                                                              ▼
Prelim P&L ------------------------------------------► Tax Provision
                                                              │
IC Elimination --------------------------------------► Consolidation
                                                              │
Prelim P&L + Tax + IC -------------------------------► Final Consolidation
                                                              │
                                                              ▼
Final Consolidation ---------------------------------► Management Package
```

### Метрики закрытия для отслеживания
| Метрика | Цель | Как измерять |
|---|---|---|
| Длительность закрытия | ≤ 10 рабочих дней | От открытия в День 1 до подписи CFO в День 10 |
| Задачи в срок | ≥ 95% | Задачи, завершённые к сроку / всего задач |
| Аудиторские корректировки | < 5 за период | Количество проводок после закрытия |
| Реституции (restatements) | 0 | Корректировки прошлых периодов |
| Сверочные позиции > $50K | < 3 нерешённых | Отчёт по старению сверочных позиций |

---

## 5. Анализ отклонений и комментарии

### Когда использовать
- Отчётность «бюджет против факта»
- Сравнения с прошлым периодом
- Объяснение драйверов выручки или расходов руководству
- Построение водопадных диаграмм для презентаций CFO/совету директоров

### Фреймворк анализа отклонений

**Шаг 1. Рассчитайте отклонения**
```
Dollar Variance = Actual − Budget (or Actual − Prior Period)
Percent Variance = (Actual − Budget) / |Budget| × 100

Favorable (F) = Revenue above budget OR Expense below budget
Unfavorable (U) = Revenue below budget OR Expense above budget
```

**Шаг 2. Примените фильтр существенности**
- Количественный порог: > $[X]K в абсолюте ИЛИ > [Y]% от бюджета
- Качественный порог: любое отклонение, влияющее на ключевые нарративные метрики

**Шаг 3. Декомпозиция на драйверы**
- Отклонение выручки = ценовое отклонение + объёмное отклонение + отклонение микса
- Отклонение расходов = отклонение ставки + объёмное отклонение + отклонение эффективности

**Шаг 4. Подготовьте нарративный комментарий**

### Шаблон отчёта об отклонениях
```
[Company Name]
Budget vs. Actual Variance Report
Period: [Month/Quarter] [Year]

EXECUTIVE SUMMARY
Total Revenue:   Actual $[X]M  |  Budget $[X]M  |  Variance $[X]M ([Y]%) [F/U]
Total Expenses:  Actual $[X]M  |  Budget $[X]M  |  Variance $[X]M ([Y]%) [F/U]
Operating Income: Actual $[X]M |  Budget $[X]M  |  Variance $[X]M ([Y]%) [F/U]

KEY REVENUE DRIVERS
1. [Product Line A] — $[X]M favorable: [Explanation — volume/price/mix]
2. [Product Line B] — $[X]M unfavorable: [Explanation]
3. [Geography / Segment] — $[X]M: [Explanation]

KEY EXPENSE DRIVERS
1. [Cost Category] — $[X]M unfavorable: [Explanation]
2. [Cost Category] — $[X]M favorable: [Explanation]

DETAILED VARIANCE TABLE
Account              Actual      Budget      Var $      Var %    F/U   Commentary
Revenue
  Product Revenue    $X,XXX      $X,XXX      $XXX       X.X%     F     [Note]
  Service Revenue    $X,XXX      $X,XXX     ($XXX)     (X.X%)    U     [Note]
  Total Revenue      $X,XXX      $X,XXX      $XXX       X.X%     F

Cost of Revenue
  COGS – Product     $X,XXX      $X,XXX     ($XXX)     (X.X%)    U     [Note]
  COGS – Service     $X,XXX      $X,XXX      $XXX       X.X%     F     [Note]
  Total COR          $X,XXX      $X,XXX      $XXX       X.X%     F

Gross Profit         $X,XXX      $X,XXX      $XXX       X.X%     F
Gross Margin         XX.X%       XX.X%       X.Xpts

Operating Expenses
  R&D                $X,XXX      $X,XXX      $XXX       X.X%     F     [Note]
  S&M                $X,XXX      $X,XXX     ($XXX)     (X.X%)    U     [Note]
  G&A                $X,XXX      $X,XXX      $XXX       X.X%     F     [Note]
  Total OpEx         $X,XXX      $X,XXX      $XXX       X.X%     F

Operating Income     $X,XXX      $X,XXX      $XXX       X.X%     F
Operating Margin     XX.X%       XX.X%       X.Xpts
```

### Декомпозиция выручки
```
Revenue Variance = Volume Effect + Price Effect + Mix Effect

Volume Effect = (Actual Units − Budget Units) × Budget Price
Price Effect  = (Actual Price − Budget Price) × Actual Units
Mix Effect    = Budget Price × (Actual Mix − Budget Mix) × Total Actual Units

Example:
  Product A: Budget 1,000 units @ $100 = $100,000
  Product B: Budget 1,000 units @ $200 = $200,000
  Total Budget = $300,000

  Actual Product A: 1,200 units @ $95  = $114,000
  Actual Product B: 800 units  @ $210  = $168,000
  Total Actual = $282,000

  Overall Variance = $282,000 − $300,000 = ($18,000) Unfavorable

  Volume Effect: (+200 − 200) × weighted avg = net zero (units same total)
  Price Effect A: ($95 − $100) × 1,200 = ($6,000) U
  Price Effect B: ($210 − $200) × 800  = $8,000   F
  Mix Effect: Shift from higher-margin B to lower-margin A = ($20,000) U
```

### Шаблон нарратива для водопадной диаграммы
```
"Operating income of $[X]M came in $[Y]M [above/below] budget of $[Z]M.

Revenue was $[A]M [favorable/unfavorable] driven by:
+ $[B]M higher volume in [segment] driven by [reason]
− $[C]M lower pricing in [segment] due to [competitive pressure/discounting]
− $[D]M unfavorable mix as [higher-margin product] underperformed

This was partially [offset by / compounded by] expenses:
+ $[E]M favorable in R&D due to [timing of headcount / vendor delays]
− $[F]M unfavorable in S&M due to [campaign pull-forward / trade show costs]
± $[G]M in G&A due to [litigation reserve / one-time item]

Outlook: Management [reaffirms / revises] full-year guidance of $[X]M revenue
given [trend rationale]."
```

---

## 6. Поддержка аудита и соответствие SOX

### Когда использовать
- Тестирование контролей по SOX 404
- Подготовка аудиторских выборок для внутренних или внешних аудиторов
- Документирование внутренних контролей
- Ответы на запросы аудиторов
- Классификация недостатков (значительный недостаток против существенной слабости)

### Рабочий процесс тестирования контролей SOX 404

**Шаг 1. Определите контроли в периметре**
```
Tier 1 – Company-Level Controls (ITGC)
  □ User access reviews (quarterly)
  □ Segregation of duties (SoD) matrix
  □ Change management controls
  □ Backup and recovery procedures

Tier 2 – Process-Level Controls
  □ Financial close controls (journal entry review, reconciliations)
  □ Revenue recognition controls (contract review, billing accuracy)
  □ Procurement controls (PO approval, 3-way match)
  □ Payroll controls (authorization, accurate calculation)
  □ Financial reporting controls (management review of fluctuations)
```

**Шаг 2. Выберите размер выборки (рекомендации PCAOB)**
```
Population Size    Risk Level    Sample Size
< 25               Any           Entire population
25 – 99            Low           25
25 – 99            High          40
100 – 249          Low           30
100 – 249          High          60
250 – 499          Low           35
250 – 499          High          75
500+               Low           40
500+               High          100

Sampling Method: Random (use RAND() in Excel or Python random.sample())
For automated/IT controls: Sample 1–3 (test once if no exceptions found)
```

**Скрипт выбора выборки (Python):**
```python
import random

def select_audit_sample(population: list, sample_size: int, seed: int = None) -> list:
    """
    Randomly select audit sample from population.
    
    Args:
        population: List of transaction IDs or items
        sample_size: Number of items to select
        seed: Random seed for reproducibility (document this!)
    
    Returns:
        List of selected sample items
    """
    if seed:
        random.seed(seed)
    
    if len(population) <= sample_size:
        return population  # Test entire population
    
    sample = random.sample(population, sample_size)
    return sorted(sample)

# Example: Select 40 journal entries from 500+ population
all_jes = list(range(1001, 1537))  # JE numbers 1001–1536
sample = select_audit_sample(all_jes, sample_size=40, seed=20260303)
print(f"Sample size: {len(sample)}")
print(f"Sample items: {sample}")
```

### Шаблон документации тестирования контроля
```
CONTROL TEST WORKPAPER

Control ID:        [SOX-FIN-001]
Process:           [Financial Close / Revenue / Payroll / etc.]
Control Name:      [Journal Entry Review]
Control Owner:     [Controller, CFO]
Control Type:      [Preventive / Detective]
Frequency:         [Daily / Weekly / Monthly / Quarterly]
Risk Addressed:    [Unauthorized journal entries, recording errors]

CONTROL DESCRIPTION:
[The Controller reviews and approves all manual journal entries above
$[X]K before posting. The review includes: (1) business purpose, (2)
supporting documentation, (3) correct accounts, (4) proper period.]

TESTING PROCEDURE:
1. Obtain population of manual JEs for the period
2. Apply SALT to identify anomalies (round numbers, unusual times, etc.)
3. Select sample per PCAOB guidance (population: [N]; sample: [N])
4. For each sample item, inspect:
   □ Journal entry form / ERP screenshot
   □ Approval signature / system approval log
   □ Supporting documentation attached
   □ Posted to correct account and period

RESULTS SUMMARY:
Population:        [N] manual JEs totaling $[X]M
Sample:            [N] items
Exceptions found:  [0] / [Describe any exceptions]
Conclusion:        Control [Operating Effectively / Exception Noted]

DEFICIENCY ANALYSIS (if applicable):
Deficiency Description: [Describe]
Root Cause:             [Describe]
Financial Statement Impact: $[Amount] / [None / Immaterial]
Classification:         [Control Deficiency / Significant Deficiency / Material Weakness]

Prepared by: ____________  Date: ____________
Reviewed by: ____________  Date: ____________
```

### Фреймворк классификации недостатков
```
CONTROL DEFICIENCY
  Definition: A control does not operate effectively or does not exist
              where necessary to prevent or detect a misstatement.
  Impact: Immaterial potential misstatement
  Required action: Remediate; no disclosure required

SIGNIFICANT DEFICIENCY
  Definition: A deficiency, or combination of deficiencies, that is
              less severe than a material weakness but important enough
              to merit attention by those responsible for financial reporting.
  Impact: More than inconsequential potential misstatement
  Required action: Report to Audit Committee; remediate promptly

MATERIAL WEAKNESS
  Definition: A deficiency where there is a reasonable possibility that
              a material misstatement of the financial statements will
              not be prevented or detected on a timely basis.
  Impact: Could result in material misstatement of financial statements
  Required action: External disclosure required (10-K); remediation
                   plan with timeline; re-test after remediation

MATERIALITY THRESHOLD GUIDANCE:
  Quantitative: Typically 5% of pre-tax income (SEC Staff guidance)
  Qualitative: Consider nature of account, risk, fraud indicators
```

### Чеклист ответа на запросы аудитора
```
For each Prepared by Client (PBC) item:
□ Understand exactly what the auditor needs (format, period, scope)
□ Assign a single owner responsible for the item
□ Set internal due date 2 days before auditor deadline
□ Quality review before submission (completeness, formatting)
□ Log in PBC tracker: item #, description, owner, due date, status
□ Label files clearly: [PBC-###]_[Description]_[Period].xlsx
□ Brief person delivering item on likely follow-up questions
□ Keep copy of everything submitted
```

---

## 7. Рынки и инвестиционный анализ

### Когда использовать
- Текущие цены акций/крипты/ETF
- Исторические данные о ценах для анализа
- Финансовая отчётность публичных компаний
- Транскрипты звонков по результатам (earnings call)
- Построение инвестиционного тезиса
- Анализ сопоставимых компаний
- Эмуляция фреймворков известных инвесторов

### КРИТИЧНО: никогда не используйте веб-поиск для финансовых данных

**НЕ используйте `search_web` для:** цен акций, исторических цен, P/E, рыночной капитализации, цифр выручки, EPS, гайденса, транскриптов earnings. Веб-поиск возвращает устаревшие, неструктурированные фрагменты.

**ВСЕГДА используйте финансовые инструменты из коннектор-сервиса:**
```python
# Step 1: Discover tools
list_external_tools(queries=["finance_"])

# Step 2: Get schemas (REQUIRED before calling)
describe_external_tools(source_id="finance", tool_names=["finance_quotes", "finance_financials"])

# Step 3: Call tools — always use source_id="finance"
call_external_tool(tool_name="<tool>", source_id="finance", arguments={...})
```

### Протокол опорной даты
У каждого финансового запроса есть опорная дата. Перед вызовом инструментов сопоставьте её с фискальными параметрами:

| Месяц опорной даты | Фискальный квартал |
|---|---|
| Январь–март | Q1 |
| Апрель–июнь | Q2 |
| Июль–сентябрь | Q3 |
| Октябрь–декабрь | Q4 |

**Текущая дата: 3 марта 2026 → `as_of_fiscal_year=2026, as_of_fiscal_quarter=1`**

### Краткий справочник по финансовым инструментам

| Инструмент | Назначение | Ключевые параметры |
|---|---|---|
| `finance_tickers_lookup` | Определить тикер по названию компании | `queries: ["Tesla"]` |
| `finance_quotes` | Цена в реальном времени, P/E, рыночная капитализация | `ticker_symbols, fields` |
| `finance_ohlcv_histories` | Исторические цены OHLCV в CSV | `ticker_symbols, start_date, end_date` |
| `finance_financials` | ОПУ, баланс, ОДДС | `ticker_symbols, period, as_of_fiscal_year, limit` |
| `finance_earnings` | Транскрипты earnings, история EPS | `ticker_symbol, as_of_fiscal_year, data_types` |
| `finance_earnings_schedule` | Даты earnings | `ticker_symbols, as_of_fiscal_year` |
| `finance_company_profile` | CEO, сектор, число сотрудников | `ticker_symbols` |
| `finance_company_peers` | Сопоставимые компании | `ticker_symbol` |
| `finance_segments` | Выручка по сегментам, KPI | `ticker_symbols` |
| `finance_estimates` | Консенсус-прогнозы аналитиков | `ticker_symbols` |
| `finance_fundamentals` | Временные ряды P/E, EV/EBITDA | `ticker_symbols` |
| `finance_analyst_research` | Целевые цены, апгрейды | `ticker_symbols` |
| `finance_market_gainers` | Топ растущих сегодня | — |
| `finance_market_losers` | Топ падающих сегодня | — |
| `finance_massive` | Опционы, тиковые данные, макро (сырой API) | `pathname, params` |

### Типовые паттерны финансовых запросов

```python
# Get current quote
call_external_tool("finance_quotes", "finance", {
    "ticker_symbols": ["AAPL", "MSFT"],
    "fields": ["price", "marketCap", "pe", "eps", "dividendYieldTTM"]
})

# Get historical prices (use for past reference dates, not finance_quotes)
call_external_tool("finance_ohlcv_histories", "finance", {
    "ticker_symbols": ["NVDA"],
    "start_date_yyyy_mm_dd": "2025-01-01",
    "end_date_yyyy_mm_dd": "2026-03-03"
})

# Get financials — always pass as_of
call_external_tool("finance_financials", "finance", {
    "ticker_symbols": ["TSLA"],
    "period": "annual",
    "as_of_fiscal_year": 2025,
    "limit": 3,
    "income_statement_metrics": ["revenue", "netIncome", "grossProfit"],
    "balance_sheet_metrics": ["totalDebt", "cashAndCashEquivalents"],
    "cash_flow_metrics": ["freeCashFlow", "capitalExpenditures"]
})

# Get earnings transcript — primary source for guidance, KPIs, non-GAAP
call_external_tool("finance_earnings", "finance", {
    "ticker_symbol": "AAPL",
    "as_of_fiscal_year": 2025,
    "as_of_fiscal_quarter": 4,
    "limit": 1,
    "data_types": ["transcript_full"]
})

# Resolve unknown ticker
call_external_tool("finance_tickers_lookup", "finance", {
    "queries": ["Palantir Technologies", "ARM Holdings"]
})
```

### Дерево решений по источникам данных
```
Public company question?
├-- Revenue, margins, EPS, debt, FCF → finance_financials
├-- Guidance, non-GAAP metrics, segment KPIs, management commentary
│   → finance_earnings (transcripts answer ~50% of filing questions)
├-- Price targets, analyst ratings → finance_analyst_research
├-- Options, tick data, macro (treasury yields, CPI) → finance_massive
└-- Only if finance tools insufficient → search_web
    (10-K footnotes, proxy statements, 8-K offering terms)
```

### Фреймворк инвестиционного анализа

**Шаблон одностраничного инвестиционного тезиса:**
```
COMPANY: [Name] | TICKER: [X] | SECTOR: [X]
DATE: [X] | ANALYST: [X] | RECOMMENDATION: BUY / HOLD / SELL
PRICE TARGET: $[X] (current: $[X], upside: [X]%)

INVESTMENT THESIS (3-sentence summary):
[Core reason to own the stock]
[Key catalyst or competitive advantage]
[Risk-adjusted return expectation]

BUSINESS OVERVIEW:
Revenue model: [Subscription / Transaction / Product / Advertising]
Total addressable market: $[X]B
Market share: [X]%
Key products/services: [List]
Moat: [Brand / Network Effects / Switching Costs / Cost Advantage / IP]

FINANCIAL SNAPSHOT (LTM):
Revenue:       $[X]B    YoY growth: [X]%
Gross Margin:  [X]%     vs. peers: [higher/lower]
EBITDA Margin: [X]%     vs. budget: [on track/ahead/behind]
FCF Yield:     [X]%     Net Debt/EBITDA: [X]x
P/E (NTM):     [X]x     EV/Revenue (NTM): [X]x

BULL CASE ($[X] target, [X]% probability):
- [Catalyst 1]
- [Catalyst 2]

BASE CASE ($[X] target, [X]% probability):
- [Expected trajectory]
- [Key assumptions]

BEAR CASE ($[X] target, [X]% probability):
- [Risk 1]
- [Risk 2]

KEY RISKS:
1. [Competitive / Market / Regulatory / Execution]
2. [Balance sheet / Leverage / Liquidity]
3. [Macro / Interest rate / Currency]

COMPARABLE COMPANIES:
Company    EV/Revenue  EV/EBITDA  P/E    Growth   Margin
[Peer A]   [X]x        [X]x       [X]x   [X]%     [X]%
[Peer B]   [X]x        [X]x       [X]x   [X]%     [X]%
[Target]   [X]x        [X]x       [X]x   [X]%     [X]%
```

### Фреймворки известных инвесторов

**Уоррен Баффетт (внутренняя стоимость / экономический ров):**
```
Screen for:
- Consistent high ROE (> 15%) for 10+ years
- Low debt (Net Debt/EBITDA < 2x)
- Strong free cash flow conversion
- Identifiable economic moat (brand, network, cost)
- Management integrity and capital allocation track record
Value at: Conservative DCF, 10-year horizon, margin of safety > 25%
```

**Питер Линч (GARP — рост по разумной цене):**
```
PEG Ratio < 1.0 = potentially undervalued
Criteria: EPS growth 20–50% per year; P/E < growth rate
Tenbagger checklist: boring name, niche market, institutional under-ownership,
  no analyst coverage, growing earnings, product with repeat purchases
```

**Рэй Далио (всепогодный / макро):**
```
Macro framework: Rising/Falling Growth × Rising/Falling Inflation
Risk parity: Weight positions by risk contribution, not dollar size
Asset allocation across environments:
  Rising growth: Stocks, corporate bonds
  Falling growth: Treasuries, gold
  Rising inflation: Commodities, TIPS, gold
  Falling inflation: Stocks, bonds
```

**Майкл Бьюрри (глубокая стоимость / катализатор):**
```
Focus on: Misunderstood companies, distressed assets, complex situations
Process: Bottom-up forensic accounting analysis; look for hidden value
Check: FCF vs reported earnings; off-balance sheet items; asset values
Catalyst required: Specific event that forces value recognition
```

**Цитирование:**
При представлении данных из финансовых инструментов всегда цитируйте:
`https://perplexity.ai/finance/<TICKER>`

---

## 8. Дата-инжиниринг для финансов

### Когда использовать
- Построение финансовых дата-пайплайнов (ERP → хранилище данных)
- Автоматизация выгрузок ГК, отчётов оборотно-сальдовой ведомости
- Настройка dbt-моделей для финансовой отчётности
- Реализация проверок качества данных на финансовых данных
- Стриминг транзакционных данных в реальном времени
- Обработка изменений схемы в финансовых системах-источниках

### Архитектура финансового дата-пайплайна

```
Source Systems                Extract              Transform            Load
-----------------------------------------------------------------------------
ERP (SAP/Oracle/NetSuite) --► Fivetran/Airbyte --► dbt models --► Snowflake
General Ledger --------------► CDC (Debezium) ----► Spark ---------► BigQuery
AP/AR Subledgers ------------► API extracts -------► dbt -----------► Redshift
Payroll System --------------► SFTP/API -----------► Pandas --------► Databricks
Market Data API -------------► finance_tools -------► Python --------► PostgreSQL
Bank Feeds ------------------► Plaid / OFX ---------► dbt -----------► DW
```

### Структура dbt-моделей для финансов

```
dbt_finance/
├-- models/
│   ├-- staging/                    # 1:1 with source tables, clean & rename
│   │   ├-- stg_gl_transactions.sql
│   │   ├-- stg_chart_of_accounts.sql
│   │   ├-- stg_ar_invoices.sql
│   │   └-- stg_ap_invoices.sql
│   ├-- intermediate/               # Business logic, joins
│   │   ├-- int_trial_balance.sql
│   │   ├-- int_ar_aging.sql
│   │   └-- int_budget_actuals.sql
│   └-- marts/                      # Final reporting tables
│       ├-- finance/
│       │   ├-- fct_gl_transactions.sql
│       │   ├-- dim_chart_of_accounts.sql
│       │   ├-- fct_ar_aging.sql
│       │   ├-- fct_budget_vs_actual.sql
│       │   └-- rpt_income_statement.sql
│       └-- schema.yml              # Tests + documentation
```

**Пример: dbt-модель оборотно-сальдовой ведомости**
```sql
-- models/marts/finance/rpt_trial_balance.sql
{{
    config(
        materialized='table',
        tags=['finance', 'close', 'daily']
    )
}}

WITH gl AS (
    SELECT * FROM {{ ref('stg_gl_transactions') }}
),

coa AS (
    SELECT * FROM {{ ref('stg_chart_of_accounts') }}
),

aggregated AS (
    SELECT
        gl.account_number,
        coa.account_name,
        coa.account_type,           -- Asset, Liability, Equity, Revenue, Expense
        coa.financial_statement,    -- Balance Sheet, Income Statement
        coa.department,
        gl.fiscal_year,
        gl.fiscal_period,
        SUM(gl.debit_amount)  AS total_debits,
        SUM(gl.credit_amount) AS total_credits,
        SUM(gl.debit_amount) - SUM(gl.credit_amount) AS net_balance
    FROM gl
    LEFT JOIN coa USING (account_number)
    GROUP BY 1, 2, 3, 4, 5, 6, 7
)

SELECT
    *,
    CASE
        WHEN account_type IN ('Asset', 'Expense') AND net_balance >= 0 THEN net_balance
        WHEN account_type IN ('Liability', 'Equity', 'Revenue') AND net_balance <= 0 THEN ABS(net_balance)
        ELSE 0
    END AS normal_balance,
    CURRENT_TIMESTAMP AS dbt_updated_at

FROM aggregated
```

**Пример: dbt-модель «бюджет против факта»**
```sql
-- models/marts/finance/fct_budget_vs_actual.sql
{{
    config(
        materialized='incremental',
        unique_key=['account_number', 'department', 'fiscal_year', 'fiscal_period'],
        tags=['finance', 'variance']
    )
}}

WITH actuals AS (
    SELECT
        account_number,
        department,
        fiscal_year,
        fiscal_period,
        SUM(amount) AS actual_amount
    FROM {{ ref('fct_gl_transactions') }}
    GROUP BY 1, 2, 3, 4
),

budget AS (
    SELECT
        account_number,
        department,
        fiscal_year,
        fiscal_period,
        budget_amount
    FROM {{ ref('stg_budget_data') }}
),

combined AS (
    SELECT
        COALESCE(a.account_number, b.account_number) AS account_number,
        COALESCE(a.department, b.department)          AS department,
        COALESCE(a.fiscal_year, b.fiscal_year)        AS fiscal_year,
        COALESCE(a.fiscal_period, b.fiscal_period)    AS fiscal_period,
        COALESCE(a.actual_amount, 0)                  AS actual_amount,
        COALESCE(b.budget_amount, 0)                  AS budget_amount,
        COALESCE(a.actual_amount, 0) - COALESCE(b.budget_amount, 0) AS variance_amount,
        CASE
            WHEN COALESCE(b.budget_amount, 0) = 0 THEN NULL
            ELSE (COALESCE(a.actual_amount, 0) - COALESCE(b.budget_amount, 0))
                 / ABS(COALESCE(b.budget_amount, 0))
        END AS variance_pct
    FROM actuals a
    FULL OUTER JOIN budget b USING (account_number, department, fiscal_year, fiscal_period)
)

SELECT * FROM combined
{% if is_incremental() %}
WHERE fiscal_year = EXTRACT(YEAR FROM CURRENT_DATE)
  AND fiscal_period = EXTRACT(MONTH FROM CURRENT_DATE)
{% endif %}
```

### Тесты качества финансовых данных (dbt schema.yml)

```yaml
version: 2

models:
  - name: fct_gl_transactions
    description: "General Ledger transactions — source of truth for all financial reporting"
    tests:
      - dbt_utils.recency:
          datepart: day
          field: transaction_date
          interval: 2
          severity: warn

    columns:
      - name: transaction_id
        description: "Unique GL transaction identifier"
        tests:
          - unique
          - not_null

      - name: debit_amount
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0

      - name: credit_amount
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0

      - name: account_number
        tests:
          - not_null
          - relationships:
              to: ref('stg_chart_of_accounts')
              field: account_number

      - name: fiscal_period
        tests:
          - not_null
          - accepted_values:
              values: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

  - name: rpt_trial_balance
    description: "Trial balance — debits must equal credits per period"
    tests:
      # Custom test: debits == credits in each period
      - dbt_utils.expression_is_true:
          expression: "ABS(SUM(total_debits) - SUM(total_credits)) < 0.01"
          config:
            severity: error
```

### Airflow DAG для пайплайна данных закрытия месяца
```python
# dags/monthly_close_pipeline.py
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'finance-data-team',
    'email': ['finance-alerts@company.com'],
    'email_on_failure': True,
    'retries': 2,
    'retry_delay': timedelta(minutes=10),
}

with DAG(
    'monthly_close_pipeline',
    default_args=default_args,
    description='Month-end close data pipeline: ERP → dbt → reports',
    schedule_interval='0 6 1 * *',   # 6am on 1st of every month
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['finance', 'close', 'monthly'],
) as dag:

    extract_gl = BashOperator(
        task_id='extract_gl_transactions',
        bash_command='python /opt/airflow/scripts/extract_erp.py --period {{ ds[:7] }}'
    )

    extract_budget = BashOperator(
        task_id='extract_budget_data',
        bash_command='python /opt/airflow/scripts/extract_budget.py --period {{ ds[:7] }}'
    )

    run_staging = BashOperator(
        task_id='dbt_run_staging',
        bash_command='cd /opt/dbt && dbt run --select staging.*'
    )

    run_marts = BashOperator(
        task_id='dbt_run_marts',
        bash_command='cd /opt/dbt && dbt run --select marts.finance.*'
    )

    test_data = BashOperator(
        task_id='dbt_test',
        bash_command='cd /opt/dbt && dbt test --select marts.finance.*'
    )

    generate_reports = BashOperator(
        task_id='generate_financial_reports',
        bash_command='python /opt/airflow/scripts/generate_reports.py --period {{ ds[:7] }}'
    )

    notify_success = SlackWebhookOperator(
        task_id='notify_close_complete',
        slack_webhook_conn_id='slack_finance',
        message='Month-end close pipeline completed for {{ ds[:7] }}. Reports available.',
        trigger_rule='all_success',
    )

    [extract_gl, extract_budget] >> run_staging >> run_marts >> test_data >> generate_reports >> notify_success
```

### Гид по архитектурным решениям

| Сценарий | Рекомендуемый стек | Примечания |
|---|---|---|
| Ежедневная выгрузка ГК, < 1M строк | Fivetran + dbt + Snowflake | Простейший, минимум поддержки |
| Мониторинг транзакций в реальном времени | Debezium + Kafka + Spark Streaming | Детекция мошенничества/аномалий за секунды |
| Консолидация нескольких юрлиц | dbt + Snowflake + Monte Carlo | Логика элиминирования в dbt |
| ML-прогноз из данных ГК | Spark + MLflow + Airflow | Feature engineering из истории ГК |
| ERP в BI-инструмент | Fivetran + dbt + Looker/Tableau | Стандартный современный дата-стек |

---

## 9. ML и прогнозирование для финансов

### Когда использовать
- Прогнозирование выручки методами ML
- Детекция аномалий в транзакциях (мошенничество, ошибки проводок)
- Прогноз оттока (churn) для подписочных бизнесов
- Прогнозирование денежного потока
- Планирование спроса для финансирования запасов
- Скоринг кредитного риска

### Рабочий процесс прогнозирования выручки

**Шаг 1. Feature engineering из финансовых данных**
```python
import pandas as pd
import numpy as np

def engineer_revenue_features(gl_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build ML features from GL transaction history for revenue forecasting.
    
    Input: DataFrame with columns [date, account, amount, department, customer_id]
    Output: Monthly feature matrix for forecasting
    """
    # Aggregate to monthly revenue
    monthly = gl_df[gl_df['account'].str.startswith('4')].copy()  # Revenue accounts
    monthly['year_month'] = pd.to_datetime(monthly['date']).dt.to_period('M')
    
    revenue = monthly.groupby('year_month')['amount'].sum().reset_index()
    revenue.columns = ['year_month', 'revenue']
    revenue = revenue.sort_values('year_month')
    
    # Lag features (prior months)
    for lag in [1, 2, 3, 6, 12]:
        revenue[f'revenue_lag_{lag}'] = revenue['revenue'].shift(lag)
    
    # Rolling statistics
    revenue['revenue_ma3']  = revenue['revenue'].rolling(3).mean()
    revenue['revenue_ma12'] = revenue['revenue'].rolling(12).mean()
    revenue['revenue_std3'] = revenue['revenue'].rolling(3).std()
    
    # YoY growth
    revenue['yoy_growth'] = revenue['revenue'].pct_change(12)
    
    # Seasonality features
    revenue['month'] = revenue['year_month'].dt.month
    revenue['quarter'] = revenue['year_month'].dt.quarter
    
    # Month-end effects (close timing)
    revenue['is_q_end'] = revenue['month'].isin([3, 6, 9, 12]).astype(int)
    revenue['is_year_end'] = (revenue['month'] == 12).astype(int)
    
    return revenue.dropna()


def build_revenue_forecast_model(features_df: pd.DataFrame, 
                                  horizon_months: int = 3):
    """
    Train XGBoost revenue forecast model with cross-validation.
    Returns forecast with confidence intervals.
    """
    from xgboost import XGBRegressor
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import mean_absolute_percentage_error
    
    feature_cols = [c for c in features_df.columns 
                    if c not in ['year_month', 'revenue']]
    
    X = features_df[feature_cols].values
    y = features_df['revenue'].values
    
    # Time series cross-validation (no data leakage)
    tscv = TimeSeriesSplit(n_splits=5)
    cv_scores = []
    
    model = XGBRegressor(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        random_state=42
    )
    
    for train_idx, val_idx in tscv.split(X):
        model.fit(X[train_idx], y[train_idx])
        preds = model.predict(X[val_idx])
        mape = mean_absolute_percentage_error(y[val_idx], preds)
        cv_scores.append(mape)
    
    print(f"CV MAPE: {np.mean(cv_scores):.2%} ± {np.std(cv_scores):.2%}")
    
    # Retrain on full data
    model.fit(X, y)
    
    # Feature importance
    importance = pd.Series(
        model.feature_importances_, 
        index=feature_cols
    ).sort_values(ascending=False)
    
    return model, importance
```

**Шаг 2. Сценарное прогнозирование (Base / Bull / Bear)**
```python
def generate_scenarios(base_forecast: float, 
                        growth_assumptions: dict) -> dict:
    """
    Generate three-scenario revenue forecast.
    
    growth_assumptions = {
        'bear': {'revenue_growth': -0.05, 'probability': 0.20},
        'base': {'revenue_growth': 0.10,  'probability': 0.60},
        'bull': {'revenue_growth': 0.20,  'probability': 0.20},
    }
    """
    scenarios = {}
    for name, params in growth_assumptions.items():
        scenarios[name] = {
            'forecast': base_forecast * (1 + params['revenue_growth']),
            'growth_rate': params['revenue_growth'],
            'probability': params['probability'],
        }
    
    # Expected value
    ev = sum(s['forecast'] * s['probability'] 
             for s in scenarios.values())
    scenarios['expected_value'] = ev
    
    return scenarios


# Example usage
growth_assumptions = {
    'bear': {'revenue_growth': -0.03, 'probability': 0.20},
    'base': {'revenue_growth': 0.12,  'probability': 0.60},
    'bull': {'revenue_growth': 0.22,  'probability': 0.20},
}

base_revenue = 10_000_000  # $10M current quarter
scenarios = generate_scenarios(base_revenue, growth_assumptions)

for name, values in scenarios.items():
    if name != 'expected_value':
        print(f"{name.upper():6s}: ${values['forecast']:>12,.0f}  "
              f"({values['growth_rate']:+.1%} growth, "
              f"{values['probability']:.0%} probability)")
print(f"{'EV':6s}: ${scenarios['expected_value']:>12,.0f}")
```

### Детекция аномалий в финансовых транзакциях

```python
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import pandas as pd
import numpy as np

def detect_transaction_anomalies(transactions_df: pd.DataFrame,
                                  contamination: float = 0.01) -> pd.DataFrame:
    """
    Detect anomalous financial transactions using Isolation Forest.
    
    Detects: Unusual amounts, timing, account combinations, round-number entries
    
    Args:
        transactions_df: GL transactions with amount, hour, account, user columns
        contamination: Expected fraction of anomalies (default 1%)
    
    Returns:
        DataFrame with anomaly_score and is_anomaly columns
    """
    # Feature engineering for anomaly detection
    df = transactions_df.copy()
    
    # Amount-based features
    df['log_amount'] = np.log1p(df['amount'].abs())
    df['is_round_number'] = (df['amount'] % 1000 == 0).astype(int)
    df['is_round_5k'] = (df['amount'] % 5000 == 0).astype(int)
    
    # Timing features (Benford's Law analysis)
    df['first_digit'] = df['amount'].abs().astype(str).str[0].astype(int)
    benfords_expected = {1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097,
                         5: 0.079, 6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046}
    df['benfords_deviation'] = df['first_digit'].map(benfords_expected)
    
    # Posted hour (unusual hours = higher risk)
    df['post_hour'] = pd.to_datetime(df['posted_at']).dt.hour
    df['is_off_hours'] = ((df['post_hour'] < 7) | (df['post_hour'] > 20)).astype(int)
    df['is_weekend'] = pd.to_datetime(df['posted_at']).dt.dayofweek.isin([5, 6]).astype(int)
    
    # Account-level Z-score
    df['account_z_score'] = df.groupby('account_number')['amount'].transform(
        lambda x: (x - x.mean()) / x.std()
    )
    
    # Select features for model
    feature_cols = ['log_amount', 'is_round_number', 'is_off_hours', 
                    'is_weekend', 'account_z_score', 'benfords_deviation']
    X = df[feature_cols].fillna(0)
    
    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Isolation Forest
    iso_forest = IsolationForest(
        contamination=contamination,
        n_estimators=200,
        random_state=42
    )
    
    df['anomaly_score'] = iso_forest.fit_predict(X_scaled)
    df['anomaly_raw_score'] = iso_forest.score_samples(X_scaled)
    df['is_anomaly'] = (df['anomaly_score'] == -1)
    
    # Return anomalies sorted by risk
    anomalies = df[df['is_anomaly']].sort_values('anomaly_raw_score')
    print(f"Flagged {len(anomalies)} anomalies out of {len(df)} transactions ({len(anomalies)/len(df):.1%})")
    
    return anomalies[['transaction_id', 'date', 'account_number', 
                       'amount', 'description', 'posted_by',
                       'is_off_hours', 'is_round_number', 'anomaly_raw_score']]
```

### MLOps для финансовых моделей

**Триггеры переобучения для финансов:**
| Триггер | Обнаружение | Действие |
|---|---|---|
| Конец периода | Ежемесячный cron | Переобучить на свежих данных закрытия |
| MAPE > 10% | Мониторинг точности прогноза | Немедленное переобучение + алерт |
| Пересмотр бюджета | Ввод от финансовой команды | Переобучить на новой бюджетной базе |
| M&A / выделение | Изменение юрлица в ERP | Полное обновление данных + переобучение |
| Значимое рыночное событие | Порог макроиндикатора | Переобучение + ручная проверка |

**Дашборд мониторинга модели:**
```python
def track_forecast_accuracy(actuals: pd.Series, forecasts: pd.Series) -> dict:
    """
    Track forecast accuracy metrics against finance team targets.
    Target: Revenue +/-5%, Expenses +/-3%
    """
    from sklearn.metrics import (mean_absolute_error, 
                                  mean_absolute_percentage_error,
                                  mean_squared_error)
    
    mae   = mean_absolute_error(actuals, forecasts)
    mape  = mean_absolute_percentage_error(actuals, forecasts)
    rmse  = mean_squared_error(actuals, forecasts, squared=False)
    
    # Bias (over/under forecast)
    bias = (forecasts - actuals).mean()
    bias_pct = bias / actuals.mean()
    
    metrics = {
        'MAE':       f"${mae:,.0f}",
        'MAPE':      f"{mape:.2%}",
        'RMSE':      f"${rmse:,.0f}",
        'Bias':      f"${bias:,.0f} ({bias_pct:+.2%})",
        'On Target': mape <= 0.05,  # Finance team target: +/-5%
    }
    
    return metrics
```

---

## 10. Управление счетами и документами

### Когда использовать
- Организация папки со счетами для подготовки налоговой отчётности
- Стандартизация имён файлов счетов и структуры папок
- Извлечение ключевых данных (поставщик, дата, сумма) из PDF и изображений
- Создание сводного CSV по счетам для бухгалтеров
- Настройка постоянной автоматической организации счетов
- Сверка расходов для возмещения или обработки кредиторки

### Рабочий процесс организации счетов

**Шаг 1. Просканируйте папку**
```bash
# Find all invoice-related files
find . -type f \( -name "*.pdf" -o -name "*.jpg" -o -name "*.png" \) -print
```
Отчёт: общее количество, типы файлов, диапазон дат, текущая организация.

**Шаг 2. Извлеките информацию из каждого файла**

Из PDF (извлечение текста):
- Ищите: `Invoice Date:`, `Date:`, `Issued:`
- Ищите: `Invoice #:`, `Invoice Number:`
- Название компании (обычно сверху)
- `Amount Due:`, `Total:`, `Amount:`
- `Description:`, `Service:`, `Product:`

Из изображений: прочитайте видимый текст, определите поставщика сверху, найдите дату и итог.

Запасной вариант: используйте подсказки из имени файла; проверьте дату изменения файла; пометьте на проверку.

**Шаг 3. Стандартизированный формат имени файла**
```
YYYY-MM-DD Vendor - Invoice - Description.ext

Examples:
2024-03-15 Adobe - Invoice - Creative Cloud.pdf
2024-01-10 Amazon - Receipt - Office Supplies.pdf
2023-12-01 Stripe - Invoice - Monthly Payment Processing.pdf
```

**Шаг 4. Структуры организации**

```
# By Vendor (Simple)
Invoices/
├-- Adobe/
├-- Amazon/
└-- Google/

# By Year and Category (Tax-Friendly — recommended)
Invoices/
├-- 2024/
│   ├-- Software/
│   ├-- Hardware/
│   ├-- Services/
│   ├-- Travel/
│   └-- Office/
└-- 2025/
    └-- ...

# By Quarter (Detailed Tracking)
Invoices/
├-- 2024/
│   ├-- Q1/
│   │   ├-- Software/
│   │   └-- Travel/
│   └-- Q2/

# By Tax Category (Accountant-Ready)
Invoices/
├-- Deductible/
│   ├-- Software/
│   └-- Professional-Services/
├-- Partially-Deductible/
│   └-- Meals-Travel/
└-- Personal/
```

**Шаг 5. Сгенерируйте сводный CSV по счетам**
```csv
Date,Vendor,Invoice Number,Description,Amount,Category,Tax Deductible,File Path
2024-03-15,Adobe,INV-12345,Creative Cloud,52.99,Software,Yes,Invoices/2024/Software/Adobe/...
2024-03-10,Amazon,123-4567890,Office Supplies,127.45,Office,Yes,Invoices/2024/Office/Amazon/...
2024-02-28,Delta Airlines,TICKET-789,Flight NYC-SFO,342.00,Travel,Partial,Invoices/2024/Travel/...
```

**Шаг 6. Итоговая сводка по завершении**
```
Processed:    [X] invoices
Date range:   [earliest] to [latest]
Total amount: $[sum]
Vendors:      [Y] unique vendors

Files needing review: [list files where info couldn't be extracted]
Next steps:
1. Review invoice-summary.csv
2. Check Needs-Review/ folder
3. Import CSV into accounting software
4. Keep originals for 7 years (standard audit period)
```

### Особые случаи

| Ситуация | Решение |
|---|---|
| Нет даты/поставщика | Используйте дату изменения файла; пометьте в папку Needs-Review/ |
| Дублирующие счета | Сравните хеши файлов; оставьте версию лучшего качества; отметьте в CSV |
| Многостраничные счета | При необходимости объедините PDF; используйте единое именование для частей |
| Нестандартные форматы | Извлеките что возможно; пометьте на проверку |
| Загрузки из Gmail вида «invoice.pdf» | Прочитайте каждый файл, чтобы извлечь реального поставщика/дату; переименуйте по содержимому |

### Полезные советы
1. Организуйте ежемесячно, а не раз в год — намного меньше работы за сессию
2. Сохраняйте все счета в одну папку перед пакетной обработкой
3. Сохраняйте оригиналы перед реорганизацией (копируйте, не перемещайте)
4. Помечайте вычитаемость в момент получения, а не в конце года
5. Включайте суммы в CSV для отслеживания бюджета
6. Храните чеки 7 лет (стандартное окно аудита IRS)
7. Для подписок: создайте трекер повторяющихся счетов в CSV

---

## 11. Уникальные возможности Perplexity Computer

Эти возможности доступны только через подключённые инструменты Perplexity Computer и недоступны в Claude Code или других средах.

### Рыночные данные в реальном времени и исторические
```
finance_quotes        → Live prices, P/E, market cap for stocks/crypto/ETFs
finance_ohlcv_histories → Historical OHLCV data as CSV (no web search needed)
finance_market_gainers/losers/most_active → Today's movers
finance_market_sentiment → Aggregate market mood (bullish/bearish/neutral)
finance_ticker_sentiment → Bull/bear analysis per ticker
```

### Отчётность SEC и транскрипты earnings
```
finance_earnings      → Full earnings call transcripts with management Q&A
                        Primary source for:
                        - Forward guidance (revenue ranges, margin targets)
                        - Non-GAAP metrics (adjusted EBITDA, organic growth)
                        - Company-specific KPIs (ARR, GMV, take rate, churn)
                        - Beat/miss vs prior guidance
finance_financials    → Standardized income statement, balance sheet, CF
                        Direct from SEC filings, structured format
finance_segments      → Revenue by segment, unit economics, operating KPIs
finance_estimates     → Analyst consensus forward estimates
finance_analyst_research → Price targets, rating changes, upgrades/downgrades
```

### Биржевая активность Конгресса
```
finance_list_politicians    → All tracked politicians with stock activity
finance_politician_holdings → A specific politician's full portfolio
finance_politician_trades   → Recent congressional transactions
finance_ticker_politician_holders → Politicians holding a specific stock
```

### Продвинутый сырой API (finance_massive)
```
Options chains:     /v3/snapshot/options/{ticker}
Tick-level trades:  /v3/trades/{ticker}
Treasury yields:    /fed/v1/treasury-yields
CPI/Inflation:      /fed/v1/inflation
Labor market:       /fed/v1/labor-market
RSI indicator:      /v1/indicators/rsi/{ticker}
Index aggregates:   /v2/aggs/ticker/{index}/range/{mult}/{timespan}/{from}/{to}
```

### Список наблюдения пользователя
```
finance_watchlist_fetch → Retrieve user's personal watchlist/portfolio
```

### Протокол цитирования
При представлении данных из любого финансового инструмента всегда цитируйте источник:
```
https://perplexity.ai/finance/<TICKER>
Example: "Apple's revenue grew 6% YoY ([Perplexity Finance – AAPL](https://perplexity.ai/finance/AAPL))"
```

---

## 12. Быстрый гид по выбору раздела

Используйте это, чтобы определить, какой раздел применить:

| Запрос пользователя | Раздел для использования | Ключевые инструменты/шаблоны |
|---|---|---|
| «Подготовь отчёт о прибылях и убытках» | §1 Финансовая отчётность | Шаблон ОПУ, таблица коэффициентов |
| «Рассчитай коэффициент P/E» | §1 Финансовая отчётность | Таблица оценочных мультипликаторов |
| «Построй DCF-модель» | §1 Финансовая отчётность | Рабочий процесс DCF + §7 finance_financials |
| «Запиши зарплатную проводку» | §2 Журнальные проводки | Шаблон зарплатной проводки |
| «Начисли невыставленные расходы» | §2 Журнальные проводки | Шаблон проводки начисления |
| «Сверь банковский счёт» | §3 Сверка | Шаблон банковской сверки |
| «Подтверди баланс» | §3 Сверка | Чеклист подтверждения баланса |
| «Спланируй ежемесячное закрытие» | §4 Управление закрытием | Календарь на 15 дней + трекер задач |
| «Объясни, почему не выполнили бюджет» | §5 Анализ отклонений | Шаблон водопада + декомпозиция |
| «Протестируй контроли SOX» | §6 Поддержка аудита | Рабочий лист теста контроля + размеры выборки |
| «Узнай цену акции Apple» | §7 Рынки | finance_quotes (НЕ search_web) |
| «Найди транскрипт earnings Tesla» | §7 Рынки | finance_earnings |
| «Исследуй инвестицию» | §7 Рынки | Шаблон инвестиционного тезиса |
| «Построй дата-пайплайн ГК» | §8 Дата-инжиниринг | dbt-модели + Airflow DAG |
| «Спрогнозируй выручку следующего квартала» | §9 ML и прогнозирование | XGBoost-прогноз + сценарии |
| «Обнаружь подозрительные транзакции» | §9 ML и прогнозирование | Код Isolation Forest |
| «Организуй счета для налогов» | §10 Управление счетами | Рабочий процесс + шаблон CSV |
| «Получи данные опционной цепочки» | §11 Уникальные возможности | finance_massive |
| «Какие политики владеют NVDA?» | §11 Уникальные возможности | finance_ticker_politician_holders |

---

## Приложение A: Краткий справочник финансовых счетов

### Соглашения по номерам счетов (типовой 5-значный план счетов)
```
1XXXX — Assets
  10XXX — Cash & Cash Equivalents
  11XXX — Accounts Receivable
  12XXX — Inventories
  13XXX — Prepaid Expenses & Other Current Assets
  14XXX — Fixed Assets (Gross)
  15XXX — Accumulated Depreciation (contra)
  16XXX — Intangibles & Goodwill
  19XXX — Other Non-Current Assets

2XXXX — Liabilities
  20XXX — Accounts Payable
  21XXX — Accrued Liabilities
  22XXX — Deferred Revenue
  23XXX — Short-term Debt
  24XXX — Long-term Debt
  25XXX — Lease Liabilities
  29XXX — Other Liabilities

3XXXX — Equity
  30XXX — Common Stock & APIC
  31XXX — Retained Earnings
  32XXX — AOCI
  33XXX — Treasury Stock (contra)

4XXXX — Revenue
  40XXX — Product Revenue
  41XXX — Service Revenue
  42XXX — Subscription Revenue
  43XXX — Other Revenue

5XXXX — Cost of Revenue
  50XXX — COGS — Product
  51XXX — COGS — Service

6XXXX — Operating Expenses
  60XXX — Research & Development
  61XXX — Sales & Marketing
  62XXX — General & Administrative
  63XXX — Depreciation & Amortization

7XXXX — Other Income/Expense
  70XXX — Interest Income
  71XXX — Interest Expense
  72XXX — Other Non-Operating

8XXXX — Tax
  80XXX — Income Tax Expense
  81XXX — Deferred Tax
```

---

## Приложение B: Распространённые финансовые сокращения

| Сокращение | Полное название |
|---|---|
| EBITDA | Earnings Before Interest, Taxes, Depreciation & Amortization |
| FCF | Free Cash Flow |
| NWC | Net Working Capital |
| WACC | Weighted Average Cost of Capital |
| CAPM | Capital Asset Pricing Model |
| DCF | Discounted Cash Flow |
| LTM | Last Twelve Months |
| NTM | Next Twelve Months |
| YTD | Year to Date |
| MTD | Month to Date |
| QTD | Quarter to Date |
| YoY | Year over Year |
| QoQ | Quarter over Quarter |
| MoM | Month over Month |
| AR | Accounts Receivable |
| AP | Accounts Payable |
| DSO | Days Sales Outstanding |
| DPO | Days Payable Outstanding |
| DIO | Days Inventory Outstanding |
| CCC | Cash Conversion Cycle |
| NIM | Net Interest Margin |
| ROE | Return on Equity |
| ROA | Return on Assets |
| ROIC | Return on Invested Capital |
| SBC | Stock-Based Compensation |
| CapEx | Capital Expenditures |
| D&A | Depreciation & Amortization |
| GAAP | Generally Accepted Accounting Principles |
| ASC | Accounting Standards Codification |
| PCAOB | Public Company Accounting Oversight Board |
| SOX | Sarbanes-Oxley Act |
| MW | Material Weakness |
| SD | Significant Deficiency |
| PBC | Prepared by Client |
| ETL | Extract, Transform, Load |
| ELT | Extract, Load, Transform |
| dbt | Data Build Tool |
| MAPE | Mean Absolute Percentage Error |
| PSI | Population Stability Index |
| ARR | Annual Recurring Revenue |
| MRR | Monthly Recurring Revenue |
| CAC | Customer Acquisition Cost |
| LTV | Lifetime Value |
| NRR | Net Revenue Retention |
| GMV | Gross Merchandise Value |
