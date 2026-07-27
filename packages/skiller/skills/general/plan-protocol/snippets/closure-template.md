# Шаблон отчёта закрытия фазы — `plans/<PLAN-ID>/closure/<Pn>.json` (схема v1)

Машиночитаемая сдача ФАЗЫ рядом с прозой `## Phase Handoff` (не вместо неё). Включается
opt-in полем `## 0. Meta` плана: `Closure Protocol | v1` — единственное легальное значение.
Плана без поля правило не касается ни одной диагностикой; уже закрытые записи не
переписываются (SKILL §8, «Отчёт закрытия фазы»).

Пишет файл `plan-close <ID> Pn` — МЕХАНИЧЕСКИ из полей items фазы (пересказ запрещён).
Читают: `plan_lint` (схема + сверка с `## Phase Status` и Status Board) и `plan-audit <ID> Pn`
(первый вход ступени 1 — перепрогон команд из `evidence` на `git.head_sha`, детект правки ТЗ
фазы после закрытия по `inputs_sha256`).

## Файл целиком

```json
{
  "schema_version": 1,
  "plan": "2026.07.25-ECO-OPT",
  "phase": "P8",
  "closed_at": "2026-07-30",
  "closed_by": {"command": "plan-close", "actor": "implementation/low"},
  "phase_status": "🟢 Done",
  "git": {"head_sha": "<40 hex>", "branch": "<ветка>", "dirty": false},
  "inputs_sha256": {"plan.md": "<64 hex>", "phases/P8.md": "<64 hex>"},
  "items": [
    {"id": "P8.7", "status": "🟢 Done", "evidence_class": "real",
     "evidence": "PYTHONPATH=. python3 -m unittest core.tests.test_io -v — 9 passed (на <sha>)"},
    {"id": "P8.9", "status": "🟠 Done with deviations", "evidence_class": "synthetic",
     "evidence": "прогон на одной фикстуре tests/fixtures/eval-one-case.json — 1 кейс, не корпус"}
  ],
  "gates": [
    {"id": "validate.sh:task", "status": "PASS", "evidence_class": "real",
     "evidence": "bash packages/task/scripts/validate.sh — exit 0 (на <sha>)"},
    {"id": "fleet-adoption", "status": "PENDING", "evidence_class": "baseline_pending",
     "evidence": "ни один живой план кроме ECO-OPT не включил Closure Protocol v1"}
  ],
  "metrics": [
    {"name": "lint_new_from_closure", "value": "0", "label": "real"},
    {"name": "docs_impact_blocked_changes", "value": "—", "label": "baseline_pending"}
  ],
  "limitations": ["матрица возможностей проверена на 2 из 9 поверхностей"],
  "external_side_effects": []
}
```

## Правила заполнения

| Поле | Правило |
|:--|:--|
| `schema_version` | ровно `1` (число). Иных версий схемы не существует |
| `plan` / `phase` | совпадают с фактическим PLAN-ID и `Pn` — иначе ERROR линтера |
| `closed_at` | ISO-дата закрытия фазы (та же, что `Last Updated` в Meta) |
| `closed_by` | `command` — какая команда закрыла; `actor` — её neutral route `<model class>/<effort>` |
| `phase_status` | БАЙТ-В-БАЙТ строка статуса фазы из `## 4. Phase Index & Status Board` |
| `git` | `head_sha` (40 hex, якорь чисел §8), `branch`, `dirty` (bool — было ли дерево грязным) |
| `inputs_sha256` | sha256 `plan.md` и `phases/<Pn>.md` на момент закрытия; потребитель — `plan-audit` |
| `items[]` | ПО СТРОКЕ на каждый item фазы: `id`/`status` — из `## Phase Status` без расхождений |
| `gates[]` | гейты сдачи (`validate.sh:<пакет>`, CI-джоба, полевой прогон): `id`/`status`/класс/доказательство |
| `metrics[]` | числа сдачи: `name`/`value` (СТРОКА — не float)/`label` (тот же enum классов) |
| `limitations[]` | честные ограничения сдачи; нечего сказать — пустой список, а не отсутствие ключа |
| `external_side_effects[]` | что тронуто ВНЕ репозитория (чужие деревья, машинное состояние, флот) |

**Отсутствие ключа = ошибка схемы, а не «нет данных».** «Нет числа» выражается ЗНАЧЕНИЕМ:
запись с `baseline_pending` и причиной — ради этого приём и взят.

## Класс свидетельства (`evidence_class`, у метрик — `label`)

| Значение | Когда |
|:--|:--|
| `real` | прогон на ЗАКОММИЧЕННОМ дереве; `evidence` несёт команду и её вывод/число (пустое доказательство при `real` = ERROR) |
| `synthetic` | фикстура / один кейс / симуляция — `evidence` ОБЯЗАН это называть словами |
| `baseline_pending` | числа нет; `evidence` называет ПРИЧИНУ (нет baseline, гейт не на чем прогнать, ждём полевого прогона) |

Это ось «на каких ДАННЫХ получен результат». Она НЕ заменяет закрытый перечень классов
ДОКАЗАТЕЛЬСТВА `recomputed` / `cross-checked` / `pinned-not-recomputable` / `unknown`
(`source-evidence-verification-v1.md`, SKILL §13 — «выводимо ли утверждение из коммиченного
bundle'а»): оба словаря действуют одновременно, ни один не переопределяет другой.
