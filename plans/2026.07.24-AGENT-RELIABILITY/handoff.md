# HANDOFF — 2026-07-26 — after P3.5

**Next:** design-phase: task:plan-design 2026.07.24-AGENT-RELIABILITY P3

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `high` |
| Capabilities | `—` |
| Context | `NEW SESSION — шаг-не-item` |
| Model | `opus`/`fable` (Claude) или `gpt-5.6-sol` (Codex) — по §3 Routing через checked mapping, проверяется на cold-start preflight |
| Thinking | `high` — ремедиация по УЖЕ закрытым находкам, не открытое проектирование |
| Суть | Развернуть ремонт вердикта REMEDIATE: два новых item'а в живой фазе P3 (layer-2 paired run; регенерация транскриптов P2.5 поверх `trace_emitted`), реконсиляция записи и два мелких фикса. **P4 не стартует.** |

```
/task:plan-design 2026.07.24-AGENT-RELIABILITY P3

РЕЖИМ: ремедиация вердикта REMEDIATE — ДОБАВИТЬ items в живую фазу P3 и свести запись; НЕ реопен закрытых Deliverable'ов (P3.1–P3.4 пересчитаны и зелены), НЕ детализация с нуля
ВХОД: plans/2026.07.24-AGENT-RELIABILITY/findings/P3.5-terminal-audit.md → § 3 «Находки» и § 6 «Ремонт — состав и адрес»; прочитать ПЕРВЫМ. Затем phases/P3.md → блок `## Audit P3 — 2026-07-26`
СКОУП: 1) новый item — харнес «живой claude -p/Codex вызов → типизированный event-транскрипт, который грейдит адаптер P3.3» + парный прогон на PRE_PLAN_SHA 7479972f: заполняет F6/F8/F9/F10 (находка F1); 2) новый item — перегенерация кандидатских транскриптов artifacts/P2.5 поверх доставленного P3.1 `trace_emitted`, версионируя обе стороны по § Correction procedure: снимает остаточный critical `trace-record-missing`, даёт честное F1 (находка F1); 3) реконсиляция записи без мутаций кода — P3.3 → 🟠 + Known Deviations (F2), ретро-запись кодов pre_mutation/pre_final в Completion Notes P3.1–P3.4 со ссылкой на пересчёт P3.5 (F3), `12` → `8` в phases/P3.md + findings/P3.4-canary.md + handoff.md с якорем `(на cfd0e4ba)` (F4), строка Known Deviations в P3.1 о старт-записи журнала (F7); 4) фикс-item — режим `--check` (или вынос `tree_anchor` из хешируемого payload'а) в artifacts/P2.5/verify_result_manifest.py (F5); 5) уборка — снять регистрацию /tmp/skm-p3.4-debug.TAcgRY/worktree и привести формулировку Known Deviations P3.4 к факту (F6)
НЕ ТРОГАТЬ: ТЗ/Scope/Files/Validation закрытых P3.1–P3.4 (кроме перечисленных в п. 3 полей записи) · замороженные контракты P0/P1/P2 и их артефакты · пороги банка reliability-bank-v1 (правка порога кандидатом запрещена, D15) · фазы P0–P2 и их аудиты · гипотезы и items фазы P4 — P4 не стартует до GREEN · artifacts/source-evidence/** (неизменяем, D25)
```

**Done:**

- **P3.5 закрыт 🟢 Done** (item-commit `e17f61f7`) — независимый terminal reliability
  audit P0–P3, read-only, исполнен `task:plan-run` под **Claude Opus 5 / xhigh**
  (`frontier/xhigh` = предписанное §3 Routing, точное совпадение).
- **Вердикт (item enum): REMEDIATE.** Вердикт фазы по порогу `plan-audit` §2: **ATTENTION**.
  Заход аудита фазы P3 — **1** из двух. Отчёт — `findings/P3.5-terminal-audit.md`; вердикт,
  таблица находок и launch-block продублированы блоком `## Audit P3 — 2026-07-26` в
  `phases/P3.md`.
- **Почему не GREEN — арифметика, не оценка:** **F1 `critical_requirement_retention` = 0.96**
  при target `== 1.0` (единственный остаточный critical `trace-record-missing`), и
  **F6/F8/F9/F10 — весь относительный layer-2 — никогда не измерялись**. GREEN потребовал бы
  повысить `deferred` до green, что Implementation Rules P3.5 и D30 прямо запрещают.
- **ROLLBACK отклонён явно:** кандидатное дерево строго лучше pre-plan по каждой измеренной
  оси (`first_pass_success` 0.1935 → 0.9677, `critical_regression_escape` 22 → 0, effective
  collisions 16+1 → 0). Отрепетированный путь отката остаётся доступен, но не показан.
- **Пересчитано из закоммиченных входов и ЗЕЛЕНО** (на `21ebd7b2`): P0.1 — четыре неизменяемые
  команды + `semantic_bundle_verifier.py` воспроизвёл отчёт **побайтово** (16/16), бандл тронут
  **одним** коммитом за всю историю · P0.2 — 23 кейса / 16 кодов / 4-4 critical corpus · P0.3 —
  `verify ok` + независимо пересчитанные sha256 четырёх файлов, трёх `source_inputs` и
  `content_hash` `82d1e6a9…` · P1.4 — холодная установка: codex 216 / claude-code 204, **0
  коллизий, 0 undeclared root** (F4 = 0), негативная фикстура 9/9 · P2.1 — 135/135 ячеек ·
  P2.8 — `transcripts.json` и `candidate-results.json` регенерированы с **совпавшими sha256** ·
  P3.3 — `benchmark.json` **byte-identical**, 17 ключей против `layer1_metrics` без расхождений ·
  P3.4 — шесть case-коммитов присутствуют (parent = `CANDIDATE_SHA`), шесть патчей побайтово
  равны `git diff --binary`, allowlist соблюдён поимённо, трассы валидны против
  `unified-agent-trace/v1`.
- **Граница authority (G1) соблюдена:** тегов на HEAD нет, 72 коммита не запушены, записей вне
  этого репозитория нет; `plans/2026.07.18-FOREMAN/*` и `plans/2026.07.25-ECO-OPT/plan.md` —
  предписанная §11 кросс-плановая бухгалтерия, разрешённая владельцем, а не consumer write.
- **Пиннованное осталось пиннованным:** `classified_lifecycle_events` (550) и `dedup_correction`
  — `pinned-not-recomputable`; ни один зелёный предикат на них не стоит.
- `plan.md` §0 Meta v1.17.0 → **1.18.0**, §4 Status Board P3 → `4/5`, **D81** (вердикт и его
  основание), §6 Update Log; `phases/P3.md` Phase Status P3.5 → `🟢 Done` + блок `## Audit P3`;
  `roadmap.md` — блок `P3.R` как действующий следующий шаг, блок P4.1 помечен гейтом.

**Remaining:**

- **Ремедиация фазы P3** (следующий шаг выше) — пять пунктов СКОУПа, из них два новых item'а.
- **P4** ⬜ — **не стартует до GREEN**. Гейт назван в самом блоке P4.1 роадмапа («verify literal
  GREEN P3.5») и в Pending Work P3.5.

**Sources of truth:**

- `findings/P3.5-terminal-audit.md` — полный отчёт: § 1 порог вердикта, § 2 проверенное без
  находок с доказательствами, § 3 восемь находок (severity/type/finding_id/failure scenario),
  § 4 классы доказательства и честная граница непересчитанного, § 6 состав ремонта.
- `phases/P3.md` — `## Phase Status` (P3.5 `🟢 Done`), блок P3.5 (Completion Notes несут
  напечатанные коды ОБЕИХ границ компилятора), блок `## Audit P3 — 2026-07-26`.
- `plan.md` — §0 Meta (v1.18.0), §4 Status Board (P3 = `4/5`, `🟡 In progress`), **D81**, §6.
- `journal.jsonl` — пара записей P3.5 (`plan-run`, `actor=opus/xhigh`).

**Open risks:**

- **Восемь находок аудита открыты** — ни одна не переоткрывает продукт P3.1–P3.4, все адресованы
  ремедиацией: F1 (Blocker, product) недостижимая приёмка · F2/F3/F4/F5 (Major) · F6/F7 (Minor) ·
  F8 (Nit). Полный текст с failure scenario — § 3 отчёта.
- **`verify_result_manifest.py` мутирует закоммиченный артефакт при каждом запуске** (находка
  F5). Любая следующая сессия, пересчитывающая доказательство P2.5, получит ту же незапрошенную
  правку двух строк; отменять `git checkout --`, пока фикс-item не поставлен.
- **Живой debug-worktree `/tmp/skm-p3.4-debug.TAcgRY/worktree`** (35 MB, `7479972f`) остаётся
  зарегистрированным — `git worktree add` того же имени упадёт (находка F6). Удаление не
  выполнено здесь: P3.5 read-only, а `rm`-образные команды вне `safe-dirs.json` в этом окружении
  запрещены хуком.
- **Остаточный lint вне диффа item'а:** `plan-lint` даёт **0 ERROR / 1 WARN** — строка
  `## 6. Update Log` P1.4 длиной 303 символа при пороге 300; открыта с предыдущих handoff'ов.
- **`analyst`/`harness` package-API minor bumps** (`0.1.0`→`0.2.0`, `0.3.0`→`0.4.0`) всё ещё
  должны с P3.1/P3.2 — `package.json` вне `Files` каждого прошедшего item'а.
- **`skiller eval` / `analyst metrics` CLI-подключение** не сделано — долг с P3.2/P3.3.
- **P0 phase-index row** (`task:plan-close … P0`) — все items P0 терминальны, строка доски
  остаётся `🟡`; открыто с ранних handoff'ов.

**Workarounds / Deferred / Open questions:**

- **Репетиция отката P3.4 помечена `cross-checked`, а не `recomputed`** — переигровка switch'а
  потребовала бы создать worktree, то есть произвести ровно тот остаток, который вменяет F6.
  Предпосылки проверены независимо (ancestry, счёт файлов 5/8, `plan-lint` 0 ошибок).
- **Дрейф 18 проб банка при `--strict-probes` — не находка**, а задокументированное самообнуление
  layer-1 после появления seam'а P2 (`reliability-acceptance-v1.md` § Correction procedure). Не
  «чинить»: перегенерация baseline без бампа версии банка запрещена.
- **Самоатрибуция маршрута машинно не проверяема** (`plan-protocol` §9): «Opus 5 / xhigh» выше —
  заявление исполнителя, а не измерение. Жёсткий гейт остаётся за `plan-exec`.
- **FOREMAN re-scope marker** — без изменений, обе терминальные фазы-условия (P2.1, P3.1) уже
  терминальны; владелец — собственная бухгалтерия `2026.07.18-FOREMAN`.
- **`docs-sync` follow-up** (`packages/task/CLAUDE.md`, описание compiler/enforcement seam) —
  долг P3.1, не тронут.
