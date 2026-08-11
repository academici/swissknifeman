# Шаблоны Task plan-protocol — референс

Все скелеты документов плана живут одним набором snippets в SSOT скилла:
`packages/skiller/skills/general/plan-protocol/snippets/` (манифест — `index.json` там же).
Эта страница — указатель «какой шаблон для чего»; содержимое НЕ дублируется — единый
источник истины > копий. Команды `/task:plan-*` берут скелеты оттуда автоматически.

| Шаблон (snippet) | Для чего | Ключевое в v2 |
|:--|:--|:--|
| `plan-template.md` | скелет `plan.md`: Meta, Context, Execution Rules, Routing, Status Board, Decision/Update Log | поля Meta `Home` / `Paused By`; указатель на `open-questions.md`; лимит Update Log ≤ 2 строк |
| `phase-template.md` | stable phase index/item spec; v1 compatibility block | v2 отделяет spec от generated state |
| `handoff-template.md` | скелет rolling `handoff.md`: Next/Done/Remaining/Sources of truth/Open risks | Next в форме launch-block; ключи devloop-телеметрии |
| `launch-block-template.md` | фиксированная форма «что запускать дальше»: таблица Model/Thinking/Context/Суть + голая команда code-block'ом | правила cold-start: plan-ID + входные доки + утверждение гейта |
| `active-template.md` | 4-строчный указатель `plans/ACTIVE.md` | парсится `plan-lint` байт-в-байт |
| `code-guidance-patterns.md` | 3 паттерна Code Guidance для типовых классов item'ов | анти-подгонка (conformance/contract) · анти-самообман (gate) · if-then эскалация к D# |
| `decision-record-template.md` | append-only `decisions/<D-id>.md` | evidence, supersession, actor/model, consequences |
| `item-state-template.md` | generated `<Pn.m>.state.md` | пять volatile result-полей; руками не редактируется |
| `closure-template.md` | opt-in judgement evidence `closure/<Pn>.json` | дополняет, не заменяет generated `<Pn>.closed.md` |

## Как этим пользоваться

- **Новый план / фаза** — не собирать руками: `/task:plan-design` разворачивает
  `plan-template.md` и `phase-template.md` сам.
- **Handoff** — `plan-exec`/`plan-close` перезаписывают `handoff.md` по
  `handoff-template.md`; блок Next обязан быть launch-block'ом
  (`launch-block-template.md`) — проверяется `plan-lint`.
- **Code Guidance item'а** — формулировки не изобретаются: берётся подходящий паттерн из
  `code-guidance-patterns.md` и параметризуется под item.

Схемы полей и правила заполнения — скилл `general/plan-protocol` и
`references/plan-layout-v2.md`. Валидатор: `python3 packages/task/scripts/plan-lint.py
plans/<PLAN-ID>` — новые проверки 2.0 (скелет-маркер, порядок полей, launch-block,
`[NEEDS CLARIFICATION]` при 🟡+, лимит Update Log) выдаются warning-уровнем.
