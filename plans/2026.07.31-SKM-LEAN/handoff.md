# HANDOFF — 2026-08-02 — after P5.11

**Next:** закрыть фазу P5 — все 11 items терминальны

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | low — шаг-не-item: сверка терминальности 11 items по git-фактам, Phase Handoff, `closure/P5.json` |
| Context | NEW SESSION — шаг-не-item |
| Суть | Закрыть фазу P5 (таблицы, Phase Handoff, `closure/P5.json` по Closure Protocol v1, lint) — после неё фаза P6 стартует с P6.3 (D62) |
| Команда | `/task:plan-close 2026.07.31-SKM-LEAN P5` |

**Done:** **P5.11 закрыт 🟢 Done.** Политика доверия вендоренному классу (ветка (B) OQ-6) стала
исполнимой машиной: человеческий вердикт переехал из таблицы внутри плана в аддитивный блок
`audit` (`verdict`/`at`/`by`/`upstream_sha`/`note`) рядом со скиллом, форму блока и правила
`kind` проверяет `validate.sh`, отсутствие блока — находка триажа `AUDIT_MISSING`, расхождение
якоря — `AUDIT_STALE` (обе в существующем коде выхода **11** и в `--json`). Якорь
`audit.upstream_sha` хранится ОТДЕЛЬНО от `files[].sha256` и не обновляется ни `--apply`, ни
`--resolve` — отметка «вердикт протух» переживает применение апстрима (дыра §5 фактуры
закрыта, доказательство — тест `test_apply_refreshes_files_sha_but_audit_stale_survives`);
производный `stale_verdicts` не удалён, а сужен до бандлов БЕЗ блока `audit` с различимой
причиной. Бэкфилл **56/56** блоков по таблице §4 `findings/P5-vendored-audit.md` тем же
item-коммитом: **51 clean / 5 attention / 0 risk** (на `ab508bbf`), 55/56 свёрток провенансной
базы совпали с колонкой `audited_at`; единственное расхождение и единственное отличие вердикта
от таблицы — `frontend/web-design-guidelines` (`attention` → `clean`, `by: … P5.10`), что
предписано `Inputs` item'а и следует из ремедиации P5.10. `voice-ai/voice-ai` получил
`kind: "reference-only"` и записан без якоря. `validate.sh` зелёный (`230 skills checked`),
`test.sh` — **602** теста (порог ТЗ «> 581»), `--check --json` по реестру: 0 `AUDIT_MISSING`,
0 `AUDIT_STALE`, 6 находок триажа в одном `security/security` (граница §3.2 не ослаблена),
`plan-lint --baseline HEAD` — 0 новых ERROR. Два коммита: item `ab508bbf`
(`feat(skiller): …`), bookkeeping — следующий коммит этого захода.

- **Pending Work item'а:** `packages/skiller/schema/upstream.schema.json` (DX-схема) не
  описывает `audit`/`kind` — вне `Files` item'а, ни один гейт не ломает
  (`additionalProperties` не закрыт, `test_schema.py` файл не покрывает), закрывается
  отдельной аддитивной правкой.

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠) · P4 6/6 (🟢 Done) ·
**P5 6/11 — все 11 items терминальны, фаза ждёт закрытия** · P6 0/3 (⬜) · P7 0/4 (⬜).
Следующий шаг — `plan-close P5`; далее фаза P6 стартует **с P6.3** (порядок D62).

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P5.md` (Completion Notes всех 11 items,
Phase Handoff — пустой) · `plan.md` §4 Status Board, §5 D107–D112, §6 Update Log ·
`roadmap.md` (карта батчей, порядок P6.3 → P6.1 → P6.2) · `packages/skiller/docs/guide/
vendored-skills.md` (носитель политики доверия после P5.11).

**Open risks:**

- **Чужой дифф в рабочем дереве** (этим заходом не тронут): удалённый
  `RESEARCH/AUDIT-loqum-findings.md`; untracked `.swissknife/` и `audits/`. `git add -A`
  запрещён.
- **Преэкзистентный `HTTP 404` на `oss-dev/to-issues`** даёт `--check` код выхода **2** по
  всему реестру (мёртвый URL, Pending Work P5.1) — не путать с гейтом вердикта: находки
  `AUDIT_*` по реестру нулевые.
- **85 файлов апстримов разошлись с записанным sha** (notify) — преэкзистентное состояние,
  не находка. После `--apply` по любому из этих бандлов сработает `AUDIT_STALE`: это ожидаемое
  поведение (байты, против которых вынесен вердикт, изменились), процедура «перечитал →
  обнови `audit`» описана на док-странице.
- Прежние (не изменились): ветка (C) OQ-6 не проверена данными (usage не мерялся) ·
  U1/U2 `[UNVERIFIED]`, остаток риска D106, контракт P4.1 пинован на `06fefc87` ·
  `scripts/test-provider-docs.py` несёт 2 известных FAIL (адрес P6.3) · окружной дефект
  `codex exec -s read-only` (bwrap/AppArmor) · P5.3 Pending Work (унификация четырёх парсеров
  `*.env.ini`) · P5.5 Pending Work (`codex plugin update` без теста) · P5.9 Pending Work
  (stray-упоминание `plan-audit-loop.md` в `roadmap/plan-design-vs-exec-status-check.md:70`).

**Workarounds/Deferred/Open questions:**

- **workarounds:** —
- **deferred:** без изменений: унификация парсеров `*.env.ini` (P5.3) · `codex plugin update`
  round-trip (P5.5) · DX-схема `upstream.schema.json` для `audit`/`kind` (P5.11) — все решением
  владельца.
- **open_questions:** три открытых — OQ-3 (P4.6/P7.1) · OQ-8 (P7.1) · OQ-9 (владелец
  протокола). Новых этим заходом не заведено.
