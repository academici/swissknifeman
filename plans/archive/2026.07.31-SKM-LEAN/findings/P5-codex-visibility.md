# P5-codex-visibility — живой замер видимости служебных каталогов плана для Codex

Якорь: swissknifeman рабочее дерево, измерено 2026-08-01. `codex-cli 0.146.0`
(`command -v codex` → `~/.local/bin/codex`).

## 1. Промпт (дословно, оба прогона)

```text
You are working on item P5.4 of plan 2026.07.31-SKM-LEAN. Do NOT write or edit any files — this is a
read-only visibility check. Read exactly these paths under the current repository and report back:

1. plans/2026.07.31-SKM-LEAN/brief/00-brief.md
2. every file inside plans/2026.07.31-SKM-LEAN/findings/ (list filenames, then open one and quote its
   first heading)
3. every file inside plans/2026.07.31-SKM-LEAN/research/ (list filenames, then open one and quote its
   first heading)
4. the top-level entries of .claude/ (list them)
5. the top-level entries of .codex/ (list them)
6. the top-level entries of .agents/ (list them)

Output a Markdown report with one section per numbered item above. For each, say explicitly whether you
were able to read/list it (yes/no) and give the concrete evidence (filenames found, first heading quoted,
or the exact error if you could not). Do not summarize or skip any of the six items.
```

## 2. Прогон 1 — окружной дефект (раскрывается по `root.evidence-integrity`)

```
codex exec -C "$PWD" -s read-only --skip-git-repo-check -o <output.md> "<промпт выше>"
```

Отказ ДО первого чтения — `bwrap` (bubblewrap-песочница Codex CLI) не смог поднять сетевой
неймспейс:

```
bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted
```

Причина — хостовое ограничение Ubuntu AppArmor на непривилегированные user-namespaces
(`sysctl kernel.apparmor_restrict_unprivileged_userns` → `1`), а не что-либо, специфичное для
дерева `swissknifeman` или для канона инструкций. Это дефект ОКРУЖЕНИЯ (`root.evidence-integrity`:
«sandbox» — один из перечисленных классов), не находка про видимость каталогов: `-s read-only`
у `codex exec` не смог стартовать НИ ОДНУ команду, поэтому все шесть пунктов вернулись `no` с
одинаковой ошибкой песочницы — не доказательство отсутствия видимости.

## 3. Прогон 2 — успешный (после смены флага песочницы)

```
codex exec -C "$PWD" --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check \
  -o <output.md> "<тот же промпт>"
```

`--dangerously-bypass-approvals-and-sandbox` выбран намеренно и только для этого разового
измерения: промпт запрещает какие-либо записи, задание — только чтение и перечисление, риска
записи в дерево нет (подтверждено фактом — см. п. 5). Session id
`019fbdd8-147c-7211-9c78-edec3c5bbe8d`.

Полный вывод последнего сообщения агента (`-o`), дословно:

