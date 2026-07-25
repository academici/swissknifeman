# 2026.07.25-ECO-OPT — волна оптимизаций экосистемы: хвосты, Claude 5, память между машинами, код-граф, контекст-гигиена

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.07.25-ECO-OPT |
| Title | Волна оптимизаций: закрытие хвостов TOKEN-ECON/CONTEXT-ECONOMY, Claude 5 guidance, cross-machine память mAInd, пилот code-review-graph, контекст-гигиена, Codex-делегирование |
| Version | 0.1.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | Claude Fable 5/high (design pass 1) |
| Last Updated | 2026-07-25 |
| Repository | swissknifeman |
| Related Packages | skiller, harness, maind, task, analyst |
| Execution Mode | phase-first |
| Target Operator Models | Claude: frontier→Opus 5 · implementation→Sonnet · economy→Haiku (SSOT-матрица plan-protocol §9) |
| Approval Owner | Dmitry Vostrikov |
| Home | repo:/home/vostrikov/projects/packages/swissknifeman |
| supersedes | 2026.07.15-TOKEN-ECON-P6 |
| Paused By | — |
| Design Passes | 1/2 — 7 фаз/16 items → N=2; pass 1 = скелеты+контракты+RAG-финдинги+детализация P1; pass 2 = детализация P2–P7 до DoR + finish + roadmap |

## 1. Context

Владелец дал волну из 13 идей (brief/00-brief.md): внешние находки (код-граф
для ревью, obsidian-mind, i-have-adhd, wshobson/agents, codex-plugin-cc),
выход Opus 5 с официальным prompting-гайдом, проблема работы с нескольких
машин, дыры в perplexity-дисциплине и контекст-гигиене, плюс требование
закрыть незавершённые планы `2026.07.15-TOKEN-ECON-P6` (перенос P6.2/P7–P9
сюда, supersedes) и `2026.07.12-CONTEXT-ECONOMY` (терминален, архив).
RAG-разведка выполнена в pass 1 (`findings/rag-2026-07-25.md`): все 5 реп
верифицированы GitHub API, Opus 5 гайд прочитан first-party, Claude Code
факты по контексту/compact сняты по доке. Очередь исполнения: план идёт
ПОСЛЕ ремонта `2026.07.24-AGENT-RELIABILITY` (ACTIVE, там A1-аудит →
G-EXEC → exec) — кроме независимых P1/P4, которые могут идти параллельно;
`2026.07.18-FOREMAN` — после обоих (гейт G1 AGENT-RELIABILITY решает его
продолжение). Итог плана — работающие механизмы, не доки-ради-док.

## 2. Execution Rules

- Один item за раз; статус в плане обновляется до завершения работы; статусы
  — 6 канонических строк байт-в-байт.
- **stdlib-only** в python-пакетах SKM; внешние MCP-серверы (code-review-graph)
  — внешние процессы, НЕ зависимости пакетов.
- Внешние факты — RAG-лестница (context7 → perplexity-web агрессивно →
  WebSearch); репы — только GitHub API/прямое чтение (дисциплина D19
  FOREMAN); поведение Claude Code — только first-party дока.
- Coupling с AGENT-RELIABILITY: его P2.2 бампает plan-protocol/task-команды —
  items P2.2 и P7.1 этого плана НЕ стартуют, пока фаза P2 AGENT-RELIABILITY
  не терминальна (cross-plan gate §11); при конфликте эскалация, не мерж.
- Правки скиллов: SKILL.ru.md → SKILL.md → `check-translations.sh --stamp` →
  `skiller registry`; после always-on правок — `skiller budget --first-turn`.
- Owner-гейты: P3.3 (решения OQ-4/OQ-5), P4.1 (ADR памяти), P5.2 (adopt/skip
  код-графа), P7.2 (Codex-профиль). Остальное — без остановок.
- Коммиты — Conventional Commits (рус.), item-топология из plan-protocol §8.

## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
| | P1.1 | frontier/high | manual | full | GATED-вердикт по first-party доке (перенос TOKEN-ECON P6.2) |
| B1 | P1.2 | implementation/medium | plan-exec | light | канон-строка + механический бэкфилл ссылок |
| | P2.1 | implementation/medium | plan-exec | light | выжимка first-party гайда в Brain — компиляция, решений нет |
| | P2.2 | frontier/high | manual | full | правка канон-команд task под Opus 5 — несущие директивы, cross-plan gate |
| B2 | P3.1 | implementation/medium | plan-exec | full | замер N + сжатие описаний (экс-P7 TOKEN-ECON), детерминированные гейты |
| B2 | P3.2 | implementation/medium | plan-exec | full | maind trimming (экс-P8), stdlib, детерминированная Validation |
| | P3.3 | frontier/high | manual | full | owner-решения OQ-4/OQ-5 (экс-P9) — не выводятся агентом |
| | P4.1 | frontier/high | manual | full | ADR cross-machine памяти (вариант 1 D12) — несущий дизайн, сетевой контур доверия |
| | P4.2 | implementation/high | manual | full | реализация в maind: демон-хост + клиенты — ядро памяти экосистемы |
| | P4.3 | implementation/medium | plan-exec | full | rollout вторая машина + doctor-гейты |
| | P5.1 | implementation/high | manual | full | пилот code-review-graph: замеры против Serena на живых проектах |
| | P5.2 | frontier/high | manual | full | вердикт adopt/skip + mcp-advisor — owner-гейт |
| B3 | P6.1 | implementation/high | manual | full | statusline context-notify в harness — новый always-on механизм |
| B3 | P6.2 | implementation/medium | plan-exec | light | compact-дисциплина в скиллах (context-economy/plan-protocol заметка) |
| B3 | P6.3 | implementation/high | manual | full | verify-claims анти-overconfidence + pressure-evals |
| | P7.1 | implementation/high | manual | full | codex-plugin-cc + маршрутизация лёгких задач; после AGENT-RELIABILITY P1/P2 |
| | P7.2 | frontier/high | manual | full | Codex-профиль (тонкий AGENTS.md слой) — по итогам пилота P7.1 |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P1 | Хвосты: tool-search вердикт + канон план-ссылок | 0/2 | ⬜ Not started |
| P2 | Claude 5 / Opus 5 guidance (Brain + ревизия команд) | 0/2 | ⬜ Not started |
| P3 | Перенос TOKEN-ECON: описания, maind-тримминг, owner-решения | 0/3 | ⬜ Not started |
| P4 | Cross-machine память mAInd (демон-хост + Tailscale/LAN) | 0/3 | ⬜ Not started |
| P5 | Пилот code-review-graph vs Serena | 0/2 | ⬜ Not started |
| P6 | Контекст-гигиена: notify + compact-дисциплина + anti-overconfidence | 0/3 | ⬜ Not started |
| P7 | Codex-делегирование (codex-plugin-cc + профиль) | 0/2 | ⬜ Not started |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-25 | Идеи волны оформлены ОТДЕЛЬНЫМ планом, не встроены в AGENT-RELIABILITY: тот заморожен строгой authority-цепочкой (A1-аудит → G-EXEC) и посвящён reliability-механике; смешивание сорвало бы его аудит-слоты. | RAG:— (repo-grounded: AGENT-RELIABILITY plan.md §10, D32). |
| D2 | 2026-07-25 | supersedes 2026.07.15-TOKEN-ECON-P6: его незакрытые P6.2/P7/P8/P9 перенесены как P1.1/P3.1/P3.2/P3.3; предшественник в архив. 2026.07.12-CONTEXT-ECONOMY терминален сам по себе → архив без переноса (его Pending Work — кандидаты сюда не включены, кроме уже покрытых: prosить их отдельно по field-feedback). | RAG:— (repo-grounded: TOKEN-ECON plan.md §4; CONTEXT-ECONOMY handoff «все 8 фаз терминальны»). |
| D3 | 2026-07-25 | Коллизия ссылок на планы в коде решается КАНОНОМ «полный PLAN-ID» (`<PLAN-ID> Pn.m`), а не внутренним порядковым номером: второй ID-неймспейс = второй носитель факта; архивирование планов СОХРАНЯЕТСЯ — каталог `plans/archive/<ID>` держит ID, grep по ID находит план в обоих домах. Ссылки по пути `plans/<ID>/...` в коде заменяются на ID-форму. | RAG:— (repo-grounded: голые `P4.3`/`P5.2` в analyst/harness lib; §12 plan-protocol «планы не удаляются»); брифо-идея 5. |
| D4 | 2026-07-25 | Cross-machine память = вариант 1 roadmap-стаба (`roadmap/cross-machine-memory.md`, D12 CONTEXT-ECONOMY): единственный живой демон agentmemory на always-on хосте + остальные машины MCP-клиентами через Tailscale/LAN; критерий активации стаба сработал (несколько постоянных машин). obsidian-mind как механизм памяти — skip (дублирует maind+Brain). | RAG:✅ 2026-07-25 perplexity (гибрид: durable=self-hosted сервис, git-vault для human-curated; `findings/rag-2026-07-25.md` §4.2) + RAG:— (repo-grounded: roadmap-стаб, запрет file-sync SQLite). |
| D5 | 2026-07-25 | Opus 5 guidance: выжимка в Brain (model-notes, как для Fable 5) + ТОЧЕЧНАЯ ревизия task-команд/agent-packs на анти-паттерны (явные verify/double-check инструкции для Opus-pinned команд, effort-дефолты, subagent-капы). В evergreen-скиллы модель-специфику не размазываем (волатильна). | RAG:✅ 2026-07-25 first-party guide (`findings/rag-2026-07-25.md` §3); брифо-идея 4. |
| D6 | 2026-07-25 | Гипотеза «детализация фазы после предыдущей» уже покрыта каноном plan-protocol (contract-first скелеты + reconcile at detailing + JIT-детализация через D-запись); «согласование до кодинга» = owner-гейты в design-фазах. Изменений канона не требуется — зафиксировано как разъяснение. | RAG:— (repo-grounded: plan-protocol §5 contract-first, D-canon 2026-07-16). |
| D7 | 2026-07-25 | OS-уведомление о высоком контексте — ТОЛЬКО через statusline-скрипт harness (видит `context_window.used_percentage`, event-driven, троттлинг), НЕ hook: hooks context-полей не получают, PreCompact-события в актуальной доке нет; «агент сам предлагает compact» — эвристикой по типу задачи в скиллах (модель фактический % не видит). | RAG:✅ 2026-07-25 first-party дока via claude-code-guide (`findings/rag-2026-07-25.md` §5). |
| D8 | 2026-07-25 | i-have-adhd — skip как зависимость (дублирует lean output style + `core:compact-responses`); 1–2 правила (answer-first, no closers) — кандидаты в правку compact-responses при P6.2, по месту. wshobson/agents — reference: паттерны quality-gates (LLM judge + Monte Carlo) и `make garden` drift-детект — кандидаты в skiller eval (не в этот план, roadmap). | RAG:✅ 2026-07-25 GitHub API + README (`findings/rag-2026-07-25.md` §1–2). |
| D9 | 2026-07-25 | Инцидент «Codex тупил неделю»: по RAG — не «SKM вреден», а (а) duplicate-identity коллизии (чинит AGENT-RELIABILITY P1) и (б) отсутствие enforcement (его P2); спецнастройка Codex = тонкий слоёный AGENTS.md + dedup. Поэтому P7 (делегирование Codex) гейтится на терминальность P1/P2 AGENT-RELIABILITY. | RAG:✅ 2026-07-25 perplexity web+social (`findings/rag-2026-07-25.md` §4.1). |
| D10 | 2026-07-25 | Очередь планов: AGENT-RELIABILITY (ACTIVE) → ECO-OPT (P1/P4 могут идти параллельно — не трогают task/skiller канон) → FOREMAN (после G1; его P1.4 разблокирован терминальностью DUAL-PROVIDER — waiting-условие снято). | RAG:— (repo-grounded: DUAL-PROVIDER handoff «план закрыт»; FOREMAN handoff waiting-условие; AGENT-RELIABILITY Execution Rules «FOREMAN не исполнять»). |

