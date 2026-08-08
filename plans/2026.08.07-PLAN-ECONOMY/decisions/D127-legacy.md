---
id: D127
date: 2026-08-08
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Владелец замораживает `reader-contract`, `item-state-projection`, `history-projection` и `read-path` v1 после сквозной сверки и проходящей оценки P1.5.** Reader set остаётся закрытым множеством из четырёх ролей; `scoped-review`/`full-audit` — профили `auditor` с `return-to-root`, не новые readers. `index`/`artifacts` получают явные optional slow slots. Bundle input — whole file либо ТОЛЬКО явно объявленный digest-qualified section/symbol slice; inferred slice и неучтённые обязательные байты запрещены. **Consequences:** все четыре строки P1 в `## 7. Contracts` переходят в 🟢 одновременно; форма bundle остаётся P3, capsule/verdict — P4.5/P6.3; порог `read-budget` не меняется.

## Почему

Явное поручение владельца «исполнить P1.5 и заморозить reader-contract v1»; `findings/06-p1-path-feasibility.md` и generated `artifacts/p1-feasibility.json` показывают проходящую реконструкцию на крупном и здоровом реальных планах, включая самые тяжёлые Required Reads. Сквозной machine check не оставил отсутствующих/orphan carrier, немонотонного пути, history/handoff на executor path или требования поля вне запечатанной journal schema. RAG:— (owner-grounded + repo-grounded, generator digest в finding §4).