```markdown
## 1. Brief

**Able to read:** Yes

**Path:** `plans/2026.07.31-SKM-LEAN/brief/00-brief.md`

**Evidence — first heading:**

> # Бриф владельца — 2026.07.31-SKM-LEAN (слой 0)

## 2. Findings

**Able to list:** Yes
**Able to open a file:** Yes

**Files found:**

- `P1-fleet-baseline.md`
- `P1-plugin-cli-probe-2026-07-31.md`
- `P1-plugins-cwd-defect-2026-07-31.md`
- `P2-fleet-after.md`
- `P2-hub-pilot.md`
- `P2-resident-layer-probe-2026-07-31.md`
- `P2-rules-carrier-contract-conflict.md`
- `P2-rules-pilot.md`
- `P2.4-fleet-emit-dryrun.md`
- `P2.4-provider-emit-probe-2026-07-31.md`
- `P3-desc-burndown.md`
- `P3-fork-selection.md`
- `P3-native-fields-context-cost-2026-07-31.md`
- `P3-native-fields-smoke.md`
- `P3-paths-mechanism.md`
- `P3-scope-pilot.md`
- `P3-scope-rollout.md`
- `P3.1-bench-harness-probe-2026-08-01.md`
- `P3.1-paths-escalation-rag-2026-08-01.md`
- `P4-headless-envelope-2026-07-31.md`
- `P4-wave-acceptance.md`
- `P5-hygiene-surfaces-2026-07-31.md`
- `P5-oq6-remediation-facts-2026-08-01.md`
- `P5-vendored-audit.md`
- `P6-core-recon-2026-07-31.md`
- `P6-manifest-drift-2026-07-31.md`
- `rag-2026-07-31-native-skill-fields.md`
- `repo-recon-2026-07-31.md`

**Opened:** `P1-fleet-baseline.md`

**First heading:**

> # P1-fleet-baseline — резидентный первый ход по флоту

## 3. Research

**Able to list:** Yes
**Able to open a file:** Yes

**Files found:**

- `01-user-intent.md`
- `02-p2-resident-model.md`
- `03-p3-native-scope-model.md`
- `04-p4-driver-model.md`
- `05-p5-hygiene-model.md`
- `06-p6-core-model.md`
- `07-p7-roadmap-address-map.md`
- `08-premortem-and-oq7-verdict.md`
- `09-validation-executability-2026-07-31.md`
- `10-validation-acceptance-form-2026-07-31.md`
- `11-p3-paths-mechanism-2026-08-01.md`
- `12-D100-acceptance-not-public-2026-08-01.md`
- `13-D102-bookkeeping-verdict-2026-08-01.md`
- `14-oq6-trust-policy-2026-08-01.md`

**Opened:** `01-user-intent.md`

**First heading:**

> # Синтез 01 — трассировка брифа владельца «мысль → куда ушла»

## 4. `.claude/`

**Able to list:** Yes

**Top-level entries:**

- `.maind-feature-log.last`
- `agent-pack.lock.json`
- `agents/`
- `analyst/`
- `analyze/`
- `auto-approve.env.ini`
- `maind-memory.sh`
- `memory.env.ini`
- `output-styles/`
- `run-report.env.ini`
- `runs/`
- `scheduled_tasks.lock`
- `settings.json`
- `settings.local.json`
- `skills/`
- `worktrees/`

## 5. `.codex/`

**Able to list:** Yes

**Top-level entries:**

- `agents/`
- `config.toml`
- `hooks/`
- `hooks.json`
- `hooks.json.provider-artifact.bootstrap-transfer.bak`

## 6. `.agents/`

**Able to list:** Yes

**Top-level entries:**

- `plugins/`
- `skills/`

No files were written or edited.
```

Свод по шести пунктам:

| # | Путь | Прочитано/пролистано | Улика |
|:--|:--|:--|:--|
| 1 | `plans/2026.07.31-SKM-LEAN/brief/00-brief.md` | да | заголовок `# Бриф владельца — 2026.07.31-SKM-LEAN (слой 0)` |
| 2 | `plans/2026.07.31-SKM-LEAN/findings/` | да | 27 файлов перечислены поимённо, открыт `P1-fleet-baseline.md` → `# P1-fleet-baseline — резидентный первый ход по флоту` |
| 3 | `plans/2026.07.31-SKM-LEAN/research/` | да | 14 файлов перечислены поимённо, открыт `01-user-intent.md` → `# Синтез 01 — трассировка брифа владельца «мысль → куда ушла»` |
| 4 | `.claude/` | да | 16 верхнеуровневых записей перечислены |
| 5 | `.codex/` | да | 5 верхнеуровневых записей перечислены |
| 6 | `.agents/` | да | `plugins/`, `skills/` |

## 4. Вердикт

**Разрыв НЕ подтверждён.** Живая холодная `codex`-сессия, получив прямое задание, читает и
перечисляет содержимое ВСЕХ шести проверенных путей — служебных каталогов плана
(`brief/`, `findings/`, `research/`) и корневых dot-каталогов (`.claude/`, `.codex/`, `.agents/`) —
без единого отказа. Поимённый список невидимого: **— (пусто)**.

Это честный отрицательный результат (Code Guidance P5.4, «анти-самообман»): половина (б) Scope
Included закрыта фактом прогона, а не рассуждением, и факт — «видимость есть». По Implementation
Rule (7) P5.4 правка Codex-ветки канона (пункт (в) Scope Included) НЕ выполняется — разрыва,
который она бы чинила, не существует.

Замер не отменяет исходное наблюдение `findings/P5-hygiene-surfaces-2026-07-31.md` §6 о том, что
канон НЕ называет служебные каталоги плана явно («о доках» и «о служебных каталогах плана» —
разные утверждения); просто отсутствие явного упоминания на практике не превратилось в отсутствие
доступа, когда агенту прямо сказали, что читать.

## 5. Побочный факт — запись в дерево не производилась

`git status --short` до и после обоих прогонов идентичен (кроме файлов этого item'а, правленных
до запуска Codex): ни один прогон Codex не создал и не изменил ни одного файла в дереве.
