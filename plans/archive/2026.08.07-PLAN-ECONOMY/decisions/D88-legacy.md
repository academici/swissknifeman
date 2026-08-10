---
id: D88
date: 2026-08-07
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Вся детализация плана и все untracked-слои знаний коммитятся ДО старта исполнения, отдельным коммитом, строго по `plans/2026.08.07-PLAN-ECONOMY/`.** Сознательно НЕ коммитятся: `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/` (чужой план — D3) и `plans/2026.08.07-PLAN-ECONOMY/.swissknife/` (телеметрия прогона analyst, машинно-специфична). Отсутствие `.swissknife/analyst/**/*.ndjson` в корневом `.gitignore` при наличии там же `.claude/analyst/**/*.ndjson` фиксируется как наблюдённый дефект среды и чинится в owning-источнике (шаблон `.gitignore`, раздаваемый harness), а не молчаливой правкой здесь.

## Почему

Результат обоих прогонов дизайна существовал только в рабочем дереве: `git show HEAD:…/plan.md` даёт 145 строк и 13 D-записей против 715 и 83; `roadmap.md`, `brief/01-refinements.md`, `research/02`–`08`, `findings/03`, `05`, `08`–`11` не отслеживались вовсе. Три следствия, каждое реально: (а) P2.8 требует «до неё дерево чистое (`git status --porcelain` пуст по `plans/`)» — предусловие невыполнимо; (б) холодный старт по `git log` видит скелет плана, тогда как `handoff.md` утверждает «дизайн закрыт»; (в) `git clean` уничтожает ~6900 строк несущих слоёв без следа в истории. Канон `root.evidence-integrity` требует раскрывать дефект среды, а не обходить его. RAG:— (repo-grounded: `git status --porcelain plans/`, 2026-08-07; `findings/13-…` F4)
