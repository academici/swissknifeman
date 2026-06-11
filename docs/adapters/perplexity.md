# Адаптер: Perplexity

Скиллы из `skills/imported/` совместимы с Perplexity Computer out of the box —
большинство из них и пришли из экосистемы Perplexity super-skills
(см. `references/get-zeked-perplexity-super-skills.md`).

## Загрузка

В интерфейсе Perplexity:

**Skills → Create skill → Upload `SKILL.md`**

Файлы загружаются по одному; сниппеты при необходимости вставляются в тело
скилла или загружаются как вложения.

## Что учесть

- Perplexity не читает локальные каталоги — установка только через UI;
- upstream-tracked скиллы (`skills/imported/`) обновляются через
  [upstream-sync](/guide/upstream-sync): после обновления в реестре перезагрузите
  файл в Perplexity вручную.
