# P3 audit RED — bounded repair-forward synthesis

## Входы

- `phases/P3/P3.md` → `Audit P3 — 2026-08-11`, attempt 1, RED;
- exact P3.1/P3.3 Validation из `packages/task`;
- journal lines 51–57 и git refs `ddc19647`, `d8214950`, `57a922b3`, `ec5c71bc`;
- D17 bounded audit cap и owner directive D25.

Все выводы repo-grounded; внешних факт-классов нет. RAG:—.

## Finding → owner → proof

| Finding | Owner | Repair proof |
|:--|:--|:--|
| Focused unittest не видит top-level `fixtures` | P3.4 | Оба exact module set с `PYTHONPATH=tests`: 144/63 green на одном 40-hex ref; test/product files не меняются. |
| P3.1 full validator был red на historical product commit | P3.4 | Append-only P3.1 `closed-deviations` с exact historical/current refs; старую journal-строку не переписывать. |
| P3.3 изменил undeclared parity test | P3.3 spec + P3.4 | `Files` дополнен; P3.3 state становится `closed-deviations` и называет `57a922b3`. |
| P3.3 spec/D24 появились post-factum | D25 + P3.4 | Весь repair contract committed до P3.4 start; P3.4 bookkeeping commit — predecessor P3.2. |
| P3.2 переиспользовал P3.3 session | P3.2 attempt 2 | Отдельный native process; current `session_id` ≠ P3.4 и ≠ historical shared id. |
| Counts без anchor | P3.4/P3.2 | Каждая цифра в report/journal/state/handoff несёт `<count> (на <40-hex git-ref>)`. |

## Граница repair

`PYTHONPATH=tests` — execution bootstrap, а не новый runtime contract. P3.4 не добавляет
`tests/__init__.py`, shim, dependency, provider telemetry или product fix. Если explicit bootstrap
не проходит на committed amendment anchor, это acceptance red: расширять Files
в этом attempt запрещено. P3.2 остаётся report-only и не стирает прежний ложный GO.
