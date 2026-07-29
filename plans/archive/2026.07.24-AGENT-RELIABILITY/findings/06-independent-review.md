# Finding 06 — независимая проверка причинной модели и SSOT

Два read-only reviewer работали независимо от основного synthesis.

## Исправления основной модели

1. Наивная сумма cumulative JSONL events была завышена. После dedup:
   952 turns, 125.70 summed task-hours, 135.11M input. План исправлен.
2. Session fragmentation — усилитель, но не единственный cause:
   forgotten launch-block и scope drift встречались внутри одной session.
3. Аудиты нельзя просто убрать: ранние P6 attempts ловили реальный
   fail-open defect. Нужны severity/terminal/cap.
4. Ключевой missing gate — public/consumer outcome. Internal byte/hash
   evidence преждевременно считался GREEN.
5. Буквальное «не было ни одной чистой задачи» имеет counterexample:
   узкий `HONEST-HTTP-ERRORS`. Это подтверждает, что bounded clear outcome
   способен работать, и не ослабляет системную жалобу по крупным планам.

## SSOT verdict

- canonical registry clean;
- 12 active duplicate identities;
- 13 full root copies вместо thin adapters;
- 48 invalid provider-substitution literals;
- installed core cache incomplete при том же version;
- generated Codex bodies/commands содержат Claude-only carriers;
- current gates prove reproducibility, not provider executability.

Эти поправки включены в D1/D6/D8–D10, P0.4, P1.1–P1.4 и P3.
