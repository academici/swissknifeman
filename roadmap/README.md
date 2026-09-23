# roadmap — отложенные направления swissknifeman

Здесь живут только самодостаточные спецификации, чей измеримый критерий запуска ещё не
сработал. Реализованная, отклонённая или перенесённая в исполняемый план либо ограниченное
задание работа из каталога удаляется; её история остаётся в git и у именованного владельца.

> **Правило каталога:** колонка **Статус** описывает только живой остаток. Исторические
> ссылки на plan items вне собственного плана всегда используют форму `<PLAN-ID> Pn.m`.

## Живой каталог

Сводный [аудит слоёв инструкций и незавершённых остатков от 16 сентября](../tasks/2026.09.16-instruction-layers-audit/README.md)
различает исправления исходников, локальную доставку и полевой acceptance. Source remediation
выполнена; живой остаток — consumer/provider field acceptance без fleet rollout.

| Файл | Статус | Критерий запуска / исторический якорь |
|:--|:--|:--|
| [`2026.09.23-task-cursor-explicit-model-route-evidence-gap.md`](2026.09.23-task-cursor-explicit-model-route-evidence-gap.md) | 🔴 source/consumer gap; Task adapter не исправлен | AzGuard `2026.09.22-№1-AZGUARD-CORRECTNESS P1.2`, `P2.2`, `P4.2`, `P6.2` требуют Grok high: explicit Cursor `--model` фиксируется как medium/unknown, а fallback может приписать глобальный cli-config чужому запуску. Нужен bounded Task repair с fail-closed route proof и полевым допуском Grok. |
| [`2026.09.22-task-productivity-residuals.md`](2026.09.22-task-productivity-residuals.md) | 🟡 отложенные идеи аудита; нужны измерения/owner-решения | После прямого быстрого ремонта сохранены только дорогие или спорные продолжения: persistent index, compact context, route ranges, validation classes, CI split, governance levels и telemetry. Каждый пункт имеет отдельный field trigger и вопросы для обсуждения. |
| [`2026.09.22-task-owner-session-authority-provider-gap.md`](2026.09.22-task-owner-session-authority-provider-gap.md) | 🟣 owner-направление принято; runtime-реализация отложена | CoreX `2026.09.19-№1-COREX-PLATFORM-HARDENING P5.16`: exact Codex `plan-run` подтвердил route/current owner message, но finite grant упёрся в `OWNER_ATTESTATION_UNSUPPORTED`; relaunch capability не добавляет. Решение — явные `owner-session` и `provider-proof` boundaries. |
| [`2026.09.22-task-plan-exec-control-plane-overhead.md`](2026.09.22-task-plan-exec-control-plane-overhead.md) | 🔴 bounded execution regression; решение не внедрено | CoreX `2026.09.19-№1-COREX-PLATFORM-HARDENING P5.13`: двухстрочная правка заняла около 40 минут из-за model overshoot и ручного plan control plane. Следующий шаг — owner-решение по P0 execution capsule/finalizer и пилот на P5.17. |
| [`2026.09.22-task-design-proof-overreach-diagnostic.md`](2026.09.22-task-design-proof-overreach-diagnostic.md) | 🔴 два полевых подтверждения; решение не внедрено | Audit P1.1 и Chatom P02 показали одну регрессию: после раннего semantic answer работа уходит в exhaustive proof и design control plane. Следующий шаг — owner-решение по P0 native-first design и пилот на трёх реальных планах. |
| [`2026.09.21-cursor-safe-dirs-fail-closed-non-rm-shell.md`](2026.09.21-cursor-safe-dirs-fail-closed-non-rm-shell.md) | 🟡 field workaround на Insiders; stdout-fix в generator ожидает | Insiders Agent: Shell блокируется hook `security.safe-dirs` (`returned no output`, failClosed); корень — пустой stdout без `{"permission":"allow"}` (+ envelope/path); allowlist не при чём. |
| [`2026.09.21-consumer-context-rollout-regression.md`](2026.09.21-consumer-context-rollout-regression.md) | 🔴 воспроизведённый field regression | Insiders после update сохранил resident hub, лишний plugin bucket, дубли local/marketplace skills и шесть optional-агентов; compact source fix `b2543bf8` не обеспечил consumer convergence. |
| [`2026.09.17-task-final-plan-audit-and-route-coalescing.md`](2026.09.17-task-final-plan-audit-and-route-coalescing.md) | 🔴 field evidence + owner rule; runtime-ремонт не выполнен | `azguard:PLAN1`: после design только P1 Task предложил execution при скелетах P2–P7. Норма владельца: весь план детализирован → один общий design audit → execution. |
| [`2026.09.17-task-batch-launch-scope-regression.md`](2026.09.17-task-batch-launch-scope-regression.md) | 🔴 воспроизведённый field regression | CoreX P6: native fresh launch был вручную сужен с B-P6-SEARCH `P6.6–P6.8` до P6.6, хотя handoff сохранял полный `plan-run` range. |
| [`2026.09.16-SKM-PLAN-BUNDLE-ADMISSION-GAP.md`](2026.09.16-SKM-PLAN-BUNDLE-ADMISSION-GAP.md) | 🧪 source + local runtime готовы; field acceptance | Bundle preparation/admission, whole-workset Stop coverage, terminal reconciliation и run-report provenance реализованы; нужен реальный consumer batch/provider final, без fleet rollout. |
| [`2026.07.25-memory-hub-service.md`](2026.07.25-memory-hub-service.md) | 🧭 deferred by decision | Второй человек, больше двух машин/машина вне LAN, project ACL или тысячи записей; подготовительный предшественник — `2026.07.25-ECO-OPT P4`. |
| [`2026.08.15-locale-corpus-after-field-validation.md`](2026.08.15-locale-corpus-after-field-validation.md) | ⬜ ждёт field evidence | Конкретный проект, surface и воспроизводимый пользовательский эффект после compact field cut `2026.08.02-PROVIDER-CONTRACT-LOCALE P4`. |
| [`2026.09.14-owner-session-continuity-regression.md`](2026.09.14-owner-session-continuity-regression.md) | 🧪 код доставлен; field acceptance | FlexCRM incident: агент выдумал новую сессию и повтор текущего item вместо `continue-root`. |
| [`2026.09.14-task-owned-dirty-worktree-continuity.md`](2026.09.14-task-owned-dirty-worktree-continuity.md) | 🧪 код доставлен; field acceptance | Edufy P6.2: dirty path от предыдущего owner workflow был ошибочно объявлен blocker'ом вместо baseline. |
| [`plan-design-vs-exec-status-check.md`](plan-design-vs-exec-status-check.md) | ⬜ один замер | Повтор ошибочного выбора `plan-design` для уже готовой фазы на втором плане; первый замер — `2026.07.16-INS-EVO P1`. |
| [`plan-lesson-capture.md`](plan-lesson-capture.md) | ⬜ один замер | Повтор потери post-closure owner finding на втором плане; первый замер — `2026.07.14-DTEREMA-SITE P6.2–P6.3`. |
| [`2026.09.14-task-terminal-command-emission-regression.md`](2026.09.14-task-terminal-command-emission-regression.md) | 🧪 код доставлен; field acceptance | Edufy P5.2 снова завершился user-facing summary без native команды P5.3, хотя delivery receipt её содержал. |
| [`2026.09.14-task-unicode-cross-plan-bundle-regression.md`](2026.09.14-task-unicode-cross-plan-bundle-regression.md) | 🧪 код доставлен; field acceptance | CoreX P3.1: `№` в cross-plan ID делал declared input нераспознаваемым и блокировал bundle до execution. |
| [`upstream-notify-diet-fork.md`](upstream-notify-diet-fork.md) | ⬜ trigger не сработал | Реальный болезненный drift либо содержательная диета `notify`-скилла; последняя квалификация — `2026.07.31-SKM-LEAN P7.3`. |