Coupling-поверхность: канон plan-protocol/task-команды (P2.2, P6.2, P6.3 ↔
AGENT-RELIABILITY P2.2 — самый горячий hotspot, cross-plan gate в §2);
скилл `mcp-advisor` (P5.2 ↔ P6-правки скиллов); harness configs (P6.1 ↔
agent-packs); maind (P3.2 ↔ P4.2 — оба правят lib/maind, последовательно).

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-25 | plan-design/Claude Fable 5 | Design pass 1/2: brief + RAG-финдинги (5 реп GitHub API, Opus 5 guide, CC-факты, 2 perplexity-синтеза), 7 фаз/16 items (P1 детализирована, P2–P7 скелеты с контрактами), Обсуждение (7 развилок), D1–D10. Supersedes TOKEN-ECON-P6. |

## Обсуждение

### 1 — Память для нескольких машин: obsidian-mind vs agentmemory-хостинг
- **(рекоменд.) Вариант A. Демон agentmemory на always-on хосте + Tailscale/LAN** (вариант 1 roadmap-стаба). Плюсы: единственный писатель (нет конкурентной записи), namespace/audit сохраняются, консенсус-паттерн индустрии, реюз готового maind. Минусы: офлайн-машина без памяти; хост держать живым; контур доверия (ACL).
- **Вариант B. obsidian-mind (git-vault память).** Плюсы: офлайн, human-readable, простой синк. Минусы: дублирует maind+Brain; merge-конфликты при мульти-агентных записях; вторая система памяти = дрейф; TS/Node-стек.
- **Вариант C. Export/import событий** (вариант 2 стаба). Плюсы: офлайн. Минусы: свой протокол+конфликт-резолвер, задержка синка.
**Статус:** Resolved → D4 (A; C остаётся fallback в стабе, если хост окажется непрактичным — фиксируется в ADR P4.1).

