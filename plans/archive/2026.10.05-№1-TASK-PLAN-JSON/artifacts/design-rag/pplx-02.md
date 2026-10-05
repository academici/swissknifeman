# Query

Pattern: cheap/fast model gathers and compresses repository context (context pack / briefing) before an expensive coding model implements a task, e.g. Codex or Claude Code scout subagent, Aider repo-map, 'context engineering' handoff. What are documented best practices and measured results in 2025-2026? When does it hurt quality?

# Answer

Короткий вывод: дешёвый scout полезен как поисковый индексатор и маршрутизатор, а не как автор окончательной версии архитектуры. Наиболее устойчивый паттерн — короткая, проверяемая карта «куда смотреть и почему», после которой сильная модель сама открывает исходники, тесты и связанные места. Публичные измерения подтверждают полезность отдельных механизмов поиска и компрессии, но пока не доказывают, что именно «дешёвая модель сначала делает briefing» повышает итоговый pass rate кодинга.

## Что подтверждено измерениями

- ContextBench (2026) оценивает поиск контекста на 1 136 задачах из 66 репозиториев и восьми языков. Авторы сообщают, что сложный агентский scaffolding даёт лишь небольшие улучшения retrieval; агенты часто исследуют контекст, который потом не используют, и склонны к полноте поиска в ущерб точности. Это аргумент против предположения «больше предварительной упаковки
