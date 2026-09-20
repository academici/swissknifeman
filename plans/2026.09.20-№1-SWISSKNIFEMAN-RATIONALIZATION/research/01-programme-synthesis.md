# Programme synthesis

План принимает не конкретные удаления из аудита, а его главную проверяемую гипотезу:
лёгкий daily path и opt-in durable orchestration могут снизить стоимость без потери полезных
локальных инвариантов. Пять фаз разделяют evidence, field reality, capability value,
selection и implementation.

## Малая измерительная программа

Для matched experiments используются реальные недавние tasks и clean temporary worktrees. Корпус
ограничивается достаточным для практического решения и не претендует на publication-grade
статистику. Минимум метрик: acceptance outcome, elapsed time, input/output tokens при наличии,
tool calls/reads, owner interruptions, unrelated writes, false activation и субъективная usefulness на короткой якорной шкале.

Выход из эксперимента — одно из четырёх: `go`, `keep`, `defer`, `reject`. Неоднозначный
или provider-defective результат не попадает в implementation под видом `go`.

## Model gate для execution

- Grok 4.6: wide/cross-project discovery, набор доказательств, который может не поместиться
  в 200k, или проектирование с внешней tool orchestration.
- Composer 2.5: bounded packet, Cursor-local repo inspection и implementation-ready slicing с быстрым
  search/edit/terminal loop.
- P1–P3 → Grok 4.6 и P4–P5 → Composer 2.5 — только исходная гипотеза, а не route.
  После детализации всех фаз единый design audit перепроверяет её по фактическим пакетам,
  запечатывает батчи и exact `Grok 4.6`/`Composer 2.5` routing и вносит нужные profile/provider fixes до execution.
