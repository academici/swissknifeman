---
type: contract
plan: 2026.07.18-FOREMAN
contract: artifex-policy-file
status: sealed (P0.3)
exports: "artifex policy file (per project): opt-in маркер + декларативная политика"
version: v1
consumers: "драйвер P2 (retry/model-override/auto-drive), P3.1/P3.2 (permission-mode/rule severity override — D30), P4.1/P4.2 (каналы/severity-таймаут), прогресс-движок P5.2/P5.3 (пороги/rulebook override), пилот P6.3"
reconcile: "философия-директивы (§3) — СТРУКТУРА бинаря; ЗНАЧЕНИЯ = каталог P0.5 findings/owner-principles-catalog.md после «Утверждено»; D13-находка (ось process-governance + O29 breaking-excision) — owner-gated, §3.3"
verdict: "RAG:— (repo-grounded: D5/D6/D12/D15в-ж/D18/D30, brief/01-refinements §5/§8, package-contribution-protocol, artifex-run-folder.md P0.6, harness policy/base.json JSON-пресеты); формат TOML — D25 stdlib tomllib"
---

# Контракт policy-файла проекта (Artifex) — schema v1

**Назначение.** Канон **декларативной политики per project** для супервизора Artifex: он же
**opt-in маркер** (нет файла → Artifex проект НЕ трогает — D5). Один драйвер — разные политики
проектов; философия владельца НЕ хардкодится в код драйвера, а декларируется здесь (бриф
§Философия, D5). Файл — человекочитаемый, версионированный, читается драйвером через Python
stdlib (D25).

**Границы (что policy — НЕ):**
- **policy = per project (постоянная)**, мандат = per run (временная зона — P0.6). Мандат может
  ТОЛЬКО сузить policy, не расширить (§4).
- policy — **контракт-конфиг, не код**: значения-плейсхолдеры (пороги P5, философия-значения
  P0.5) несут явную ссылку на фазу-наполнитель, не пустоту.
- policy НЕ несёт сиюминутного state прогона (курсор/счётчики — run-folder `state.json`, P0.6).

---

## 1. Формат и место файла

**Формат — TOML.** Обоснование выбора (Implementation Rule P0.3: YAML / TOML / MD-frontmatter):

| Кандидат | Вердикт | Почему |
|:--|:--|:--|
| **TOML** | **выбран** | (1) парсится Python **stdlib** `tomllib` (3.11+; репо 3.12) — драйвер stdlib-only (D25), без внешних зависимостей; (2) поддерживает **комментарии** — обязательны для человеко-авторимой политики (провенанс принципов A1–A9, оговорки порогов); (3) декларативный, секции ⇄ группы полей; (4) semver-строка нативна |
| YAML | отвергнут | нет парсера в Python stdlib (нужен PyYAML — против D25 stdlib-only) |
| MD-frontmatter | отвергнут | frontmatter = YAML (та же проблема) + смешение конфига с прозой тела |

> JSON (формат harness policy-пресетов `configs/claude-code/policy/base.json`) в список кандидатов
> Implementation Rule НЕ входит и **не подходит**: harness-пресеты — машинно-генерируемые фрагменты,
> мёржатся в `settings.json` (обязан быть JSON); policy Artifex — **человеко-авторимый** per-project
> декларатив, где отсутствие комментариев в JSON дисквалифицирует. TOML сохраняет stdlib-парсимость
> при человекочитаемости.

**Место и имя файла.** `.artifex/policy.toml` в корне проекта.
- **Opt-in-семантика (D5):** существование файла `.artifex/policy.toml` = проект подписан на
  Artifex; отсутствие → драйвер проект не ведёт (проверка существования — единственный gate opt-in).
- Дот-директория `.artifex/` = дом **конфига** Artifex per project; runtime-**state** прогонов
  (`runs/<дата-код>/`) остаётся в корне рядом с `plans/` — **как запечатано P0.6 §7** (durable,
  git-tracked, зеркалит канон дома `plans/`). Config (policy) и durable-state (runs) — разной
  природы, разнесены намеренно.
- Отвергнуто: голый `artifex.toml` в корне (замусоривает корень; дот-дир группирует
  будущий per-project конфиг Artifex под одним неймспейсом).

Имя пакета — **Artifex** (D45, sealed). Legacy PLAN-ID `FOREMAN` в путях НЕ используется.

---

## 2. Полная схема v1

TOML-документ. Ниже — все секции с полями (`тип`, `дефолт`, `обяз.`, назначение). Обязательное
поле без дефолта отсутствующее в файле → драйвер отказывает + эскалация (не тихий дефолт).

