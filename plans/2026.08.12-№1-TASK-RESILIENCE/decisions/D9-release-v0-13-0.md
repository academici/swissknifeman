---
id: D9
date: 2026-08-12
status: accepted
item: P6.1
items: [P6.1, P6.2, P6.3]
supersedes: []
superseded_by: null
---
## Решение

Следующий локальный annotated release tag — `v0.13.0`. Неопубликованный `v0.12.0` tag был удалён;
его candidate changes входят в новый release вместе с намеренным breaking retirement Layout v1.
Для pre-1.0 umbrella это minor bump. Push и GitHub release не входят без отдельной команды владельца.
RAG:— (repo-grounded: release-discipline, Git tags и owner instruction).

## Почему

Повторное создание `v0.12.0` скрыло бы существенное расширение scope после преждевременного release
commit; patch bump недостаточен для удаления ранее поддержанного execution layout.
