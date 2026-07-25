# HANDOFF — 2026-07-25 — after P0.0

Стартовый handoff: план создан design pass 1/2 (скелеты+контракты+RAG,
P1 детализирована). Исполнение НЕ начато; ACTIVE остаётся
2026.07.24-AGENT-RELIABILITY (очередь — D10).

**Next:** design-phase: task:plan-design 2026.07.25-ECO-OPT P2

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | — |
| Context | cold-start — plan-step |
| Суть | Design pass 2/2: детализация P2–P7 до DoR (по фазе на заход), затем finish + roadmap |

````
/task:plan-design 2026.07.25-ECO-OPT P2

РЕЖИМ: детализация скелет-фазы (design pass 2/2 начинается с P2; далее P3–P7 отдельными заходами, затем `finish`)
ВХОД: plans/2026.07.25-ECO-OPT/brief/00-brief.md → plans/2026.07.25-ECO-OPT/findings/rag-2026-07-25.md → plan.md (D1–D10, Обсуждение) → phases/P2.md (контракт-блок)
СКОУП: 1) развернуть items фазы по 16-полевой схеме против контракт-блока; 2) reconcile Потребляет↔Производит с закрытыми фазами; 3) DoR-чеклист фазы
НЕ ТРОГАТЬ: закрытые D-записи; brief; findings pass 1; канон plan-protocol (cross-plan gate с AGENT-RELIABILITY P2.2)
````

**Done:** Design pass 1/2 (Claude Fable 5): brief (13 идей владельца без
потери мысли), RAG-финдинги (5 реп через GitHub API + README; Opus 5 guide
first-party; CC контекст-факты через claude-code-guide; 2 perplexity-синтеза
— Codex-контекст и cross-machine память), plan.md с 7 фазами/16 items,
Routing (Claude-модели), Обсуждение (7 развилок, 5 Resolved / 2 Exploration),
open-questions (3), P1 детализирована до DoR, P2–P7 — скелеты с
контракт-блоками. Supersedes 2026.07.15-TOKEN-ECON-P6 (перенос P6.2→P1.1,
P7→P3.1, P8→P3.2, P9→P3.3).

**Remaining:** pass 2: детализация P2–P7 (по фазе на заход) → `finish` (свип
+ roadmap.md) → `plan-audit design` → exec по очереди D10.

**Sources of truth:** `plan.md` (§3 Routing, §5 D1–D10, Обсуждение) ·
`brief/00-brief.md` · `findings/rag-2026-07-25.md` · `phases/P1–P7.md` ·
`open-questions.md` · `roadmap/cross-machine-memory.md` (вход P4).

**Open risks:** cross-plan hotspot — task-команды/plan-protocol (P2.2/P6.x
здесь ↔ AGENT-RELIABILITY P2.2): гейт в §2, нарушение = конфликт канона;
заявка 82× экономии code-review-graph — самозамер автора, до P5.1 не
считать фактом; P7 без гейта D9 повторит Codex-инцидент.

**Workarounds/Deferred/Open questions:**
- workarounds: —;
- deferred: исполнение всех фаз (после AGENT-RELIABILITY, кроме P1/P4 —
  допущен параллель D10);
- open_questions: OQ-1 (код-граф), OQ-2 (роль Codex), OQ-3 (дом notify).
