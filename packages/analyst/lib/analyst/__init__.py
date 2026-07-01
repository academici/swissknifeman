"""analyst — слой непрерывного обучения экосистемы academici.

Детерминированный (stdlib-only, on-demand — БЕЗ демона) пакет данных/пайплайна:
извлекает кандидат-уроки из потоков задач Claude Code (`run-report`), хранит их с
провенансом и жизненным циклом, показывает человеку и — только с человеком в гейте —
продвигает в переиспользуемое знание (память mAInd → скиллы). Не авто-запись.

Контур: digest + lessons-store + human review/promote (P1); cross-project агрегатор `scan`
(P2); confidence-арифметика (Beta/decay) + числовая state-machine `recompute` (P3)."""