### 2 — code-review-graph: MCP vs наши ревью-скиллы vs комбинация
- **(рекоменд.) Пилот-комбинация.** MCP-граф как retrieval-слой ПОД ревью-скиллы (`/task:review` Stage A/B читают через граф-тулы), Serena остаётся для symbol-точных операций. Замерить экономию на 1–2 живых проектах, потом решать. Плюсы: числа вместо веры (заявка 82× — самозамер автора). Минусы: +1 резидентный MCP (контекст-цена тулов, гейт budget --first-turn).
- **Вариант B. Сразу adopt вместо Serena.** Минусы: недоказанная точность (F1 0.71, circular ground truth), потеря LSP-точности.
- **Вариант C. Skip.** Минусы: потенциально крупнейший token-рычаг волны не проверен.
**Статус:** Exploration (решается P5.1→P5.2, owner-гейт) — см. open-questions.md OQ-1.

### 3 — Идентификация планов в коде: внутренний номер vs полный PLAN-ID
- **(рекоменд.) Полный PLAN-ID** в ссылках из кода (`2026.07.15-TELEMETRY-OPT P1.2`, не голое `P1.2`); архив сохраняется (ID в пути живёт). Плюсы: ноль новых механизмов, grep-надёжно. Минусы: длиннее.
- **Вариант B. Внутренний порядковый номер в шаблоне.** Минусы: второй ID-неймспейс (дрейф, коллизии между репо), ручная нумерация.
- **Вариант C. Не архивировать планы.** Минусы: ломает конвейер план→архив→docs; проблема была не в архиве, а в голых Pn.m.
**Статус:** Resolved → D3.

### 4 — Opus 5 рекомендации: скиллы vs Brain
- **(рекоменд.) Brain-выжимка + точечные правки команд** (D5). Плюсы: model-специфика волатильна — ей место в model-notes; команды правятся только там, где сейчас есть анти-паттерн. Минусы: два места (нота + правки).
- **Вариант B. Встроить в скиллы.** Минусы: скиллы evergreen и мульти-модельные; при смене поколения моделей — массовая чистка.
**Статус:** Resolved → D5.

### 5 — Детализация фаз: upfront vs после предыдущей фазы
- Канон УЖЕ даёт средний путь: contract-first скелеты на `new`, полная детализация до exec — дефолт, JIT-детализация — по явной D-записи для волатильных фаз; reconcile при детализации ловит расхождения. «Согласование до кодинга» = owner-гейты внутри design-фаз (уже практика).
**Статус:** Resolved → D6 (изменения канона не требуются).

### 6 — Compact-уведомления: hook vs statusline vs эвристика агента
- **(рекоменд.) Statusline-скрипт** (единственный документированный носитель `context_window.*`) + скилл-эвристика «объёмная фаза → предложи /clear-границу» (P6.1/P6.2). Плюсы: first-party подтверждено. Минусы: statusline-скрипт должен остаться дешёвым.
- **Вариант B. Hook.** Отклонён: hooks context-полей не получают, PreCompact в доке нет (D7).
**Статус:** Resolved → D7.

### 7 — Codex: делегировать ли лёгкие задачи после недели «тупления»
- **(рекоменд.) Гейтированный пилот.** Сначала AGENT-RELIABILITY P1 (dedup identities) + P2 (enforcement) терминальны, потом codex-plugin-cc на лёгких/механических задачах с ревью Claude; вердикт по факту (P7.1), профиль — P7.2. Плюсы: причины «тупления» адресованы до пилота (D9). Минусы: отложенный выигрыш.
- **Вариант B. Делегировать сразу.** Минусы: повторит инцидент — усилители не устранены.
- **Вариант C. Отказаться от Codex.** Минусы: теряется дешёвый слой для рутины; ресурсы Claude важнее (директива владельца).
**Статус:** Exploration (вердикт — P7.1) — см. open-questions.md OQ-2.
