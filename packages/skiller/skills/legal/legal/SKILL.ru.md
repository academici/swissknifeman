> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: legal-super-skill
bucket: legal
version: 1.0.0
description: Comprehensive legal operations skill merging Perplexity Computer's 6 legal skills with Claude Code's writing, communications, and planning skills. Covers contract review, NDA triage, compliance (GDPR/CCPA), risk assessment, meeting briefings, canned responses, legal writing, internal communications, and structured planning. Use for contract analysis, NDA screening, compliance reviews, risk assessments, legal meeting prep, response drafting, or any legal operations work.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Юридический супер-скилл — навигатор

Единый справочник по юридическим операциям для внутренних юридических команд.
Полное тело (~2100 строк) — в [`references/full.md`](references/full.md).
**Открывай точечно нужный раздел по якорю под конкретный вопрос, не целиком.**

> Операционный скилл. Для чек-листов дизайн-тайм комплаенса при архитектурной
> работе — `architect/legal-compliance`.

## Карта разделов ([`references/full.md`](references/full.md))

| Задача | Раздел |
|:--|:--|
| Карта покрытия по исходным скиллам | §1 Gap Analysis |
| Анализ договоров, чек-лист клаузул, редлайны, приоритеты переговоров | §2 Contract Review & Redlining |
| Триаж NDA, правила GREEN/YELLOW/RED, стандартные позиции | §3 NDA Triage & Classification |
| Памятки GDPR/CCPA, чек-лист DPA, воркфлоу DSR | §4 Compliance & Privacy |
| Матрица severity×likelihood, риск-меморандум, реестр, внешние юристы | §5 Risk Assessment & Escalation |
| Стандарты письма, форматы статусов/лидерства/инцидентов, шаблонные ответы | §6 Legal Writing & Communications |
| Подготовка встреч, шаблон брифинга, трекинг действий | §7 Meeting Briefings & Action Tracking |
| Чек-листы верификации перед сдачей, дисциплина QA | §8 Verification & Quality Assurance |
| Возможности, уникальные для Perplexity Computer | §9 Unique Perplexity Computer Capabilities |
| Дополнительные шаблоны и чек-листы | §10 Extended Templates & Checklists |
| Флоучарты решений (договор/NDA/эскалация) | §11 Decision Flowcharts |
| Интеграция с legal-tech стеком (CLM) | §12 Integration with Legal Tech Stack |
| Стандартные определения | Приложение A |
| Справочник регуляторов (EDPB/CNIL/ICO/FTC/…) | Приложение B |

## Ключевой принцип

Любой юридический результат — редлайн, классификация NDA, риск-меморандум,
комплаенс-ответ, брифинг к встрече — обязан быть конкретным, подкреплённым
доказательствами, действенным и верифицированным (§8) перед сдачей.

## Сопровождение (для мейнтейнеров реестра)

Апстрим `strategy: notify`; отслеживаемое тело — `references/full.md`. SKILL.md
написан вручную — `scripts/update-upstreams.sh` его не перезаписывает. Полный
русский перевод тела удалён при переносе на thin-navigator (P2.3
SKM-MASTER-003) — доступен в git-истории этого файла.
