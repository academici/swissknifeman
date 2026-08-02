# HANDOFF — 2026-08-02 — after P7.2

**Next:** `/task:plan-exec 2026.07.31-SKM-LEAN P7.3`

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — Routing `implementation/high`/`manual` (final verification + инварианты «ноль записей без адреса», ложный GREEN неотличим от честного) |
| Context | continue (/clear) — ручной item |
| Суть | сведение `roadmap/README.md` (пересборка индекса, снятие заголовка «Входы активных планов», разрешение находок F1/F2/F3/F5) + машинная сверка инварианта «каждый файл ↔ одна строка ↔ класс» |
| Команда | `—` |

```
ЗАПУСК ВРУЧНУЮ: opus/high
/model opus
/effort high
/task:plan-run 2026.07.31-SKM-LEAN P7.3
```

**Done:** **P7.2 закрыт `🟠 Done with deviations`** (item-коммит `2afaf981`; bookkeeping-коммит —
следом за этим handoff). Обе спеки (`analyst-plan-scan.md` 53 строки, `analyst-fleet-coverage.md`
43 строки) перенесены дословно в новый раздел `packages/analyst/docs/roadmap.md`
§«Перенесено из корневого `roadmap/` (2026-08-02)» с провенансом на каждую тему; критерий
внедрения сохранён байт-в-байт (единственная правка структуры — понижение заголовков тем
`##`→`####`, обязательное правилом «структура не перестраивается, добавляется один раздел»).
Оба файла удалены `find roadmap -name '<файл>' -delete` (без подстроки `rm`); два указателя
добавлены в `roadmap/README.md` §«Закрыто и удалено» по образцу `self-learning-memory.md`.
`grep`-сверка ссылок (Implementation Rule 3) вскрыла третье вхождение — `roadmap/
plan-lesson-capture.md:49` называла `analyst-plan-scan.md` «соседним roadmap-файлом», что стало
ложью после переезда; строка починена этим же item'ом (файл не входил в `Files` ТЗ, правка
обязательна правилом (3) — это и есть причина `🟠`, не ошибка переноса). Также исправлена
формулировка провенанса: изначальный «Перенесено из …» с заглавной буквы не матчился
регистрозависимым `grep -c 'перенесено из'` из Validation(4) — переформулировано в «Провенанс:
перенесено из …».

Носители правок: `plan.md` (§0 Last Updated, §4 Status Board — P7 остаётся 1/4, счётчик считает
только 🟢, §6 строка Update Log) · `phases/P7.md` (Phase Status, P7.2 Status `🟠`/Completion
Notes/Known Deviations) · `journal.jsonl` (start + close записи P7.2).

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠) · P4 6/6 (🟢) · P5 6/11 (🟠) ·
P6 0/3 (🟠) · **P7 1/4 (🟡)** — очередь строгая: **P7.3 → P7.4**. `Inputs` P7.3 потребляют
`Deliverables` P7.1/P7.2, `Inputs` P7.4 — Deliverables всех семи фаз. `plans/ACTIVE.md` и
`Status` плана не трогаются — план не терминален.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P7.md` (P7.2 Completion Notes; P7.3
ТЗ) · `plan.md` §3 Routing (P7.3 = `implementation/high` / `manual`) · `research/
07-p7-roadmap-address-map.md` (карта, находки F1/F2/F3/F5, словарь классов — вход P7.3).

**Open risks:**

- **P7.2 закрыт `🟠`, не `🟢`** — единственное material-отклонение: item-коммит несёт правку
  `roadmap/plan-lesson-capture.md` вне `Files` ТЗ, обязательную Implementation Rule (3).
  P7.3/P7.4 (сверка полноты, релизная бухгалтерия) обязаны видеть эту запись как легитимную,
  не как посторонний шум.
- **Чужой дифф в рабочем дереве** (не тронут): изменённый `configs/provider-capabilities.json`,
  удалённый `RESEARCH/AUDIT-loqum-findings.md`; untracked `.swissknife/` и `audits/`.
  `git add -A` запрещён.
- Прежние (не изменились): `verify-citations --strict` — 15 находок, все пред-существующие ·
  остаточные WARN `plan-lint` (10, все пред-существующие, новых от P7.2 диффа — 0) · `ruff`
  несёт 3 пред-существующие ошибки на путях skiller · `scripts/test-provider-docs.py` — 1
  известный FAIL (F5, предмет P7.3) · U1/U2 `[UNVERIFIED]`, контракт P4.1 пинован на
  `06fefc87` · окружной дефект `codex exec -s read-only` (bwrap/AppArmor) · Pending Work
  P5.3/P5.5/P5.9/P6.2.

**Workarounds/Deferred/Open questions:**

- **workarounds:** —
- **deferred:** без изменений по составу (см. предыдущий handoff — унификация парсеров
  `*.env.ini` P5.3 · `codex plugin update` round-trip P5.5 · DX-схема `upstream.schema.json`
  P5.11 · снимок `test_committed_outputs…` P6.3 · типизация `.swissknifeman/config.json` P6.2 ·
  перевод 4 потребителей `load_config` на атрибуты P6.2 · `plan-lint` WARN D29 по фазам с
  заявленной оркестрацией).
- **open_questions:** один открытый — **OQ-9** (владелец протокола, вне плана). Новых этим
  заходом не заведено.
