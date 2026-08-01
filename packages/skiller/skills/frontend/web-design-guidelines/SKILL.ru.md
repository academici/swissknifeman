> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: web-design-guidelines
description: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
metadata:
  author: vercel
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines (Руководство по веб-интерфейсам)

Проверка файлов на соответствие Web Interface Guidelines (Руководству по веб-интерфейсам).

## Как это работает

1. Прочитать правила из вендоренного payload'а: [`references/web-interface-guidelines.md`](references/web-interface-guidelines.md)
2. Прочитать указанные файлы (или запросить у пользователя файлы/шаблон)
3. Проверить по всем правилам из payload'а
4. Вывести найденное в лаконичном формате `file:line`

## Источник рекомендаций

Правила вендорены локально — пинованный коммит `vercel-labs/web-interface-guidelines`
`4e799d45c17aec1498c269287a83b9dba22b966b` (провенанс и процедура пере-пиновки — в
`upstream.json`). Сетевой запрос не выполняется: читайте
[`references/web-interface-guidelines.md`](references/web-interface-guidelines.md) напрямую.

## Использование

Когда пользователь передаёт аргумент-файл или шаблон:
1. Прочитать `references/web-interface-guidelines.md`
2. Прочитать указанные файлы
3. Применить все правила из payload'а
4. Вывести найденное в формате, заданном в payload'е

Если файлы не указаны, спросите у пользователя, какие файлы проверять.
