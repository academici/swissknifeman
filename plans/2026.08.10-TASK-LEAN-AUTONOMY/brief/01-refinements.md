# Уточнения владельца — 2026-08-10

- План должен быть компактным и быстро реализуемым.
- Не строить доказательство преимущественно на программных тестах: реальный проект является
  главным canary, а проверки кода — ограниченной страховкой.
- Нужна разумная граница между жёстким первичным проектированием и свободой исполнения.
- Минимизировать число фаз, сессий, аудитов и повторных погружений в контекст.
- Обычный Perplexity Web обязателен для RAG. Ошибка `search_advanced` не считается
  недоступностью MCP, пока базовый `search` не проверен отдельно.

Эти уточнения заменяют идею большой механизированной batching-системы: план использует две
фазы и четыре пункта, а группировку оставляет адаптивным решением owning-агента.

## Design-finish remediation — 2026-08-10

- Исправить F1–F10 из `findings/03-design-audit-2026-08-10.md` без исполнения P0/P1 и без
  реопена фаз.
- Сохранить четыре item'а, получить 4/4 buildable Task Contracts, exact Validation и
  package-cwd launch carriers, конечные `Files`, определённые GO/ADJUST transitions и
  минимизированные generated bundles.
- Не ослаблять D1–D6, не править generated views вручную, не включать в remediation чужие
  изменения ARTIFEX, `docs/reference.md`, `roadmap/` и `plans/ACTIVE.md`.

## Design-finish remediation after audit round 2 — 2026-08-10

- Выполнить whole-plan `finish` remediation F11–F15 из блока `Audit design — 2026-08-10 — заход 2`,
  не исполняя P0/P1 и не реопеня фазы.
- В P1.1 закрепить exact layout-v2 context acceptance: обычное продолжение производит
  `continue-root`, а red-first v2 fixture и отдельный v1 compatibility fixture защищают обе
  ветви без молчаливого fallback.
- Назначить P1.1 владельцем canonical Task docs, deterministic umbrella projection и обеих
  сборок — standalone package docs и aggregate site; generated aggregate не править вручную.
- Не поглощать чужой dirty `docs/reference.md`: оформить owner-owned committed prerequisite,
  который P1.2 проверяет до canary и при отсутствии оставляет работу в waiting-состоянии.
- Дополнить plan-local RAG точным официальным источником management by exception и сузить
  Spec Kit claim до условной phased decomposition с наибольшим overhead среди перечисленных
  стратегий, сохранив независимый repo-grounded отказ от нового control plane.
- Закрыть исходный dangling journal start только append-событием и регенерировать все затронутые
  views/bundles штатным owner generator.
- Не ослаблять D1–D8, не менять package/product behavior в этом design-заходе и не включать,
  откатывать или перезаписывать чужие ARTIFEX, `docs/reference.md`, корневой `roadmap/` и
  `plans/ACTIVE.md` изменения.

## Design-finish remediation after audit round 3 — 2026-08-11

- Commit complete target-plan carriers отдельно от foreign ARTIFEX, `docs/reference.md`, root
  `roadmap/` и `plans/ACTIVE.md`, затем повторить gates на полученном git-ref.
- Определить один real post-P1.1 canary и точные результаты `not-observed` для отсутствующих
  local-repair/material-review событий без synthetic fault и второго audit loop.
- Вынести factual `[Unreleased]` ledger в P1.1 до возможного D9 waiting; ADJUST не удаляет и не
  откладывает эту запись, а дальнейшая owning-package remediation обновляет её при изменении
  release-visible смысла.
- Обновить index для refinements, research-05/06 и D9/D10; переписать stale handoff на F16–F19.
- Не выполнять P0/P1, не менять package/product code, не ослаблять D1–D9 и не hand-edit
  generated views.

## Field feedback from final design audit — 2026-08-11

- Сам audit не должен тормозить работу из-за детерминированной non-material plan-bookkeeping
  мелочи: stale date/freshness marker, навигационная опечатка или generated-view drift в пределах
  разрешённых plan carriers исправляются inline текущим owning-root.
- После одной repair + deterministic gate rerun тот же audit attempt закрывается `GREEN`; новый
  audit/design pass/session, `ATTENTION` handoff или reopen из-за такой мелочи не создаётся.
- Это исключение не распространяется на material product/spec/acceptance, authority/security,
  необратимость, sealed item scope или решение с модельным judgement: они остаются finding/gate.
- Наблюдаемый инцидент: заход 4 почти остановил исполнение из-за `index.md` freshness date, хотя
  содержательная трассировка была полной. Исправить F20 и сам протокол в текущем root, без пятого
  audit-захода.

## Cross-project telemetry directive — 2026-08-11

- До исполнения разобрать конкретные причины остановок, retries, audit loops и tool failures во
  всех доступных планах/logs Agelto и Swiss Knife Man; голые счётчики без causal case study
  недостаточны.
- Агент сначала проверяет, что фактически произошло с процессом, diff и acceptance, и только
  затем решает repair/retry/continue/stop. Low-level error, ATTENTION, dirty tree или routing
  mismatch не равны product failure.
- Дать гибкую, лёгкую схему: мелкие items и строгие safety/authority/acceptance boundaries, но
  свободная same-session группировка, локальные fallbacks и отсутствие panic/re-audit на
  procedural noise.
- Сохранить настоящие stop cases: security/data loss, frozen acceptance, irreversible/unknown
  write outcome, live-state ownership и исчерпанная authority.
- Дополнить repo evidence обычным Perplexity Web по adaptive execution, resilient failure
  handling и alert fatigue; принимать только выводы, перепроверенные по первичным источникам.
- Встроить решения непосредственно в executable items и canary scorecard; новый supervisor,
  daemon или отдельный telemetry project не создавать.

## Owner correction after P1 audit — 2026-08-11

- Больше одного дополнительного repair-подхода после первого non-GREEN audit считается дефектом
  lifecycle, а не нормальным refine-loop.
- Первый non-GREEN обязан вести прямо в один bounded repair по текущему ТЗ; `plan-design` не
  используется как универсальная реакция на validation/evidence/state mismatch.
- Второй audit финальный. Повторный non-GREEN останавливает автоматический цикл и отдаёт владельцу
  выбор принять названный долг либо остановить фазу; третьего repair/audit нет.
- Исправить конфликт немедленно в Task command/compiler source и закрепить regression tests.
