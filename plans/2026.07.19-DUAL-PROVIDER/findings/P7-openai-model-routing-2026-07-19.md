# P7 finding — current OpenAI model routing

**Проверено:** 2026-07-19  
**Источник:** https://developers.openai.com/api/docs/models  
**Дополнительные страницы:** https://developers.openai.com/api/docs/models/gpt-5.6-sol ·
https://developers.openai.com/api/docs/models/gpt-5.6-terra ·
https://developers.openai.com/api/docs/models/gpt-5.6-luna  
**Метод:** official-domain web fallback; OpenAI Developer Docs MCP не был доступен в сессии.  
**Confidence:** medium — один первичный vendor source, страницы семейства согласованы.

## Повторная проверка pass 3/3

**Проверено:** 2026-07-19  
**Источники:** https://developers.openai.com/api/docs/models ·
https://developers.openai.com/api/docs/models/gpt-5.6-terra  
**Метод:** official-domain search + direct open двух primary vendor pages; OpenAI Developer
Docs MCP не был выставлен в текущей сессии.  
**Confidence:** high — общий официальный catalog и отдельная Terra model page согласованы.

Повторно подтверждены exact IDs `gpt-5.6-sol`/`gpt-5.6-terra`, role split
complex reasoning/coding vs balanced intelligence/cost и reasoning efforts
`medium`/`high`/`xhigh`. Изменение plan Routing не требуется; доступность IDs в аккаунте
владельца остаётся runtime gate и не выводится из публичного каталога.

## Проверенные факты

- OpenAI рекомендует GPT-5.6 Sol как flagship для complex reasoning и coding.
- GPT-5.6 Terra позиционируется как баланс intelligence/cost и соответствует implementation-tier.
- GPT-5.6 Luna позиционируется для cost-sensitive high-volume workloads; это не основание
  направлять на неё correctness-critical contracts, security или release audit.
- Sol, Terra и Luna поддерживают reasoning efforts `none`, `low`, `medium`, `high`, `xhigh`,
  `max`; выбор effort остаётся независимым от model tier.

## Вердикт для плана

- Design/contract/adversarial audit с открытыми решениями или высокой ценой ошибки:
  `gpt-5.6-sol/high|xhigh`.
- Prescribed implementation против frozen contracts: `gpt-5.6-terra/high`.
- Deterministic implementation/docs/conformance: `gpt-5.6-terra/medium`.
- `gpt-5.6-luna` не используется в текущих items: даже механические slices входят в
  public-contract/release critical path и требуют Terra review floor.
- Финальный cross-phase `finish` и design audit: `gpt-5.6-sol/xhigh`; `max` не нужен,
  потому что это verification уже спроектированных contracts, а не новый irreversible design.

## Проверка (verification status)

- RAG: official OpenAI web — pass 1 discovery/open + pass 3 direct open двух primary pages — OK.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: доступность конкретных model IDs в аккаунте владельца;
  plan execution обязан fail closed при недоступности, а не молча downgrade.
- Обходки/[POSSIBLE-DEFECT]: Docs MCP отсутствовал; использован разрешённый official-domain
  fallback. Package/API behavior не выводился из search snippets.
