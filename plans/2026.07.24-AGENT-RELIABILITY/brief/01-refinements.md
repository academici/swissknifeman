# Refinements — Design Pass 2 — 2026-07-24

## Audit RED, attempt 1

Владелец потребовал полный новый design sweep, а не локальную правку и не
запуск P0. Исправления обязательны:

- neutral Routing по canonical closed enums;
- roadmap с точной таблицей, готовым native Codex `NEW SESSION` carrier для
  каждой solo/batch/workflow-группы и только реальными Owner gates;
- честный счётчик `Design Passes: 2/3`, следующий шаг — новый Pass 3;
- falsifiable RCA: declarative audit/session controls уже существовали, а
  причина их фактического неприменения пока не доказана;
- cold-start evidence: hash/claim inventory внешнего аудита, exact manifest
  семи journals, selected session manifest и deterministic stdlib extractor;
- точные Files/Validation/RAG markers, без wildcard/JIT ambiguity;
- freeze acceptance bank до hook behavior mutation;
- disposable worktree topology для P3 canary;
- полный DoR reconcile и `plan-lint`.

Ограничения: не исполнять P0; не коммитить; не менять packages,
`docs/reference.md`, `CHANGELOG.md`, FOREMAN или consumer repositories;
сохранить user-owned `tmp/` byte-for-byte.

## Design Pass 3/3 — 2026-07-24

Fresh finish обязан дополнительно:

- удалить любую P1.4 isolation через `HOME`/`CODEX_HOME`; использовать только
  task-specific temporary roots, переданные явными arguments/native flags;
- заменить динамический P4.1 `core modules/callers named by audit` точным
  списком `core/provider*.py` и `core/tests/test_provider*.py`;
- применить `package-contribution-protocol` к load-bearing shared/public
  changes: existing-seam survey, Rule of Three, alternatives, ADR и SemVer;
- дать каждому roadmap carrier одновременно semantic Next/model
  class/effort/capabilities/plan context и native Codex
  model/thinking/approval/sandbox/cwd/`NEW SESSION`;
- требовать `command.subagents` для каждого item carrier и fail closed без
  solo fallback, если capability не подтверждена;
- после finish передать план в отдельную fresh frontier/xhigh
  `audit-design`, а не начинать P0.

## Provider portability — 2026-07-24

Владелец уточнил, что план может исполняться Claude. Поэтому:

- `plans/<ID>/root/` — относительный canonical каталог long-lived
  plan-artifacts по plan-protocol, не OS `/root` и не путь для замены;
- canonical repo paths, contracts и semantic task commands должны читаться
  обоими providers; `.agents` и native launch blocks — projections;
- roadmap сохраняет обязательные local Codex recovery blocks, но добавляет
  детерминированный Claude/Codex renderer из
  `packages/task/configs/command-routing.json`;
- host-bound inputs допустимы только как явные evidence exceptions:
  user-owned `tmp/swissknifeman-audit.md`, `~/.codex` sessions и foreign
  journals. Claude на той же машине их читает; другой clone — нет;
- P0.1 fail-closed при отсутствии/hash drift и коммитит manifests,
  corpus/baseline в plan directory; только после этого P0.2+ не зависит от
  raw host paths. Cross-machine portability P0.1 заранее не заявляется.

## Owner portability decision — supersedes host-bound execution — 2026-07-24

Владелец потребовал вынести всё execution-required evidence в план до
`audit-design`. Поэтому:

- ни один item не зависит для исполнения от `tmp/`, `~/.codex`, foreign
  repositories, mAInd или другого hidden local state;
- в `artifacts/source-evidence/` материализуются full Perplexity audit
  snapshot, семь lossless journal snapshots, sanitized selected session
  incident evidence, manifests, precomputed corpus/baseline и stdlib verifier;
- raw rollouts целиком не копируются (сотни MB, secrets/reasoning risk);
  external paths остаются optional provenance и не участвуют в execution gate;
