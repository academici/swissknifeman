# P1.1 — Механические гейты репо

Диапазон ревью: `ea8e4d3..HEAD` (фактический HEAD на момент прогона:
`1d45be9 merge: feat/gitignore-ephemeral-artifacts (harness/skiller updates)`).

## Таблица «гейт → статус → вывод/находка»

| Гейт | Команда | Статус | Находка |
|:--|:--|:--|:--|
| validate.sh skiller | `bash packages/skiller/scripts/validate.sh` | 🔴 FAIL (exit 1) | F1 (blocker) |
| validate.sh harness | `bash packages/harness/scripts/validate.sh` | 🟢 PASS (exit 0) | — |
| validate.sh maind | `bash packages/maind/scripts/validate.sh` | 🟢 PASS (exit 0) | — |
| validate.sh analyst | `bash packages/analyst/scripts/validate.sh` | 🟢 PASS (exit 0) | — |
| validate.sh task | `bash packages/task/scripts/validate.sh` | 🟢 PASS (exit 0) | — |
| core tests | `PYTHONPATH=. python3 -m unittest discover -s core/tests` | 🟢 PASS (151 tests, OK) | — |
| идемпотентность `skiller registry` | `git status --porcelain` до/после `packages/skiller/bin/skiller registry` | 🔴 FAIL (непустой diff) | F2 (major) |
| stdlib-гейт (grep импортов) | см. Code Guidance | 🟢 PASS (1 остаток — не нарушение, см. ниже) | — |
| gitignore/git status | `git status --porcelain` + `git check-ignore packages/analyst/node_modules` | 🟢 PASS | — |

Рабочее дерево после item'а: `git status --porcelain` пусто относительно изменений
этого item'а (после `git checkout --` возврата файлов, тронутых idempotency-проверкой);
предсуществующее `M plans/ACTIVE.md` — артефакт P0.0 (создание плана), не относится к P1.1.

## Находки

## Исходы (P2.1)

- **F1 · blocker → fixed.** Реализованы `SKILL_MANAGED_MARKER`/`_mark_skill_managed`/
  `strip_skill_managed_marker` в `packages/skiller/lib/skiller/common.py` — байт-режим
  (без text-mode нормализации `\r\n`), BOM-safe, идемпотентно. Все 7 тестов
  `tests/test_common.py` зелёные; `packages/skiller/scripts/validate.sh` зелёный
  (335 тестов). Функции пока НЕ вызываются из production-кода (`safe_copy_skill` и
  т.п.) — интеграция вне ТЗ находки (сама находка требовала только не-падающий
  `validate.sh`, не новую фичу-интеграцию).
- **F2 · major → fixed.** `skiller registry` прогнан и закоммичен: `skills.json`
  (`content_sha256` скилла `core:context-economy`) и `docs/guide/budget.md`
  обновлены до актуального состояния `SKILL.md`. Повторный прогон после коммита —
  без дальнейшего diff (идемпотентность подтверждена).

### F1 · blocker · packages/skiller/tests/test_common.py:12
**Суть:** `packages/skiller/scripts/validate.sh` падает (exit 1) — весь тестовый прогон
skiller (329 тестов) заканчивается `FAILED (errors=1)` из-за ошибки загрузки модуля
`test_common`: `ImportError: cannot import name 'SKILL_MANAGED_MARKER' from
'skiller.common'`. Импортируемые имена (`SKILL_MANAGED_MARKER`, `_mark_skill_managed`,
`strip_skill_managed_marker`) в `packages/skiller/lib/skiller/common.py` **отсутствуют
полностью** (`grep -n "managed\|MANAGED" common.py` — 0 совпадений); ближайшая
инфраструктура — `HUB_MARKER`/`safe_copy_skill` в том же файле, но байт-точный
CRLF/LF/BOM round-trip маркера «управляется swissknifeman», который описывает
docstring теста (регресс на баг с `content_sha256`, расходящимся из-за нормализации
`\r\n`→`\n` при text-mode чтении), в коде не реализован.
**Сценарий отказа:** любой запуск `validate.sh`/CI для skiller красный; фича
byte-exact marker round-trip, ради которой писался тест, не существует в проде —
т.е. описанный в docstring баг («ложный update на КАЖДОМ sync без реального дрейфа»)
не пофикшен, только тест-заглушка была закоммичена без реализации.
**Note:** тест не был изменён/добавлен коммитами `ea8e4d3..HEAD` (`git log` по этому
пути в диапазоне — пусто), т.е. это pre-existing breakage, унаследованный HEAD'ом;
фиксируется как находка т.к. это фактическое состояние ветки на момент аудита (Phase
Context P1: «ревьюим фактический HEAD»). Возможно связано с F2 (`content_sha256`
дрейфует при regen — та же область, byte-exact хеширование содержимого скилла).
**→ ТЗ для P2.1:** реализовать `SKILL_MANAGED_MARKER`/`_mark_skill_managed`/
`strip_skill_managed_marker` в `skiller/common.py` (байт-режим, без нормализации
переводов строк) — либо, если фича признана устаревшей/отменённой, удалить
`test_common.py` осознанным коммитом (не молчаливым скипом).

