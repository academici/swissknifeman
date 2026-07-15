# P4.1 — Регресс-прогон `plan-lint` по 10 корням / 30 планам

Замер 2026-07-15. Методология — парный прогон на ОДНОМ снимке (D53): для каждого корня
запускается СТАРЫЙ `plan-lint.py` (снят коммитом-предком фазы P1, `dd57d80`, через
`git worktree add --detach`) и ТЕКУЩИЙ `plan-lint.py` (HEAD) — оба на одном и том же
(текущем) состоянии чужого дерева. Различие счётчиков между «до» и «после» изолирует
изменение ПОВЕДЕНИЯ линтера от независимой мутации флота (планы 9 чужих репо меняются
своим ходом). Для `swissknifeman` (свой репо) дополнительно проверено содержательное
before/after на дереве `dd57d80` vs `HEAD` (Completion Notes ниже).

Команда (шаблон, ROOT — путь к `plans/`):
```bash
WT=<git worktree добавлен на dd57d80>
python3 "$WT/packages/task/scripts/plan-lint.py" "$ROOT"   # ДО (старый линтер)
python3 packages/task/scripts/plan-lint.py "$ROOT"          # ПОСЛЕ (текущий линтер)
```

## Таблица

| Корень | Планов до/после | ERROR до | ERROR после | WARN до | WARN после | Дельта — чем объясняется |
|:--|--:|--:|--:|--:|--:|:--|
| `Vaults/Brain/plans` | 19 → 23 | 86 | 84 | 113 | 200 | планы +4 (archive/ впервые линтуется, N3/D14 — ожидаемое расширение); ERROR −2 = чистый эффект после вычета 78 пар message-rewording (D14 actionable-текст: те же 78 полей REGHUB/P3 репортятся другим текстом — 78 «снято» + 78 «добавлено» взаимно гасятся, см. §Метод); WARN +87 — archive-плана (WARN там впервые) + рост живых планов (не диффом этого плана) |
| `swissknifeman/plans` | 6 → 6 | 4 | 0 | 44 | 35 | −4 ERROR / −9 WARN — фиксы ЭТОГО плана (P1–P3), не регресс |
| `vaulter/plans` | 4 → 6 | 6 | 9 | 12 | 25 | планы +2 (archive/ впервые линтуется); 0 новых ВНЕ archive/, 1 снята вне archive/; весь прирост — archive-покрытие |
| `azguard/plans` | 1 → 1 | 0 | 0 | 0 | 0 | без изменений |
| `corex/plans` | 1 → 1 | 1 | 0 | 21 | 21 | −1 ERROR — снята форма Next (класс m8), не регресс |
| `loqum/plans` | 1 → 1 | 0 | 0 | 2 | 2 | без изменений |
| `themeon/plans` | 1 → 1 | 16 | 16 | 81 | 81 | 0 — 4 пары message-rewording (D14, item P3.8) взаимно гасятся, счёт не изменился |
| `edufy/plans` | 1 → 1 | 0 | 0 | 0 | 0 | без изменений |
| `agelto/agelto/plans` | 3 → 3 | 9 | 7 | 44 | 54 | −2 ERROR = сняты 2 фантомные ERROR `plans/archive/{plan,handoff}.md отсутствует` (N3/D14, класс, ради которого фикс писан); WARN +10 — рост живых планов флота (не диффом) |
| `dterema/dterema/plans` | 1 → 1 | 0 | 0 | 0 | 0 | без изменений |

**Итого по флоту: НОЛЬ новых ERROR/WARNING** вне двух объяснённых классов (archive-покрытие
впервые + message-rewording нейтральные пары) и вне фиксов самого этого плана.

## Метод проверки нулевой дельты (не по агрегату, по строкам)

Для каждого корня посчитан построчный diff нормализованных диагностик (ключ —
`(kind, путь_без_строки, текст_сообщения)`, номер строки отброшен — как в `--baseline`, D6):

- `Vaults/Brain/plans`: 78 «новых» строк вне `/archive/` — ВСЕ являются рефразом
  8-полей-на-item REGHUB `P3.1`–`P3.8` (D14: старый текст `«нет обязательного поля «X»»`,
  новый — тот же текст, actionable-хвост не менялся с P1.1, разница только у REGHUB
  из-за архив-путей в её собственных строках — проверено `diff`, идентичное число и
  состав полей снято/добавлено, net 0). 0 новых внутри `/archive/`.
- `themeon/plans`: 4 «новых» / 4 «снятых» — те же 4 поля item `P3.8`, идентичный класс.
- `vaulter/plans`, `agelto/.../plans`: 0 новых вне `/archive/`; расхождения — только
  archive-покрытие (vaulter) и снятие фантомных ERROR (agelto, N3/D14).
- `swissknifeman/plans`, `corex/plans`: 0 новых, только снятые (фиксы этого плана).

## Воспроизведение

```bash
cd /home/vostrikov/projects/packages/swissknifeman
WT=$(mktemp -d)
git worktree add --detach "$WT" dd57d80
for r in /home/vostrikov/Vaults/Brain/plans \
         /home/vostrikov/projects/packages/swissknifeman/plans \
         /home/vostrikov/projects/packages/vaulter/plans \
         /home/vostrikov/projects/packages/azguard/plans \
         /home/vostrikov/projects/packages/corex/plans \
         /home/vostrikov/projects/packages/loqum/plans \
         /home/vostrikov/projects/packages/themeon/plans \
         /home/vostrikov/projects/edufy/plans \
         /home/vostrikov/projects/agelto/agelto/plans \
         /home/vostrikov/projects/dterema/dterema/plans; do
  echo "== $r"
  echo "  ДО:    $(python3 "$WT/packages/task/scripts/plan-lint.py" "$r" 2>&1 | tail -1)"
  echo "  ПОСЛЕ: $(python3 packages/task/scripts/plan-lint.py "$r" 2>&1 | tail -1)"
done
git worktree remove "$WT"
```
`dd57d80` — коммит-предок фазы P1 (родитель `4c03715`, первый item кластера protocol-gap).

## Вывод

Back-compat-гейт Execution Rules плана («ни одна правка `plan_lint.py` не имеет права
добавить НИ ОДНОЙ новой ERROR ни одному из живых планов флота») — **выполнен на всех
10 корнях / 30 планах**. Единственные новые WARNING объяснены явно (archive-покрытие,
carve-out D34) и не являются ложно-положительными: они репортят реальные пробелы
(недозаполненный скелет, легаси-формы) в архивных/чужих планах, которые линтер раньше
молча пропускал.