### 2.1 `[meta]` — opt-in и версия

| Поле | Тип | Дефолт | Обяз. | Назначение |
|:--|:--|:--|:--:|:--|
| `meta.version` | str (semver) | — | ✔ | версия **схемы policy**, которой соответствует файл (эта схема → `"1.0"`); драйвер сверяет с поддерживаемой (§5) |
| `meta.opt_in` | bool | `true` | — | явный тумблер: `false` → драйвер игнорирует проект даже при наличии файла (пауза opt-in без удаления политики) |
| `meta.project` | str | — | — | человекочитаемая метка проекта (для журнала/эскалаций); **без** бизнес-специфики в логике |
| `meta.plan_compat` | str (semver-range) | `"*"` | — | окно версий ведомого плана (`plan.md` Meta Version), с которым policy совместима; вне окна → эскалация (§5, механизм sync D15ж) |

### 2.2 `[retry]` — лимиты попыток (три класса сбоя — D18)

| Поле | Тип | Дефолт | Обяз. | Назначение |
|:--|:--|:--|:--:|:--|
| `retry.tier1_transport` | int | `3` | — | ретраи транспортных сбоев (сеть/битый JSON — P2.3 tier1) |
| `retry.tier2_semantic` | int | `1` | — | ретраи семантических (воркер вернул `is_error`/невалидный результат — tier2); консервативно (D10 сомнение→эскалация) |
| `retry.tier3_quota` | table | см. §2.6 | — | ветка quota (D18) — отдельный класс, не «ретрай»: см. `[quota]` |
| `retry.attempt_cap_per_item` | int | `5` | — | жёсткий потолок суммарных прогонов одного item до эскалации (граница с прогресс-движком P5 — D37) |

### 2.3 `[model_routing]` — override роутинга (D15/O6–O8)

| Поле | Тип | Дефолт | Обяз. | Назначение |
|:--|:--|:--|:--:|:--|
| `model_routing.respect_plan` | bool | `true` | — | по умолчанию модель/effort item'а берутся из §3 Routing плана (SSOT) |
| `model_routing.overrides` | array of table | `[]` | — | per-паттерн override `{ match = "P2.*", model = "sonnet", effort = "high" }`; override НАД планом только когда `respect_plan=false` или явный матч; расширяет model-routing плана, не заменяет канон |

### 2.4 `[escalation]` — каналы (канал-агностик — D12/D32/D34)

| Поле | Тип | Дефолт | Обяз. | Назначение |
|:--|:--|:--|:--:|:--|
| `escalation.channels` | array of str | `[]` | — | упорядоченный список каналов (`["max","tg"]`) — порядок fan-out (D34); пустой → эскалация только в журнал+пауза (fail-safe) |
| `escalation.full_undelivered_action` | enum | `"pause"` | — | при недоставке во ВСЕ каналы: `pause` (fail-safe D34) \| `abort`; никогда не `continue` |
| `escalation.severity_timeout` | table | см. §2.5 | — | деградация по severity (D15в/D33) — см. `[escalation.severity_timeout]` |
| `escalation.night_urgent_only` | array of str | `["quota_weekly"]` | — | какие kind'ы будят ночью (D18: quota-weekly — будить; рутина — ждать утра) |

### 2.5 `[escalation.severity_timeout]` — таймаут-деградация по severity (D33)

Функция severity → действие по таймауту (критичное блокирует навсегда; рутина — safe-action,
НИКОГДА `allow`):

| Поле | Тип | Дефолт | Обяз. | Назначение |
|:--|:--|:--|:--:|:--|
| `critical.timeout_s` | int\|null | `null` | — | `null` = блок навсегда до ответа владельца (contract/деньги/tenant-isolation — O1) |
| `critical.action` | enum | `"block"` | — | `block` (единственно допустимо для critical) |
| `routine.timeout_s` | int | `1800` | — | короткий таймаут рутинного вопроса |
| `routine.action` | enum | `"skip"` | — | безопасное действие по таймауту: `skip` \| `retry`; **`allow` запрещён** (fail-safe, D33) |

### 2.6 `[quota]` — quota-resilience (третий класс сбоя — D18)

| Поле | Тип | Дефолт | Обяз. | Назначение |
|:--|:--|:--|:--:|:--|
| `quota.session_window_action` | enum | `"wait"` | — | 5h-окно (`limit_type=session`): `wait` (таймер до сброса, учётку НЕ менять — директива владельца) |
| `quota.weekly_action` | enum | `"escalate_urgent"` | — | недельный/`unknown`: URGENT-эскалация во все каналы + инструкция смены учётки (ручная, v1) |
| `quota.wait_poll_s` | int | `300` | — | период проверки сброса 5h-окна |

