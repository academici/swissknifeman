# Open Questions — 2026.07.25-ECO-OPT

## OQ-1 — code-review-graph: adopt / skip / combine
**Статус:** Exploration
Развилка Обсуждения §2. Решается фактами пилота P5.1 (замеры токенов против
Serena, точность multi-hop), вердикт — P5.2 с owner-гейтом. До вердикта
Serena остаётся каноном графа кода.

## OQ-2 — Постоянная роль Codex в экосистеме
**Статус:** Exploration
Развилка Обсуждения §7. Гейт: терминальность P1/P2 AGENT-RELIABILITY (D9).
Вердикт — P7.1 (пилот) → P7.2 (owner-D#). Варианты: рутинный слой /
second-opinion-review only / отказ.

## OQ-3 — Дом statusline context-notify: глобально или per-project
**Статус:** Decision pending (нужен владелец)
P6.1: пресет можно раскатывать глобально (~/.claude) или opt-in per-project.
Рекомендация — глобально (механизм дешёвый, полезен везде), но это
owner-выбор при детализации P6.
