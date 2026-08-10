---
id: D141
date: 2026-08-08
status: accepted
item: P4.5
items: [P4.5]
supersedes: []
superseded_by: null
---

## Решение

Сохранить sealed journal schema v1 и все существующие bytes без изменений, но развести
schema-validity и write-site policy. Штатный `task.journal append` отклоняет новую непустую
`note` длиннее 300 символов ДО записи; историческая длинная `note` остаётся schema-valid.
Проекция layout v2 `status.md` детерминированно заменяет такую историческую `note` коротким
указателем на `journal.jsonl:<line>`, а linter проверяет именно эффективную проекцию Update Log.
RAG:— (repo-grounded: append-only contract, наблюдение
`findings/P4.5-journal-note-length-conflict.md` и владельческое поручение разрешить конфликты
в рамках текущей сессии).

## Почему

Переписывание journal уничтожило бы provenance, sidecar exception намеренно покрывает только
historical schema-invalid `friction`, а baseline не исправляет новый дефект. Отдельная политика
writer'а предотвращает повтор, а компактная проекция сохраняет полный исходный текст по точному
адресу без нарушения лимита владельческого Update Log.

## Consequences

P4.5 получает owner-authorized fix-forward scope в `packages/task` и канонических командах,
документации и plan-protocol skill. Изменение не добавляет поле, не расширяет journal schema и
не переписывает существующие строки. Repair фиксируется отдельным коммитом после уже сданного
item-коммита `39bd5e2a`; затем P4.5 закрывается новой короткой терминальной записью.
