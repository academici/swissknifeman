# Пере-скоуп исполнительского слоя `2026.07.18-FOREMAN` — вердикт v1

Носитель item'а **P4.1** этого плана (D2 «поглощение», D38 «дом остатка», D49/D51/D59 донора).
Документ выносит поимённый вердикт по **24 незакрытым items** донора, чтобы архивация (P0.5) не
спрятала их в архив без адреса, и фиксирует ЗАМЕРЕННЫЙ вход обвязки вместо унаследованной
формулировки.

Все числа и пути ниже получены командами на дереве ветки `next/harness-agnostic`, коммит
**`dde9382a`** (`git rev-parse --short HEAD` до item-коммита P4.1); сами команды — §6.
Непроверенное названо `[UNVERIFIED]` поимённо (§4), а не абзацем.

Документ НЕ пересказывает контракты `2026.07.24-AGENT-RELIABILITY` (далее AR) — цитирует адресом
(`файл § раздел`) и останавливается. Проектных решений о ФОРМЕ политики спавна здесь нет: их
владелец — item P4.2.

## §1. Закрытый набор судеб и правило присвоения

| Судьба | Когда присваивается |
|:--|:--|
| `потребляется готовым: <контракт/модуль>` | deliverable item'а донора доступен ЦЕЛИКОМ по живому адресу (модуль в `packages/**` либо файл данных с путём) — адрес открыт и прочитан, а не вспомнен |
| `остаётся работой, дом: <файл roadmap>` | deliverable недоступен целиком; работа адресована названному носителю. Уже готовая ЧАСТЬ называется отдельной колонкой и НЕ повышает судьбу |
| `отменяется по существу: <причина>` | потребителя нет и в рамках этого плана не появится; причина названа, текст донора остаётся в архиве как провенанс |

**Правило живого адреса (Implementation Rules P4.1).** Формулировка `потребляется готовым`
законна только с живым адресом. Адрес внутри архива плана живой зависимостью НЕ является — такой
item обязан называться иначе (`остаётся работой`). Именно этот класс ошибки уже произошёл у
донора: его дизайн опирался на `decide` как на функцию (§2).

**Правило полноты (применено ко всем 24 строкам).** Судьба у item'а РОВНО одна. Если несущая часть
deliverable'а отсутствует, судьба — `остаётся работой`, даже когда половина предмета уже живёт
кодом; готовая часть выносится в колонку «Что уже готово (живой адрес)». Инфляция вердикта
`потребляется готовым` за счёт частичного покрытия запрещена (анти-самообман,
`code-guidance-patterns.md` §2).

**Расширение набора не потребовалось** (анти-подгонка, §1 того же файла): все 24 items легли в три
судьбы. Два класса адресов, которых буквальный шаблон судьбы не предусматривал, зафиксированы
D-записью **D90** этого плана, а не тихой четвёртой ячейкой: (а) `дом` = item ЭТОГО плана (P1.5 →
P4.5), (б) `отменяется по существу` с причиной «объект вне репозитория» (P7.1–P7.4).

## §2. Замер входа: что из контрактов AR живёт КОДОМ, а что только данными

Раздел написан ПЕРЕД таблицей судеб и проверен командами: обвязка проектируется против факта, а не
против оглавления архива.

| Контракт / артефакт AR | Живой адрес в дереве | Размер (на `dde9382a`) | Статус |
|:--|:--|:--|:--|
| `task-contract-v1` | `packages/task/lib/task/task_contract.py` | 44 701 B | ЖИВОЙ модуль, зовётся командами `task:plan-*` (pre-mutation/pre-final) |
| `risk-review-loop-budget-v1` | `packages/task/lib/task/review_policy.py` | 14 471 B | ЖИВОЙ модуль (identity/reopen/cap), потребитель — `task_contract.py` |
| `unified-agent-trace-v1` | `packages/analyst/lib/analyst/trace.py` + `packages/harness/lib/harness/provider_trace.py` | 10 055 B + 4 031 B | ЖИВЫЕ модули, потребители — `analyst/metrics.py`, `skiller/doctor.py` |
| route evidence | `packages/task/lib/task/route_evidence.py` | 15 261 B | ЖИВОЙ модуль (`capture_actual`/`classify`/`dispatch_guard`) |
| журнал плана (донор P1.1) | `packages/task/lib/task/journal.py` | 21 644 B | ЖИВОЙ модуль, зовётся всеми пятью командами `task:plan-*` и читается `plan_lint.py` |
| **`execution-state-machine-v1` — функция `decide`** | **живого модуля НЕТ.** Машина существует как ДАННЫЕ `plans/archive/2026.07.24-AGENT-RELIABILITY/artifacts/P2.1/state-transition-cases.json` (ключ `cells`) + валидатор тотальности `validate_state_cases.py` — оба ВНУТРИ архива плана | 89 207 B (`cells`: 135) + 34 637 B | ДАННЫЕ, не библиотека |

