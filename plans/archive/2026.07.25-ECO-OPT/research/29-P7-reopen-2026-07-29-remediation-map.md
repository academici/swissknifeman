# research/29 — Карта ремедиации реопена P7 (2026-07-29)

**Тип:** слой 2 (авторский синтез). **Вход (слой 1 и факты):**
`phases/P7.md` § `## Audit P7 — 2026-07-29` (вердикт RED, находки F1–F13) ·
`artifacts/P7.1/breakage-log.md` №2 · `research/21-P7.2-instruction-slice-spec.md` §3.4/§5 ·
живой прогон `codex-cli 0.145.0` этой сессии (ниже §1) · `plan.md` §5 D140–D143, §6 Update Log.
**Потребители:** ТЗ items P7.4/P7.5/P7.6 (`Required Reads`), D144–D146.

Файл существует ровно затем, чтобы исполнитель **не сочинял формулировки**: все правки ниже
даны текстом «было → стало». Отклонение от них — не свобода стиля, а находка ревью.

---

## §1. Машинная проверка основания F2 (внешний факт о поведении CLI)

Прогнано в этой сессии 2026-07-29 на `codex-cli 0.145.0`:

| Команда | Факт |
|:--|:--|
| `codex doctor --help` | `Usage: codex doctor [OPTIONS]`; в списке опций **`-c, --config <key=value>`** (+ `--json`, `--enable/--disable`, `--summary`, `--all`, `--no-color`). Флага `-m/--model` в списке НЕТ |
| `codex doctor -m gpt-5.6-terra --json` | `error: unexpected argument '-m' found` |
| `codex exec --help` | несёт `-c, --config` **и** `-m, --model`; `-a/--ask-for-approval` отсутствует |
| `codex --help` (TUI) | несёт `-c`, `-m` **и** `-a, --ask-for-approval <APPROVAL_POLICY>` |

`RAG:✅ 2026-07-29 — живой прогон бинаря, не память и не пересказ.` Аудит (`## Audit P7`, F2)
получил то же самое независимо, включая `codex doctor --json -c 'approval_policy="never"'` →
`approval policy = Never`.

**Что из этого следует и что НЕ следует.** Ложно только основание («does not accept
`-m`/`-c`»): `-c` принимается. Операционный вывод буллета остаётся ВЕРНЫМ и не пересматривается:
`codex doctor` показывает состояние, которое резолвит **для себя** (свои `-c` + `config.toml`),
и о пине ЧУЖОЙ живой сессии не знает ничего — источник истины по model/effort остаётся сама
запущенная команда.

---

## §2. Правки текста «было → стало»

### 2.1 F2 — `AGENTS.md`, буллет preflight (сейчас строки 67–72)

Меняется **только скобка** в первом предложении; остальная часть буллета — байт-в-байт как есть.

Было:
```
- Cold-start preflight is `pwd` → `git status --short` → `codex doctor --json` (does not
  accept `-m`/`-c`; useful for hook/auth checks, NOT for a session's model/effort) →
```
Стало:
```
- Cold-start preflight is `pwd` → `git status --short` → `codex doctor --json` (takes `-c`
  overrides but rejects `-m`; it reports the config/auth/hook state it resolves for ITSELF,
  never a running session's model/effort) →
```

### 2.2 F12 — `AGENTS.md`, буллет launch-блока (сейчас строки 57–61)

Было:
```
  a table with the exact native model, reasoning effort, approval policy, sandbox, cwd and
  context (`NEW SESSION`), followed by one copy-paste shell command containing `codex -C`,
  `-m`, `model_reasoning_effort`, `-a never`, `-s danger-full-access` and a self-contained
  cold-start prompt.
```
Стало:
```
  a table with the exact native model, reasoning effort, approval policy, sandbox, cwd and
  context (`NEW SESSION`), followed by one copy-paste shell command carrying cwd (`codex -C`),
  model, `model_reasoning_effort`, approval policy, `-s danger-full-access` and a
  self-contained cold-start prompt — in the form valid for the launch path used: the TUI form
  pins approval with `-a never`, the headless `codex exec` form (which has no `-a` flag) with
  `-c 'approval_policy="never"'`.
```

Остаток буллета (со слов `If there is no executable next item, …`) не трогается.

### 2.3 F2-синхрон — `research/21-P7.2-instruction-slice-spec.md` §3.4 (сейчас строки 110–113)

Спека цитирует ПРЕДПИСАННЫЙ текст буллета — цитата обязана совпасть с §2.1 дословно
(две строки блока `​```…​```` внутри §3.4). Абзац «**Факт:**» ниже уже говорит верно и
**не трогается**; к нему добавляется одно предложение:

