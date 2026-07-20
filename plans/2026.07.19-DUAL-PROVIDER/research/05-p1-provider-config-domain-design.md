# P1 design synthesis — provider config/domain и resolution

**Дата:** 2026-07-19  
**Основание:**
`brief/00-brief.md`,
`research/01-target-architecture-options.md`,
`research/02-sequence-and-boundaries.md`,
`research/03-p0-design-and-premortem.md`,
`root/contracts/provider-capability-contract.md`,
`root/contracts/provider-artifact-contract.md`,
а также read-only recon текущих config seams:
`core/__init__.py`, `core/project.py`,
`packages/skiller/lib/skiller/{common,config,update}.py`,
`packages/skiller/schema/swissknife.schema.json`,
`packages/maind/lib/maind/config.py`,
`packages/harness/lib/harness/settings.py`.

## Наблюдаемая граница до P1

- `.swissknife.json` — project-owned carrier. Его ключи и JSON Schema принадлежат
  `skiller`; `harness` пишет отдельные ключи merge-only, не владея общей валидацией.
- Корневой `config.json` — node/fleet carrier `maind`: top-level defaults и записи
  `projects[]` валидируются вручную на stdlib. Реальный файл содержит локальное состояние
  флота и не является тестовой фикстурой.
- Текущий precedence в `skiller` уже ставит явный project config выше registry/manifest,
  а CLI flags — выше project config. RAG:— (repo-grounded:
  `packages/skiller/lib/skiller/config.py`, `packages/skiller/lib/skiller/update.py`)
- `core` — плоский stdlib-only пакет общих примитивов и не импортирует package modules.
  RAG:— (repo-grounded: `core/__init__.py`, `CLAUDE.md`)

## Целевая композиция конфигурации

P1 вводит один pure resolver с явными слоями и provenance. Рекомендуемый precedence,
от сильнейшего к слабейшему:

1. operation-local override, переданный вызывающим command/API;
2. project-owned `.swissknife.json:providers`;
3. fleet project override `config.json:projects[].providers`;
4. fleet defaults `config.json:providers.defaults`;
5. compatibility default: старый config без `providers` означает прежний
   Claude Code-only режим и не переписывается на диск.

Карты providers/capabilities сливаются по stable ID; правило для каждого составного поля
(merge/replace/forbid) объявляет frozen config contract, а не реализация «по ощущениям».
Неизвестный provider/capability, неподдерживаемый requested capability и конфликт слоёв
возвращаются как структурированные diagnostics с provenance. Package boundary решает,
как превратить diagnostic в русское CLI-сообщение; `core` не печатает и не завершает процесс.

## Рассмотренные альтернативы

| Вариант | Плюсы | Минусы | Вердикт |
|:--|:--|:--|:--|
| Project-owned layer выше fleet | локальная декларация проекта не перетирается удалённым orchestration state; совпадает с текущим skiller precedence | fleet не может молча навязать override | принять; явный operation override остаётся механизмом осознанного запуска |
| Fleet project override выше `.swissknife.json` | централизованное управление | скрытая смена проекта и риск непереносимого поведения вне конкретного hub | отклонить |
| Каждый package сам merge'ит dict | быстро начать | разные precedence/diagnostics и повторение semantic contract | отклонить по D2/D9 |

## Module boundary и последовательность

1. P1.1 запечатывает config contract и golden precedence examples после frozen P0 gates.
2. P1.2 вводит immutable provider domain и минимальные adapter protocols в `core/provider.py`.
3. P1.3 вводит pure resolution/diagnostics в `core/provider_config.py`, затем thin validation
   adapters в `skiller` и `maind`; package file I/O не переезжает в `core`.
4. P1.4 доказывает legacy no-op и precedence общей fixture matrix. Она не меняет реальный
   `config.json`, consumer projects, FOREMAN или provider artifacts.

Цепочка последовательная: P1.2 потребляет frozen P1.1 contract, P1.3 — API P1.2,
P1.4 — обе реализации. Критерий workflow orchestration не срабатывает.

## Pre-mortem P1

| Отказ | Ранний сигнал | Mitigation | Owner/item |
|:--|:--|:--|:--|
| Legacy config внезапно включает Codex или переписывается | отсутствующий `providers` даёт новый on-disk diff | explicit Claude-compatible fallback + byte-preservation fixtures | P1.1/P1.4 |
| `skiller` и `maind` по-разному merge'ят слои | одинаковый fixture даёт разный effective config | pure resolver в core + общая expected matrix | P1.3/P1.4 |
| `core` превращается в I/O/service locator | module читает cwd/home/config самостоятельно | pure inputs/outputs; file ownership остаётся в packages | P1.2/P1.3 |
| Draft P0 fields зашиты в public API | P1 code стартует до P0.3/P0.4 | hard entry gate + if-then escalation к D# | P1.1–P1.3 |
| Тесты трогают живой fleet config | test path указывает на repo `config.json` | только TemporaryDirectory/synthetic fixtures; before/after guard | P1.4 |

## Verification

- Repo-grounding: read-only сверены перечисленные config/core seams и текущие precedence;
  package code не исполнялся.
- Новых внешних capability claims в P1-design не вводилось; повторный web/RAG проход не нужен,
  P1 потребляет future-frozen P0 contracts как единственный внешний evidence boundary.
- Непроверенное → ПОВТОРНЫЙ ПРОХОД: точные capability/support поля P0 всё ещё draft;
  P1.1 обязан читать их frozen v1.0.0 и эскалировать любое несовпадение до реализации.
- [POSSIBLE-DEFECT]: P0 спроектирована, но не исполнена; поэтому P1 design готов, а execution
  остаётся fail-closed до терминальных P0.3/P0.4. FOREMAN/fleet не читались и не менялись.
