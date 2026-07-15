# P5.2 — Внешний RAG-развед best-practices токен-экономии (2026)

**Дата:** 2026-07-15 · **Исполнитель:** manual/fable/medium · **Движки:** context7 (промах —
monthly quota exceeded, keyless-тир) → `perplexity-web` (6 последовательных `search`, без
параллели по правилу item'а). WebSearch не понадобился.

Каждая практика сверена с рамками репо (CLAUDE.md «Философия и рамки»): stdlib-only ·
MCP-модель (maind per-project) · кэш-профиль (cache_hit ≈ 100%, промахов 0/114 —
`findings/telemetry-baseline.md`) · запрет always-on инжекта без `skiller budget`-гейта ·
`docs/rejected-optimizations.md` (дубли не переоткрыты).

## Сводка кандидатов

| # | Практика | Вердикт | Куда бьёт |
|:--|:--|:--|:--|
| C1 | Prompt-cache структурирование + TTL 5m/1h | **reference** (рычага нет — кэш уже здоров) | — |
| C2 | Context compaction/pruning дисциплина (/compact ~60%, /clear на смене задачи) | **reference** (уже адоптировано в `context-economy`) | CORE-скилл |
| C3 | Sub-agent context isolation (thin orchestrator, summary-return) | **reference** (подтверждает архитектуру task/workflow-craft) | workflow-craft |
| C4 | Tool-result trimming: лимиты/пагинация/truncation-receipts в MCP-ответах | **adopt-кандидат** (в backlog P5.3) | maind MCP-тулы |
| C5 | MCP tool-def deferred loading + лимит резидентных серверов | **adopt-кандидат** (в backlog P5.3; пара к К1 из P5.1) | mcp-advisor / онбординг |
| C6 | Tiered model-routing («не даунгрейдить ревьюеров ниже mid-tier») | **reference** (подтверждает D8/D9-политику P3) | docs/routing.md |
| C7 | Runtime cascade-router (cheap-first, авто-эскалация per request) | **skip** → rejected-optimizations | — |
| C8 | Внешний vector-store слой памяти для context offload | **skip** → rejected-optimizations | — |

## Карточки

### C1 — Prompt-cache структурирование и TTL — reference
RAG:✅ 2026-07-15 `perplexity-web` (Anthropic docs, platform.claude.com/docs/en/build-with-claude/prompt-caching,
upd. 2026-02-05; aws.amazon.com Bedrock 1h-caching 2026-01).
Факты: TTL ровно два — `5m` (write 1.25×) и `1h` (write 2×), read 0.1×; refresh-on-read; порядок
префикса tools → system → messages, до 4 breakpoints; при смешении TTL длинный раньше короткого;
для сессий с паузами >5 мин рекомендован 1h-TTL на общий префикс.
**Сверка:** телеметрия репо — cache_hit ≈ 100%, low-cache 0/114 → кэш-профиль уже оптимален,
рычага нет. Структура префикса управляется Claude Code, не нами (мы не строим API-запросы).
**Вердикт:** reference — знание для routing-прозы; никаких правок. Действие не требуется.

### C2 — Context compaction/pruning дисциплина — reference (уже адоптировано)
RAG:✅ 2026-07-15 `perplexity-web` (buttondown.com/redpen «/clear vs /compact» 2026-06-02;
atlassian.com Rovo Dev context pruning 2026-04-19; zylos.ai agent context compaction 2026-04-21;
howdoiuseai.com 2026-04-16).
Факты: индустрия сошлась на «/compact в пределах одной фичи (~60% контекста, до авто-компакта
на ~83–85%), /clear на смене задачи»; summarize-then-continue + observation-masking (дроп
низкосигнальных tool-результатов); компакт недетерминирован — для трассируемости внешние логи.
**Сверка:** CORE-скилл `context-economy` уже несёт /compact-vs-/clear и Plan→Clear→Execute —
практика адоптирована ДО этого разведа; новых обязательных элементов нет (порог «~60%» —
косметика, не входит в официальный контракт).
**Вердикт:** reference — подтверждение канона `context-economy`; правка скилла не требуется.

### C3 — Sub-agent context isolation — reference (подтверждает архитектуру)
RAG:✅ 2026-07-15 `perplexity-web` (code.claude.com/docs/en/sub-agents; spring.io agentic patterns
2026-01-27; agentic-design.ai context-isolate-patterns; inngest.com three-patterns).
Факты: субагент = чистый контекст, шумный I/O — в воркеры, наверх — компактный структурный
summary; НО суммарные сырые токены растут (репорты ~10–15× против одиночного чата) — выгода
только когда воркер-контексты короче замещаемой монолит-сессии; анти-паттерн — оркестрировать
тривиальные задачи.
**Сверка:** task-команды уже так устроены (`task:fix` — single-agent token-frugal; workflow-craft —
summary-return, «субагенты возвращают данные, не прозу»). Анти-паттерн «over-orchestration»
покрыт правилом «Scale to what the user asked» + пинами per-команда. P1 (D7) показал реальный
токен-жор не от изоляции, а от resume-циклов отладки — отдельный, уже закрытый кластер.
**Вердикт:** reference — внешнее подтверждение принятой архитектуры; действий нет.

### C4 — Tool-result trimming в MCP-ответах — adopt-кандидат (backlog P5.3)
RAG:✅ 2026-07-15 `perplexity-web` (dev.to «MCP Tool Output Budget Checklist» 2026-05-16;
tianpan.co «Silent Tool Truncation» 2026-05-09; agentpatterns.ai «Graceful Tool-Output
Truncation / PARTIAL signal» 2026; blog.firetiger.com large tool results 2026-03-24).
Факты: молчаливое обрезание tool-выхлопа = баг-класс (модель галлюцинирует поверх невиденного);
best practice — per-tool потолок + явный `truncated: true`/PARTIAL-маркер + continuation-handle;
JSON-конверт с `total/returned/next_offset`; большие тела — в артефакты, в ответ — хэндл+превью.
**Сверка:** прямо применимо к maind MCP-тулам (`maind_memory_recall`, `maind_graph_*` могут
возвращать длинные списки). stdlib-only не нарушается (правка Python-ответов сервера). Это НЕ
always-on инжект (наоборот, режет payload) — budget-гейт не задевает.
**Вердикт:** adopt-кандидат: item-кандидат «аудит размеров ответов maind MCP-тулов + потолок с
явным truncation-receipt». Экономия не измерена (нужен замер фактических размеров recall-ответов) —
ROI считает P5.3.

### C5 — MCP tool-def deferred loading + лимит серверов — adopt-кандидат (пара к К1)
RAG:✅ 2026-07-15 `perplexity-web` (paddo.dev «Claude Code hidden MCP flag» 2025-12-28/upd.
2026-02; reddit.com/r/mcp case study «92% cut» 2026-04-13; mindstudio 2026-04-01; getunblocked
2026-05-13).
Факты: резидентные tool-схемы MCP жгут 18–67K ток/сессию (GitHub MCP один ~42K); progressive
disclosure / Tool Search (ленивые схемы) режет overhead на ~85–100%; в Claude Code заявлен
`ENABLE_TOOL_SEARCH` в settings.json (источник — блог paddo.dev, не first-party дока —
`[UNVERIFIED]` до проверки по официальному спеку перед внедрением); базовая рекомендация —
жёстко лимитировать число подключённых серверов per-project, неиспользуемые отключать.
**Сверка:** бьёт точно в К1 из P5.1 (MCP tool-defs 2250→10650 ток, 35% итога dterema/app,
7 резидентных серверов). «Лимит серверов» уже канон `mcp-advisor` («обоснованный план
подключения, не дамп всех серверов») — усилить числами К1. Deferred loading — настройка
клиента Claude Code (не наш рантайм), stdlib-рамку не задевает; раскатка через harness-пресеты
возможна ПОСЛЕ верификации флага по first-party доке.
**Вердикт:** adopt-кандидат, самый высокий потенциал (измеренный резидент уже есть у К1):
(а) число-подкреплённая прополка MCP-серверов на жирных проектах; (б) проверить
`ENABLE_TOOL_SEARCH` по официальной доке → при подтверждении — кандидат в harness-пресет.
ROI и порядок — P5.3.

### C6 — Tiered model-routing — reference (подтверждает P3)
RAG:✅ 2026-07-15 `perplexity-web` (augmentcode.com routing guide 2026-04-11; agentpatterns.ai
cost-aware agent design 2026-02-18; dev.to «$87K→$24K» 2026-05-19; tianpan.co cascade-trap
2026-04-22).
Факты: канон 2026 — frontier на планирование/ревью, mid-tier на имплементацию, small на
механику; явное правило «не даунгрейдить ревьюеров ниже mid-tier»; даунгрейд review/design/critic
ролей даёт измеримо худший defect-detection; экономия 40–85% при сохранении качества — только
с оценкой качества (A/B), не вслепую.
**Сверка:** ровно политика P3 (D8/D9): keep-Opus на design/plan-audit/review
(correctness-critical, Owner-гейт), downgrade dev/make-workflow → sonnet. Внешний канон
подтверждает и pre-mortem D8 («тихий downgrade ревью — деградация, никем не замечаемая»).
**Вердикт:** reference — внешняя валидация `docs/routing.md` «Model-routing пинов task-команд»;
правок нет.

### C7 — Runtime cascade-router — skip
RAG:✅ 2026-07-15 `perplexity-web` (arxiv.org/html/2604.03527v1 explainable routing 2026-03-25;
tianpan.co «cascade-router reliability trap» 2026-04-22).
Факты: cascade «cheap-first, эскалация по low-confidence» — доминирующий паттерн router-слоя;
НО наивные каскады тихо деградируют надёжность (ошибки дешёвой модели загрязняют логи/эксперименты,
бимодальная латентность).
**Сверка с рамками:** (1) нет first-party API смены модели/effort сессии изнутри — уже
верифицировано и записано (`docs/reference.md` строка code.claude.com, 2026-07-15;
`docs/rejected-optimizations.md` «авто-делегация с model/effort из §3»); (2) router-слой =
новая рантайм-сущность (зеркало отклонённого демона analyst); (3) наш routing статичен и
прозрачен — пины per-команда + §3 Routing планов, качество держат Owner-гейты.
**Вердикт:** skip → строка в `docs/rejected-optimizations.md`.

### C8 — Внешний vector-store слой памяти для context offload — skip
RAG:✅ 2026-07-15 `perplexity-web` (zylos.ai agent context compaction 2026-04-21; firetiger/
sourcegraph context engineering 2026-05-27 — «older turns → external vector/KV store, retrieval
по запросу»).
Факты: индустрия выносит старые ходы/трейсы в векторные хранилища с retrieval вместо раздувания
окна.
**Сверка с рамками:** vector-store = pip/JS-рантайм зависимость → авто-skip (stdlib-only —
жёстко, правило item'а); функциональная ниша уже закрыта mAInd-памятью (namespace recall через
MCP) + session-handoff скиллом — off-context знание с явным retrieval уже есть, без новой
зависимости.
**Вердикт:** skip → строка в `docs/rejected-optimizations.md`.

## Проверка

- Проверено: C1–C8 — все несущие вердикты на `perplexity-web` 2026-07-15 (6 запросов,
  последовательно), источники и даты в карточках; сверка с рамками — repo-grounded
  (CLAUDE.md, telemetry-baseline, rejected-optimizations, reference.md).
- Непроверенное: `ENABLE_TOOL_SEARCH` (C5) — единственный источник блог paddo.dev, first-party
  докой не подтверждён → `[UNVERIFIED]`, помечен как обязательная пред-проверка перед внедрением
  (ПОВТОРНЫЙ ПРОХОД по официальному споку на фазе реализации). context7 недоступен (quota) —
  ступень задокументирована, фолбэк штатный.
- Обходок-`[POSSIBLE-DEFECT]` нет; один запрос (`model-routing`) вернулся деградированным
  (голые источники без фактов) — переспрошен follow-up'ом, результат полный.
