# Пофазная топология continue-first Task

| Проблема | Фаза | Продуктовый шов |
|:--|:--|:--|
| Разрозненные roadmap-симптомы / обязательный RAG | P0 | gap/acceptance matrix + successful Perplexity evidence |
| Две исполняемые схемы плана | P1 | fleet v1 migration → v2-only reader/commands |
| Коллизии ID и bare item refs | P2 | parser/linter/canon qualified reference |
| Мелочь становится terminal / отрицание ложно объявляет orchestration | P3 | journal/state observations + command repair loop + negation-aware lint |
| Гипотеза о блоке сразу эскалируется | P4 | closed candidate + isolated confirmation + RAG pending |
| Исполнитель завершает chat до durable terminal | P5 | receipt, phase candidate, provider/docs parity |
| Изменение не доезжает до проектов | P6 | clean release, new tag, registered-channel rollout |

Порядок задан зависимостями: P1 сохраняет resumeability до удаления v1, provider commands P5
проецируют каноны P1–P4, а release P6 принимает только их совместный зелёный результат. RAG:✅
2026-08-12 (Perplexity Web safe-deployment/version-retirement synthesis;
`findings/02-rag-resilience-and-schema-cutover-2026-08-12.md`).
