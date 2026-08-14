---
id: D33
date: 2026-08-14
status: accepted
item: P7.2
items: [P7.2, P7.3, P7.5]
supersedes: []
superseded_by: null
---

## Решение

Отсутствующий или untracked source-файл, на который уже ссылается текущий item, считается
детерминированным local repair: исполнитель сам назначает его самому раннему совместимому item,
уточняет `Files` и `Validation`, затем повторяет изолированную проверку. Он не терминализирует
работу и не ждёт owner approval. Новый/изменённый файл либо commit вне текущего scope — это
наблюдение для snapshot/attribution, а не stop-сигнал.

Явная последующая команда владельца продолжить работу создаёт новый in-progress attempt и
перевешивает прежнюю terminal-проекцию. Предыдущий `final`, `Blocked` или `Done` остаётся
историческим evidence, но не может сам по себе отклонить возобновлённое выполнение.

## Почему

P7.2 преждевременно превратил omission ownership для `terminal_policy.py` в `Blocked`, хотя
файл, import-цепочка и подходящая P7.2 boundary были наблюдаемы локально. Причина — ошибочное
приравнивание отсутствующего владельца файла к scope boundary до попытки минимального repair.
Второй дефект — terminal row был прочитан как необратимый stop, хотя владелец явно потребовал
продолжить. Это процессные сбои исполнения, а не authority/safety/public/frozen boundary. RAG:—
(owner-grounded: 2026-08-14 feedback; repo-grounded: P7.2 block-candidate and return judgement,
`roadmap/2026.08.11-terminal-final-continuity-receipt.md`).

## Consequences

P7.2 получает `terminal_policy.py` в свой declared Files и продолжает execution; P7.3 получает
регрессии против terminal escape для ownership defect, incidental tree change и owner-directed
resume. P7.5 сохраняет roadmap-диспозицию только после проверки snapshot, а не использует
появление/изменение roadmap-файла как повод остановить текущий item. Реальные authority/safety/
public/frozen/external boundaries по-прежнему требуют доказательств и не автофиксятся.
