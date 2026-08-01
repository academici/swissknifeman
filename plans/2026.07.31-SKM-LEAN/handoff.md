# HANDOFF — 2026-08-01 — after P5.7

**Next:** ЗАПУСК ВРУЧНУЮ: implementation/high

| Параметр | Значение |
|:--|:--|
| Model | implementation |
| Thinking | high — канон launch-block, которому следует весь флот планов (5 команд + 5 Codex-зеркал + 11 golden-фикстур + semver-бамп скилла); аддитивность гейта против 26+ живых планов — инварианты, effort high+ по §9 (Routing P5.8) |
| Context | continue (/clear) — ручной item |
| Суть | P5.8: строка `\| Команда \|` в форме launch-block; текущая сессия уже sonnet/high (= предписанному) — можно продолжить тем же `plan-run` без ритуала `/model`+`/effort` |

```
/model sonnet
/effort high
/task:plan-run 2026.07.31-SKM-LEAN P5.8
```

**Done:** **P5.7 закрыт этим заходом** (`task:plan-run`, сессия sonnet/high — Routing P5.7 =
implementation/high, точное совпадение, без перебора/недобора).

- **P5.7 🟢 Done** — диагностируемый отказ `INSTRUCTION_WRITE_FORBIDDEN` от `apply_instructions`
  теперь печатает ожидаемый порядок целей `--authorize` (алфавитный по `target_path`,
  копипастопригодный — тот же разделитель `,`, что парсит CLI) через новое опциональное
  keyword-only поле `_write_refusal(..., message=…)`. Обогащение адресное: message передаёт
  ТОЛЬКО вызов из `apply_instructions` при позиционном/составном рассогласовании; остальные
  восемь вызовов `_write_refusal` `message` не передают (проверено тестом — `repair_instructions`
  и `adopt_instructions` остаются `None`). Попутно починена немая механика `_print_report`:
  `next_action="refuse"` у ВСЕХ `_write_refusal`-отказов забивал `observed` в дефолтном
  (не-`--json`) текстовом выводе CLI — без этой правки новое `message` было бы видно только в
  `--json`, а не в обычном прогоне `harness instructions apply`. Позиционная сверка не изменена
  ни строкой (Implementation Rule 1). Долг воспроизведён живым CLI до/после: `apply --authorize
  CLAUDE.md,AGENTS.md` (неверный порядок) → отказ, stderr называет `AGENTS.md,CLAUDE.md`; тот же
  порядок скопирован буквально → `OK`. Три новых теста в `test_provider_instructions.py`
  (`packages/harness/tests/`): копипастопригодность + round-trip · порядок берётся из живого
  `fresh.artifact_plan.actions`, не хардкодится (сужённый scope-набор) · `message` не затронут у
  двух других вызовов. `docs/reference/instruction-canon.md` дополнен строкой, что отказ печатает
  порядок целиком (существующая строка про алфавитный порядок — от 2026-07-30, предшествует
  плану). Roadmap-запись `instruction-authorize-order.md` закрыта и удалена (`find … -delete`),
  строка в `roadmap/README.md` §«Закрыто и удалено». `bash packages/harness/scripts/test.sh` —
  637/637, `validate.sh` — `OK` (10/10, включая дрейф инструкций 12/12 `clean/noop`),
  `python3 -m harness.instructions --check` — `OK`. Item-коммит `578eb1ca`. Known Deviations: —.

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠) · P4 6/6 (🟢 Done) ·
**P5 3/11 (🟡 In progress)** · P6 0/3 (⬜) · P7 0/4 (⬜). Открыты P5.8–P5.11. Следующий по
порядку — **P5.8** (`solo`, `manual`, implementation/high).

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/phases/P5.md` (ТЗ P5.8 и далее) · `plan.md` §3
Routing · `roadmap.md` (карта батчей — P5.8/P5.9 строго последовательны, D43: оба правят
`plan_lint.py`).

**Open risks:**

- Прежние (не изменились этим заходом): supply-chain находка §3.1 живая до закрытия P5.10 · гейт
  триажа красен по конструкции (D109) · пинованный внешний источник может исчезнуть · ветка (C) OQ-6 не
  проверена данными · преэкзистентный HTTP 404 `oss-dev/to-issues` · U1/U2 `[UNVERIFIED]`, остаток риска
  D106, контракт P4.1 пинован на `06fefc87`.
- **Чужой дифф в рабочем дереве** (этим заходом не тронут): удалённый `RESEARCH/AUDIT-loqum-findings.md`;
  untracked `.swissknife/` и `audits/`.
- `scripts/test-provider-docs.py` несёт 2 известных FAIL (устаревшие утверждённые хеши манифеста) —
  адрес P6.3, не трогать здесь.
- P5.3 Pending Work: унификация четырёх самописных парсеров `*.env.ini` — вне Scope, уходит в
  `roadmap/` при подтверждении владельцем.
- Окружной дефект `codex exec -s read-only` (bwrap/AppArmor, обход `--dangerously-bypass-approvals-
  and-sandbox`) остаётся в силе для будущих item'ов, зовущих `codex exec` в sandboxed режиме;
  P5.7 его не задел — весь прогон шёл через прямые `harness instructions`/`test.sh`.
- P5.5 Pending Work (не изменилось этим заходом): `codex plugin update` отдельным тестом не покрыт.
- **P5.8/P5.9 — строго последовательны** (D43, roadmap.md): оба правят `plan_lint.py`; если
  свип `finish` найдёт скрытую зависимость — батч распускается (roadmap.md примечание).

**Workarounds/Deferred/Open questions:**

- **workarounds:** —
- **deferred:** без изменений (см. предыдущий handoff): унификация парсеров `*.env.ini` (P5.3
  Pending Work); `codex plugin update` round-trip (P5.5 Pending Work) — обе решением владельца.
- **open_questions:** три открытых — OQ-3 (P4.6/P7.1) · OQ-8 (P7.1) · OQ-9 (владелец протокола).