- P0.1 только проверяет и нормализует committed bundle. P0.2+ читают bundle
  artifacts; отсутствие внешнего origin не блокирует;
- Pass 3 finish и следующий `audit-design` возможны только после фактической
  materialization и deterministic verification bundle.

## Canonical self-contained planning — package capability — 2026-07-24

Владелец потребовал сделать подход не локальной особенностью этого плана, а
скомпилированным и тестируемым контрактом `plan-protocol`/`task-plan-design`:

- simple single-session/low-risk plan может ограничиться committed
  brief+acceptance;
- multi-session, high-risk, handoff и audit plans обязаны ссылаться только на
  committed execution inputs или exact paths, produced by a predecessor;
- host/chat/mAInd/`tmp`/foreign paths разрешены только как typed
  provenance/advisory, не как execution inputs;
- evidence bundle, когда он нужен, минимизирует данные, не содержит secrets,
  chain-of-thought или raw bulk и имеет deterministic manifest/verifier;
- semantic carrier остаётся provider-neutral; Claude/Codex — renderers;
- правило должно быть enforced в Task Contract, `plan-design` и `plan_lint`,
  покрыто conformance/eval cases и опубликовано в canonical docs. Prose-only
  инструкция без lint/compiler/tests не считается выполнением.

## Pass 3 reopen — generated closure and Codex identity ownership — 2026-07-24

Audit attempt 2 был остановлен до verdict: inspection доказал два execution
gap, поэтому audit cap не израсходован, P0 не начинался.

- P1.1 замораживает version-first ledger и exact generated-scope guard.
  Skiller получает отдельную canonical map package-API и publication-unit
  versions; unrelated bucket manifests обязаны оставаться byte-identical.
- P1.2/P1.3/P2.2/P2.3 выполняют только порядок
  version bump → full owning generator/tree/locks/marketplaces → read-only
  second check → exact diff-scope assertion. Один `(name,version)` не может
  обозначать разные bytes.
- P2.2 является единственным владельцем canonical plan-protocol/command
  изменения. P2.3 расширяет independently-green compiler через frozen policy
  hook, но не редактирует canonical commands/protocol второй раз.
- `codex plugin list --json` read-only preflight подтвердил enabled
  `core@0.4.0` и `task@0.3.0`. Поэтому executable resolution удаляет все
  шесть root core и шесть root task auto-discovered adapter directories;
  installed generated bundles authoritative, conditional suppression
  запрещён. P1.4 cold-installs repository marketplaces into explicit
  temporary roots and требует каждую из 12 identities ровно один раз.
- Remaining `.agents/skills` — unique bootstrap adapters. Cold recovery
  проверяет canonical package paths and repository marketplaces, а не
  возвращает дублирующий auto-discovery layer.

## Owner override B — redesigned executable contract — 2026-07-25

После literal RED финального design audit attempt 2/2 владелец выбрал ровно
вариант B: явно переопределил исчерпанный двух-аудитный cap и выдал новую
authority на один redesigned executable contract плюс один последующий fresh
independent design audit.

Границы authority:

- исторические design audit verdicts 1/2 и 2/2 остаются RED и не
  переименовываются;
- разрешён ровно один redesign pass 4/4, устраняющий F1/F2 структурно, без
  исполнения P0.1 и без package/docs/runtime/fleet/consumer/FOREMAN changes;
- после redesign разрешён ровно один exceptional independent design audit
  (`0/1` до его старта); он не выполняется в redesign-сессии;
- literal GREEN exceptional audit необходим, но не разрешает P0.1 сам по
  себе: audit-сессия останавливается, а P0.1 требует отдельного явного
  Owner execution approval; option B разрешает redesign + audit, не
  исполнение;
- RED/ATTENTION exceptional audit не выдаёт автоматическую authority на
  дополнительный ремонт или ещё один design audit — следующий шаг снова
  Owner decision.

Обязательная форма ремонта:

