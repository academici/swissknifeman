# Roadmap исполнения — <PLAN-ID>

<!-- Собирается ПОСЛЕ полной детализации всех фаз (SKILL §5 дефолт, §8 канон roadmap).
     Отвечает на «какую команду дальше?» без анализа всего плана. Живой документ:
     закрытие фазы / re-design обновляет таблицу (+строка в Update Log плана).
     Правила: Batch = последовательные мелкие items одной модели со сцепленным scope —
     одна сессия, одна команда; solo — большой/сложный/рисковый (обоснование в Примечании
     ОБЯЗАТЕЛЬНО); workflow — независимые по scope items (скрипт в plans/<ID>/workflows/).
     Roadmap не переопределяет Routing §3 (модели/effort) — только группирует запуски. -->

**Обновлён:** <YYYY-MM-DD> · **Соответствует plan.md:** v<X.Y.Z>

## Карта исполнения

| Item | Batch | Запуск | Model/Thinking | Гейт владельца | Примечание |
|---|---|---|---|---|---|
| P0.1 | B1 | plan-exec серия | sonnet/medium | — | сцеплен с P0.2 по файлам |
| P0.2 | B1 | ↑ | sonnet/medium | — | |
| P1.1 | solo | plan-run (manual) | opus/high | ✅ утверждение матрицы | design-item, объединять нельзя: вердикт владельца посреди; перед запуском /model opus + /effort high |
| P2.1–P2.3 | W1 | workflow | sonnet/medium | — | независимый scope → wf-<codename>-p2.js |
| … | | | | | |

## Готовые launch-block'и групп

### B1 — <суть батча>

| Параметр | Значение |
|:--|:--|
| Model | <model> |
| Thinking | <effort> — <причина> |
| Context | Холодный старт: plan.md → roadmap.md → phases/<Pn>.md |
| Суть | Серия <Pn.a>–<Pn.b> одной сессией, гейты между items — внутри сессии |

```
/task:plan-exec <PLAN-ID> <Pn.a> <Pn.b> <Pn.c>
```

<!-- Батч-серии — ТОЛЬКО через plan-exec (список items): её пин sonnet/medium — жёсткий
     гейт тира. /task:plan-run — без пина, для manual design-items под моделью сессии
     (ритуал /model+/effort по Routing перед запуском). -->

### W1 — <суть workflow-группы>

```
Workflow({scriptPath: "plans/<PLAN-ID>/workflows/wf-<codename>-<purpose>.js"})
```

## Гейты владельца (сводно)

| Где | Что утверждает | Блокирует |
|---|---|---|
| <Pn.m> | <артефакт> | <какие batch'и ждут> |