`grep -rn "def decide" packages/ core/` даёт два совпадения, и ни одно не несёт семантику
контракта: `packages/harness/tests/test_safedirs.py:241` — тестовый хелпер safedirs,
`packages/analyst/lib/analyst/recompute.py:104` — `decide_transition` состояния analyst-памяти.
Спека функции — `execution-state-machine-v1.md` § The decision function
(`decide(state, event, payload, profile)`, чистый lookup по 135 ячейкам); `profile` определён
соседним контрактом `risk-review-loop-budget-v1.md` § Authority profiles (`owner-gated` /
`self-host`, «supplied by the caller and never inferred»).

**Вывод 1 (несущий, ремонт R4 pre-mortem `research/08` §7).** Формулировка донора «обвязка
ПОТРЕБЛЯЕТ `decide` вместо собственного движка» сегодня означает «потребляет 135-клеточную
таблицу из каталога артефактов АРХИВИРОВАННОГО плана». Между «вызвать функцию» и «внести машину
решений в живой пакет» лежит отдельная работа с собственным владельцем: она здесь только
НАЗЫВАЕТСЯ (Scope Excluded P4.1) и записана предусловием в `roadmap/artifex-thin-wrapper.md`.
Пять из шести строк таблицы — живой код, шестая (и единственная несущая для цикла решений) — нет.

**Вывод 2.** Оба контракта, вокруг которых донор строил ядро (`execution-state-machine-v1`,
`risk-review-loop-budget-v1`), в дереве ПРИСУТСТВУЮТ хотя бы одной стороной: review/loop-budget —
кодом, state machine — данными. Триггер эскалации Code Guidance P4.1 («какой-то из трёх контрактов
AR в дереве ВООБЩЕ отсутствует») не сработал: `review_policy.py` и `trace.py` открыты и прочитаны,
основание контракт-блока фазы в силе.

### §2.1 Смежные живые механизмы, на которые опирался бы остаток

Замер сделан потому, что три items донора (P3.1, P3.2, P4.1 донора) писались против «того, что
есть в harness», и с 2026-07-18 это «есть» изменилось.

| Механизм | Живой адрес | Замер (на `dde9382a`) | Что это значит для остатка |
|:--|:--|:--|:--|
| PreToolUse auto-approve | `packages/harness/configs/claude-code/hooks/auto-approve/` | `auto-approve.sh` 1 367 B, `lib/analyze.sh` 8 475 B, декларативный `config.json` 4 815 B, три режима (`modes/{strict,permissive,bypass}.sh`), `permissionDecision` `allow`/`deny` — `lib/common.sh:54,62`; per-project override `<project>/.claude/auto-approve.config.json` | предмет донорского P3.2 покрыт целиком (§3) |
| notify-хук | `packages/harness/configs/claude-code/hooks/notify/notify.sh` | 3 602 B; каналы — ТОЛЬКО локальный десктоп (`notify-send`, `osascript`), мессенджеров нет: `grep -rln "telegram\|Telegram" packages/harness/{configs,lib}` → 0 файлов | канал-агностик слой TG/MAX донорского P4.1 живого адреса не имеет |
| unattended-настройки | `packages/harness/configs/claude-code/settings.yolo.json`, `settings.base.json`, `configs/claude-code/policy/{base,max-permissive}.json` | 335 B / 1 510 B / 646 B + 860 B; `settings.yolo.json` несёт `defaultMode: bypassPermissions` + deny-guardrail'ы, НЕ pattern-scoped allowlist, которого требовал донор | часть предмета P3.1 готова, маппинг «тип запуска → `--permission-mode`» — нет |
| agent-packs | `packages/harness/lib/harness/agentpacks.py` + `configs/claude-code/agent-packs/` (11 паков + `_common`) | механизм render/upgrade/lock живой; пака `artifex` нет | раскатка донорского P6.1 имеет механизм, но не имеет продукта |
| память mAInd | `packages/maind/lib/maind/memory.py` | 39 094 B | репортинг донорского P4.4 имеет приёмник, но не имеет источника (драйвера) |
| стоимость/транскрипт прогона | `packages/harness/configs/claude-code/hooks/run-report/_usage.py` | 10 496 B | reuse, на который донор рассчитывал, цел |
| пакет `packages/artifex` | **отсутствует** | `ls -d packages/artifex` → нет | ни один кодовый item донора не имеет дома в дереве |
| скилл `supervisor-protocol` | **отсутствует** | `ls -d packages/skiller/skills/*/supervisor-protocol` → нет | поведенческий канон живёт только внутри `plan-protocol` (1 346 строк `SKILL.md`) |