## Диспозиция 2026-09-15

Новые причины и ограниченные исправления сведены в
[отчёт задания](../tasks/2026.09.15-roadmap-field-fixes/README.md). Два завершённых исходных
carrier'а 15 сентября перенесены в [archive/](archive/README.md); их field/transport остатки
зафиксированы в отчёте, а не создают параллельный живой backlog. Четыре записи 14 сентября
не требуют повторной реализации. Полная экономия ресурсов и native final acceptance пока не
заявлены.

## Диспозиция 2026-09-13

Task launch-block parity был закрыт: `continue-root` продолжает ready batch в том же root, а
delivery не предлагает `plan-design` для уже детализированной незавершённой фазы. Однако полевая
регрессия Edufy 2026-09-14 показала, что saved delivery receipt всё ещё можно не вывести в
user-facing final; живой carrier снова фиксирует обязательный finalization seam.

Четыре новых incident carrier реализованы напрямую в одной сессии без master plan:
Task opt-in routing, interrupted predecessor recovery, finite owner authority/calendar
и release-to-runtime delivery. Оригиналы перенесены в [`archive/`](archive/README.md).
Релизная аттестация фиксирует байты; результат внешней доставки хранится в machine-local receipt,
а активные provider-сессии требуют перезапуска. Отложенные темы остаются в живом каталоге.