### F2 · major · packages/skiller/skills.json, packages/skiller/docs/guide/budget.md
**Суть:** `skiller registry` **не идемпотентен** — повторный прогон на чистом дереве
меняет закоммиченные артефакты:
- `skills.json`: `content_sha256` скилла `core:context-economy` меняется
  (`1090127c...edcdb` → `49a2dbf8...bea2`) без изменения исходного `SKILL.md`;
- `docs/guide/budget.md`: `on-demand` токен-бюджет бакета `general` меняется
  (8863 → 11028 ток; итоговый `on-demand` 791885 → 794050).
**Сценарий отказа:** каждый `skiller registry` (в т.ч. CI/pre-release) производит
diff на «чистом» дереве без реальных изменений скиллов — это либо (a) недетерминизм
хеширования/подсчёта токенов (порядок файлов, non-canonical сериализация, скрытые
временные метки), либо (b) `content_sha256`/token-count реально устарели в
закоммиченном `skills.json`/`budget.md` относительно текущего `SKILL.md` (дрейф,
который сама генерёжка и чинит на следующий прогон — тогда «находка» не в самой
генерёжке, а в том, что коммит с устаревшим `skills.json` был смержен без повторного
`registry` перед коммитом). Нарушает тезис CLAUDE.md «Детерминированная доставка. …
манифесты генерируются, не правятся руками» — если руками правились/коммитились
файлы скилла без последующего `registry`, README/pre-commit не гарантирует синхрон.
**Восстановление:** после проверки `git checkout --` вернул `skills.json` и
`budget.md` к закоммиченному состоянию — рабочее дерево чистое.
**Диагностика (a) vs (b) — выполнена:** прогнал `skiller registry` дважды подряд
подряд на дереве без промежуточных изменений (второй раз — сразу после первого,
без `git checkout --` между ними); diff второго прогона байт-в-байт идентичен
diff'у первого (`diff /tmp/diff1.txt /tmp/diff2.txt` → пусто). Значит это **(b)**:
не недетерминизм генерёжки, а разовый дрейф — закоммиченные `skills.json`/
`budget.md` устарели относительно текущего `SKILL.md` скилла `core:context-economy`
(кто-то закоммитил правку скилла без последующего `skiller registry`).
**→ ТЗ для P2.1:** прогнать `skiller registry` и закоммитить актуальные
`skills.json`/`budget.md` (major, не blocker — генерёжка сама себя не ломает,
проблема в дисциплине коммита, не в коде).

## Не-находки (проверено, ложных сигналов нет)

- **stdlib-гейт:** единственный незаматченный импорт —
  `packages/analyst/lib/analyst/doctor.py:13: import core  # noqa: F401` —
  это внутрипроектный пакет `core/` (не сторонняя зависимость); regex-паттерн
  задания не покрывает форму `import core` (только `from core`), но по факту
  нарушения stdlib-only нет.
- **node_modules/gitignore:** `packages/analyst/node_modules` корректно
  игнорируется (`.gitignore:3:node_modules/`), `git status --porcelain` пуст —
  подтверждает D3 плана (VitePress devDependency, не находка).
- **Отсутствующий validate-гейт:** не применимо — у всех 5 пакетов
  (skiller/harness/maind/analyst/task) есть `scripts/validate.sh`.