## §3. Таблица «item донора → судьба» (24 незакрытых items)

Items фаз донора P2–P7 названы с суффиксом «донора» там, где номер сталкивается с номером item'а
ЭТОГО плана. Судьба — ровно одна на строку.

| Item донора | Предмет | Судьба | Что уже готово (живой адрес) |
|:--|:--|:--|:--|
| P1.5 | re-пин parse-контракта `driver-plan-protocol.md` на терминальную версию канона | `остаётся работой, дом: plans/archive/2026.07.29-HARNESS-AGNOSTIC/phases/P4.md` item P4.5 (D37; адрес-класс — D90) | измерение OQ-2 выполнено: `research/03` §3–§4, вердикт «вариант B, сломан якорь 3 из 5» |
| P2.1 | каркас пакета `packages/artifex` (лаунчер, CLI-скелет, `validate.sh`, plugin.json) | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | образец раскладки пакета — `packages/skiller/` (живой), собственного каркаса нет |
| P2.2 | ядро цикла: очередь → `claude -p` → defensive parse → решение | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | ничего: и `plan_reader`, и `worker` отсутствуют; решение — `decide` (§2, данные в архиве) |
| P2.3 | state прогона + запись в журнал + retry-лестница tier1/2/3 | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | журнал плана — `packages/task/lib/task/journal.py`; классификатор retry отсутствует |
| P2.4 | run-folder: `state.json`, `journal.jsonl`, resume-by-folder, crash recovery | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | парный sealed-контракт `artifex-run-folder.md` (архив донора, провенанс — не зависимость) |
| P2.5 | dry-run пилот драйвера на реальном плане | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | ничего: предмет пилота (драйвер) не существует |
| P3.1 | settings-фрагменты unattended-профиля + маппинг «тип запуска → `--permission-mode`» | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | `settings.yolo.json` + `policy/max-permissive.json` + `harness doctor --settings`; pattern-scoped allowlist и маппинг режимов — нет (§2.1) |
| P3.2 | PreToolUse auto-approve policy hook (детерминированный `allow`/`deny`/`ask` по декларативным правилам, всё вне правил → не тихий `allow`) | `потребляется готовым: packages/harness/configs/claude-code/hooks/auto-approve/` (`config.json` + `modes/` + `lib/common.sh:54,62`) | предмет целиком: хук РАСШИРЯЛ существующий harness auto-approve (его собственный Intent), а источник правил `.artifex/policy.toml` отменён (`research/03` §2.1) — расширять больше нечего |
| P3.3 | скилл `supervisor-protocol` (не-спрашивай→ATTENTION+friction, философия из policy, критерии остановки, дисциплина Completion Notes) | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | половина предмета — канон `plan-protocol` (§8 handoff/эскалация, §6 статусы) + friction-маркеры `journal.py`; философия-директивы адресовали отменённый носитель `.artifex/policy.toml` |
| P4.1 донора | канал-агностик слой эскалации (TG/MAX) + envelope | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | notify-хук есть, но только десктопные каналы (§2.1) |
| P4.2 донора | эскалация драйвера: ATTENTION/RED → каналы + пауза очереди | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | сигнальная сторона в плане есть (`Escalation Needed`, friction `escalation`); отправителя и очереди нет |
| P4.3 донора | Layer 3 remote-approve + блокирующий Q&A через messenger inbox (опционально, гейт OQ-2 донора) | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | ничего; в спеке остатка помечен опциональным слоем, а не обязательным |
| P4.4 донора | репортинг прогонов в память mAInd | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | приёмник — `packages/maind/lib/maind/memory.py`; источник (журнал прогона драйвера) отсутствует |
| P5.1 | модель прогресса: сигналы из журнала/handoff/аудитов | `отменяется по существу: собственный движок решений отменён донором (его D49), замена — чужой контракт execution-state-machine-v1` | — |
| P5.2 | решающая логика continue/point-fix/escalate | `отменяется по существу: тот же D49 — шесть decision outputs объявлены чужим контрактом, второй движок запрещён его § Consumers` | — |
| P5.3 | rulebook правил прогресса + процесс пополнения | `отменяется по существу: сид-каталог правил (owner-principles-catalog) и носитель философии .artifex/policy.toml отменены (research/03 §2.1/§2.2)` | — |
| P5.4 | лог решений супервизора | `отменяется по существу: контракт остался draft (§7 донора), а decision-события принадлежат run-folder несуществующего драйвера` | — |
| P6.1 | раскатка: agent-pack `artifex` + skiller-профиль + lock | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | механизм `harness agent-packs` (`agentpacks.py`) живой; пака нет |
| P6.2 | документация пакета (Diátaxis) | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | ничего: документируемого пакета не существует |
| P6.3 | боевой unattended-пилот + вердикт по рубрике D41 донора | `остаётся работой, дом: roadmap/artifex-thin-wrapper.md` | ничего; в спеке остатка это КРИТЕРИЙ приёмки, а не первый шаг |
| P7.1 | аудит читаемости стратегической поверхности Brain | `отменяется по существу: объект — vault Brain (другой репозиторий), носителя для vault-работ ни у этого плана, ни у каталога roadmap/ swissknifeman нет (D90)` | — |
| P7.2 | анализ фактической практики разработки экосистемы | `отменяется по существу: тот же объект вне репозитория; частично уже сдано доками экосистемы (docs/, plan-protocol), повторного адресата здесь нет` | — |
| P7.3 | стратегический канон `02-Knowledge/00-Strategy` | `отменяется по существу: объект вне репозитория; возврат — новый план с домом Brain, не item этого плана` | — |
| P7.4 | Brain-скиллы доступа к канону | `отменяется по существу: объект вне репозитория; зависит от отменённого здесь P7.3` | — |