- immutable `artifacts/source-evidence/` и его verifier не меняются; P0.1
  получает отдельного item-owned semantic verifier, детерминированные tests и
  report, а нерепродуцируемые из committed bundle raw-session dedup/classifier
  claims маркируются `pinned-not-recomputable`/`unknown`, не «verified»;
- 13 repository-bootstrap identities получают реальные bilingual canonical
  sources, private/source-only publication rule и один generator owner.
  Normal bucket/core/marketplace publication их не публикует. Один
  `registry.py` → `publication.py` path детерминированно эмитит thin Claude и
  Codex root adapters с provenance/hash/version lock; P1.4 проверяет closure и
  exactly-once discovery.

## Owner option B after exceptional attempt 3 — latest authority — 2026-07-25

После exceptional design audit attempt 3 RED владелец снова выбрал option B
и явно разрешил ровно один bounded redesign pass, ограниченный тремя
находками `findings/09-design-audit-exceptional-attempt-3.md`, а затем ровно
один fresh independent design audit. Эта директива является последней и
append-only supersedes authority-C/Claude repair carrier из
`brief/02-claude-takeover.md`; исторические D32–D34 и сам файл не
переписываются и не переименовываются.

Границы последней authority:

- redesign исправляет только deterministic `ITEM_BASE_SHA` contract/carrier,
  две same-item future-artifact Required Reads и exact P1.1 acceptance для
  13-source/26-projection bootstrap map;
- immutable `artifacts/source-evidence/`, packages, runtime, docs,
  CHANGELOG, FOREMAN, fleet, consumers, release, tag и push не меняются;
- после redesign разрешён ровно один новый independent design audit
  (`0/1` до его фактического старта); redesign-сессия его не выполняет;
- literal GREEN audit останавливается на отдельном Owner gate `G-EXEC` и не
  разрешает P0.1; RED/ATTENTION возвращает план владельцу без implicit repair
  или следующего audit;
- semantic plan carrier остаётся provider-neutral. Текущий recovery carrier
  будущего audit — native Codex `gpt-5.6-sol/xhigh` NEW SESSION по корневому
  `AGENTS.md`; это не назначение acting provider для будущих executable
  items.

## Owner authority D — bounded repair находок A1 — 2026-07-25

Директива владельца (сессия 2026-07-25, Claude Opus 5/high), без потери мысли:

1. Формула владельца — «нельзя запускать такой план» — означает **грант на
   проработку, НЕ на исполнение**: план дорабатывается, `G-EXEC` не выдан,
   ни один из executable items не стартует этой директивой.
2. Режим — **реопен фазы P1 по §3 plan-protocol (4 шага)**: bounded repair
   находок A1 (`findings/10-design-audit-a1-attempt-4.md`). Это НЕ детализация,
   НЕ исполнение P0.1, НЕ новый design pass (счётчик `Design Passes` не растёт).
3. Guard-строка «НЕ раньше: Owner grant» в launch-block'е `findings/10`
   снята этой директивой; сам отчёт и его вердикт RED не переписываются.
4. Скоуп ремонта — ровно находки F1–F10 отчёта A1:
   - **F1** — перезамерить effective-коллизии по фактическому runtime (23
     включённых плагина `@swissknifeman`, не 2: `architect@0.4.0` дублирует
     `architecture`/`codebase-design`/`domain-modeling`/
     `package-contribution-protocol`; `query-craft` дублирован core↔research),
     расширить scope D28/D31 и remediation-map, заменить прозаический
     before-state машинно-сравнимыми identity-записями;
   - **F2** — определить производителя и путь `PRE_PLAN_SHA` (файл + item +
     аргумент `run_canary.py`) либо снять rollback-репетицию P3.4 с D-записью;
   - **F3** — A0/D29 → A1/D32 в носителях гейта P0.1 (`phases/P0.md`, roadmap,
     P0.1-carrier);
   - **F4** — назвать `--effort` в Claude-форме P3.4;
   - **F5** — `plan-lint plans/2026.07.24-AGENT-RELIABILITY` в Validation P2.2 +
     правило «план обязан удовлетворять собственным новым tier-правилам»;
   - **F6–F10** — Exported-строка `risk-review-loop-budget-v1`; cross-plan
     запись про `2026.07.25-ECO-OPT` + правило исключения чужих коммитов в
     diff-scope guard; снятие staleness §1/Meta/index/«findings 00–08»;
     P2.5 «isolated provider homes»; D-запись «brief/02 инструкционный слой
     делегирован ECO-OPT D9/P7».
