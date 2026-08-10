<!-- plan-projection
projection: decision-archive
projection_version: v1
source_scope: decisions/
through: 2026-08-07/D99
inputs_sha256: e94fe336458f25c5b534c328b98b86b603e536c067e1254550bc0d932e6f01f6
generated_by: task plan-views decisions
-->

# Архив решений

> Не править руками: это генерируемый вид.

| ID | Date | Status | Items | Решение |
|:--|:--|:--|:--|:--|
| D157 | 2026-08-09 | superseded | P6.9 | После frozen v1.1.1 arm-A `fail` P6.9 является structural `waiting`, а не executable item: текущий write scope пуст, ARTIFEX остаётся на паузе, а следующий допустимый шаг появляется только после нового accepted owner D# на successor acceptance/repair после D155. Даже после такого D# первым запускается повторный `task:plan-design 2026.08.07-PLAN-ECONOMY P6.9`; прямой `plan-exec` запрещён до reconcile нового verdict identity, producer paths и donor scope. RAG:— (repo-grounded: `findings/12-p6-acceptance-measurement.md` §Attempt v1.1.1; D153–D155; `research/27-p6.9-terminal-waiting-gate-2026-08-09.md`). |
| D50 | 2026-08-07 | superseded | — | **Отпечаток причины — версионированный КАНОНИЧЕСКИЙ КОРТЕЖ (`fingerprint_version` \ |
| D52 | 2026-08-07 | superseded | — | **Шов дефекта ОБЪЯВЛЯЕТСЯ со стороны `decisions/`/`findings/`, а не новым полем журнала, и его вокабуляр (`file` × `rule_or_contract_locus` × `defect_class`) переиспользуется дословно.** Схема `journal.jsonl` этим планом не меняется; входное объявление отпечатка обязано быть удовлетворимо полями уже замороженного `history-projection` v1. Отвергнуто расширение схемы журнала. |
| D91 | 2026-08-07 | superseded | — | **Бухгалтерия дизайн-бюджета восстанавливается, а её машинная проверяемость заводится в P6.2.** (а) В `## 6. Update Log` дописывается закрывающая строка прогона 1 канонической формы, ПОМЕЧЕННАЯ как восстановленная постфактум. (б) Обязанность команд передавать `--session-id` при записи в журнал вносится в scope P6.2 вместе с литеральным тестом предписания и негативным кейсом; источник значения называется явно — идентификатор сессии присутствует в пути каталога сессии и в имени файла транскрипта. Расфриза схемы журнала при этом НЕ происходит. |
