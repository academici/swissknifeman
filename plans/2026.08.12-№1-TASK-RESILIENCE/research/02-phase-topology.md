# Пофазная топология continue-first Task

| Проблема | Фаза | Продуктовый шов |
|:--|:--|:--|
| Разрозненные roadmap-симптомы | P0 | единая gap/acceptance матрица |
| Коллизии ID и bare item refs | P1 | parser/linter/canon/provider reference |
| Мелочь становится terminal | P2 | journal/state observations + command repair loop |
| Гипотеза о блоке сразу эскалируется | P3 | closed candidate + isolated confirmation + external RAG |
| Исполнитель завершает chat до durable terminal | P4 | receipt, phase candidate, provider/docs parity |
| Изменение не доезжает до проектов | P5 | clean release, tag, registered-channel rollout |

Порядок задан зависимостями: provider commands P4 проецируют каноны
P1–P3, а release P5 принимает только их совместный зелёный результат. RAG:—
(repo-grounded: `findings/00-roadmap-and-runtime-gap.md`, `research/01-target-design.md`).