5. Финал захода — обновить `handoff.md` и **запросить у владельца следующий
   гейт**: новый independent audit ИЛИ `G-EXEC` под названный долг. Заход сам
   гейт не выбирает и аудит не выполняет.
6. Не трогать: ТЗ/Scope/Files/Validation остальных items; `findings/07–09` и
   исторические вердикты RED (факты, не переименовывать);
   `artifacts/source-evidence/**` (immutable); `packages/**` и runtime
   (design-only); исторические Codex-блоки roadmap как projections;
   `plans/2026.07.18-FOREMAN`; чужой незакоммиченный дифф в рабочем дереве
   (архив-переносы старых планов + `tmp/`).

Расхождение нумерации, зафиксированное явно: директива называла новую
authority-запись «D35», но `D35–D38` уже заняты bounded redesign Pass 5
(владелец писал по состоянию pre-redesign `fe3e1646`, где последней была D34).
Authority D записана как **D39**; смысл директивы не изменён.

## Owner authority E — делегирование решений агенту + провенанс dual-provider — 2026-07-25

Директива владельца (сессия 2026-07-25, Claude Opus 5/xhigh, после вердикта A3 RED
`findings/13-design-audit-a3.md`), без потери мысли:

1. **«Пакет полностью разрабатывается ИИ для ИИ, моё участие тут минимальное.
   Если бо́льшую часть ты сам можешь разрулить — разруливай, если это реально
   будет правильно.»** Это стоячая делегация решений агенту, а не разовый грант:
   проектные развилки, скоуп ремонта, приёмочные пороги и очередь шагов агент
   закрывает сам и называет выбор записью, а не вопросом владельцу.
2. **«Двухпровайдерную структуру пилил Codex, и он сильно косячил при
   разработке.»** Владелец понижает доверие к выходу плана
   `2026.07.19-DUAL-PROVIDER` как к входу этого плана.
3. **«В новой сессии запущу тот промт»** — следующий шаг остаётся bounded repair
   находок A3; исполняет отдельная свежая сессия по launch-block'у `handoff.md`.

### Что эта authority разрешает (толкование, зафиксированное для аудита)

- **Ремонт F1–F6 отчёта A3** в режиме реопена P1 по §3 — без нового design pass.
- **Схлопнуть audit-экономику.** Модель «слот аудита как рационируемый ресурс»
  (cap 2/2 → exceptional → A1 → A2 → A3, authority A–D) проектировалась под
  человека в гейте. При делегации она — чистые накладные расходы: **шесть RED и
  пять design pass при нуле исполненных items** — это ровно тот failure mode
  (audit/fix-loop без продукта), который план создан лечить, воспроизведённый на
  самом плане. Ремонтная сессия обязана заменить рационирование обычным правилом
  канона (`два аудита на фазу`, третий → решение), сняв персональные слоты A0–A3
  как исторические факты, а не как действующий механизм.
- **`G-EXEC` считается выданным этой authority** для self-host работы: P0–P3
  исполняются без отдельного человеческого гейта. G0 (заморозка Acceptance) агент
  принимает сам и фиксирует D-записью.
- **Остаётся за владельцем — только необратимое и наружу:** G1 в P4.3 (tag/push/
  release), раскатка на fleet и 17 подключённых проектов, любая запись в consumer-
  репозитории, продолжение `2026.07.18-FOREMAN`. Это граница «нельзя откатить /
  видно снаружи», а не граница компетенции.
- Если владелец с расширенным толкованием не согласен — сказать до запуска
  промта; тогда действует только пункт «ремонт F1–F6», а `G-EXEC` не выдан.

