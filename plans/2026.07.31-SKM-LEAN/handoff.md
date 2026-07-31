# HANDOFF — 2026-07-31 — after P2.1

**Next:** ЗАПУСК ВРУЧНУЮ: opus/high

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — новый носитель в контракте проекции + пилот на чужом репозитории |
| Context | continue (/clear) — ручной item |
| Суть | P2.2 — носитель path-scoped `.claude/rules` в проекторе инструкций + пилот переноса на одном проекте флота с замером «до/после» |

```
Исполни item P2.2 мастер-плана 2026.07.31-SKM-LEAN строго по его ТЗ.

ТЗ: plans/2026.07.31-SKM-LEAN/phases/P2.md → `### P2.2 — Path-scoped `.claude/rules`:
носитель в проекторе + пилот` (все 16 полей; Required Reads — до первой правки). Протокол
исполнения и закрытия item'а — packages/task/commands/plan-run.md: Pre-mutation Task
Contract ДО первой мутации, статус 🟡 до работы, два коммита (item + bookkeeping), строка
`write-site: pre_mutation: … · pre_final: …`, запись в journal.jsonl.

ВХОД: `Deliverables` P2.1 — пять секций-кандидатов в path-scoped правила, названных поимённо
в Completion Notes P2.1 (`phases/P2.md`): root.package-boundaries (`packages/**`),
root.shared-core (`core/**`, `packages/*/lib/**`), root.marketplace (`.claude-plugin/**`,
`packages/*/commands/**`), root.reference-provenance (`docs/**`, `**/upstream.json`),
root.docs-build (`docs/**`, `packages/*/docs/**`).
УЧЕСТЬ: перенос секции канона в правило меняет проекцию, поэтому гейт размера канона
(P2.1, `validate_canon_size`) и гейт дрейфа обязаны остаться зелёными тем же коммитом;
`compatibility_assertions` переносимой секции обязаны уехать в правило ДОСЛОВНО — их
присутствие в теле фрагмента проверяет `_validate_fragments`.
```

**Done:** **P2.1 закрыт: 🟢 Done** (item-коммит `7b63b21e`). Правило «резидентный канон
инструкций ≤ 200 строк» перестало быть прозой: `validate_canon_size` в
`packages/harness/lib/harness/instructions.py` проверяет все двенадцать проекций по строкам и
по оценке токенов внутри уже стоящего гейта `[9/10]` `packages/harness/scripts/validate.sh`.
Пороги — четыре именованные константы на два класса артефакта (корневой 200/6 000, пакетный
100/3 000) с выводом числа в комментарии; находка размера аддитивна (`CanonSizeFinding` +
ключ `size_findings`), потому что таблица кодов `provider-instruction-contract` v1.0.0
заморожена (D86). Оценка токенов дублирует `skiller.budget.estimate_tokens` явно, равенство
пинится тестом на общем входе.

Аудит источников: **21 секция корневого канона** (18 `root/common.md` + 3
`root/claude-code.md`) получила поимённый вердикт — **сжата 1** (`root.untrusted-content`
несла свою же формулировку дважды), **приведена к факту 1**
(`root.claude-code.context-budget` — сверен с `budget.py:203–204` = 16 000/23 000 и с
процедурой `--with-plugins`, расхождений нет), **5 кандидатов в path-scoped правила** (вход
P2.2), **14 оставлено**. Числа «до/после»: строка `CLAUDE.md + rules` **2387 → 2370 ток**,
`Итого` 11919 → 11902 ток, `CLAUDE.md` 88 строк (потолок 200).

Тем же заходом закрыты находки **аудита P1 A1–A8** (плановая бухгалтерия, `plans/**`
carve-out, отдельного коммита не даёт): гейт владельца **A1** — вариант A (`🟠` P1.1 и фазы
остаются исторической записью, класс отклонения переиздан как carve-out (b), не material,
**D88**); **A2** — `Files` P1.3 получил пятый носитель канона, `Files` P2.1 — обе литеральные
фикстуры; **A4/A5** — `roadmap.md` и `index.md` приведены к факту; **A6/A7/A8** — три
невоспроизводимых числа отчётов зафиксированы **D87** без ретро-правки ТЗ закрытых items.

**Валидация P2.1 (на item-коммите `7b63b21e`):** `harness instructions --check` — exit 0,
12 целей `clean`; `packages/harness/scripts/validate.sh` — `validate: OK`;
`packages/harness/scripts/test.sh` — **Ran 552 tests, OK** (было 537, +15 новых);
`wc -l CLAUDE.md AGENTS.md` — 88 / 92, оба ≤ 200.

`plan-lint --baseline HEAD` (после перезаписи `handoff.md`): **0 ERROR / 1 WARN — новых от
диффа item'а: K = 0** (WARN — известное с P1.1/P1.3 ложное срабатывание
`ORCHESTRATION_MARKER_RE` на цитате прежней DoR-формулировки в Completion Notes P1.1,
`phases/P1.md:113`). `verify-citations.py --strict` (на итоговом дереве, после перезаписи
`handoff.md`): **186 цитат · находок 0** — четыре находки захода
(`plans/2026.07.31-SKM-LEAN/handoff.md:45`, `phases/P1.md:281`, `phases/P1.md:672`,
`plan.md:223`, все — сокращённая ссылка `root/claude-code.md:6`) закрыты так: в живой прозе
`handoff.md` путь починен до полного
`packages/harness/configs/common/instructions/root/claude-code.md:6`, три оставшихся внесены
в `plans/verify-citations-known-exceptions.json` с причиной (D-лог append-only, ТЗ закрытого
P1.3, дословная цитата промпта в блоке `## Audit P1` — все три неправимы по правилам плана).

**Remaining:** **P2.2** (solo, `Exec = manual`, implementation/high — носитель path-scoped
правил + пилот), затем P2.3 → P2.4 → P2.5 → P2.6 и далее P3 → P7 по `roadmap.md`. Доска:
P1 `3/4` (закрыта 🟠) · P2 `1/6` 🟡 · P3 `0/5` · P4 `0/6` · P5 `0/9` · P6 `0/3` · P7 `0/4`.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/plan.md` (§0 Meta v1.0.4, §4 доска, §5
D1–D88, §6 Update Log) · `phases/P2.md` (P2.1 Completion Notes — таблица 21 секции и числа
«до/после») · `phases/P1.md` (§ Audit P1 — находки A1–A9) · `closure/P1.json` ·
`packages/harness/lib/harness/instructions.py` (`validate_canon_size`, четыре константы) ·
`packages/harness/docs/reference/instruction-canon.md` (§ Потолок размера канона) ·
`open-questions.md` (открытых пять: OQ-2 · OQ-3 · OQ-5 · OQ-6 · OQ-8) · `roadmap.md`.

**Open risks:** (прежние риски P1–P7 в силе, см. предыдущие handoff — правило двух SSOT) плюс:

- **Диета канона упёрлась в пинованные литералы D76 и дальше сама не пойдёт** — ещё два
  дубля внутри секций (`root.engineering-invariants`, `root.shared-core`) не снимаются без
  правки `compatibility_assertions`, а те пинует матрица §2 в
  `plans/archive/2026.07.29-HARNESS-AGNOSTIC/`; снятие пина — отдельное решение владельца,
  не побочный эффект диеты.
- **Гейт размера меряет файл целиком, включая байты вне управляемых блоков** — если владелец
  допишет прозу в `CLAUDE.md` вне маркеров, красным станет гейт канона, хотя канон не рос;
  диагностика называет метрику и файл, но не различает «наш» и «чужой» вклад.
- **Токенная оценка продублирована в двух пакетах** — расхождение поймает тест-сверка, но
  только в монорепо-раскладке: в standalone-раскладке harness тест пропускается (`skipTest`).
- **Пять кандидатов в path-scoped правила названы, но не проверены на семантику** — P2.2
  обязан подтвердить каждым `paths:`, что знание действительно применимо лишь к части дерева;
  кандидат, оказавшийся общеприменимым, остаётся в `CLAUDE.md` (это легальный исход).
- **`closure/P1.json` `inputs_sha256["phases/P1.md"]` больше не совпадает с живым файлом** —
  после аудит-блока и синхронизации `Files` P1.3 (D85/D87); снимок описывает дерево на момент
  закрытия фазы (`58c60965`), и это его смысл, а не дефект (названо в D87).
- **Порог заморожен поверх модели стоимости MCP, которую P2.3 пере-издаст** (D84, осознанно) —
  P2.3 обязан ТЕМ ЖЕ item-коммитом пере-считать распределение флота и подтвердить или
  пере-издать `16 000/23 000`.

**Workarounds/Deferred/Open questions:** «—» / «—» / OQ-2 · OQ-3 · OQ-5 · OQ-6 · OQ-8 (пять
открытых; OQ-1 и OQ-4 закрыты — D83/D84), см. `open-questions.md`.
