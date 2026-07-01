"""analyst — слой непрерывного обучения экосистемы academici.

Детерминированный (stdlib-only, on-demand — БЕЗ демона) пакет данных/пайплайна:
извлекает кандидат-уроки из потоков задач Claude Code (`run-report`), хранит их с
провенансом и жизненным циклом, показывает человеку и — только с человеком в гейте —
продвигает в переиспользуемое знание (память mAInd → скиллы). Не авто-запись.

Полный дизайн — `research/analyst-self-learning-system.md`. Этот пакет реализует P1 (MVP):
digest + lessons-store + human review/promote. Cross-project агрегатор и confidence-арифметика
(Beta/decay) — последующие фазы (P2/P3)."""