### 2.7 `[progress]` — пороги прогресс-движка (ПЛЕЙСХОЛДЕР — наполняет P5)

> **Плейсхолдер-секция.** Числовые пороги детекции застоя/цикла — **не здесь как значения**:
> их калибрует P5 (rulebook P5.3, similarity-порог калибруется пилотом P6.3 — D36 `[UNVERIFIED]`).
> P0.3 фиксирует ТОЛЬКО место под них и override-механизм; значения-числа = P5.

| Поле | Тип | Дефолт | Обяз. | Назначение |
|:--|:--|:--|:--:|:--|
| `progress.rulebook` | enum | `"baseline"` | — | `baseline` (artifex-shipped `packages/artifex/rulebook/` — D38) \| путь к project-override rulebook |
| `progress.thresholds` | table | `{}` | — | per-project override порогов rulebook (P5.3); пустой → baseline; **значения — P5**, здесь структура |

### 2.8 `[auto_drive]` — скоуп авто-драйва (D27, консервативный дефолт)

| Поле | Тип | Дефолт | Обяз. | Назначение |
|:--|:--|:--|:--:|:--|
| `auto_drive.forms` | array of str | `["plan-exec","plan-close"]` | — | какие `**Next:**`-формы драйвер ведёт авто (D27 DRIVE + механический close); `plan-run`/`plan-audit`/`plan-design`/«ЗАПУСК ВРУЧНУЮ» → пауза+эскалация; дефолт **консервативен** |

### 2.9 `[permissions]` — override unattended-профиля (D30 reconcile P3↔P0.3)

> **Reconcile D30.** P3.1/P3.2 (permission-mode-per-тип-запуска + severity-теги правил) — 
> artifex-shipped дефолты; policy может override тем же механизмом, что model-routing.
> Поля добавлены в P0.3-схему по reconcile-ожиданию D30 (опциональные).

| Поле | Тип | Дефолт | Обяз. | Назначение |
|:--|:--|:--|:--:|:--|
| `permissions.mode_override` | table | `{}` | — | override permission-mode per тип запуска (`{ "plan-exec" = "acceptEdits", "analysis" = "plan" }`); пустой → artifex-дефолт P3.1 (baseline `acceptEdits`, D28) |
| `permissions.rule_severity` | table | `{}` | — | override severity-тегов PreToolUse-правил P3.2 (`{ "<rule-id>" = "critical" }`); пустой → artifex-дефолт P3.2; **никогда** не понижает до silent-allow (fail-safe D29) |

### 2.10 `[philosophy]` — философия-директивы владельца (СТРУКТУРА — см. §3)

Структура поля фиксируется здесь; **ЗНАЧЕНИЯ = каталог P0.5 после «Утверждено»** — §3.

---

## 3. Философия-директивы: СТРУКТУРА (значения досеваются)

**Scope P0.3 = СТРУКТУРА поля, не значения** (значения = утверждённый владельцем каталог P0.5
`findings/owner-principles-catalog.md`). Owner-гейт P0.5 НЕ закрыт (каталог «на утверждении») →
здесь фиксируется форма + плейсхолдер, значения досеваются после «Утверждено» (Pending Work).

### 3.1 Бинарная классификация (ядро D13, каталог §1)

Структура — **бинарь** `architect:package-contribution-protocol` (межпакетное/публичный
контракт/2+ потребителя → **согласование**; внутрипакетное чистое улучшение/один потребитель →
**свободно**):

```toml
[philosophy]
# Мета-принцип (асимметрия качества): усиление строгости/надёжности/изоляции — free;
# ослабление — стоп+эскалация (каталог §1.1, F2).
meta_principle = "ideal_systems_never_block_quality"   # усиление free / ослабление stop

# СТРУКТУРА (два списка принципов-директив). ЗНАЧЕНИЯ ниже — ПЛЕЙСХОЛДЕР,
# досеваются из каталога P0.5 §1 (A1–A9 / F1–F2) ПОСЛЕ «Утверждено».
[[philosophy.require_approval]]   # → супервизор ЭСКАЛИРУЕТ
id = "<A#>"; principle = "<seed: каталог P0.5 §1.2>"; provenance = "<план · D#>"

[[philosophy.autonomous]]         # → супервизор действует СВОБОДНО
id = "<F#>"; principle = "<seed: каталог P0.5 §1.3>"; provenance = "<план · D#>"
```

Поле директивы: `id`, `principle` (текст-условие), `provenance` (план · D# — обязателен,
дисциплина D19: директива без прецедента не сеется). Валидатор policy (P2/P3) отклоняет
директиву без `provenance`.

