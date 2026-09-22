# Roadmap исполнения — 2026.09.22-№1-TASK-AUDIT-REMEDIATION

**Обновлён:** 2026-09-22 · **Соответствует plan.md:** Layout v2

## Правило группировки

- Каждый item — отдельный solo launch; P1–P6 не объединяются в один invocation.
- Каждый successor потребляет terminal GREEN артефакты predecessor; missing output —
  `dependency-not-ready`, а не defect predecessor.
- P1/P6 идут как manual frontier/high из-за external/cross-project evidence; P2–P5 идут
  через fixed `task:plan-exec` implementation/medium.
- Review не создаёт phase audit. P3 и P6 требуют fresh independent bounded review
  sealed candidate; owner-bound audit admission нужен только для formal `task:plan-audit`.

## Карта исполнения

| Итерация | Item | Batch | Запуск | Model class/Effort | Review | Гейт |
|:--|:--|:--|:--|:--|:--|:--|
| 1 | P1.1 | solo | manual | frontier/high | light | Perplexity + ordinary web + local coverage 17/17 |
| 2 | P2.1 | solo | plan-exec | implementation/medium | light | GREEN P1 verified subset |
| 3 | P3.1 | solo | plan-exec | implementation/medium | light | GREEN P2 + provider trust decision + Agentools smoke |
| 4 | P4.1 | solo | plan-exec | implementation/medium | light | GREEN P3 + durability contract |
| 5 | P5.1 | solo | plan-exec | implementation/medium | light | GREEN P4 + frozen privacy/path policy |
| 6 | P6.1 | solo | plan-exec | implementation/medium | light | GREEN P5 + reconciliation of the three real task records |

## Текущий frontier

P1.1 — единственный runnable item. P2–P6 детализированы, но dependency-gated.

## Гейты владельца (сводно)

| Граница | Когда нужен owner action | Без owner action |
|:--|:--|:--|
| P3 provider trust | Provider не даёт trusted attestation, а выбор между enforced fail-closed и workflow-only mode меняет public promise | Нельзя назвать editable transcript/env security evidence |
| P6 field corpus | Нет трёх реальных tasks или нужен live consumer rollout | Можно отклонить non-code candidate и закрыть P6 без него |
| Release/rollout | Всегда отдельно | План закрывается до release/rollout |