```
Уточнение 2026-07-29 (реопен P7, D144/F2): `codex doctor` **принимает** `-c/--config`
(проверено `codex doctor --help` и `codex doctor --json -c 'approval_policy="never"'`
на codex-cli 0.145.0) и отвергает только `-m`; предписанный текст буллета выше приведён
к этому факту, цель правила («не выводить пин из файлов») не изменилась.
```

### 2.4 F8 — `phases/P7.md:534` (Completion Notes P7.2, цитата команды)

Было: `` (`find . -name AGENTS.md` → только корневой) ``
Стало: `` (`find . -name AGENTS.md -not -path "*/node_modules/*"` → только корневой; голая
форма даёт 5 попаданий, 4 под `node_modules/`) ``

### 2.5 F9 — `CHANGELOG.md:288` (счёт починенных поломок)

Было: «Три из четырёх поломок живого dogfood-прогона P7.1 (`findings/P7.1-switch-test.md` §6)
починены по адресу: …» + три пункта.
Стало: «**Четыре** поломки живого dogfood-прогона P7.1 (`findings/P7.1-switch-test.md` §6)
починены по адресу: …» + те же три пункта + четвёртый, дословно:
```
форма семантического носителя `Next` больше не переписывается здесь — строка
router-таблицы отправляет к канону `general/plan-protocol` §8 (поломка №6).
```
Скоуп сообщения коммита (`feat(root,task)`, находка F11) НЕ переписывается — история git
неизменяема, а компенсирующей записи аудит не требовал.

### 2.6 F10 — «пятикратный» → ≈4,5× (32 768 / 7 252 = 4,52)

| Носитель | Было | Стало |
|:--|:--|:--|
| `CHANGELOG.md:294` | `(≈22%, запас пятикратный)` | `(≈22%, запас ≈4,5× — 32 768 / 7 252)` |
| `phases/P7.md:533` | `запас 25 516 б (≈78%, пятикратный)` | `запас 25 516 б (≈78%, ≈4,5×)` |
| `research/21-…:149` | `запас пятикратный с большим отрывом` | `запас ≈4,5× (32 768 / 7 252 = 4,52)` |
| `research/21-…:160` | `при пятикратном запасе (§5)` | `при запасе ≈4,5× (§5)` |

**НЕ трогать** `findings/P7.1-switch-test.md:25`: там замер 5 398 б, `32 768 / 5 398 = 6,07` ⇒
«более чем пятикратный» — **истинно**. Замена там была бы порчей верного факта.

### 2.7 F7 — `phases/P7.md`, Completion Notes P7.1 (строка после `write-site:`)

Вставляется строкой (форма — как у P7.2/P7.3, которые открываются `Session: …`):
```
Session: Claude Opus 5/high (`plan-run`, подтверждается §6 Update Log — строка
«plan-run/Claude Opus 5/high (P7.1 закрыт 🟠)»). Против §3 Routing P7.1 = `implementation/high`
это ПЕРЕБОР тира (frontier вместо implementation): по ходу item'а принимались owner-развилки
(D140 — реопен чужой фазы P6 и ТЗ нового item'а P6.4), то есть открытые design-решения
фактически были; перебор законен по Tier policy §9 и называется здесь явно, а не остаётся
выводимым только из §6.
```

### 2.8 F13 — `phases/P7.md`, `Pending Work` P7.1 (строки 326–328)

Было: «Фаза P6 остаётся реопененной и ждёт отдельного закрытия: `Возобновление:
/task:plan-close 2026.07.25-ECO-OPT P6` …».
Стало:
```
**Pending Work:** — (хвост снят: фаза P6 закрыта повторно 2026-07-29 коммитом `52b4e1c7`,
§4 Status Board — `| P6 | … | 1/4 | 🟠 Done with deviations |`; маркер `> УСТАРЕЛ` с её
`## Phase Handoff` снят тем же закрытием).
```

### 2.9 F1 — агрегат `## Phase Handoff` фазы P7 (строки 845–852)

Правило: агрегат собирается **грепом полей** `**Known Deviations:**` трёх items, а не по
памяти о ходе сессии. Фактическая раскладка на 2026-07-29 (после D146):

| Item | Поле `Known Deviations` | В агрегат |
|:--|:--|:--|
| P7.1 | шесть записей (4 `material` + 2 `process`) | как сейчас, без правки текста |
| P7.2 | `—` (пусто) | «поле пусто — материальных отклонений не заявлено» |
| P7.3 | **две** записи: (1) унаследованное (отчёты `budget-first-turn-{before,after}.json` сняты до ре-дизайна ТЗ, дельта 0 = граница инструмента); (2) **`material`** (переклассифицировано D146, было `process`) — проба маршрутизированного вызова сделана прямым `codex-companion.mjs task`, обёртка `/codex:rescue` не проверялась | обе записи названы явно |

