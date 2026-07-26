# HANDOFF — 2026-07-26 — after P4.1

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P4.2

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | — |
| Model | `sonnet` |
| Thinking | `high` |
| Context | `same-session — item` |
| Суть | Read-only effective source doctor — расширить `skiller doctor` одним versioned JSON/text представлением активного семантического владельца/provenance/коллизий, следующий по D90 после вердикта гипотез |

```
task:plan-exec 2026.07.24-AGENT-RELIABILITY P4.2
```

**Done:**

- **Фаза P4 доведена до DoR** заходом `plan-design … P4` (Claude Opus 5/high). Входной гейт
  «P4 не стартует до GREEN» (D81) **переопределён D89**: принят measured-scope Owner packet;
  план НЕ терминируется на `🟠`. Приёмка объявлена формально НЕ выполненной — floors не
  повышаются, замороженные контракты/банк (владелец P0.3) не правятся, слово GREEN в доках и
  packet'е не появляется. Состав фазы — 5 items (D90, порядок `P4.4 → P4.5 → P4.1 → P4.2 →
  P4.3`); оркестрация объявлена (D93, carrier `workflows/wf-agent-reliability-p4.js`).
- **P4.4 закрыт 🟠 Done with deviations** (item-коммит `4ca7af67`) — машинный гейт `plan_lint`
  напечатанных кодов границ (ремонт Ф2), ревью ATTENTION: подтверждён Major/Minor дефект
  точности предиката `_lint_write_site_codes_44` (ложный ERROR/ложное молчание на цитировании
  чужих кодов). Детали — `phases/P4.md` P4.4 Completion Notes.
- **P4.5 закрыт 🟢** (item-коммит `e45d0f8f`) — Contribution gate D23 оплачен: `analyst`
  `0.1.0 → 0.2.0`, `harness` `0.3.0 → 0.4.0`; `registry --check` — «артефакты актуальны»,
  нулевой дрейф. Детали — `phases/P4.md` P4.5 Completion Notes.
- **P4.1 закрыт 🟠 Done with deviations** (item-коммит `a376a64e`) — code-grounded вердикт по
  16 несущим гипотезам запиненного снапшота внешнего аудита: 3 accept (оформлены как FP-1/FP-2/
  FP-3 — bounded future proposals с владельцем/контрактом/тестами/наблюдаемым исходом,
  `implemented_by_this_item=false`), 11 reject, 2 unknown (H15 heuristic drift, H16 semantic
  duplication — недостающее доказательство названо поимённо). Ни одной мутации `packages/**`/
  `core/**` (`git diff --exit-code -- packages core` = 0). Validation зелёная дословно: `py_compile`
  exit 0, `json.tool` exit 0, `verify_claim_verdicts.py` → «ok — 553 проверок, снапшот аудита
  совпал с bundle-manifest» exit 0, `git diff --exit-code -- packages core` exit 0. Boundary
  codes: `pre_mutation: allow`, `pre_final: allow` (write-site `task_contract.build`, маршрут
  исполнителя `frontier/high`, model=opus, D75; codegate P4.4 не диагностирует этот item —
  `Updated=2026-07-26` < `WRITE_SITE_CODES_CANON_DATE=2026-07-27`). **Ревью — ATTENTION, не
  GREEN**: deliverables_met=true, scope_boundary_ok=true, files_outside_scope пусто, НО продукт
  item'а несёт два подтверждённых дефекта целостности улик — (Major) `hypothesis-verdicts.json`
  H06 цитирует несуществующий тест `core/tests/test_provider_config.py::TestProviderConfigResolution::
  test_negative_validation_matrix_covers_frozen_contract` (реальный тест лежит в
  `core/tests/test_provider_manifest.py:97`); (Major) сам гейт `verify_claim_verdicts.py`
  (строки 148–151) проверяет только существование ФАЙЛА из `ref`, символ после `::` не
  валидируется вовсе — воспроизведено подменой на выдуманное имя теста, вывод остаётся
  «553 проверок ok»; (Minor) заявленное универсальное правило «every `reject` carries
  `observation_upheld`» нарушено в H05, гейтом не проверяется. Полная запись — `phases/P4.md`
  P4.1 Completion Notes / Known Deviations.

**Remaining:**

- **Два items фазы P4** — P4.2, P4.3 — не стартовали (`⬜`). Ручной фолбэк по items описан в
  `roadmap.md` § «Фаза P4 — carrier оркестрации»; carrier `wf-agent-reliability-p4.js` остаётся
  доступным как альтернативный launch-путь (P4.1/P4.4/P4.5 закрыты `task:plan-run`, не carrier'ом).
- **Ремонт предиката `_lint_write_site_codes_44`** (находки ревью P4.4) — долг с носителем
  «будущий проход по `plan_lint.py`», ОБЯЗАН попасть в P4.3 Owner packet поимённо.
- **Ремонт гейта `verify_claim_verdicts.py`** (не проверяет символ после `::` в `ref`) и
  **исправление цитаты H06** — новый долг с носителем из этого захода, ОБЯЗАН попасть в P4.3
  packet поимённо (или быть исправлен до P4.3, если владелец P4.2/P4.3 сочтёт это дешевле —
  правка самого `verify_claim_verdicts.py`/`hypothesis-verdicts.json` НЕ входит в Scope P4.2).
- **FP-1/FP-2/FP-3 и H15/H16** — обязаны попасть в P4.3 Owner packet поимённо с владельцами;
  FP-1 пересекается с предметом P4.2 (P4.2 может печатать подмножество provenance-данных в
  своём замороженном скоупе, но владельцем FP-1 не становится, D92); FP-2 предлагается тому же
  владельцу, что и долг D88 п.6а.
- **G1** — единственный действующий Owner-гейт: принимается ВЛАДЕЛЬЦЕМ после packet'а P4.3
  (fleet/consumers/FOREMAN/tag/push/release либо hold). Ни один агент прогона наружу не выходит.
- **Строка доски P0** остаётся `🟡` при терминальных items — снимается `task:plan-close … P0`
  (открыто с ранних handoff'ов, вне фазы P4).

**Sources of truth:**

- `phases/P4.md` — `## Phase Context` (переопределённый вход, контракт фазы, порядок),
  `## Phase Status` (5 items, P4.1/P4.4 `🟠`, P4.5 `🟢`), P4.1/P4.4/P4.5 ТЗ + Completion Notes +
  Known Deviations.
- `plan.md` — §0 Meta (v1.21.4), §3 Routing (строки P4.1–P4.5), §4 Status Board (`P4 1/5`),
  §7 Contracts Exported, D89–D93 (§5), §6 Update Log.
- `artifacts/P4.1/hypothesis-verdicts.json` + `artifacts/P4.1/verify_claim_verdicts.py` —
  вердикты 16 гипотез + детерминированный верификатор (с обнаруженным ревью пробелом на `::`).
- `findings/P4.1-code-grounded-audit.md` + `root/provider-core-hypotheses.md` — вход для P4.3.
- `research/10-p4-entry-gate-and-composition.md` — основание решений захода, в т.ч. § 6
  (долги с носителями, вход packet'а P4.3) и § 8 (pre-mortem).
- `phases/P3.md` § `## Phase Handoff` + `findings/P3.11-terminal-audit-2.md` — фактический
  вход фазы (что доказано / что не доказано, с числами).

**Open risks:**

1. **Приёмка формально не выполнена и не будет выполнена этим планом** (D88/D89): `F1 = 0.96`,
   `F10 = unknown`, layer-2 на знаменателе `5/31`, `F6` на знаменателе 1. Носитель ремонта —
   будущий producer layer-2, вне этого плана; packet обязан назвать это первым.
2. **Гейт P4.4 НЕ покрывает P4.1/P4.2/P4.3 этой же фазы**: cutoff `2026-07-27` строго в будущем
   относительно даты их закрытия (`2026-07-26`) — спроектированное поведение D91. Печать кодов
   границ остаётся ручной дисциплиной (P2.7/P2.11), не машинно проверяемой в этом прогоне.
3. **Предикат `_lint_write_site_codes_44` несёт подтверждённый дефект точности** (ревью P4.4,
   ATTENTION): ложный ERROR/ложное молчание на цитировании чужих кодов границ.
4. **Гейт `verify_claim_verdicts.py` не проверяет символ после `::` в `ref`** (ревью P4.1,
   ATTENTION) — мис-цитата H06 прошла все 553 «проверки»; риск повторения при доборе гипотез.
5. **Гейт P4.4 может покрасить чужой живой план флота**, если его items закрываются после
   cutoff без кодов границ — измерено: `validate.sh` по всем 14 планам репо, 0 ошибок.
6. **Ф2 закрывается ПРИЧИНОЙ, не экземплярами**: запись закрытых items P0–P3 не правилась.
7. Остаточный lint вне диффа: 0 ERROR при 1 WARN (строка Update Log P1.4, 303 символа при
   пороге 300) — открыт с предыдущих handoff'ов, не тронут этим item'ом.
8. Долги без носителя в этом плане (D92): producer layer-2 · расширение наблюдаемости карты ·
   канал `owner_question` · Codex-сторона · CLI-подключение `analyst metrics`/системного
   `skiller eval` · промоушен D83 в канон eval-дисциплины · остатки A1 (F11) и A2 · ремонт
   предиката `_lint_write_site_codes_44` · ремонт гейта `verify_claim_verdicts.py` (символ
   после `::`) и цитаты H06.

**Workarounds / Deferred / Open questions:**

- Ф3 (одна строка формулировки `findings/P3.10-layer2-paired.md:29`) и Ф4 (переатрибуция
  производителя layer-2 в замороженном манифесте — только через § Correction procedure
  владельца P0.3) остаются записью; отдельных заходов не стоят.
- Посторонний untracked-каталог `.swissknife/` в рабочем дереве — не тронут этим item'ом.
- `docs-sync` follow-up (`packages/task/CLAUDE.md`, описание compiler/enforcement seam) — долг
  P3.1, не тронут; ближайший естественный носитель — P4.3 (docs), если попадёт в его Scope.
- H15/H16 (unknown-гипотезы) — недостающее доказательство названо поимённо в
  `hypothesis-verdicts.json::missing_evidence`, не решается на закоммиченном дереве.
