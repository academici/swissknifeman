# Идея: register падает REGISTER_REFUSED, если `next`/`impact` проблемы начинается с «-»

Статус: исправлено в `bridges/planner-orch/register.py` (форма `--next=значение`), источник: PLAN3 vaulter P5.4, 2026-10-17.

- Симптом: после 20 мин работы пункт останавливался `REGISTER_REFUSED … plan.py log: error: argument --next: expected one argument`.
  Исполнитель написал `next` с ведущим «-» (список), argparse принял значение за флаг.
- Урок: все значения-тексты в argv моста передавать в форме `--flag=value`; то же проверить для `--summary`, `--deviation`, `--pending`.
- Резюме после правки: `resume --run` повторил только register, работа не потеряна (хорошо).
