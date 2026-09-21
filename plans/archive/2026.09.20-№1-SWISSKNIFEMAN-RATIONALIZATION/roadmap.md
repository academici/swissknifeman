# Roadmap исполнения — 2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION

**Обновлён:** 2026-09-20 · **Соответствует plan.md:** Layout v2

## Правило группировки

- GREEN global design audit подтвердил solo batching P1–P4 и их exact
  semantic class/effort/review. Cursor проектирует `frontier/high` в `Grok 4.6`,
  `implementation/high` в `Composer 2.5`; Codex — соответственно в
  `gpt-5.6-sol/high` и `gpt-5.6-terra/high`. Для P5 запечатано только правило D8;
  exact P5 route/review фиксируются после terminal P4 GO-manifest admission.
- После audit объединяются только dependency-safe adjacent items с общими Required Reads,
  setup, validation и совместимым `Exec`; item status, journal и closure остаются отдельными.
- P5 не объединяется с P4: P4 производит digest-bound GO manifest, а P5 может стартовать
  только после его terminal readiness и следующего execution admission.

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|---|---|---|---|---|---|
| P1.1 | P1-solo | manual | frontier/high | — | Cursor `Grok 4.6`, Codex `gpt-5.6-sol/high`; no review; ready |
| P2.1 | P2-solo | manual | frontier/high | — | Cursor `Grok 4.6`, Codex `gpt-5.6-sol/high`; light review; после P1 |
| P3.1 | P3-solo | manual | frontier/high | — | Cursor `Grok 4.6`, Codex `gpt-5.6-sol/high`; light review; после P1–P2 |
| P4.1 | P4-solo | manual | implementation/high | — | Cursor `Composer 2.5`, Codex `gpt-5.6-terra/high`; light review; после P1–P3 |
| P5.1 | pending terminal P4 admission | manual | D8 rule → exact route | empty GO-set требует D# | manifest-bound implementation; exact route/review после terminal P4 |

## Текущий frontier

P1.1 готов к execution в текущем root после GREEN focused re-check; P2–P5
остаются dependency-gated своими predecessor outputs.

## Гейты владельца (сводно)

| Где | Что утверждает | Блокирует |
|---|---|---|
| P4 → P5 | Nonempty digest-bound GO manifest материализует exact P5 route/review по D8; empty manifest требует D# | P5.1 |
| Global design audit | GREEN: exact semantic route/review для P1–P4 и provider projections запечатаны; P5 selection rule подтверждено | не блокирует P1–P4; P5.1 ждёт post-P4 admission |