### Провенанс dual-provider — repo-grounded подтверждение пункта 2

Проверено чтением репозитория, не со слов:

- `plans/2026.07.19-DUAL-PROVIDER/plan.md`: `Authoring Model` = **Codex
  gpt-5.6-sol/high**, 8 фаз / 54 items, D-лог до **D127**, версия **1.4.68**,
  терминальный статус — **🟠 Done with deviations** (не 🟢), в `handoff.md`
  историческая P7.4 остаётся literal `ATTENTION`.
- Именно этот план произвёл всю Codex-поверхность, которую сейчас чинит P1:
  `.agents/plugins/marketplace.json` (`302a5f0a` 2026-07-20 «feat(skiller):
  добавить Codex publication adapter (P3.3)», `04be7d9e` «fix(task): активировать
  Codex plugin publication»).
- **Все 30 рукописных root-адаптеров `.agents/skills/` пришли одним коммитом**
  `e8f5b477` 2026-07-21 «chore(codex): add repository-native bootstrap» — мимо
  генератора, без provenance/hash. Отсюда 16 коллизий из `findings/12`.
- В §7 Consumed этого плана строка «provider publication/artifact contract |
  2026.07.19-DUAL-PROVIDER | preserve Claude compatibility and managed generation»
  сейчас трактует тот выход как надёжный pinned вход.

Следствие для ремонта: строку §7 Consumed переклассифицировать в
**low-trust/verify-before-use**, а items P1.2/P1.3/P1.5, которые расширяют
`publication.py`/`registry.py`/`command_render.py`, обязаны доказывать поведение
тестом на месте, а не наследовать «зелёное» от 🟠-плана. Это не приказ переписать
DUAL-PROVIDER (он терминален и не исполняется) — это снятие презумпции
корректности с его артефактов.

## Решения ремонта A3, принятые агентом по authority E — 2026-07-25

Владелец делегировал развилки агенту («разруливай сам»), поэтому ниже —
не вопросы, а зафиксированный выбор. Каждый несёт D-запись в `plan.md` §5.

1. **Состав фикстуры P1.4 (F1 → D51).** Из четырёх вариантов выбран
   «все units репозиторного marketplace МИНУС три донорских бакета
   (`general`/`research`/`oss-dev`)» — максимальный D42-конформный состав
   (~198 identity Codex / ~205 Claude против ~30 у варианта
   `{core, task, architect}`). Девять пар `core`↔донор и
   `workflow-craft`↔`unit:general` перенесены в обязательный НЕГАТИВНЫЙ прогон:
   там они доказываются поимённо как диагностика D42, а не замалчиваются.
   Разбор вариантов — `research/04-p1.4-fixture-composition.md`.
2. **Метрика §8 (F5 → D53).** Выбран квалификатор «0 в объявленной фикстуре»,
   а НЕ вынос владельцу решения по живой паре `core`+`research`: правка
   user-owned enabled-множества — живая мутация вне границ плана (D42), а
   authority E оставляет владельцу только необратимое/наружное.
3. **Порядок коммитов (F4 → D55).** Весь ремонт (v1.9.0 + v1.10.0 +
   `findings/10–13`) — один bookkeeping-коммит плановых путей; хеш вписан в
   `handoff.md` вторым коммитом ровно одного файла (собственный хеш физически
   не вписать в собственный коммит).
4. **Седьмой design-аудит НЕ назначается.** Шесть RED при нуле исполненных
   items — тот самый audit/fix-loop без продукта; следующий шаг — исполнение
   P0.1. Риск («ремонт уходит в exec без независимой проверки») назван в §9 и
   принят; первая независимая проверка — канонический аудит фазы P0.
5. **Толкование authority E** (снятие рационирования, `G-EXEC` для self-host,
   G0 агенту) записано в D50 и §10 целиком. Владелец может отклонить любой
   пункт одной фразой — тогда действует только «ремонт F1–F6».