**Свод 24 = 1 `потребляется готовым` + 15 `остаётся работой` + 8 `отменяется по существу`.**
Пустых ячеек нет. Из 15 остающихся: 14 — дом `roadmap/artifex-thin-wrapper.md`, 1 (P1.5) — item
P4.5 этого плана.

Сверка с инвентарём P0.3 (`research/03` §2.5), где действовал ДРУГОЙ набор судеб («переиспользуется
как есть / переходит item'ом в P4 / отменяется»): 20 «переходят item'ом в P4» здесь разложились на
1 `потребляется готовым` (P3.2), 15 `остаётся работой` (включая P1.5) и 4 `отменяется по существу`
(P7.1–P7.4); четыре отмены фазы P5 совпадают. Расхождение — не реопен инвентаря: «переходит
item'ом в P4» означало АДРЕСАЦИЮ вердикта сюда (его §1), а вердикт — это и есть эта таблица.

## §4. Поимённые `[UNVERIFIED]`: где обвязка опиралась бы на непринятую приёмку AR

Приёмка `reliability-acceptance-v1.md` формально НЕ выполнена и объявлена недостижимой на этом
инструментальном поколении (AR D88; долги перечислены его D92). Ниже — конкретные утверждения,
которыми будущий строитель обвязки НЕ вправе пользоваться как доказанными.

1. `[UNVERIFIED]` **«трасса прогона несёт связь с контрактом и находками»** — `contract_ref` и
   `finding_refs` не заполняются P3.4-харнесом ни в одной из восьми committed trace-записей
   (AR D88 п. 2, D92 «producer layer-2 → F1»); floor `F1 = 0.96` красный. Обвязка, которая
   атрибутирует решение конкретной ревизии контракта, строится на незаполненном поле.
2. `[UNVERIFIED]` **«наблюдаемость покрывает поток исполнения»** — знаменатель измерения 5/31
   кейсов, 26 из 31 структурно `unmappable`, покрытие типов событий 10/20 и outcome 2/22
   (AR D88 п. 1/2, D92 «расширение наблюдаемости карты»). Вывод «драйвер увидит происходящее»
   держится на пятой части банка.
3. `[UNVERIFIED]` **«канал вопроса владельцу существует»** — `F10 = unknown`, канала
   `owner_question` у headless-диспатча нет вовсе (AR D88 п. 2, D92). Именно на этом канале стоят
   донорские P4.2/P4.3 (блокирующий Q&A и remote-approve): их проектная посылка не подтверждена.
4. `[UNVERIFIED]` **«вторая провайдерская сторона наблюдаема»** — Codex-сторона наблюдаемости не
   пробовалась (AR D88 п. 2, D92). Для плана, чья тема — паритет провайдеров, это прямое
   ограничение: обвязка, спроектированная по Claude-стороне, на Codex не доказана.
5. `[UNVERIFIED]` **«machine решений можно вызвать»** — спека `decide` заморожена, реализации нет
   (§2). Утверждение «потребляем `decide`» доказано только как «существует таблица из 135 ячеек и
   валидатор её тотальности внутри архива».
6. `[UNVERIFIED]` **точная схема пейлоада Codex `apply_patch`** за пределами `tool_name`
   (унаследовано из Open risks этого плана) — задевает любую auto-approve-политику, которая
   решала бы по содержимому правки на стороне Codex.

## §5. Граница: что строит этот план, чего не строит

**Строит (фаза P4 этого плана).** Этот вердикт (P4.1) + спека остатка `roadmap/artifex-thin-wrapper.md`;
запечатанную схему политики исполнения (P4.2) и её живой носитель с валидатором и гейтом (P4.3);
пять обязательных полей задания субагенту в грамматике оркестратора обеих провайдерских проекций
(P4.4); закрытую судьбу parse-контракта донора (P4.5).

**НЕ строит (дом — `roadmap/artifex-thin-wrapper.md`, критерий внедрения там же).** CLI-драйвер
fresh-session цикла; run-folder со state/resume/crash recovery; retry-лестницу tier1/2/3; каналы
эскалации в мессенджеры и remote-approve; прогресс-движок и rulebook (эти четыре — отменены по
существу, §3); репортинг прогонов в mAInd; пак раскатки и боевой пилот; внесение машины решений
`state-transition-cases.json` в живой пакет (названо, не проектируется — Scope Excluded P4.1);
любые работы по vault Brain.

**Не трогает.** Замороженные контракты AR и sealed-контракты донора (правка — D# на нашей стороне,
не reopen донора, §2 Execution Rules); архив донора, кроме предмета item'а P4.5; форму политики
спавна (владелец — P4.2).

## §6. Проверка

Команды, которыми получены числа §2/§2.1 (прогнаны на `dde9382a`):

```
git rev-parse --short HEAD
wc -c plans/archive/2026.07.24-AGENT-RELIABILITY/artifacts/P2.1/state-transition-cases.json \
      plans/archive/2026.07.24-AGENT-RELIABILITY/artifacts/P2.1/validate_state_cases.py
python3 -c "import json;d=json.load(open('plans/archive/2026.07.24-AGENT-RELIABILITY/artifacts/P2.1/state-transition-cases.json'));print(len(d['cells']))"
grep -rn "def decide" packages/ core/
wc -c packages/task/lib/task/{task_contract,review_policy,route_evidence,journal}.py \
      packages/analyst/lib/analyst/trace.py packages/harness/lib/harness/provider_trace.py \
      packages/maind/lib/maind/memory.py \
      packages/harness/configs/claude-code/hooks/auto-approve/{auto-approve.sh,config.json} \
      packages/harness/configs/claude-code/hooks/auto-approve/lib/analyze.sh \
      packages/harness/configs/claude-code/hooks/notify/notify.sh \
      packages/harness/configs/claude-code/settings.{base,yolo}.json \
      packages/harness/configs/claude-code/policy/{base,max-permissive}.json \
      packages/harness/configs/claude-code/hooks/run-report/_usage.py
grep -rln "telegram\|Telegram" packages/harness/configs packages/harness/lib
ls -d packages/artifex packages/skiller/skills/*/supervisor-protocol
```

**Прочитано под вердикт:** `execution-state-machine-v1.md` § The decision function / § Supervisor,
item executor and fresh dispatch / § Consumers · `risk-review-loop-budget-v1.md` § Loop budget and
cadence / § Authority profiles / § Consumers · `plans/archive/2026.07.18-FOREMAN/phases/P2.md` и
`phases/P5.md` (контракт-блоки + маркер пере-скоупа D51/D59) · Intent/Scope всех 24 незакрытых
items донора · `research/08` §1/§2/§7 · `research/03` целиком · `roadmap/README.md` ·
`roadmap/codex-subagent-offload.md` (образец формы).

**Не проверялось:** живой прогон `claude -p`/`codex exec` под драйвером (продукта нет) и поля
JSON-конверта на живом CLI — унаследованный `[UNVERIFIED]` §3 якорь 5 `research/03`; на вердикты
этого документа не влияет.