### 3.2 Асимметрия (каталог §1.1 / F2)

`meta_principle` кодирует асимметрию: правки, **усиливающие** строгость/надёжность/изоляцию —
класс `autonomous` (free); правки, **ослабляющие** изоляцию/контракт/безопасность — класс
`require_approval` (stop+escalate) даже если технически внутрипакетные. Структурно: одна и та же
правка попадает в разный класс по **знаку** (усиление/ослабление), не только по границе пакета.

### 3.3 D13-находка — owner-gated (НЕ расширяется самовольно)

> **If-then P0.3 Code Guidance сработал.** Каталог P0.5 (готов) выявил структуру **богаче
> бинарной**: ~29 принципов на **ортогональной оси process-governance** (§3 каталога) + вызов
> O29 (breaking-as-excision требует меньше церемонии, чем эволюция контракта — бинарь не
> различает). Per Code Guidance — **эскалация к D13, НЕ самовольное расширение схемы**.

Действие P0.3 (не hard-stop — item спроектирован закрыться со СТРУКТУРОЙ + Pending, handoff-интент
`plan-run` exec-ready): фиксируем бинарь как СТРУКТУРУ поля `[philosophy]` (каталог §4: «§1 бинарь
→ структура поля»), а D13-находку **переносим как owner-gated открытое решение** (P0.5 уже
эскалировал её каталогом §5; здесь — restate + Pending Work):

- **Ось process-governance (O1–O29):** по каталогу §4 сеет **rulebook P5.3**, НЕ поле `[philosophy]`
  policy. Поэтому v1-схема `[philosophy]` остаётся **бинарной** — расширять её осью самовольно
  запрещено (If-then). Если владелец при сиде решит ввести ось в policy — это **новый D#** +
  minor-bump схемы (§5), не правка исполнителя.
- **O29 (breaking-excision):** owner-вопрос «нужен ли под-класс low-ceremony `breaking_excision`
  внутри `require_approval`» — оставлен открытым (каталог §5 п.3). До решения — excision идёт общим
  путём `require_approval` (консервативно, сомнение→эскалация D10).
- **O28 (run-mandate сужает права):** сеет границу §4 (мандат сужает policy) — уже в схеме.

Пока владелец не разрулил D13-находку — `[philosophy]` бинарна; ось process-governance живёт в
rulebook P5.3. Расширение оси/подкласса — эскалация к D13 (D13-находка), не самоправка.

---

## 4. Правило «мандат СУЖАЕТ policy, не расширяет» (граница с P0.6/D16)

Точная семантика (зеркалит P0.6 §4): эффективные права прогона = **`policy ∩ mandate`**.

- Мандат (`runs/<код>/brief/00-mandate.md`, P0.6) может ТОЛЬКО: убрать право, сузить скоуп фаз,
  укоротить список каналов, ужесточить severity.
- Мандат НИКОГДА не может: добавить право сверх policy, включить фазу вне проектного opt-in,
  расширить `auto_drive.forms`, ослабить `severity_timeout`.
- Мандат, пытающийся расширить policy → **невалиден**: драйвер отказывается стартовать +
  эскалация владельцу (не тихое усечение) — та же граница пересечения, что в P0.6 §4.

policy = потолок прав (per project, постоянный); мандат = вырез внутри потолка (per run, временный).

---

## 5. Версионирование и синхронизация (механизм, D15ж/idea 6)

**`meta.version` = semver схемы policy** (эта схема → `"1.0"`). Механизм (не только декларация):

1. **Совместимость схемы (драйвер-side).** Драйвер несёт `SUPPORTED_POLICY_SCHEMA` (major).
   При старте читает `meta.version`:
   - `major > supported` → **отказ старта + эскалация** (unknown-схема, как P0.2 breaking-детект);
   - `major == supported`, `minor` любой → OK (additive-only, новые опц. поля игнорируются старым
     драйвером безопасно — дефолты §2);
   - `major < supported` → драйвер применяет миграцию-дефолты или эскалирует (по policy-migration-
     таблице, наполняется при первом major-bump).
2. **Синхронизация с версией ПЛАНА (D15ж).** «policy знает версию плана» конкретно: драйвер читает
   `plan.md` Meta **Version** через контракт P0.2 (SSOT плана) и сверяет с `meta.plan_compat`
   (semver-range). Вне окна → эскалация «policy рассинхронизирована с планом» (не тихий прогон на
   несовместимой политике). Обе версии (`meta.version`, `plan.Meta.Version`) пишутся в run-folder
   journal (`item_launch`/`run_started`) — аудируемость рассинхрона.