## Диспозиция 2026-09-11

Две сегодняшние записи и связанный инцидент 10 сентября объединены в
[аудит-задание Task execution cost](../tasks/2026.09.11-task-execution-cost/README.md).
Локальная реализация завершена: исправлены навязанный phase audit, конфликт глубины
review и пробелы completion/delivery. Позднейший раздел Delivery того же отчёта фиксирует
частичную consumer-поставку: 19 root подтверждены, четыре сохранены без перезаписи из-за
`SPUB_OWNERSHIP_CONFLICT`. Причины и путь исправления вынесены в
[release-to-runtime carrier](archive/2026.09.11-release-to-runtime-attestation-and-recovery.md).

Все три исходника сохранены байт-в-байт в
[source-roadmap](../tasks/2026.09.11-task-execution-cost/source-roadmap/).
Источники остаются историей инцидентов; актуальный результат находится в отчёте задачи.

## Диспозиция 2026-09-09

- 23 owner-prioritized/triggered carrier'а перенесены байт-в-байт в
  [`2026.09.09-№1-LEAN-EXECUTION/artifacts/source-roadmap/`](../plans/2026.09.09-№1-LEAN-EXECUTION/artifacts/source-roadmap/);
  исполняемый SSOT — item contracts этого плана; Laravel parallel-isolation
  carrier назначен точно `2026.09.09-№1-LEAN-EXECUTION P5.3`.
- Artifex-остаток передан его живому плану-владельцу
  [`2026.08.03-ARTIFEX-SUPERVISOR`](../plans/2026.08.03-ARTIFEX-SUPERVISOR/), а завершённая
  memory-recall запись — архивному владельцу
  [`2026.08.07-PLAN-ECONOMY`](../plans/archive/2026.08.07-PLAN-ECONOMY/).
- Исправленная provider-docs запись и отклонённый OTEL preset удалены из живого каталога;
  их доказательства остаются соответственно в git и в
  [`docs/rejected-optimizations.md`](../docs/rejected-optimizations.md).
- Полная проверяемая матрица судеб, включая 24 удалённые ссылки прежнего индекса, находится в
  [`findings/00-roadmap-disposition.md`](../plans/2026.09.09-№1-LEAN-EXECUTION/findings/00-roadmap-disposition.md)
  и решении
  [`D1-roadmap-promotion.md`](../plans/2026.09.09-№1-LEAN-EXECUTION/decisions/D1-roadmap-promotion.md).

## Принцип

Не внедрять спекулятивно. Новый carrier получает проверяемый trigger; сработавший trigger
переводит работу в один исполняемый план или ограниченное задание, а не создаёт параллельный backlog. Внешний provenance
фиксируется в [`docs/reference.md`](../docs/reference.md), отклонённые повторяющиеся идеи — в
[`docs/rejected-optimizations.md`](../docs/rejected-optimizations.md).
