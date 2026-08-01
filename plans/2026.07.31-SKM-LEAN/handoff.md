# HANDOFF — 2026-08-01 — after P5.2

**Next:** exec-items: task:plan-exec 2026.07.31-SKM-LEAN P5.3 P5.6

| Параметр | Значение |
|:--|:--|
| Model | Sonnet |
| Thinking | medium |
| Context | continue (/clear) — ручной item |
| Суть | Два оставшихся scope-независимых item'а батча **B2**: `*.env.ini` граница/трекинг/схема (P5.3) · playwright `--output-dir`+пиновка (P5.6) |

```
/task:plan-exec 2026.07.31-SKM-LEAN P5.3
```

**Done:** **P5.2 закрыт 🟢 Done** (одна сессия plan-exec) — провенанс `configs/provider-capabilities.json`
зафиксирован ВНЕ файла, в генерируемых носителях.

- Блок «Manifest provenance» в `render_guide()` (`docs/provider-support.md`) + симметричная строка в
  `render_readme_block()` (`README.md`): манифест — рукописный SSOT без генератора, `root.generated-artifacts`
  к нему не применяется, процедура правки — `--write` → `--check`.
- Структурный тест `test_manifest_is_not_an_output_of_the_generator` (`scripts/test-provider-docs.py`):
  `Path('configs/provider-capabilities.json') not in expected_outputs()`.
- Негативный прогон `--check` подтверждён (искажение строки → drift → код 1; восстановление → 0).
- `python3 scripts/test-provider-docs.py`: 5 тестов, 2 FAIL — те же два имени, что на baseline ДО правки
  (устаревшие `APPROVED_*_SHA256`, адрес P6.3/D63); новый тест и остальные три зелёные.
- Item-коммит `b09bab62`; bookkeeping — этим заходом.

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠) · P4 6/6 (🟢 Done) ·
**P5 1/11 (🟡 In progress)** · P6 0/3 (⬜) · P7 0/4 (⬜). Открыты P5.3–P5.11.

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P5.md` (ТЗ P5.3, P5.6, …) · `plan.md` §3 Routing ·
`findings/P5-hygiene-surfaces-2026-07-31.md` §4 (инвентаризация `*.env.ini`) и §7 (три носителя playwright).

**Open risks:**

- Прежние (не изменились этим заходом): supply-chain находка §3.1 живая до закрытия P5.10 · гейт триажа
  красен по конструкции (D109) · пинованный внешний источник может исчезнуть · ветка (C) OQ-6 не проверена
  данными · преэкзистентный HTTP 404 `oss-dev/to-issues` · U1/U2 `[UNVERIFIED]`, остаток риска D106,
  контракт P4.1 пинован на `06fefc87`.
- **Чужой дифф в рабочем дереве** (этим заходом не тронут): `.gitignore` (modified), удалённый
  `RESEARCH/AUDIT-loqum-findings.md`, untracked `.swissknife/` и `audits/`.
- `scripts/test-provider-docs.py` несёт 2 известных FAIL (устаревшие утверждённые хеши манифеста) —
  адрес P6.3, не трогать здесь.

**Workarounds/Deferred/Open questions:**

- **workarounds:** —
- **deferred:** без изменений (см. предыдущий handoff).
- **open_questions:** три открытых — OQ-3 (P4.6/P7.1) · OQ-8 (P7.1) · OQ-9 (владелец протокола).