3. **Bump-дисциплина.** Breaking-изменение схемы policy (удаление/переименование обязательного
   поля, смена семантики) → major-bump + уведомление проектов-подписчиков (та же дисциплина, что
   §7 Exported плана). Additive (новое опц. поле с дефолтом) → minor-bump.

---

## 6. Примеры

### 6.1 Минимальный валидный (opt-in только)

Достаточно для подписки проекта: существование файла + версия. Всё прочее — дефолты §2.

```toml
# .artifex/policy.toml — минимальный: проект подписан, вся политика по дефолтам Artifex
[meta]
version = "1.0"
```

### 6.2 Полный пример (все секции)

```toml
# .artifex/policy.toml — полная политика проекта (пример)
[meta]
version = "1.0"
opt_in = true
project = "FLEX-2"
plan_compat = ">=0.18, <1.0"

[retry]
tier1_transport = 3
tier2_semantic = 1
attempt_cap_per_item = 5

[model_routing]
respect_plan = true                       # роутинг из §3 плана — SSOT
overrides = [ { match = "P2.*", model = "sonnet", effort = "high" } ]

[escalation]
channels = ["max", "tg"]                   # порядок fan-out (D34)
full_undelivered_action = "pause"          # fail-safe: не ехать без владельца (D34)
night_urgent_only = ["quota_weekly"]       # ночью будить только на quota-weekly (D18)

[escalation.severity_timeout.critical]
timeout_s = 0                              # 0/отсутствие → блок навсегда (contract/деньги — O1)
action = "block"
[escalation.severity_timeout.routine]
timeout_s = 1800
action = "skip"                            # НИКОГДА allow (D33)

[quota]
session_window_action = "wait"             # 5h — ждать, учётку не менять (D18)
weekly_action = "escalate_urgent"
wait_poll_s = 300

[progress]
rulebook = "baseline"                      # artifex-shipped (D38); значения-пороги — P5
thresholds = {}                            # placeholder: override порогов — P5.3

[auto_drive]
forms = ["plan-exec", "plan-close"]        # консервативный дефолт (D27)

[permissions]
mode_override = {}                         # artifex-дефолт P3.1 (acceptEdits baseline, D28)
rule_severity = {}                         # artifex-дефолт P3.2

# --- философия-директивы: СТРУКТУРА; ЗНАЧЕНИЯ досеваются из каталога P0.5 после «Утверждено» ---
[philosophy]
meta_principle = "ideal_systems_never_block_quality"
# [[philosophy.require_approval]]  id="A1"  principle="<seed P0.5 §1.2>"  provenance="EDUFY · Exec Rules"
# [[philosophy.autonomous]]        id="F1"  principle="<seed P0.5 §1.3>"  provenance="FOREMAN · D13"
# D13-находка (ось process-governance O1–O29, O29 breaking-excision) — owner-gated (§3.3),
# сеет rulebook P5.3, НЕ это поле, пока владелец не решит иначе (новый D# + minor-bump).
```

---

## 7. Трассировка полей → D#/потребитель (анти-«поле на будущее»)

| Поле/секция | D# | Потребитель |
|:--|:--|:--|
| `[meta].version` / `plan_compat` (§5 механизм) | D15ж | драйвер (compat-gate), журнал |
| `[meta].opt_in` + существование файла | D5 | opt-in-gate драйвера |
| `[retry]` tier1/2/3 + `attempt_cap` | D18, D37 | retry-петля P2.3, граница с прогресс-движком P5 |
| `[model_routing]` | D15/O6–O8 | запуск воркера P2.2 |
| `[escalation].channels` / `full_undelivered_action` | D12, D34 | эскалация P4.1/P4.2 |
| `[escalation.severity_timeout]` | D15в, D33 | таймаут-деградация P4.2 |
| `[escalation].night_urgent_only` + `[quota]` | D18 | quota-ветка P4.2 |
| `[progress]` (placeholder) | D36, D38 | прогресс-движок P5.2, rulebook P5.3 |
| `[auto_drive].forms` | D27 | скоуп авто-драйва драйвера P2 |
| `[permissions].mode_override` / `rule_severity` | D28, D29, D30 | unattended-профиль P3.1/P3.2 (reconcile) |
| `[philosophy]` бинарь + `meta_principle` | D13 | скилл `supervisor-protocol` P3.3, rulebook P5.3 |
| правило «мандат сужает policy» (§4) | D16, O28 | драйвер (валидация мандата), граница P0.6 |
| D13-находка (§3.3) — owner-gated ось/подкласс | D13 | owner-решение → P5.3 (ось) / P0.3-minor (если в policy) |
