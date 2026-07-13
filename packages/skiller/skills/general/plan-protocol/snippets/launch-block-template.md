# Шаблон launch-block — фиксированная форма «что запускать дальше»

Каждая выдача следующего шага — handoff.Next и финалы отчётов
plan-exec/plan-close/plan-audit — обязана иметь эту форму (SKILL раздел 8):
таблица параметров запуска + голая команда одним code-block, копипаст без правок.

`````markdown
| Параметр | Значение |
|:--|:--|
| Model | <модель: sonnet / opus / haiku> |
| Thinking | <effort: low / medium / high / xhigh> |
| Context | <fresh session / continue> |
| Суть | <1 строка: что делает запуск> |

````
<голая команда одним code-block, копипаст без правок>
````
`````

Правила:

- **Самодостаточность (cold-start).** Команда обязана работать из холодной сессии:
  plan-ID + пути входных доков (cold-start reads) + встроенное утверждение гейта,
  если исполнение гейтится. Ссылки вида «эта сессия» — только как дополнение.
- **Model/Thinking** — из Routing плана (SSOT-матрица — SKILL раздел 9); отклонение
  от матрицы обосновывается там же, не в launch-block.
- **Exec = manual (§9)** → форма «ЗАПУСК ВРУЧНУЮ»: `Model` = предписанная Routing (НЕ
  sonnet), `Context` = NEW SESSION, а code-block несёт **ГОЛЫЙ ПРОМПТ item'а**, не
  slash-команду: `/task:plan-exec` пинит sonnet/medium и по routing-гейту обязан такой
  item отклонить — команда в code-block'е была бы прямой инструкцией нарушить гейт.
- `plan-lint` проверяет (warning): handoff.Next содержит таблицу с `| Model |`
  и code-block (грепаемо).