Первая строка блока `## Phase Handoff` — маркер `> УСТАРЕЛ — фаза реопенена D144` (ставит
реопен, снимает только следующий `plan-close`); правка агрегата идёт ПОД маркером, маркер
не удаляется.

### 2.10 F1/F4 — `closure/P7.json` (ИСПОЛНЕНО design-заходом, не item'ом)

Правка сделана самим реопеном: `plan_lint` требует согласованности артефакта закрытия с
`## Phase Status` и Status Board (`phase_status`, покрытие items[]) — реопен без неё даёт
**5 ERROR**, а линтер обязан быть зелёным на выходе design-захода. Прецедент — реопен P6
(D140): `closure/P6.json` тогда получил `phase_status: 🟡 In progress` и запись нового `P6.4`
со `status: ⬜ Not started`, `evidence_class: baseline_pending`.

Фактически внесено 2026-07-29:
- `phase_status`: `🟠 Done with deviations` → `🟡 In progress`;
- `items[] P7.3`: `status` → `🟠 Done with deviations`, в `evidence` дописан хвост про D146;
- `items[]` дополнен `P7.4`/`P7.5`/`P7.6` (`⬜ Not started`, `baseline_pending`, «чисел нет:
  item не исполнялся»);
- `metrics[] items_green_of_total`: `"2/3"` → `"1/6"` (счёт по ФАЗЕ, как в §4 Status Board);
- `limitations[]`: +2 записи — граница P7.3 (`/codex:rescue` не проверена) и пометка, что
  `closed_at`/`git`/`inputs_sha256` фиксируют ОТМЕНЁННОЕ закрытие.

`closed_at`, `git.head_sha`, `inputs_sha256` **намеренно не пересчитаны** — они документируют
момент отменённого закрытия; следующий `plan-close` перегенерирует файл целиком и обязан
**перенести обе новые записи `limitations[]`** (иначе граница P7.3 потеряется — ровно класс
находки F1).

**Для P7.6 остаётся только проверка**, что артефакт согласован (греп-ассершены его Validation),
и запись в `Pending Work` про перенос `limitations[]` при повторном закрытии.

---

## §3. Раскладка находок по носителям (кто чинит что)

| Находка | Носитель | Кто чинит |
|:--|:--|:--|
| F2 (+ синхрон спеки §3.4) | `AGENTS.md`, `research/21` §3.4 | **P7.4** |
| F12 | `AGENTS.md` буллет 2 | **P7.4** (перенесён из нит-пакета — тот же файл и та же секция; два писателя на один файл в одном заходе — источник конфликта правок) |
| F8, F9, F10 | `phases/P7.md`, `CHANGELOG.md`, `research/21` | **P7.5** |
| F1 (агрегат), F7, F13 | `phases/P7.md` | **P7.6** |
| F1/F4 в `closure/P7.json` | `closure/P7.json` | **design-заход** (гейт `plan_lint` — см. §2.10); P7.6 только сверяет и записывает перенос при повторном закрытии |
| F3 | `plan.md` §5 (D145 + приписка к D143) | **design-заход** (D-запись — акт проектирования, не исполнения) |
| F4 | статусы/доска | **design-заход** (D146 + статус P7.3, `## Phase Status`, §4), механика в `closure/P7.json` — P7.6 |
| F5 | `handoff.md` | **design-заход** (реопен перезаписывает `handoff.md` целиком) |
| F6 | `roadmap.md` | **design-заход** (карта обязана отразить реопен и новые items) |
| F11 | сообщение коммита `cccec4eb` | **не чинится** — история git неизменяема; аудит компенсирующей записи не требовал |

---

## §4. Что реопен НЕ трогает (границы, взяты из входа владельца)

`Scope Included/Excluded/Files/Validation` закрытых items вне строк §2 · статусы P7.1 (`🟠`)
и P7.2 (`🟢`) · D140–D143 как тела записей (только новые D и датированные приписки) ·
`findings/` целиком · `research/` кроме §2.3/§2.6 · фазы P1–P6 и P8–P11 · `packages/**` и
`budget.py` (запрет D142 §2.1) · машинное состояние вне репо (`~/.claude/settings.json`,
`~/.codex/hooks.json`) · секция `## Operation router` в `AGENTS.md` целиком.
