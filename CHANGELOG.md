# Changelog

## [Unreleased]

### Added

- **Provider distribution SSOT.** `configs/provider-distribution.json` +
  `core.provider.distribution` — connect/vendor/discovery каналы без `if cursor` в
  `publication.py`. Док: `docs/reference/provider-distribution.md`.

### Changed

- **maind fleet:** проект `sova` в `config.json`; MCP/instructions adopt на cursor-consumer
  (flexcrm, cms, insiders, sova); D104 lifecycle handler для dterema/brain.

## [0.21.1] - 2026-09-17

### Fixed

- **skiller distribution (Cursor).** `build_connect_distribution_plan()` и
  `build_vendor_distribution_plan()` пропускают `cursor` — нет marketplace/vendor
  канала (D8); без этого `skiller update`/`deliver` падали на cursor-enabled проектах.
  Package `skiller` 0.17.1 → 0.17.2.

## [0.21.0] - 2026-09-17

### Fixed

- **skiller connect (Cursor).** `build_connect_distribution_plan()` пропускает `cursor` — нет
  marketplace-канала (D8); без этого `skiller update`/`deliver` падали на cursor-enabled проектах.
  Package `skiller` 0.17.0 → 0.17.1.

## [0.20.0] - 2026-09-17

### Added

- **Cursor third provider (P5).** Релиз v0.20.0: validate, attest, fleet `maind sync` +
  `skiller deliver`; явный enable Cursor на self-host и проектах с `.cursor/mcp.json`.

- **Cursor third provider (P4).** Документация: адаптер Cursor (install, trusted profile, MCP,
  permissions); generated [Provider model roles](packages/task/docs/reference/provider-model-roles.md)
  (pins design/exec/audit/economy + inventory и запрет Auto на fixed frontier); harness
  [setup/cursor](packages/harness/docs/setup/cursor.md); launch-block с таблицей class→selector,
  `agent --workspace` и IDE Run Mode checklist; instruction `root.cursor.launch-and-autonomy` в catalog.

- **Cursor third provider (P3).** Task: `mappings.cursor` + `model_inventory` для всех трёх
  провайдеров; `command_render` (launch через `agent --workspace`, не `-C`); `route_evidence_cursor`
  и generated `packages/task/adapters/cursor/`; parity/reference на три колонки. mAInd:
  `provider_deploy` для `.cursor/mcp.json`, `REQUIRED_PROVIDERS` включает `cursor`, health
  `provider:cursor trust` через harness profile resolution. Harness instructions engine:
  `PROVIDERS` + `root.cursor.*`, 21 проекция (`.cursor-instructions.mdc` / `.mdc` rules),
  catalog `1.3.0` и compatibility fixture на 87 записей.

- **Cursor third provider (P0–P2, cold-start S2).** `ProviderId.CURSOR` и полная
  36-строчная capability matrix (`8 native` / `7 adapted` / `21 unsupported`);
  harness-адаптер `packages/harness/configs/cursor/` (profile bindings, MCP,
  permissions/cli render, lifecycle hooks, `.cursor/rules/*.mdc`); conformance
  tests по design-freeze §3.6; skiller `render_cursor_publication` и listing budget
  для `cursor` без dual-write `.agents` + `.cursor`.

## [0.19.0] - 2026-09-16

### Added

- **Task: preparation и terminal reconciliation.** Выбранный bundle/state восстанавливается до
  five-carrier snapshot; одна идемпотентная операция сводит terminal journal, generated views,
  следующий frontier bundle и delivery receipt.

### Fixed

- **Task/Harness: непрерывный workset.** Recommended batch допускает текущий ready frontier с
  пустым prefix, а Stop guard видит ещё не начатый остаток receipt. Обновлённый Codex dispatcher
  доставляется через versioned owning adapter и вызывает `check-open` без специального payload.
- **Task: design-time bundle validation.** Все nonterminal admission-ready declarations проходят
  dry render без массовой materialization; неразрешимый выбранный bundle даёт точный typed repair.
- **mAInd: provenance run-report.** Чужой project/session/provider report исключается из verdict и
  становится `ATTENTION`, не ложным RED.
- **CoreX plan checker:** execution bookkeeping и generated decision views больше не инвалидируют
  design seal, а новые design decisions и изменения item contracts по-прежнему требуют reseal.

### Changed

- **Task instructions:** обязательный контекст разделён на common/design/execution/review layers;
  полный plan protocol остаётся on-demand canonical reference.
- **Версии поставки:** Task `0.19.0`, Core `0.18.0`, general `0.14.1`, Skiller API `0.16.1`,
  Harness API `0.4.4` и mAInd API `0.3.3`.

## [0.18.0] - 2026-09-15

### Fixed

- **Task: полевые ошибки и стоимость исполнения.** Decision template проходит native parser,
  terminal append заранее отклоняет невалидные решения; semicolon reads/Files распознаются,
  пустой product anchor не подтверждает closure. `only_item` измеряет только выбранный пункт
  с сохранением producer admission; история учитывает все affected `items` решения.
- **Task/Harness: ранний final открытого run.** Включённые Stop-адаптеры проверяют durable
  состояние текущей сессии даже без Task payload/lease. Проверен repository dispatcher обоих
  провайдеров; полевой transport acceptance остаётся отдельным шагом. Conformance-тест
  dry-run изолирован от версии hook в рабочем окружении разработчика. Версия Harness API `0.4.3`.

### Changed

- **Task: короткие ссылки без коллизий.** Постоянные Short ID `PLAN<N>`/`TASK<N>` для
  новых файловых планов и задач; внешние ссылки квалифицируют решения и пункты
  (`PLAN1.D35`, `PLAN1.P2.3`). Проверка дублей планов учитывает архив; старые ID сохраняются.
  Skiller больше не генерирует неоднозначный провенанс `P1.2, D31` в bootstrap.
  Версии: Skiller API `0.16.0`, Task `0.18.0`, general `0.14.0`.

## [0.17.5] - 2026-09-14

### Fixed

- **Skiller: fail-closed Python 3.10 TOML fallback.** Unsupported tables and
  inline plugin maps now reject native selection before any consumer mutation.

## [0.17.4] - 2026-09-14

### Fixed

- **Skiller: Python 3.10 Codex selection.** Native Codex selection and legacy
  link cleanup use a bounded stdlib TOML reader when `tomllib` is unavailable,
  preserving explicit plugin selection and disabled local skills.

## [0.17.3] - 2026-09-14

### Fixed

- **Release hygiene.** Runtime validation logs больше не входят в публикуемое
  дерево; доказательства выпуска остаются в структурированных JSON и Markdown
  артефактах.

## [0.17.2] - 2026-09-14

### Fixed

- **Skiller delivery: Codex native cache.** Readback по-прежнему сверяет все
  attested bytes и symlink safety, но больше не считает штатные package files и
  provider-generated cache state неизвестным drift.

## [0.17.1] - 2026-09-14

### Fixed

- **Skiller delivery: секреты consumer settings.** Dry-run больше не печатает значения
  из `env` и чувствительных полей существующего `.claude/settings*.json`; запись проекта
  продолжает использовать исходные байты без изменения.

## [0.17.0] - 2026-09-14

### Added

- **Skiller: явный native Codex selection.** `skiller connect --native-codex` записывает
  точный project-level выбор Swissknifeman plugins, не меняя permissions, сторонние TOML-поля
  или глобальные defaults; с `--hub` AGENTS строится по этому набору.

### Fixed

- **Skiller: стартовый контекст Codex.** Краткий AGENTS hub учитывает реальную Codex
  discovery и не возвращает Claude-only extras. CORE сокращён до четырёх общих скиллов,
  66 профильных descriptions укорочены;
  VueUse-каталог вынесен в reference. Управляемые дубли и явно отключённые ссылки
  архивируются с проверкой ownership и эквивалентности; чужие backups сохраняются.
- **Task: результат и продолжение.** Общий resolver принимает `plan-run` с сохранением
  owner route; renderer различает завершение заказанного scope в чате и явно запрошенную
  новую сессию. Убраны clean-tree и повторные interview gates; Task runtime содержит
  все шаблоны и references. Native Codex больше не создаёт три migrated command duplicates.
- **Skills: соразмерные правила.** TDD, review, package contribution и PHP architecture
  учитывают авторизацию и принятые контракты проекта; универсальные советы не становятся
  дополнительными blockers. mAInd setup/MCP descriptions сокращены без изменения инструкций.
- **Публикация: удалённые артефакты.** Registry снимает неизменённые retired files по
  предыдущему publication lock; release attestation корректно учитывает working-tree deletions.
- **Task: непрерывное исполнение и точный Next.** `continue-root` продолжает совместимый ready
  batch в текущем root без final, owner question или fresh session; native launch-block остаётся
  только для действительной cold-start/wait границы. Автоматический handoff отказывает
  повторный `plan-design`, когда существующая фаза уже детализирована и готова к `plan-exec`.
- **Skiller / core: локальный repair без лишнего design или перезапуска.** `anti-drift`
  использует checkpoint и смену тактики при затянувшемся исправлении; число файлов само
  по себе не требует плана. `plan-protocol` согласован с непрерывным исполнением Task;
  native handoff сохраняется для подтверждённой границы контекста, capability или ожидания.
- **Skiller connect:** dry-run замены Codex-набора проверяет post-prune snapshot вместо
  старого lock; до удаления проверяются digests всех прежних owned artifacts. Изменённые
  preimages отклоняются до записи, чужие owner records сохраняются.

- **Task: unresolved execution binding.** An item containing an explicit
  `[NEEDS CLARIFICATION: …]` marker can no longer compile as routine authority;
  it must first receive a finite owner gate and binding.
- **Task: Unicode cross-plan inputs.** Bundle/read-path parsing now recognises
  declared paths whose plan IDs contain `№` and does not mistake `D16` in a
  filename for a local decision reference; a valid cross-plan decision can no
  longer disappear as an unresolvable entry before bundle generation.
- **Task: завершение batch не стирает следующий пункт плана.** Delivery отказывает
  `Context: terminal` и `Next: none/terminal`, пока есть незавершённая фаза; правило
  распространяется и на recommendation-only receipt. Протокол сохраняет фактический
  successor вне завершённого batch и native command при запрошенной новой сессии.

## [0.16.1] - 2026-09-13

### Fixed

- **Полевой delivery readback:** отдельная source-bound `codex-native` поверхность проверяет полный native cache, а project bundles — только declared skills. Attestation исключает ignored/untracked telemetry; расширение proof coverage сверяется с предыдущим Git source tag, не требует ложного bump неизменённых units. Orphaned v1 vendor markers архивируются только при отсутствии всех объявленных директорий; реальные оставшиеся vendor-копии остаются blocked. Перед update сохраняется также lock preimage.
- **Claude skm cache:** publication version выровнена с обновлённым Codex unit, чтобы старый same-version cache не выдавался за актуальный runtime.

## [0.16.0] - 2026-09-13

### Added

- **Release-to-runtime:** `skiller attest` формирует детерминированные version/tree/file digests для обоих providers и package runtimes; tag gate отклоняет изменённые bytes под прежней unit version. `version --json` показывает umbrella и независимые units. `skiller deliver --release ... --all` явно обновляет проекты/native caches, восстанавливает ownership только известных preimages и сохраняет durable per-target receipt с digest readback и `restart-required`.

### Fixed

- **Task opt-in:** текущий owner intent определяет маршрут; dev/fix работают напрямую без обязательного плана, audit/close/handoff lifecycle. Старые embedded инструкции не переопределяют новый выбор владельца.
- **Task recovery:** successor до terminal predecessor получает `OUT_OF_ORDER_REQUEST` с active item и start/resume; старт фиксируется durable до product write, resume сохраняет run identity, terminal producer материализует только следующий ready bundle.
- **Task authority/calendar:** явный finite Authority gate проходит lint/compiler/bundle; grant материализуется из текущего provider-attested owner invocation. Отзыв проверяется заново перед start/resume; `waiting-external` сохраняет observation checkpoint, дату/predicate и continuation без нового owner questionnaire.
- **Ownership и cache:** общий lock атомарно заменяет только records своего owner; alternating/concurrent writers сохраняют чужие записи и отказывают при collision. Installed verification принимает лишь точные known Codex migration bytes и отвергает mutation, unknown extras и symlinks. Исправлены baseline snapshots уже опубликованного terminal-admission capability.

### Documentation

- **Release-to-runtime roadmap.** Зафиксированы подтверждённые причины version/cache/fleet drift: повторное использование unit versions для новых bytes, потеря ownership в multi-writer lock, разрыв native cache/project/session и отсутствие durable partial-delivery receipt; описаны безопасная reconciliation и проверяемые этапы исправления.

## [0.15.4] - 2026-09-12

### Fixed

- **Codex plugins `task` и `core`:** версии выровнены с umbrella-релизом
  0.15.4; ошибочная промежуточная цель 0.14.0 больше не публикуется и не
  устанавливается для новых сессий.

## [0.15.3] - 2026-09-12

### Changed

- **Codex plugins `task` и `core`:** выпущена линия 0.14.0 из
  актуальных provider-проекций; установки 0.13.x больше не являются допустимой
  целью для новых сессий.

## [0.15.2] - 2026-09-11

### Fixed

- **Task: завершение без лишнего audit.** Зелёная фаза закрывается direct-close независимо от legacy `Audit Intent` и числа items; дополнительный phase audit требует остаточного вопроса и адресного согласия, привязанного к candidate/run. Новые audit runs проверяют согласие через существующие decisions/journal. RED и неполная приёмка остаются owning repair.
- **Task: completion-first и экономия проверок.** Delivery отклоняет handoff на повторный запуск/закрытие текущего item и требует завершить допустимое закрытие фазы в той же сессии. Согласованы команды, канон и шаблоны: review по риску, актуальная validation переиспользуется, bookkeeping сам не запускает повторную продуктовую проверку.

## [0.15.1] - 2026-09-10

### Changed

- **Task lifecycle:** обычная межмодульная разработка по брифу без обязательного плана; read-only audit возвращает продуктовый дефект исполнителю через journal/lint/delivery, сохраняя фазу открытой. Audit budget больше не запрещает ремонт; product delta и число файлов сами по себе не требуют design. Новые рекомендованные batches допускают ready subset, исторические обязательные группы сохраняют контракт.
- **Проверки и инструкции:** один scoped commit по умолчанию, scoped plan validation отдельно от fleet; targeted context и research без обязательных перезапусков. Добавлены read-only подготовка snapshot и диагностика выбранной установленной Task/core-проекции; terminal delivery проверяет свежесть state, повторная генерация не переписывает неизменённые файлы. Analyst help показывает workflow-scan.
- **`skiller`:** явно вызываемый `general/implement` больше не навязывает полный прогон или дополнительный code review; validation и review выбираются по риску, заданному scope или PR-процессу.

## [0.15.0] - 2026-09-10

- **`skiller`: lifecycle-aware Laravel parallel isolation.** `test-isolation-guard` now keeps
  canonical serial DB protection at app boot and requires the framework callback’s exact worker
  DB/token before migration; writable parallel disks are local, contained per-process roots and
  fail closed with `FRAMEWORK_LIFECYCLE_CONFLICT` on unavailable lifecycle evidence.

- **`analyst`: workflow fleet evidence.** Новый read-only `workflow-scan` ограничен declared
  plan roots enabled-проектов, digest-дедуплицирует mirrors, статически извлекает признаки без
  исполнения JavaScript и публикует воспроизводимый `workflow-fleet-report/v1`; изменения Task
  остаются только report-backed и требуют Rule of Three по разным plan identities.

- **`skiller`: description-trigger debt queue.** `bucket-audit --description-debt` now emits the
  additive `description-trigger-priority/v1` contract with exact ratchet membership, tier-0 listing
  share, direct-call/resident/unobserved evidence, deterministic ordering, and fail-closed ledger
  diagnostics; it never rewrites canonical skills or turns missing telemetry into a usage verdict.

- **`harness` / `task`: opt-in terminal-admission Stop adapters.** Codex and Claude Code
  lifecycle bindings now delegate applicable, trusted Stop attempts to the P4.1 Task reducer;
  inactive hooks and absent leases remain no-ops, while provider limits stay explicit.

- **`task`: lease-bound terminal admission.** Новый provider-neutral reducer и worktree-local CLI
  привязывают terminal response к run/session identity, P1.3 typed continuity, свежему delivery
  receipt и точному machine-authored fragment. Leases monotonic and expiring; append-only events
  retain only hashes and stable recovery diagnostics. Provider Stop payload translation remains P4.2.

- Исправлено: `task:plan-audit` больше не принудительно передаёт совместимое продолжение в новую сессию; контекст выбирает единый evidence-based reducer.

- **`task`: evidence anchors prevent self-invalidating plan closure.** Новый derived
  `evidence-graph/v1` выявляет пересечение declared `Files` и digest inputs до journal/product
  mutation, разделяет product/closure anchor только при реальной коллизии, сохраняет
  byte-identity product paths и исключает registry-owned volatile bookkeeping из material
  candidate без явного Deliverable. `audit-finalization/v1` фиксирует rebuilt candidate и exact
  close admission перед GREEN audit.

- **`task`: единый исполнимый Routing compiler.** `Task Contract`, batch admission,
  phase audit/close и lint теперь потребляют одну exact six-column Routing table; соседние
  provider mapping-таблицы не меняют Review coverage, а duplicate executable table или item
  отказываются до mutation.

- **`task`: пропорциональная phase assurance.** Новый `Phase Assurance | v1` и единый
  `plan_assurance` reducer отделяют semantic phase risk от Routing Review и числа items;
  phase audit subject канонизируется, а post-GREEN diff получает field-level
  `audit-impact/v1` continuation вместо bare stale/full fallback.

- **`task`: компактный normal-path lifecycle.** Канонические plan-команды теперь делегируют
  admission, риск-ориентированную validation, selective projection, continuity и delivery общим
  runtime owners; обычный low-risk item выбирает focused check, один commit и один semantic Next,
  а hard-risk границы детерминированно расширяют validation/review.

- **`task`: явная готовность producer.** Закрытые `producer-readiness/v1`,
  `phase-reentry-justification/v1` и `fix-branch/v1` теперь проходят один correction reducer:
  accepted-empty и digest-bound downstream проверяются сквозным образом, priority fix привязан
  к declared target, а lint/delivery запрещают необоснованный re-entry терминальной фазы.
  Terminal close также требует green rerun exact исходного carrier после qualified repair.

- **`task`: repo-local archive не зависит от Brain.** Archive больше не ищет и не вызывает
  Brain; синхронизация Brain остаётся отдельной opt-in docs-операцией.

- **`task`: repairable carrier drift stays in the active execution batch.** `plan-exec` now
  permits a smallest scope-preserving carrier/reference repair and reruns the original check;
  `plan-run` inherits that one classifier, reserving redesign for actual frozen, public or
  authority-boundary changes.

- **`task`: единый continue-first repair reducer.** Закрытый `repair-decision/v1` связывает
  исходный carrier, clean baseline/candidate delta, атрибуцию путей, bounded diff, material surface
  и pre/post validation; qualified repair не может ложно terminalize или породить redesign,
  а block confirmation потребляет digest этого evidence без переклассификации.

- **`task`: continuation decisions keep compatible work in the current root session.** A small
  provider-neutral reducer now consumes versioned route/capability, context-health, remaining-batch,
  loaded-input and lifecycle evidence; cold starts require one canonical hard boundary and durable
  checkpoint. Renderer, DecisionRequest recovery, handoff delivery and live plan lint validate the
  same typed decision while preserving owner-wait, same-root resume and isolated-review outcomes.

- **`task`: Routing Batch is now pre-mutation authority.** One compiler derives batch membership,
  maximum route/review and digest-bound suffix receipts from `plan.md`; partial, ambiguous and stale
  executions are refused before journal or status mutation.

- **`task`: content-addressed five-carrier executor context.** Plan execution now captures immutable
  v2 inputs before analysis, proves byte-cursor completion with terminal markers, and refuses
  truncation or source drift before journal mutation; the generated history pointer now includes
  its required `--plan-dir` argument. Rootless v2 plans consume the frozen Task read-budget
  contract, while legacy plan-local contracts remain fail-closed.

- **`skiller`: Codex consumer acceptance supports skill-root aliases.** The live publication gate
  resolves current `rN/path` references through the emitted Skill roots table before checking
  cache and repository provenance.

## [0.14.0] - 2026-08-17

- **`task`: owner-gated terminal blocked phase close.** An explicit, phase-scoped accepted D# can
  record a terminal phase as `🟠 Done with deviations` while preserving its blocked item history,
  RED audits, and release disposition; without that carrier phase close remains fail-closed.

- **Документация операций provider/locale и release-candidate.** Добавлены компактные границы
  check-first/apply-with-authority/rollback, независимые поверхности locale и точный провенанс
  RFC 5646, IANA Registry и HashiCorp. Текущий P7 candidate явно non-releasable: D88 blockers
  не маскируются и не дают прав на tag/push/publish.

- **`core` / `skiller` / `harness` / `maind`: добавлен provider-health v1.**
  Чистый exact-set evaluator не позволяет зелёному provider/project скрыть missing, stale,
  unsupported или unresolved peer; Skiller публикует dependency closure и типизированные
  provider-qualified measurements, Harness — независимый settings audit Claude Code/Codex, а
  `maind projects health` собирает redacted evidence только через публичные package CLI без repair.

- **`core` / `harness` / `maind`: compacted internal source prose for field testing.**
  The P4.5 working cut translates 139 implementation files without changing provider settings,
  consumer files, credentials, or runtime contracts.

- **`core` / `skiller`: добавлен evidence-admitted locale corpus gate.**
  Единый JSON ledger и stdlib-only validator проверяют English source ownership, независимые
  EN/RU reviews, immutable tokens, preimages, rollback и bounded checkpoints; новые
  `check-locale-corpus.py` и `check-translations.sh --strict` отказывают generated, foreign,
  stale и ambiguous строки до записи. Canonical Skill template теперь EN-only и генерирует
  байт-стабильную distribution copy.

- **`core`: добавлен общий stdlib-only runtime локализации.**
  Pinned IANA registry разрешает независимые `response`/`plan`/`diagnostics` контексты,
  fail-closed BCP 47 canonicalization и sparse Russian overlay с защитой machine literals;
  Harness и Task получают один semantic context, сохраняя provider-owned rendering.

- **`task`: phase-close принимает legacy subject audit-фазы.**
  Gate нормализует `P1 — режим фазы` через общий `review_policy.phase_audit_subject`, поэтому
  matching GREEN audit с тем же candidate fingerprint больше не ошибочно считается отсутствующим.

- **`task`: launch-команды стали provider-native и безопасными для копирования.**
  Metadata-таблица больше не содержит команду: Claude Code и Codex выводят только native-форму
  активного адаптера отдельным fenced-блоком. Codex дополнительно запрещает завершать handoff без
  команды при наличии исполнимого Next; длинные shell-команды используют явные `\`.

- **`task` / `skiller`: внутренняя философия разработки стала обязательным plan-authoring контекстом.**
  Новый root-bootstrap skill `task-development-philosophy` закрепляет пропорциональную
  декомпозицию, evidence reuse, один full audit на material baseline, delta/gate-rebind для
  повторных проходов и запрет бесконечных audit/repair loops; он доступен обоим provider roots и
  срабатывает при создании планов и изменении Task workflow policy.

- **`roadmap`: измерена стоимость повторных full-аудитов и спроектирован экономный режим.**
  Полевой P0 дошёл до третьего full audit и повторил минимум 2 557 package tests; новая спека
  вводит digest-bound Validation receipts, режимы `full|delta|gate-rebind`, строгие основания для
  второго full и owner gate для третьего.

- **`task`: audit-repair перепривязывает terminal evidence к текущему ТЗ.**
  Append-only история сохраняет прежние terminal-записи, но `plan-lint` сверяет digest
  текущего spec только с последним execution event; `plan-audit` и `plan-close` проходят
  тот же fail-closed terminal policy, что `plan-exec` и `plan-run`.

- **`task`: active/archive зеркало одного Plan ID больше не считается новой волной.**
  `plan-lint` не требует `supersedes` у временной postarchive-копии того же плана, сохраняя
  проверки дубликатов ordinal и совпадающих кодовых имён для действительно разных планов.

- **`task` / `plan-protocol`: terminal outcome теперь следует единому acceptance/reducer contract.**
  Красная обязательная Validation оставляет item в progress; `closed-deviations` требует зелёных
  carriers и `repair_exhausted`, а `blocked`/phase RED допускаются только после authority/safety
  reducer evidence. Scope-aware block gate не принимает широкий in-scope inventory за границу.

- **`task`: `plan-run` получил provider-neutral route provenance и durable run receipt.**
  Claude Code session JSONL и Codex adapter проецируются в один record; unknown отделён от
  реального undershoot. Receipt связывает route с run/session и повторно проверяется pre-final.
  Installed canonical command резолвится package-relative, а delivery receipt аттестует version,
  command digest и exact terminal subject.

- **`task`: локальные Validation prerequisites repair-forward до terminal close.**
  `validation-admission/v1` распознаёт доказанно отсутствующий literal Make target как
  nonterminal local repair; material-only phase fingerprint исключает audit-owned bookkeeping,
  сохраняя stale на изменённом terminal evidence.

- **`roadmap`: завершённые Task-спеки удалены из активной очереди.**
  Использованные исходники и disposition-карта сохранены в артефактах архивного плана
  `2026.08.12-№1-TASK-RESILIENCE`; частичные записи оставлены только с точным остатком.

## [0.13.2] - 2026-08-13

- **`task`: terminal delivery игнорирует только исторический malformed terminal при наличии свежего валидного.**
  Receipt по-прежнему fail-closed возвращает `TERMINAL_RUN_ID_MISSING`, если ни одна terminal-запись
  subject не несёт `run_id`, но больше не блокирует исправленный append-only lifecycle старой строкой.

## [0.13.1] - 2026-08-13

- **`task`: phase candidate fingerprint учитывает только Git-tracked Files.**
  Exact-файлы, каталоги, recursive globs и bounded brace-наборы разрешаются через
  `git ls-files`; tracked edits/deletions инвалидируют candidate, а ignored/untracked
  runtime-байты больше не влияют на audit freshness.

## [0.13.0] - 2026-08-13

- **`task`: Codex plan runtime передаёт один current-thread route record в contract gates.**
  Устаревший `provider-doctor`/`self-attested` рецепт больше не остаётся ниже корректного
  provider binding в `plan-exec` и `plan-close`; это устраняет ложный `ROUTE_UNDERSHOOT`
  после нового запуска, `/clear` и прямого `$ task:…` вызова.

- **`task`: все Codex plan-команды проверяют effective route по текущему thread state.**
  Generated projections запускают adapter-owned capture до первой journal-мутации и
  fail-closed запрещают подменять provider-written `turn_context` выводом `codex doctor`,
  config-файлом либо self-attestation; regression test покрывает все пять plan-команд.
  Заодно lifted return-fingerprint contract принимает весь закрытый journal friction/result enum,
  поэтому `local-repair` и другие штатные наблюдения больше не ломают return-loop lint.

- **`harness`: test fixtures следуют Layout v2 carrier contract.**
  Run-gate, plan-reader, CLI и citation scenarios строят state/status/bundle через canonical
  Task v2 fixture API; отдельные legacy-rejection cases сохранены.

- **`task` / `plan-protocol`: lint проверяет bundle следующего запускаемого item.**
  План с отсутствующим или устаревшим четвёртым execution-slot теперь отклоняется до dispatch;
  future predecessor-dependent bundles остаются отложенными до появления их входного артефакта.

- **`task` / `plan-protocol`: phase audit стал одно-root audit-fixer.**
  Свежий независимый audit root сам исправляет safe in-scope отклонения, повторяет acceptance
  и привязывает финальный verdict к пересобранному candidate. Доказанная acceptance/authority/
  safety/public-frozen boundary остаётся fail-closed, а один candidate допускает не более одного
  isolated reviewer return; routine `audit → repair-run → second audit` больше не создаётся.
  Неразрешённый `DecisionRequest` остаётся нетерминальным наблюдением `decision-pending` и не
  подменяет живую execution position состоянием `blocked`.

- **`task`: owner override фазы больше не зависит от номера decision.**
  Audit-cap remediation допускается только для accepted carrier с полным точным item-set
  фазы и required literals; неполный scope получает отдельный fail-closed refusal.

- **`task` / `plan-protocol`: terminal block проходит один isolated confirmer.**
  Design, exec, run, audit и close теперь используют одну closed sequence:
  immutable capsule, distinct fresh-context reviewer и deterministic reducer. External block
  остаётся nonterminal до verified digest-qualified Perplexity evidence; Codex projections,
  Claude golden fixtures и operator reference пересобраны из canonical sources.

- **`task` / `plan-protocol`: workflow lint теперь различает явный запрет и требование.**
  Только positive declaration в `Phase Context` требует canonical workflow asset; negation той же
  строки не маскирует отдельный `scriptPath` или multi-agent declaration. Codex и Claude
  проекции пересобраны из общего канона.

- **`task`: external item references are plan-qualified, and provider projections stay synced.**
  Canonical authoring guidance, Codex artifacts, Claude golden surface and the operator reference
  now carry the same `<PLAN-ID> Pn.m` rule; audit-cap recovery grants remain limited to their
  explicitly named Validation items.

- **`task` / `plan-protocol`: executable Layout v1 retired after fleet cutover.**
  Runtime readers, migrator, policy schema and compatibility commands are removed; missing/v1
  plans fail with `PLAN_LAYOUT_V1_RETIRED`. Canonical fixtures and provider projections are v2-only,
  while terminal bundles remain schema-checked historical evidence without live source re-resolution.
  Phase-audit receipts bind the latest persisted audit launch block instead of a stale handoff, and
  canonical Batch-first launch tables are accepted by the same lint gate that publishes them.

- **`task`: fleet v1→v2 migration получил frozen admission policy и controlled apply.**
  Closed defect classes, full-tree preimage digests, byte-exact source archive, current-state/
  decision/Routing projection и migration-pending read-budget admission дают 15/15 previews без
  plan-lint ERROR; staged apply проверяет preview и восстанавливает preimage при post-write сбое.

- **`task`: phase candidate fingerprint учитывает plan-relative product files.**
  Declared `Files` сначала сохраняют совместимый repo-relative resolution, затем разрешаются от
  каталога плана; байты acceptance/RAG carriers теперь инвалидируют stale phase audit.

- **`task`: phase handoff и close получили единый risk-adaptive audit gate.**
  Low-risk фазы больше не получают гарантированно холостой `plan-close`: audit выбирается заранее
  по Review, material risk, terminal status и multi-item объёму.

- **`task`: Codex `plan-run` проверяет текущий маршрут и после `/clear`.**
  Thread-bound adapter читает model/effort, cwd, Task prompt и safety state из текущего
  `turn_context`; exact native argv сохранён как fallback. Смена модели в открытой CLI-сессии
  больше не требует перезапуска, а Claude Code projection остаётся byte-compatible.

- **`task`: downstream gate не терминализирует отсутствующий валидатор будущего item.**
  Unicode-пути numbered plans читаются из executable argv; dependency-not-ready теперь
  даёт `unknown`, а не ложный RED producer verdict.

- **`task` / `plan-protocol`: batch/solo теперь обязательная часть нового плана и handoff.**
  Шестиколоночный Routing покрывает каждый item; планировщик группирует связные adjacent items
  одной фазы при экономии чтения/setup/validation, а `solo` требует конкретной границы. Linter
  отклоняет новый layout-v2 план без `Batch`/`Review` и execution handoff, потерявший Batch.

- **`task` / `plan-protocol`: проектирование больше не запускает исполнение автоматически.**
  Terminal `plan-design` возвращает владельцу только маршрутизированную рекомендацию; successor
  получает отдельный `cold-start-root: design-root-terminal`, а design-root не вызывает команду и
  не спавнит исполнителя даже для уже готового item.

## [0.12.0] - 2026-08-12

- **`task` / `plan-protocol`: выполнение стало continue-first.** Route rejection, pending
  decision, local repair и block candidate теперь являются nonterminal journal observations и не
  расходуют attempt. Terminal `Blocked` разрешается только после isolated `JUSTIFIED`; для каждого
  внешнего кандидата обязателен verified RAG, а малые обратимые дефекты исправляются в текущем run.

- **`task`: terminal final и handoff связаны machine receipt.** Новый `plan-delivery.py`
  отказывает на нетерминальном/stale state, связывает journal run ID с digest'ами plan/handoff/state/
  closure и переносит в финальный ответ точную сохранённую рекомендацию следующего шага.

- **`task` / `plan-protocol`: новые планы получили дневную нумерацию.** Канон
  `YYYY.MM.DD-№N-CODE` проверяет положительный уникальный ordinal и согласованный Title `План №N`;
  внешние комментарии и review findings ссылаются на item как `<PLAN-ID> Pn.m`, старые IDs читаются.

- **`task`: packaged plan-protocol projection makes standalone `--conflicts` fail closed.**
  Generator-owned runtime carries canonical SHA-256 provenance; a missing or drifted projection
  is rejected instead of searching arbitrary sibling or cache paths.

- **`task`: phase close поддерживает узкий owner-authorized direct-green-validation путь.**
  Только accepted, phase-scoped и superseding decision с literal
  `phase-close: direct-green-validation` может обойти audit gate; default audit path и все
  несовпадения остаются fail-closed.

- **`task`: Codex `plan-run` использует проверяемый native launch provenance.**
  Свежий launch с `-m` и `model_reasoning_effort` задаёт маршрут manual item без недоступного
  provider probe; provenance честно не выдаётся за runtime telemetry. `plan-exec` сохраняет
  строгий provider-attested gate. Bundle v2 дедуплицирует одинаковый path/decision input в одном ordinal.

- **`task`/`plan-protocol`: terminal audit отделён от следующего запуска.**
  Завершившийся `plan-audit` теперь обязан передать successor свежему root с явно
  запиненным маршрутом; selector больше не допускается выдавать за self-attested
  actual-route evidence при отсутствии provider attestation.

- **`task` / `harness`: layout-v2 execution сверено с owner-carriers.**
  Task теперь fail-closed проверяет phase citations и write-site, а generated command/docs
  surfaces воспроизводятся в clean checkout; Harness читает semantic `Next`
  только из `handoff.md`, не расширяя schema-pure item-state; owner status теперь показывает
  смесь terminal и not-started children как `🟡 In progress`.

- **`task`: phase-audit recovery ограничена одним дополнительным repair-подходом.**
  Первый non-GREEN audit ведёт прямо в owning item под неизменным ТЗ; второй audit финальный,
  после него Task Contract блокирует третий repair/audit. RED больше не маршрутизируется в
  `plan-design` только из-за terminal status или validation/evidence mismatch.

- **`task`: plan-design оценивает влияние конфликта до остановки.**
  Локальная обратимая проблема исправляется в текущем item; re-design или owner gate требуют
  подтверждённой границы package/contract/authority/acceptance/safety.

- **`task`: plan-команды получили evidence-first runtime-переходы и коррелированный lifecycle.**
  Routing preflight больше не записывает product failure, terminal journal close идемпотентен,
  а phase candidate проходит свежий audit до close; каноническая документация Task теперь
  собирается отдельно и в агрегированном сайте.

- **`harness`: новые SessionEnd run-report'ы сохраняются в корне Git-репозитория.**
  Вложенный launch cwd остаётся в поле `cwd`, а вне Git сохранён прежний fallback; исторические
  отчёты не мигрируются.

- **`task`: v1→v2 plan migration теперь сохраняет полное исходное дерево плана.**
  Генератор добавляет `artifacts/migration-source-v1/` с точными байтами всех legacy
  файлов и SHA-256 manifest; исторические audit-разделы и свободная проза больше не
  могут исчезнуть при разбиении на v2 carriers.

## [0.11.1] - 2026-08-10

- **`task`: runtime plan-protocol больше не зависит от конкретного архивного плана.**
  Frozen schemas и калибровочные входы принадлежат `packages/task/configs/`; inplace
  v1→v2 migration окончательно выведена из эксплуатации. Утилиты проверки планов
  перенесены из `plans/` в `packages/task/scripts/` с конфигурацией в
  `packages/task/configs/`; provider-проекции, hooks и документация используют новые пути.

## [0.11.0] - 2026-08-10

- **`task`: downstream-gate исполняет только явные команды Validation.**
  Пояснительный Markdown без inline-code payload больше не становится shell-командой и не
  фабрикует RED; сохранены legacy bare command prefixes. Fixture terminal-phase input переведён
  на свежий closure digest, а P2.10 downstream evidence перепроверен зелёным.

- **`task`: freshness item-state изолирована по item journal scope.**
  Append события одного item больше не инвалидирует state views остальных: digest и `through`
  следуют declared `item_id`, а двух-item regression сохраняет D148 execution semantics
  (`2026.08.07-PLAN-ECONOMY` P6.8, D156).

- **`task`: exact five-slot acceptance v1.1.1 завершилась arm-A fail.**
  Repair-pinned measurement сохранил raw evidence, обнаружил 30/30 ready failures и по
  frozen reducer остановил arm B/session canary; P6.9 и снятие паузы ARTIFEX запрещены
  (`2026.08.07-PLAN-ECONOMY` P6.8, D154).

- **`task`: acceptance protocol получил repair-pinned v1.1.1 identity.**
  Successor сохраняет threshold/scope/reducer/arms/canary v1.1.0, пинует exact five-slot
  implementation `c0ee730c` и хранит v1.0.0 RED вместе с v1.1.0 NOT-RUN
  (`2026.08.07-PLAN-ECONOMY` P6.7, D153).

- **`task`: `plan-weight` измеряет объявленный executor path для обеих раскладок.**
  Layout v1 сохраняет legacy `plan → handoff → phase → Required Reads`; layout v2
  fail-closed проверяет свежие bundle/state, считает digest-qualified selections и
  измеряет пять carrier slots без `handoff.md` (`2026.08.07-PLAN-ECONOMY` P2.10, D152).

- **`task`: downstream consumer validation защищена от рекурсивного self-poisoning.**
  Вложенный `plan-lint` больше не перечитывает append-only downstream RED во время проверки,
  которая должна его supersede; прямой lint сохраняет fail-closed поведение.

- **`task`: `acceptance-protocol` перезаморожен как stage-aware v1.1.0.**
  После сохранённого RED v1.0.0 reducer различает `ready`, evidence-only
  `historical-pre-v2` и deferred `pending-producer`; threshold, scope traversal, arms и
  session canary остались неизменными (`2026.08.07-PLAN-ECONOMY` P6.7, D150).

- **`task`: двурукая приёмка остановлена на честном RED руке A.**
  Мигрированный `2026.08.07-PLAN-ECONOMY` превысил D2(a) (`101744 > 100000`) и сохранил четыре
  нерезолвленных входа; порог и frozen protocol не менялись, arm B/session canary не выдаются за
  пройденные, а снятие паузы ARTIFEX запрещено (`2026.08.07-PLAN-ECONOMY` P6.8).

- **`task`: протокол приёмки v1.0.0 заморожен до первого замера.**
  `acceptance-protocol` v1.0.0 машинно фиксирует scope, две несмешиваемые руки,
  пороги, антисмещение, failure policy, роли, конфаунды и четыре точные ветви
  `session_canary`; правка после прогона требует видимого реопена (`2026.08.07-PLAN-ECONOMY` P6.7).

- **`skiller`/`task`: добавлены инвентарь раскатки и безопасный runbook миграции раскладки.**
  Для `skiller update --all` зафиксирован инвентарь адопции, который отделяет актуальность канона
  `plan-protocol` от доставки инстанса `authority-frame`; недоступные или устаревшие декларации
  остаются явно помеченными как `unknown`, а не выдаются за актуальные. Владельцы также получили
  fail-closed процедуру dry-run миграции v1→v2 (`2026.08.07-PLAN-ECONOMY` P6.6).

- **`skiller`/`task`: plan-protocol переведён на EN-only compact canon и layout-v2 authoring.**
  Удалены 230 `SKILL.ru.md`, translation gate и RU→EN prompt; canonical `SKILL.md` стал
  маршрутизатором на reader-specific reference, получил две design-формы Next и три v2 context
  значения. Новый двухпороговый D93 weight-gate уменьшил carrier с 36 651 до 4 575 оценочных
  токенов и fail-closed сверяет семь классов canon↔implementation
  (`2026.08.07-PLAN-ECONOMY` P6.5).

- **`task`: четыре hard gate plan-protocol включаются forward-only.** Общий реестр хранит
  дату и append-only journal boundary активации; per-item status projection больше не
  подменяет историю глобальной датой. Downstream, return qualification, return owner gate и
  terminal decision join применяются к новой когорте без ретроактивной красноты (`2026.08.07-PLAN-ECONOMY` P6.4).

- **`task`: model judgement и уточнения получили fail-closed command seams.** Пять plan-команд
  создают `DecisionRequest` вместо свободной прозы и исполняют закрытые исходы authority resolver;
  отдельная рубрика `return-judgement@1.0.0`, provider-qualified calibration registry и reducer
  превращают неизвестную пару либо order-sensitive swap в воздержание. Codex подтверждён на
  discovery-bank, Claude остаётся `pending-provider` (`2026.08.07-PLAN-ECONOMY` P6.3).

- **`task`: закрывающие команды plan-protocol теперь производят v2-следы.** Они записывают
  session provenance, регенерируют projections, фиксируют downstream-gate record и сохраняют
  fail-closed квалификацию эскалаций; Codex подтверждён, Claude ожидает provider-owned replay
  (`2026.08.07-PLAN-ECONOMY` P6.2, D147–D149).

## [0.10.0] - 2026-08-09

- **`task`: пять protocol commands теперь выбирают declared read path по `Layout`.** Планы без
  поля сохраняют literal v1-ветвь; `Layout: v2` читает ровно plan core, phase context, item spec,
  digest-qualified bundle и fresh item state, без обязательного `handoff.md`. Codex-проекция
  регенерирована и проверена; Claude остаётся `pending-provider` с явным replay
  (`2026.08.07-PLAN-ECONOMY` P6.1).

- **`task`: очередь решений P5.4 теперь принуждает frozen contract fail-closed.** Semantic outcome
  единообразно удерживает authorization auto-answer в owner/join pending, frozen bounds считают
  substantive options отдельно от mandatory, а exact retry восстанавливает journal и все views без
  дублирования queue events или durable continuation (`2026.08.07-PLAN-ECONOMY` P5.4, D144–D146).

- **`task`: return-loop owner gate теперь создаёт ссылочный DecisionRequest.** Замороженный
  P4 packet не копируется в очередь, affected subject паркуется адресно, а policy auto-answer
  снимает только свою локальную паузу (`2026.08.07-PLAN-ECONOMY` P5.5).

- **`task`: P5.5 теперь доказывает queue semantics исполняемым producer acceptance.** Двенадцать
  fresh-copy сценариев покрывают terminal policy auto-answer без повторного owner ingress,
  единственный разрешённый `pending-authorization` owner-flow, owner `continue`/`park`/`reject`,
  границы 2/5 substantive options, mandatory-only reject и exact retry после request/resolve
  projection failure с byte-replay generated results/report (`2026.08.07-PLAN-ECONOMY` P5.5, D146).

- **`task`: добавлена durable очередь решений планов.** Append-only запросы, lease-claim,
  адресная пауза субъекта, exact root continuation, owner-gate projection и выключенный
  join-gate реализованы без добавления очереди на обязательный путь чтения
  (`2026.08.07-PLAN-ECONOMY` P5.4, D64).

- **`task`: добавлен fail-closed резолвер полномочий планов.** Единственная точка
  `authorize()` возвращает закрытый структурированный вердикт, пинует активную
  authority-frame, агрегирует решения внутри item, безопасно автоотвечает только
  provenance-подтверждённые уточнения и поддерживает shadow-наблюдение
  (`2026.08.07-PLAN-ECONOMY` P5.3).

- **`task`: заморожена deny-by-default рамка полномочий `authority-frame` v1.**
  Машинный контракт и действующий владельческий инстанс задают единственный делегированный класс
  `constructive`, три зарезервированные границы, монотонное сужение и item-scoped агрегацию против
  дробления решений (`2026.08.07-PLAN-ECONOMY` P5.2, D60–D61, D143).

- **`task`: history событий возврата теперь содержит plan-local `return_event_id`.** Он равен
  физическому адресу `journal.jsonl:<line>` и связывает judgement carrier с конкретным return event,
  не меняя frozen fingerprint tuple, digest, namespace или `same_return_max`
  (`2026.08.07-PLAN-ECONOMY` P4.2, D142).

- **`task`: return-judgement v1 теперь детерминированно потребляется return-loop.** Редьюсер
  выбирает первую schema-valid независимую запись для точного return event, собирает полный
  event-scoped owner packet, не допускает `blocks=true` вместе с continuation и воспроизводит
  acceptance из item tree (`2026.08.07-PLAN-ECONOMY` P4.6).

- **`task`: добавлен return-loop v1 для возвратов plan-protocol.** `returns --gate`
  применяет lifted лимит, печатает hard-stop owner packet над durable history и даёт
  выключенные по умолчанию opt-in lint-проверки квалификации/owner authorization
  через существующий item-scoped finding (`2026.08.07-PLAN-ECONOMY` P4.4, D138–D139).

- Добавлен детерминированный вычислитель отпечатков возврата и durable-счётчик для планов.

- **`task`: добавлен downstream-gate v1 для producer→consumer smoke-проверки.**
  Инструмент механически выводит потребителей из путей плана, исполняет только применимое
  подмножество их `Validation`, сохраняет `green`/`red`/`unknown` с ключом «SHA-256 ТЗ
  потребителя × item-коммит продюсера» и предоставляет выключенную по умолчанию opt-in
  проверку `plan-lint` (`2026.08.07-PLAN-ECONOMY` P3.7).

- **`task`: сохранена непрерывность `plan-lint` при layout v2.** Реестр
  диспозиций с интроспекционной проверкой покрывает все `_lint_*`-проверки;
  RAG/Consequences решений и лимит Update Log читают v2-носители `decisions/`
  и `journal.jsonl`, сохраняя ветку v1.

- **`task`: `plan-lint` теперь проверяет frozen read-path v1.** Проверяются порядок
  volatility, исключение history из executor path и запрет active item’у читать item-spec
  терминальной фазы; проверки опираются на registry/spec/resolver (`2026.08.07-PLAN-ECONOMY` P3.5).

- **`task`: layout-v2 Bundle v1 теперь fail-closed проверяется для ready item'ов.**
  `plan-lint` различает declaration drift, missing/extraneous entries, changed input
  bytes и unresolved declaration, не пересобирает artifact и byte-checks decision,
  status и item-state projections (`2026.08.07-PLAN-ECONOMY` P3.4, D133–D135).

- **`task`: layout-v2 планы теперь hard-fail проверяются по бюджету обязательного чтения D2.**
  Новый shared `plan_gates` использует единственные владельцы веса и admission, называет пункт,
  численный порог, qualified calibration и отдельный нечитаемый файл; v1-планы молчат
  без opt-in (`2026.08.07-PLAN-ECONOMY` P3.3).

- **`task`: детерминированный schema-valid Bundle v1 для входов item’а
  (`2026.08.07-PLAN-ECONOMY` P3.2, D132).** Единый `plan-views.py bundle`
  строит и byte-checks committed manifests, хеширует сырые/выбранные байты и
  оценивает вес по frozen calibration; неразрешимая декларация атомарно отказывает
  до записи, а P3.4 выводит её отдельным `unresolvable_entry`.

- **`task`: stage-aware admission бюджета чтения и bounded `plan-lint` carriers
  (`2026.08.07-PLAN-ECONOMY` P2.9, D131).** `plan-weight` различает
  `historical-pre-v2`/`pending-producer`/`ready`, валидирует fail-closed producer edges и
  применяет неизменные D2(a)+D2(b) только к `ready`. Монолитные lint implementation/tests
  механически разделены на bounded modules с сохранёнными public imports и byte-parity
  диагностик v1/v2 флота.

- feat(task): добавить детерминированный on-demand исторический вид пункта layout v2.

- feat(task): добавить детерминированные generated state-проекции пунктов layout v2.

- feat(task): добавить generated owner status view для plan layout v2.

- feat(task): добавить разбор тонких фазовых индексов v2 и раздельных файлов ТЗ/состояния пунктов.

- feat(task): add immutable v2 decision records and deterministic generated views.

- feat(task): add the versioned executable-plan layout resolver and frozen carrier contracts.

### Fixed

- **`task`: journal-backed Update Log больше не создаёт незакрываемый lint-конфликт.**
  Новые `note` длиннее 300 символов отклоняются до записи, а layout-v2 status детерминированно
  проецирует historical long note коротким указателем на исходную строку без изменения
  append-only journal (`2026.08.07-PLAN-ECONOMY` P4.5, D141).
- **`skiller`: validation snapshots согласованы с текущими additive carriers.** Public config
  snapshot включает `plugins`, а publication guards фиксируют фактический Codex marketplace
  locator и полный набор Claude artifacts.
- **`task`: dry-run миграция legacy-планов больше не отвергает отсутствие
  необязательного `## Обсуждение`.** Инвентарь фиксирует отсутствие носителя без
  выдуманного файла, а blocked journal-state проецируется в обязательную v2-тройку
  эскалации (`2026.08.07-PLAN-ECONOMY` P2.10).
- **`task`: исправлена единственная рассинхронизация имени v2 phase-closure carrier.** Реестр и
  read-path specification теперь одинаково адресуют `phases/<Pn>/<Pn>.closed.md`, как D34/D77 и
  проектные потребители (`2026.08.07-PLAN-ECONOMY` D130); до реализации генератора не существовало
  runtime consumer устаревшего `.closure.md`.
- **Codex plan handoff теперь пинует полный маршрут запуска.** Generated runtime проекций
  `task:plan-*` требует отдельный native launch-block с `-C`, `-m`,
  `model_reasoning_effort`, `-a never` и `-s danger-full-access`; `$ task:…` остаётся
  только внутрисессионным invocation. Для `plan-run` маршрут выводится из Routing
  следующего item'а, а не наследуется от прошлой сессии.
- **`plan-weight.py sweep` больше не роняет весь замер флота одним недоступным корнём.**
  (`2026.08.07-PLAN-ECONOMY` P0.4, D110–D112.) У `sweep` появилась учётная единица «корень
  входа» — top-level `roots[]` с закрытым статусом `resolved`/`unreadable`/`missing` на
  каждый переданный каталог; недоступный корень (`PermissionError`) перехватывается и не
  уносит остальные, а читаемый корень без планов больше не исчезает из вывода бесследно.
  `errors[]` теперь несёт только исход ПЛАНА (`plan_dir`), не корня.
- **`maind_memory_recall` больше не тонет в общем namespace.** `_recall_union` (mid-session
  recall) наследует принцип D10 из SessionStart-дайджеста: приватный scope проекта опрашивается
  без капа (`RECALL_LIMIT=200`), а shared-scope'ы (`ns:*`/`global`) при `project:<id>`-expansion —
  под новым `RECALL_SHARED_LIMIT=40`. Замер (roadmap/memory-recall-shared-namespace-priority):
  на 6 проектах общий пул давал 84–96% ответа при малой приватной памяти проекта (напр. Agelto
  2 записи vs ns:axioma 47).
- **`task` больше не приписывает всем планам чужой D50 authority grant.** Task Contract
  выводит routine authority из проверенного item-carrier текущего плана; защищённый переход
  разрешается только exact, scope-matching и неотозванной записью `[OWNER-GRANT:<gate-id>]`
  в Decision Log, иначе остаётся `block:AUTHORITY_BOUNDARY`.
- **`task` fail-closed разбирает protected owner grants.** Запись теперь обязана точно
  связывать gate, branch и finite scope с отдельным explicit repository-owner message в Layer-0
  `brief/` и его provenance; копируемый `Approval Owner`, synthetic D#, prefix-совпадения и
  произвольная owner-проза не могут вернуть `allow`.
- **`task` и core-шаблоны больше не ищут Python runtime внутри подключаемого проекта.**
  Плановые команды Codex резолвят единственный включённый `task@swissknifeman` через нативный
  список плагинов и запускают его `lib/`; Claude Code использует `${CLAUDE_PLUGIN_ROOT}`.
  Рендерер и provenance-lock допускают такой детерминированный upgrade только при смене версии
  адаптера и точном совпадении прежнего управляемого вывода; ручной дрейф остаётся fail-closed.
- **`harness doctor --settings` распознаёт актуальные настройки Claude Code 2.1.220** и не
  требует executable-bit у скрипта, запускаемого через интерпретатор. `skiller update` удаляет
  только распознанные устаревшие симлинки `packages/task` из уже подключённых проектов.
- **Harness validation снова воспроизводима на committed tree.** Provider-instruction lock
  регенерируется штатным owner surface, run-reader тест больше не зависит от корневого архива,
  generated provider reference проверяется полным package validate, а P4 provenance/G2 assurance
  требуют exact Git/journal/anchor evidence и проходят встроенные tamper probes.

### Added

- **`task`: provider-qualified калибровка оценки токенов v2
  (`2026.08.07-PLAN-ECONOMY` P0.1, D114/D118–D122).** Появились stdlib-only
  neutral contract `task.token_probe` и изолированный адаптер `codex exec --json`;
  активный артефакт теперь пинует provider/model/protocol, fail-closed отвергает v1 и
  несовпавший classifier, а `dense_ascii` стал пятым классом с единственным SSOT.
  Ограниченный прогон использует 8 provenance-qualified real samples (≤128 KiB) и
  bracket-controls (≤12 provider calls); исторические Claude v1 artifact/probe-log
  сохранены отдельно.

- **`task`: машинный замер веса обязательного чтения пункта плана
  (`2026.08.07-PLAN-ECONOMY` P0.3, D16/D107–D109).** `task.plan_weight` + лаунчер
  `scripts/plan-weight.py` (подкоманды `item`/`plan`/`sweep`, `--json`) воспроизводят
  обязательный путь чтения исполнителя из `commands/plan-exec.md` §1 буквально
  (`plan.md` + `handoff.md` + `phases/Pn.md` + `Required Reads`), считают его вес
  оценкой СВЕРХУ поверх замороженной калибровки P0.1 и проверяют каждый файл
  КОНЪЮНКЦИЕЙ обоих гейтов измеренного лимита чтения P0.2 (`size_bytes` И `tokens`,
  D108) с указанием нарушенного гейта. Нерезолвленное классифицируется закрытой
  таксономией (`unreadable_root`/`unresolved_entry`/`missing_file`/`oversized_file`),
  и сумма НИКОГДА не печатается без перечня пробелов. По каждому файлу считается
  `dense_ascii_share` (D109) — замер без порога. Режим `--exact` сверяет оценку с
  истиной дифференциального харнесса P0.1 и остаётся ручным, вне CI; `count_tokens`
  не вызывается ни в одном режиме.

### Added

- **`task`: детерминированный конвертер executable plan v1→v2 и self-host migration
  (`2026.08.07-PLAN-ECONOMY` P2.8).** Новый `plan-migrate.py` переводит только
  разрешённый self-host plan inplace либо любой plan в безопасную read-only dry-run
  проекцию с явным output; migration inventory и before/after read-weight сохраняют
  lossless evidence. Owner status теперь корректно считает фазы с terminal
  deviations завершёнными.

- **`task`: детерминированная оценка веса чтения плана СВЕРХУ, откалиброванная против
  настоящего токенизатора (`2026.08.07-PLAN-ECONOMY` P0.1, D11/D14/D92).**
  `task.token_estimate` (stdlib-only) считает токены по закрытому набору классов символов
  (`ascii_word`/`ascii_other`/`cyrillic`/`other`) и замороженному артефакту калибровки —
  без сети и ключей, никогда не занижая. Артефакт получен ДИФФЕРЕНЦИАЛЬНЫМ харнессом
  (`calibrate-token-estimate.py`, D92: канал `POST /v1/messages/count_tokens` недостижим
  без ключа Console) по трём прогонам `claude -p` на файл корпуса (пустая обёртка / файл /
  контроль дрейфа), 14 реальных файлов планов флота, `bound.violations: 0`, рыхлость
  p95 1.17 (гейт ≤1.6).

- **Artifex business-provider projections now run against current Codex and Claude Code CLI surfaces.**
  The bounded adapters use a shared Draft-07 output schema, retain only normalized observations,
  and cover current Claude structured-result metadata without persisting provider text.

- **`dart`: подключаемый через `connect` набор для Dart-пакетов и SDK.** Новый
  `dart-package-development` покрывает публичный API, null safety, async-совместимость,
  conformance fixtures, проверки и релизную границу; Flutter-верстка остаётся в `mobile`.
- **(сводная запись плана 2026.07.31-SKM-LEAN): измеритель first-turn, резидентная диета,
  нативный скоуп навыков, exec-волна, гигиена и раскладка `core/`
  (`plans/archive/2026.07.31-SKM-LEAN/`).** P1.1 добавил к `skiller budget --first-turn`
  плагинную составляющую, а P1.3 поднял порог до 16K/23K; P1.4 исправил CWD-зависимый
  подсчёт и различил `broken`/`unparsed`. P2.1 закрепил измеримый предел корневого
  канона, P2.4 сделал `.mcp.json.example` default-on только в зелёной provider-ветке,
  P2.5 убрал дублирование нативного листинга из хаб-блока. P3.2 не раскатал
  доминируемое `paths:`, но переиздал модель листинга; P3.4 вынес четыре процедурных
  навыка в `context: fork`, P3.5 добавил `when_to_use` и совместный гейт записи.
  P4.6 дал `swissknifeman env run <PLAN-ID> Pn` для последовательной exec-волны.
  Для P5.1, P5.10 и P5.11 см. отдельные записи выше; P5.4 закрепил provenance
  маршрута исполнителя, P5.6 зафиксировал Playwright MCP с `--output-dir`, P5.8
  добавил строку команды launch-block, P5.9 — `plan-lint --conflicts`. P6.1 перенёс
  provider-кластер `core` в пакетную раскладку без изменения публичного фасада.

- **Политика доверия вендоренному классу стала исполнимой: блок `audit` в `upstream.json` +
  гейт «нет вердикта / вердикт протух» (`2026.07.31-SKM-LEAN` P5.11).** Человеческий вердикт
  по бандлу переехал из таблицы внутри плана в аддитивный блок рядом со скиллом (`verdict`
  ∈ `clean`/`attention`/`risk`, `at`, `by` — адрес читавшего, `upstream_sha` — якорь, `note` —
  обязателен при `attention`/`risk`); форму блока проверяет `validate.sh`. `--check` получил
  две находки в существующем коде выхода `11`: **`AUDIT_MISSING`** (бандла без прочитанного
  человеком вердикта не бывает — «не проверяли» и «чисто» больше не неразличимы) и
  **`AUDIT_STALE`** (вердикт вынесен против других байтов). Якорь хранится ОТДЕЛЬНО от
  `files[].sha256` и не обновляется ни `--apply`, ни `--resolve`, поэтому отметка «протух»
  переживает применение апстрима — прежний производный механизм умирал от одной строки и
  остался только для бандлов без блока `audit`. Бэкфилл **56** блоков по таблице аудита P5.1;
  бандл, который не вендорит ничего, объявлен `kind: "reference-only"` (у него якоря нет по
  конструкции). Граница «чинится то, что приходит агенту как правила поведения; справка и
  артефакт пользователя — принятый класс» записана дословно в
  `skiller/guide/vendored-skills`.
- **`frontend/web-design-guidelines`: снята зависимость от сетевого канала правил, бандл
  переведён в `strategy: fork` (`2026.07.31-SKM-LEAN` P5.10).** Скилл раньше на каждый вызов
  тянул `raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md` и
  применял полученное КАК ПРАВИЛА поведения (находка аудита `PRM_REMOTE_INSTRUCTIONS`,
  единственная из шести `attention`-находок P5.1, где удалённый контент — инструкции, а не
  справка/артефакт пользователя). Payload пинованного коммита `4e799d45c17aec1498c269287a83b9dba22b966b`
  (6 939 б, sha256 сверен) вендорен pristine-копией в `references/web-interface-guidelines.md`;
  `SKILL.md`/`SKILL.ru.md` переписаны в навигаторы без единой сетевой инструкции;
  `upstream.json` несёт `strategy: fork`, `body_path` и `notes` с процедурой ручной
  пере-пиновки. Свежесть сознательно обменяна на целостность — апстрим `main` не двигался с
  2026-04-06, цена на замере равна нулю. Процедура пиновки/пере-пиновки — новый раздел
  `skiller/guide/vendored-skills`.
- **Supply-chain вендоренных скиллов: разовый человеческий аудит 56 бандлов + триаж-ступень в
  `update-upstreams.sh --check` (`2026.07.31-SKM-LEAN` P5.1).** Первый содержательный аудит
  внешних скиллов за всю историю реестра — до него проверялась ТОЛЬКО целостность байтов.
  Поимённые вердикты 56 бандлов (**50 clean / 6 attention / 0 risk**), сплошное машинное
  покрытие 100 % байтов (599 файлов, 3 070 592 б) по четырём классам угрозы, полное чтение всех
  56 `SKILL.md` и всех 27 файлов с исполняемым содержимым, названные границы покрытия —
  `plans/archive/2026.07.31-SKM-LEAN/findings/P5-vendored-audit.md`. Подчинённая аудиту триаж-ступень:
  13 стдлиб-правил (+ `BIN_UNREADABLE`), выведенных ИЗ находок аудита, **новый код выхода `11`**
  (намеренно не слит с `10` — «апстрим изменился» и «подозрительный паттерн» разные события),
  ключи `triage`/`stale_verdicts`/`triage_disclaimer` в `--json`, дословная оговорка
  **«no findings ≠ safe»** в обоих каналах. Дрейф байтов относительно `audited_at` помечает
  человеческий вердикт протухшим (D65). Процедура и её границы — новая док-страница
  `skiller/guide/vendored-skills`. Внешний сканер НЕ подключён зависимостью — паттерны
  переписаны своими (`root.engineering-invariants`), провенанс в `docs/reference.md`.
- **`update-upstreams.sh`: починен отказ всего `--check` на провенанс-записи без зеркала.**
  Запись `files[]` с пустым `path` (ссылка на внешнюю спеку, локального зеркала нет —
  `skills/voice-ai/voice-ai`) резолвилась в САМ каталог скилла, и `read_bytes()` ронял весь
  прогон `IsADirectoryError`-ом: сверка целостности реестра была неработоспособна целиком.
  Теперь такая запись печатается тегом `[ref]` и пропускается без сверки sha. Найдено аудитом
  P5.1, закрыто регресс-тестом.

- **Паритет провайдеров Claude Code/Codex по корневым инструкциям, capability и декларативной
  политике исполнения (`2026.07.29-HARNESS-AGNOSTIC`, фазы P1–P4).** Четыре фазы, терминальные
  🟠 Done with deviations: (P1) канон корневых инструкций сверен с деревом (матрица «правило →
  дом», каталог утверждений `1.0.1→1.1.1`, гейт покрытия литералов 105/105), заведён
  adoption-режим `harness instructions <plan|check|adopt|apply|repair>` и живая транзакция на
  двенадцати целях с гейтом дрейфа; (P2) 17 `unsupported`-возможностей второго провайдера
  протриажены (закрыто/адаптер/`Claude-only` с честной причиной), диспетчер Codex-обработчиков и
  группа наблюдателей/гейтов класса B доведены до конформанс-артефакта с гейтом дрейфа в
  `hygiene.yml`; (P3) канон каркаса и реестр решений приведены к измеренной реальности, петля
  аудита замкнута машинным гейтом свежести версий паков в `validate.sh`, бюджет обнаружения
  скиллов получил provider-aware модель (Codex/Claude Code) с WARN-гейтом перебора; (P4)
  запечатан контракт декларативной политики исполнения (`execution-policy.json` +
  `execpolicy.py`, гейт `[10/10]` в `validate.sh`), delegation contract приземлён в грамматику
  оркестратора PLAN и переведён `pending → enforced`. Подробности, D-лог и артефакты —
  `plans/archive/2026.07.29-HARNESS-AGNOSTIC/`.
- **Плановые команды `plan-*.md`: кап делегирования, `confidence` в находке аудита, пункт DoR
  «внешние факт-классы» (P2.3, `2026.07.25-ECO-OPT`).** То же правило A/B/C и тот же ФОРМАТ карты,
  что у P2.2, применены к пяти `packages/task/commands/plan-{design,exec,run,close,audit}.md`.
  **Класс A снова пуст** (единственное грep-совпадение — перепрогон детерминированного линтера,
  класс B2; лесов статус-апдейтов 0): кап делегирования добавлен `plan-design.md` — единственной
  из пятёрки, где субагент-разведка предполагается текстом (гайд Opus 5 §6), ось
  `confidence ∈ {high,med,low}` — в формат находки и Expected output `plan-audit.md` (гайд
  Sonnet 5, «Code review harnesses»; `review.md` свою половину получил в P2.2). Носители машинных
  гейтов (`Pre-mutation`/`Pre-final` Task Contract, Validation, DoR-чеклист) сохранены как класс B —
  их снос «как лесов самопроверки» запрещён D86/D93. Отдельно, по D81, в `plan-design.md` внесён
  пункт DoR «внешние факт-классы фазы перечислены, у каждого — источник» ДОСЛОВНО по спеке
  `research/14-P6.3-dor-delta-spec.md` §1.2 (побайтная сверка). Карта решений —
  `plans/2026.07.25-ECO-OPT/artifacts/P2.3/opus5-revision-map.md`; `model`/`effort`-пины и
  `description` не тронуты (D16).
- **Интент-команды: капы делегирования + `confidence` в формате находки ревью (P2.2,
  `2026.07.25-ECO-OPT`).** Ревизия шести интент-команд `packages/task/commands/` и двенадцати
  файлов agent-packs по правилу A/B/C (`research/01` §1, расширено D19) под гайды Claude 5.
  **Класс A (содержательно-пустые ритуалы самопроверки и леса статус-апдейтов) — пуст**, работа
  ушла в «добавить недостающее»: кап делегирования в `design.md`/`research.md`/`review.md`
  (гайд Opus 5 §6: «give explicit guidance on which scenarios warrant delegation, or set
  deterministic caps») + ось `confidence` рядом с `severity` в формате находки `review.md`
  (гайд Sonnet 5, «Code review harnesses»). Adversarial-verify чужих находок и RAG-верификация
  внешних фактов явно выведены из-под капа — гайд адресует самопроверку собственного вывода.
  Пятнадцать файлов закрыты как «изменений нет» с разобранными кандидатами; карта решений —
  `plans/2026.07.25-ECO-OPT/artifacts/P2.2/opus5-revision-map.md`. `model`/`effort`-пины и
  `description` не тронуты (D16).
- **`general/verify-claims`: anti-overconfidence — coverage-шаг + perplexity как отдельный класс
  + делегирование сводки (P6.3, `2026.07.25-ECO-OPT`).** Три дельты по двум датированным полевым
  кейсам этого же плана (D20 — тихое сужение рамки «Opus 5» вместо «Claude 5 family»; D53 —
  сводка WebSearch-only делегата принята за исчерпывающий перечень hook-событий): (1)
  coverage-шаг — перед фиксацией плана/фазы/вердикта перечислить внешние факт-классы, включая те,
  ответ на которые кажется известным; (2) `perplexity-web` переформулирован из фолбэка на промах
  доки в отдельный класс знания (полевая практика), вызываемый ДАЖЕ когда first-party попал; (3)
  раздел «Делегирование: не ронять ступень» расширен со «проверь факт» на «сводку/перечень».
  Жёсткая граница класса A/B (D15/D19) соблюдена — ни одна добавленная строка не предписывает
  самопроверку собственного вывода. Аддитивный абзац в корневом `CLAUDE.md` § «Методология
  решений». Три новых pressure-сценария (`evals/pressure.json` id 3–5, по D20/D53/time-pressure);
  прогон `skiller eval general/verify-claims` — 6/7 зелёных (пре-существующий кейс id:2 остаётся
  красным, вне Scope этого item'а — `plans/2026.07.25-ECO-OPT/findings/P6.3-pressure-run.md`).
  **Честная граница (D58):** 7 текстовых кейсов — smoke-тест формулировки, не измерение
  overconfidence-поведения. Третий усилитель D20 (пункт DoR) — анкерованная спека для P2.3
  (`research/14-P6.3-dor-delta-spec.md`, D81), файл под cross-plan гейтом здесь не правится.
  RU-источник → регенерированный EN-канон → `check-translations.sh --stamp` → `skiller registry`;
  `description` не тронут (P3.1).
- **harness: statusline context-notify — окно в фактический процент контекста (P6.1,
  `2026.07.25-ECO-OPT`).** Новая поверхность `configs/claude-code/statusline/`: скрипт
  `context-notify.sh` печатает строку `модель · каталог · бар · N%` и на ПЕРЕСЕЧЕНИИ полосы
  порога (дефолт `80,90`, кулдаун 15 мин) отсоединённо (`setsid`) дёргает существующий
  `hooks/notify/notify.sh` — второго нотификатора не заводим. Состояние на сессию пишется
  атомарно в `${XDG_RUNTIME_DIR:-/tmp}/claude-statusline/`, потому что рантайм отменяет
  statusline-скрипт на середине при новом апдейте; `used_percentage: null` (старт сессии,
  после `/compact`) не считается нулём — бар не рисуется и решение о пороге не принимается.
  Включение opt-in per-project: `harness hooks --target . --statusline context|off` (ключ
  `statusLine` в `.claude/settings.local.json` — машинно-локальная преференция, как
  `outputStyle`; чужое значение уважается skip+warn), файлы ставит ветка `--global`.
  Замеры: дельта `skiller budget --first-turn` = 0 ток (statusline не тратит контекст-токенов
  по построению), медиана рендера 5.4 мс при максимуме 6.9 мс на 50 прогонах (порог приёмки
  50/150 мс) — числа и таблица полос в `plans/2026.07.25-ECO-OPT/findings/P6.1-statusline-measure.md`.
- **`general/context-economy` + `general/compact-responses`: compact-дисциплина (P6.2,
  `2026.07.25-ECO-OPT`).** `context-economy` §3 получила три дельты: граница сессии по шву
  задачи (завершённая единица работы/смена фазы/повторный `/compact`), а не по проценту —
  фактический процент модель не видит; что теряет компактизация (отклонённые альтернативы,
  «почему НЕ выбрали») и что решения фиксируются в файл, не только в чате; первопартийный
  рычаг `# Compact instructions` в CLAUDE.md + адресный `/compact <фокус>`. `compact-responses`
  получил дельту `answer-first` (действие раньше обоснования). Кандидат D8 `no
  preamble/closers` закрыт как уже покрытый (строки предъявлены, не переписаны). RU-источник →
  регенерированный EN-канон → `check-translations.sh --stamp` → `skiller registry`;
  `description` обоих скиллов не тронут (P3.1).
- **`scripts/bootstrap-machine.sh`: роль-осознанная ступень 5 + rollout-документация второй машины
  (P4.3, `2026.07.25-ECO-OPT`, ADR-0001).** Ступень `maind service install` читает `memory.role`
  из локального `config.json` ДО ветки `--dry-run` — на `role=client` печатает информативный
  `SKIP` и НЕ поднимает локальный демон (второй писатель), поведение `standalone`/`host` не
  меняется. `docs/deploy.md` получил раздел «Вторая машина: cross-machine память (host/client)»
  (host/client чеклисты, включая обязательный `memory.url` хоста на LAN-адрес после LAN-bind
  `iii-config.yaml`); `packages/maind/docs/guide/systemd.md` называет `loginctl enable-linger`
  условием роли `host`, не опцией. Три из шести приёмочных гейтов rollout'а (клиент-специфичные)
  не прогнаны — нет второй физической машины в исполнявшей сессии; `Linger=yes` на хосте
  подтверждён; попытка гейта «бэкап-restore» вскрыла находку — встроенный mesh-discovery движка
  подключает любой локальный процесс `agentmemory` к общей группе НЕЗАВИСИМО от каталога
  данных/порта (угроза инварианту «один писатель» при локальном тестировании) — инцидент
  устранён без потери данных (254/254 записей), root cause (`config.json` без `memory.url` на
  LAN-адрес после LAN-bind) задокументирован и исправлен на этой машине. Полный протокол —
  `plans/2026.07.25-ECO-OPT/findings/P4.3-rollout-report.md`.
- **`maind`: cross-machine режим памяти — `memory.role` (standalone/host/client) +
  bearer-аутентификация (P4.2, `2026.07.25-ECO-OPT`, ADR-0001).** Новое поле
  `memory.role` (дефолт `standalone`, back-compat — существующие узлы не меняют поведение);
  `role=client` запрещает КОДОМ поднимать локальный демон (`maind memory start|run`,
  `maind service install` отказывают), чтобы не завести второго писателя. Аддитивное
  расширение `core.http` (`http_get_json`/`http_post_json`/`ping` + необязательный
  `headers`) несёт `Authorization: Bearer` из `memory.secret_file`/`AGENTMEMORY_SECRET`;
  новый `core.http.HTTPUnauthorizedError` (подкласс `RuntimeError`) отличает 401 от прочих
  сетевых сбоев — `maind doctor`/`maind health`/MCP-ветка недоступности памяти больше не
  путают «неавторизован» с «недоступен» (`/agentmemory/health` у движка ВСЕГДА публичен,
  поэтому раньше это было неразличимо). Настраиваемый бюджет ожидания
  (`MEMORY_LIGHT_TIMEOUT_S`/`MEMORY_HEAVY_TIMEOUT_S`/`MEMORY_RETRIES`) с ретраями ТОЛЬКО на
  read-путях (`export`, не `store`/`forget` — контракт без operation-id, риск дубля).
  LAN-стадия (D80): `config/memory/iii-config.yaml` бинденд `iii-http` на конкретный
  LAN-адрес хоста (не `0.0.0.0`) — управляемый конфиг движка, обратим одной строкой при
  срабатывании триггера `tailscale serve`. Замер канала —
  `findings/P4.2-remote-link-measure.md` (честная граница: настоящей второй машины ещё
  нет, P4.3 переизмерит).
- **`skiller budget --first-turn`: резидент листинга скиллов считается по модели бюджета
  Claude Code, не суммой описаний (P3.4, `2026.07.25-ECO-OPT`).** `_measure_skills` теперь
  капает каждую запись листинга на 1 536 симв (`description`+`when_to_use`, first-party дефолт)
  и держит сумму под потолком `context_window × listing_fraction` (дефолт 1M × 1% = 10 000 ток;
  оба параметра, не константы) — раньше суммировались ВСЕ описания активного набора, тот же
  класс переучёта, что был у `/context` до v2.1.196. Отчёт показывает оба числа (`raw_tokens` —
  сумма капнутых записей, `tokens` — после потолка), когда они расходятся. Перекалибровка
  `CHARS_PER_TOKEN_*`/`FIRST_TURN_TARGET_MAX`/`FIRST_TURN_WARN` через `count_tokens` на
  `claude-opus-5` — **не выполнена** (нет сети с креденшелами/SDK в исполнительной песочнице),
  Pending Work следующего захода (`findings/P3.4-tokenizer-calibration.md` §3).
- **`docs/guide/upstream-sync.md`: критерий перевода живого скилла `notify` → `fork` +
  признание цены (P3.6, `2026.07.25-ECO-OPT`).** Новые разделы «Когда переводить скилл в
  `fork`» (две обязательные оси — механическая переприменимость правки × наблюдённая стоимость
  последних синков, плюс отсекающая ось дифф-поверхности; числовые пороги операционным
  критерием запрещены) и «Цена `fork`» (permanent merge tax · drift · security backports +
  наша специфика: `review_pending` блокирует релиз всего репо). Классификация всех 56
  паспортов `upstream.json` по критерию (`findings/P3.6-vendoring-policy.md`): переводов — 0
  (легальный и ожидаемый исход, ни один паспорт не наблюдал ручного синк-долга с момента
  импорта). Устранено расхождение доки с кодом: корневой `CLAUDE.md` § «Референсы и
  провенанс» перечислял `strategy = notify | fork | merge`, пропуская `replace` — добавлен.
- **`skiller status`: две новые дельты гигиены каналов — вендор без манифеста + дубли имён с
  реестром (P3.5, `2026.07.25-ECO-OPT`).** `detect_raw_vendor_path` видит вендорный канал,
  доставленный НЕ через `skiller sync` (симлинки/копии со стороны, без
  `.swissknifeman-manifest.json`) — раньше такой канал был невидим и `channel_overlap` на нём
  молчал (репо-факт `flexcrm`: 58 записей без манифеста). `name_duplicates` ловит дубль
  frontmatter `name` между локальной записью и ЛЮБЫМ бакетом реестра (не только включённым) —
  вторая физическая копия скилла, не обновляемая `skiller update`. `dead_local_entries`
  диагностирует битые симлинки/каталоги без `SKILL.md` числом и списком. Живой прогон на
  `flexcrm`: 9 дублей имён, 41 мёртвая запись; контроль на проекте без vendor-канала — тишина.
- **`packages/skiller/tests/test_profile_listing_budget.py`: инвариант бюджета листинга
  поставляемых профилей (P3.5, `2026.07.25-ECO-OPT`).** Реальный бюджет 1M-модели — 30 000
  символов (не 10 000, единица бюджета — токены, не проценты контекста напрямую в символах,
  диагноз P3.1); с исправленным числом 9 из 10 поставляемых профилей УЖЕ укладываются — ни один
  `profiles/*.json` править не потребовалось. `standalone` — именованное исключение
  (`buckets: ["*"]`, сузить — потерять смысл профиля), тест документирует и фиксирует границу.
- **`docs/guide/profiles.md` § «Бюджет листинга» + `docs/guide/bucket-audit-2026-07.md` §
  «P3.5 приписка» (P3.5, `2026.07.25-ECO-OPT`).** Таблица профилей против исправленного бюджета
  (30 000/6 000 симв) + карточка рекомендаций (`skillOverrides: "name-only"`,
  `skillListingBudgetFraction`) для чужих конфигов; обновлённое предложение по консолидации
  бакетов (46→48, D83) с обязательным расчётом листинга ДО/ПОСЛЕ у фактических подписчиков —
  консолидация НЕ исполняется (**OQ-10 закрыт вариантом (b)**, продавать как выигрыш бюджета
  запрещено — гранулярность экономит, слияние отнимает).

- **`review-gate`: третья точка принуждения гейта цитат — `checks/plan-citations.sh` (P11.7,
  `2026.07.25-ECO-OPT`).** Изменения задели `plans/<ID>/` → прогон `packages/task/scripts/verify-plan-citations.py
  plans/<ID> --strict` по каждому задетому плану поверх диспетчера P9.1 (`run-checks.sh`);
  строка `{"name":"plan-citations","mode":"warn"}` в `config.json` — режим по факту чистоты
  (`--strict` красный на живом дереве `2026.07.25-ECO-OPT`: 16 пред-существующих находок P11.5,
  Open risk (25) — `strict` даст необъяснённый шум, upgrade условен на их адресации); граceful
  skip, если `packages/task/scripts/verify-plan-citations.py` в дереве отсутствует. Два реальных live-прогона
  субагента (Agent-тул): битая цитата в `handoff.md` ловится `[WARN] plan-citations: …`,
  генуинно чистый план (`2026.07.24-AGENT-RELIABILITY`, 0 находок) остаётся молчаливым в этом
  же прогоне (замена цели B — на `2026.07.25-ECO-OPT` «чистого» состояния сегодня нет, тот же
  confound P11.6). Раскатано на машину владельца (`~/.claude/hooks/review-gate/`), sha256
  репо↔машина сверен; `harness doctor` — третье состояние не деградировало (`plan-citations`
  добавлена как объявленная, короткого кода нет — fallback на сырое имя, `doctor.py` не тронут).

- **`plan-protocol` §8 «Порядок закрытия item'а» + `plan-close.md`: обязательный прогон гейта
  цитат при закрытии (P11.6, `2026.07.25-ECO-OPT`).** Рядом с шагом 4 (plan-lint, после
  перезаписи handoff'а, на итоговом дереве) — `python3 packages/task/scripts/verify-plan-citations.py plans/<ID>
  --strict`; шаг 5 несёт вторую строку счёта с атрибуцией: «цитаты: N находок — новых от диффа
  item'а: K» (K>0 чинится ДО bookkeeping-коммита, N−K>0 — Pending Work + Open risks). Та же
  врезка — в `commands/plan-close.md` (режим `Pn.m` шаг 6 и режим `Pn` шаг 7). Правило вводится
  ПОСЛЕ P11.5 (гейт на живых планах уже чист — K=0 по построению для первого закрываемого
  item'а). Шаги существующего канона НЕ перенумерованы (F4-рецидив: счёт без атрибуции).

- **`packages/task/configs/verify-citations-known-exceptions.json`: baseline-перечень + триаж остаточного
  корпуса гейта цитат (P11.5, `2026.07.25-ECO-OPT`).** Прогон гейта на живых планах после
  P11.1–P11.4 дал 105 находок (52 уникальных цитаты) — по четырём механическим правилам
  R1–R4 (`packages/task/docs/reference/plan-tooling.md` § «Известные исключения»): 18 цитат
  починены на полный путь (короткая форма восстановлена однозначно, `git ls-files`), 19
  занесены в перечень исключений с адресной причиной (внешние файлы — Claude Code CLI
  бандл/Serena, неоднозначные пути — несколько кандидатов `validate.sh`, цитаты в закрытых
  item'ах и в чужих планах). `python3 packages/task/scripts/verify-plan-citations.py --strict` — 0 находок на всех
  живых планах (было 52); гейт готов к strict-классу (P11.7).

- **`plan_lint.py`: кросс-документный чек `handoff.md` ↔ «## 4. Phase Index & Status Board»
  (P11.3, `2026.07.25-ECO-OPT`, D129).** Каждое вхождение шаблона `Pn a/b` в `handoff.md`
  сверяется со значением колонки `Items 🟢/всего` строки `Pn` доски — расхождение диагностируется
  с ОБЕИМИ сторонами, отсутствующая в доске фаза — «висячая ссылка» (класс защищает от находки F8
  аудита P9: handoff соврал `P9 4/4`, доска несла `2/4`). Forward-only по дате заголовка handoff'а
  (`HANDOFF_BOARD_CANON_DATE = "2026-07-28"`); severity — как у launch-block-гейта (датовый
  `plan_id` от `2026.07.16` → ERROR, легаси → WARNING). На живом дереве ECO-OPT гейт сразу
  нашёл реальное расхождение (`handoff.md:44` — `P3 1/6` vs доска `P3 0/6`), непочиненное до
  P11.8 (Scope Excluded этого item'а). Дом — структурный линтер, не `verify-citations.py` (D129).

- **`packages/task/scripts/verify-plan-citations.py`: класс цитаты `` `file.json::a.b.c` `` через `json.load`
  с greedy-обходом (P11.2, `2026.07.25-ECO-OPT`, `research/27-P11-citation-gate-target-design.md`
  §2.3).** Раньше такая цитата резолвилась старой веткой `::symbol` — точка пути работала
  как метасимвол регэкспа, проверка была ложно-зелёной. Теперь: файл распарсен как JSON →
  путь резолвится по ключам/индексам, на каждом уровне берётся ДЛИННЕЙШИЙ дотированный
  префикс остатка, являющийся ключом (регрессия — ключи с точками в собственных именах,
  напр. `owners.P2.2`); JSON не парсится → находка «JSON не парсится», не тихий пропуск.
  Граница: «ключ существует», значение не сверяется.

- **`packages/task/scripts/verify-plan-citations.py`: двухшаговый резолвер пути + семь шаблонов поверхности
  скана (P11.1, `2026.07.25-ECO-OPT`, D128).** Резолв цитаты — по ДВУМ базам в фиксированном
  порядке (корень репо → каталог плана-источника); внутриплановая короткая ссылка
  (`` `phases/P1.md:80` ``) резолвится второй базой вместо ложной находки — на живых планах
  снимает 79% ложного фона (114/144). Поверхность скана расширена с `plan.md`+`phases/*.md`
  до семи шаблонов (`+handoff.md`, `roadmap.md`, `findings/**`, `research/**`, `brief/**`,
  рекурсивно) — было слепых 120 файлов слоёв знаний. Голое path-упоминание без суффикса
  сознательно НЕ проверяется (класс отклонён по измеренному шуму 16%, D128).

- **Реестр ролей ревью как данные (P9.2, `2026.07.25-ECO-OPT`, D126).** Extension-таблица
  `packages/harness/configs/common/agent-packs/review-roles.json` (ключ `(pack_id, role_id)`,
  рядом с каноном `roles.json`) индексирует пять reviewer-ролей: проекция/оверрайды,
  фактические заголовки четырёх обязательных секций, измерения из закрытого словаря.
  `role-bindings.json`/`agentpacks.py` не тронуты (frozen provider-contract). Валидатор
  `harness.reviewroles` (stdlib, восемь проверок, каждая — под конкретный режим отказа
  policy-as-data) — шаг `[8/8]` `packages/harness/scripts/validate.sh`, единственная точка
  принуждения. Фактический дрейф пяти паков (разные заголовки, разный набор `skills`) —
  `plans/2026.07.25-ECO-OPT/findings/P9.2-review-roles-drift.md`, адресован треку 1 OQ-4.

- **docs-impact гейт в CI (P8.4, `2026.07.25-ECO-OPT`, D119–D123).** Новый
  `scripts/docs-impact.py` + `.github/workflows/hygiene.yml` останавливает change-set,
  который вводит/убирает/переименовывает файл поверхности пакета или правит его интерфейс
  (`bin`/`commands`/`configs`/`install.sh`), без правки доков ТОГО ЖЕ пакета в том же
  диапазоне — измеренное правило C, не «любая правка поверхности» (форма спеки красила
  12/12 PR и снималась бы первым спорным вечером). Обход — трейлер коммита
  `Docs-Not-Needed: <причина>` (причина печатается). Измеренная частота срабатывания:
  8/12 PR, 11/41 коммит на дереве `cd93dbc8`; граница покрытия (не ловит правку тела
  `lib/**` без нового файла/интерфейса) названа в докстринге и `docs/develop.md` §11.

- **Матрица возможностей `docs/status.md` (P8.5, `2026.07.25-ECO-OPT`).** Таблица
  «Пакет | Возможность | Зрелость | Evidence / boundary» по пяти пакетам + `core` + корневому
  роутеру, зрелость — словарь `plan-protocol` § Statuses; каждая строка несёт воспроизводимую
  команду или названную границу. Проверяется `scripts/status-check.py` (шаг `status-check` в
  CI-job `hygiene`); честно называет границу: «видимая CLI-группа не доказывает, что её рантайм
  включён», сверка полноты со списком реальных возможностей отложена (кандидат D2).

- **CI-гигиена дерева: запрещённые пути + тег = версия (P8.6, `2026.07.25-ECO-OPT`).**
  `scripts/public-hygiene.py` — fail-closed по `git ls-files` на запрещённые суффиксы/имена/
  каталоги (`.sqlite`/`.log`/`.pem`/`.key`/архивы, `.env` кроме `*.example`, `__pycache__`/
  `.venv`/`node_modules`); `scripts/verify-tag.py <tag>` — тег `vX.Y.Z` обязан быть верхним
  выпущенным заголовком `## [X.Y.Z] - YYYY-MM-DD` в корневом CHANGELOG.md. Шаг
  `public-hygiene` в job `hygiene` и новый job `release-tag` (`on: push: tags: ['v*']`) в
  `.github/workflows/hygiene.yml`; раздел в `docs/develop.md`.

- **`core.io.assert_safe_replace_target` (P8.7, `2026.07.25-ECO-OPT`).** Инвариант цели
  атомарной записи: перед `os.replace` `atomic_write_text`/`atomic_write_json` отказывают, если
  существующая цель — symlink, не-регулярный файл или жёсткая ссылка (`st_nlink != 1`); отказ
  называет путь и причину. Несуществующая цель и обычный файл — поведение байт-в-байт прежнее;
  новый параметр `check_target=False` — точечный законный выход. Дедуп: докстринг называет
  ручные копии того же инварианта в `packages/maind/lib/maind/provider_deploy.py` (перевод на
  хелпер — roadmap-кандидат, вне скоупа этого item'а).

- **`validate.sh`: секции тела CORE-девятки, анти-дублирование проекции, полнота pressure
  (P8.8, `2026.07.25-ECO-OPT`).** Три детерминированных гейта дельтой: (1) резидентные
  `core-policy.json::skills` (9 шт.) обязаны нести активационную секцию (`##When…`/
  `##Activate…`, ERROR с рэтчетом `scripts/skill-sections-burndown.txt`, 3 стартовые
  записи) и секцию ссылок (`##Links`/`References`/`Related skills`/`Related`, ERROR без
  исключений — долг нулевой); (2) тонкие проекции `.claude|.agents/skills/*/SKILL.md` не
  дублируют канон — пары из `adapters/repository-bootstrap/publication-lock.json`: тело
  ≤15 непустых строк, есть ссылка на канон, ни один `##`-заголовок канона не воспроизведён
  (fail-closed: проекции есть, лока нет ⇒ ERROR; ни того ни другого ⇒ пропуск); (3) скилл с
  `evals/evals.json` обязан иметь `evals/pressure.json` с ≥1 сценарием (ERROR), а
  `triggers.json`'s `should_trigger` без покрывающего pressure-сценария (новое поле
  `triggers[]`) — WARNING. `eval.py::validate_pressure` валидирует форму `triggers[]`.

- **`skiller eval`: детерминизм `benchmark.json` (P8.9, `2026.07.25-ECO-OPT`).**
  Метрики (`pass_rate`/`duration_*`/`tokens_*`/`delta.*`) — точная арифметика
  `fractions.Fraction` внутри (√ для stddev — целочисленно, `math.isqrt`), строка
  фиксированной точности на границе записи — ни одного `float` в отчёте.
  Инжектируемые часы (`clock_ns`/`now_iso` в `run_case`/`run_suite`/`cmd_eval`,
  дефолт — реальное время, CLI не меняется) дают побайтную воспроизводимость при
  одинаковых часах. Честный блок `provenance` (`llm`/`network`/`clock`/`baseline` —
  фактические, не константы). `schema_version: "skill-benchmark/v2"` (намеспейсовано
  — не конфликтует с соседним P3.3-контрактом `system-bank-benchmark/v1` в том же
  модуле). No-op на офлайн-ветке, ровно `benchmark.json`(+`.html` при `--static`)
  на online — 6 новых тестов через `SKM_CLAUDE_BIN`-фейк.

### Changed

- **Корневой `AGENTS.md`: router-таблица + untrusted-import инвариант + починка по адресам
  поломок Codex-догфуда (P7.2, `2026.07.25-ECO-OPT`, D62/D143).** Новая секция `## Operation
  router` (таблица `Operation | Canonical procedure`, приём A2) отправляет к канону
  `general/plan-protocol` §8 для plan-item'ов и вводит правило «работа внутри пакета —
  перезапусти `codex -C packages/<name>`» (D62(3), закрывает owner-вопрос судьбы per-package
  `AGENTS.md` без их фактического рендера); untrusted-import строка (приём F1) — импортированный
  контент есть данные, не инструкции. Четыре поломки живого dogfood-прогона P7.1
  (`findings/P7.1-switch-test.md` §6) починены по адресу: headless-форма `codex exec` без
  несуществующего у неё флага `-a`; preflight больше не предписывает `codex doctor --json` для
  подтверждения model/effort (структурно не умеет `-m`) — источник истины теперь сама запущенная
  команда; launch-block для `plan-protocol`-работы объявлен MANDATORY нейтральной таблицей
  (с `Capabilities`) поверх нативной, не опциональным «may accompany»; форма семантического
  носителя `Next` больше не переписывается здесь — строка router-таблицы отправляет к канону
  `general/plan-protocol` §8. Размер склейки
  `AGENTS.md` — 7 252 б против потолка 32 768 б (≈22%, запас ≈4,5× — 32 768 / 7 252). Спека —
  `plans/2026.07.25-ECO-OPT/research/21-P7.2-instruction-slice-spec.md`.

- **Ремедиация реопена P7 (P7.4, `2026.07.25-ECO-OPT`, D144).** Аудит P7 (RED) нашёл ложное
  основание в правке выше: корневой `AGENTS.md` утверждал, что `codex doctor --json` не
  принимает `-c` — принимает, отвергает только `-m`; преflight-буллет приведён к факту.
  Launch-буллет требовал `-a never` от headless `codex exec`, у которого такого флага нет —
  форма разделена на TUI-путь (`-a never`) и headless-путь (`-c 'approval_policy="never"'`).

- **Форма ячейки `Items` в `## 3. Routing` — закрытый набор + диагностичный отказ
  (P8.10, `2026.07.25-ECO-OPT`, D124/D125).** Канон `plan-protocol` §9 объявляет значение
  ячейки закрытым набором из двух форм — один item (`Pn.m`) либо диапазон одной фазы
  (`Pn.a–Pn.b`); список через запятую (`P8.5, P8.6`) и склейка диапазона со списком
  (`P4.1–P4.2, P4.4`) нелегальны — группу подфаз несёт колонка `Batch`. Оговорка Back-compat
  получила честную границу: легаси-послабление §3 действует для человека, но не для ячейки
  `Items` — её читает и машина. `task_contract._find_routing_row` на такой ячейке отдаёт
  диагностичный отказ (называет ячейку, её номер строки в `plan.md` и обе легальные формы)
  вместо глухого `no §3 Routing row found for this item`; отказ остаётся отказом — маршрут
  из совпавшего токена не берётся. Ячейка без запятой и без совпадения даёт прежний текст
  байт-в-байт. Замер, породивший правку: 7 живых items флота не строили Task Contract.

- **`SERENA_SCHEMA_FIELDS` сужена до факта апстрима (P5.6, `2026.07.25-ECO-OPT`, D117).**
  Константа несла 12 ключей под именем `FIELDS_WITHOUT_DEFAULTS` пиннованной Serena
  (`026b007b…`, `1.6.2.dev0`), где апстрим на этом SHA держит два — `project_name`,
  `language_servers`; остальные одиннадцать имеют дефолты (`data.setdefault`). Комментарий
  указывает адрес факта (файл+строка апстрима, дата сверки); докстринг `render_project_yaml`
  исправлен по тому же поводу («отсутствие ЛЮБОГО → KeyError» — неверно, удалено). Поведение
  рендерера не изменилось — печатаем полный набор ключей своим решением, не по требованию
  апстрима. Гейт `check_schema_connectivity` по-прежнему ловит настоящее расхождение
  (`language_servers`), но больше не красит уход необязательного ключа (`encoding`) ложным
  расхождением.

- **`code-review-graph` — вердикт `skip`, вопрос закрыт числом (P5.2, `2026.07.25-ECO-OPT`, D112/D113).**
  Внешний граф кода как retrieval-слой под ревью **не подключается**: `Ops` у кандидата отличные
  (build 1.66 с на 405 файлах, инкремент 0.24 с), но precision blast-radius против co-change ground
  truth `P_impact` = **0.039** при пороге `≥ 0.40`, объявленном ДО замера. Порог не двигали —
  вместо этого замер УСИЛИЛИ по решению владельца: k-fold (каждый изменённый файл коммита seed'ом
  по очереди, 24 fold'а на трёх реальных коммитах Laravel-проекта, протокол объявлен отдельным
  коммитом до прогона). Усиление сдвинуло числа в пользу инструмента (medium ×2.1, large ×1.45) —
  порог всё равно не взят, порог перешёл 1 fold из 24. Отказ по ШУМУ, не по слепоте: recall
  0.40–0.43 при 110 предсказанных файлах на один seed (истинные — на позициях 77 и 102, то есть
  усечение top-K делает хуже). Канон графа кода остаётся **Serena** (LSP). Записано в тело скилла
  `general/mcp-advisor` (новая строка карты серверов + блок «Граф-retrieval MCP: измеренный
  вердикт» с правилом «не подключать по README — только после своего co-change-замера» и тремя
  триггерами переоткрытия) и в `docs/reference.md` (`reference → пилот` → `skip` с числами).

### Fixed

- **Codex: базовые плагины `core` и `task` теперь устанавливаются из коробки.**
  Зонтичный `install.sh` добавляет локальный marketplace `swissknifeman` и вызывает
  нативную установку обоих плагинов, поэтому `$ task:*` доступен в новой сессии без
  ручного `codex plugin add`/симлинка внутри проекта. Список берётся из единой
  `core-policy.json`; профильные плагины глобально не раздуваются. На машине без Codex
  шаг честно пропускается, opt-out — `--no-codex-plugins`.

- **Codex: native bucket-плагины снова раскрывают skills после установки.**
  Генератор `.codex-plugin/plugin.json` перечисляет каждый каталог skill явно вместо
  корневого `./`, который Codex 0.146.0 принимал, но не раскрывал в prompt. Live
  consumer-acceptance теперь проверяет `blender` в изолированном `CODEX_HOME`.

- **harness: стартовая уборка statusline удаляет осиротевшие `*.tmp` (P6.4,
  `2026.07.25-ECO-OPT`).** Единственный `find` в ветке новой сессии теперь убирает
  устаревшие `*.state` и `*.tmp` с тем же порогом `-mtime +1`; регресс-тест сохраняет
  свежие файлы обоих видов.

- **Пин Serena восстановлен в первопричину — `SERENA_SRC`/`config.json`/`.mcp.json` флота (P5.3, `2026.07.25-ECO-OPT`, D109/D110).**
  Политика `code_graph.args`/`index_args` корневого `config.json` перебивала пиннованный дефолт
  `SERENA_SRC` (`packages/maind/lib/maind/constants.py`) непиннованным
  `git+https://github.com/oraios/serena` — весь живой флот резолвил плавающий HEAD.
  Первая попытка вернуть тег `v1.6.1` провалилась фатально (`KeyError: 'languages'`): апстрим
  переименовал `languages` → `language_servers` ПОСЛЕ релиза `v1.6.1`, а наш провиженер перешёл на
  новый ключ ещё 2026-07-23 (`ccd4505b`) — любой тег сегодня оказывается downgrade, ломающий
  загрузку `.serena/project.yml` на каждом зарегистрированном проекте. Владелец расширил форму
  пина (D110): неизменяемая ссылка = тег ИЛИ полный commit-SHA; значение —
  `@026b007bb889366283c925527e9a3bab317f66c1` (`main` HEAD, `Serena 1.6.2.dev0`) — внесено тем же
  швом в `constants.py`, `config.json` (`args`+`index_args`) и `serena.args` десяти живых
  `.mcp.json` (`agelto`/`flexcrm`/`vaulter`/`swissknifeman`/`corex`/`memster`/`cms`/`edufy`/
  `chatom`/`perplexity-web-mcp`). Smoke на двух типах проектов (python-монорепо `swissknifeman`,
  php/laravel `flexcrm`) подтвердил полный JSON-RPC цикл (`initialize` → `get_symbols_overview`)
  без фатала. Повторный `maind sync --only mcp --dry-run` подтверждает, что `unmanaged-target`
  (P10.4/D106) остаётся отдельным, не исчезнувшим дефектом — доставка `.mcp.json` во флот
  по-прежнему ручная.

- **Пин Serena перенесён в версионируемый слой + гейт связности в `maind doctor` (P5.5, `2026.07.25-ECO-OPT`, D115/D116).**
  P5.3 пиннована три поверхности, но `config.json` — **gitignored**; единственный версионируемый
  носитель той же политики, `config.example.json`, оставался непиннованным, и
  `packages/maind/install.sh` копирует его в живой `config.json` на любом новом узле — свежая
  установка воспроизводила дефект D65 собственным установщиком. Пин
  `@026b007bb889366283c925527e9a3bab317f66c1` внесён в `config.example.json`
  (`code_graph.args`+`index_args`), `.mcp.json.example` (`serena.args`) и пример в
  `packages/maind/docs/guide/code-graph.md`. Под двойной охраной: офлайновый тест
  `test_tracked_templates_pin_serena_same_as_source` (`test_constants.py`) сверяет шаблоны
  побайтно с `constants.SERENA_SRC`, и `maind doctor` теперь зовёт
  `codegraph.check_schema_connectivity` на РЕАЛЬНОМ конфиге узла — расхождение печатается,
  не чинится (D111).

- **`core.provider_lock._classify`: `unmanaged-target` теперь может быть принят под управление явным `--repair` (P10.4, `2026.07.25-ECO-OPT`, D92/D106).**
  Ветка `record is None` возвращала `OWNERSHIP_CONFLICT`/`REFUSE` РАНЬШЕ, чем в потоке
  появлялся учёт `repair_requested` — неуправляемая существующая цель не могла быть усыновлена
  никогда, даже при явном `--repair` (найдено D65, гипотеза D82). Двухтирное правило, заданное
  ДО реализации: **тир 1** — цель существует, записи нет, `repair_requested` выставлен И
  содержимое побайтно совпадает с рендером ⇒ принимается под управление (пишется provenance,
  диск не меняется — `STALE_SOURCE`/`UPDATE`, не `NOOP`, иначе `apply_plan` пропустил бы запись
  лока); **тир 2** (содержимое расходится) ⇒ по-прежнему `REFUSE`, но диагностика называет путь
  цели, класс расхождения и команду («diff … --repair»), а не голое `unmanaged-target`. Четыре
  тестовые комбинации (цель есть/нет × repair да/нет) + отдельный тест на тир 2. **Эмпирика на
  живом флоте (15 проверенных `record is None`-целей):** 15/15 — тир 2, тир 1 не встретился ни
  разу — расхождение системное (рендерер сегодня даёт `codegraph`/`perplexity` + литерал
  `"maind"`, а раскатанные `.mcp.json` несут `serena`/`perplexity-web` + `${MAIND_BIN:-maind}`),
  не по-проектный дрейф; починка конвенции рендерера — отдельный дефект, `--adopt` для тира 2
  осознанно НЕ реализован (owner-решение, D106). Доставка `.mcp.json` на флот остаётся ручной
  по факту (P5.3).

- **`plan_lint.py`: гейт напечатанных кодов границ (`_lint_write_site_codes_44`) ошибался
  в ОБЕ стороны из-за `re.search` по всему полю `Completion Notes`.** Fail-open: item,
  цитирующий в прозе коды ЧУЖОГО item'а (разбор, пример формы), проходил гейт как
  закрытый со своими. Ложный ERROR: item со своими `allow`/`allow`, процитировавший выше
  по тексту `block:*`/`n/a` чужого item'а, краснел — `search` брал ПЕРВОЕ вхождение. Обе
  цены реальны с активации гейта (`WRITE_SITE_CODES_CANON_DATE = 2026-07-27`). Починка —
  каноническая строка-носитель `write-site: pre_mutation: <код> · pre_final: <код>`
  (D88): гейт матчит ТОЛЬКО её, построчно; коды на других строках (цитаты, объяснения)
  больше не считаются. Литерал `write-site:` зарегистрирован в `CANON_LITERALS` +
  `i18n-keep`; инструкция печатать строку добавлена в `plan-exec.md`/`plan-close.md`.
  Пять новых различающих тестов (два из них — на коде ДО правки, красные) + два
  существующих теста `TestWriteSiteCodesGate`, кодировавших старую свободную форму,
  переведены на каноническую строку (фикстура, не предмет проверки).

- **skiller sync --repair теперь восстанавливает managed-скилл, УДАЛЁННЫЙ из проекта.**
  Пропавший скилл классифицируется как managed-drift (`not dst.is_dir()`), но пре-образа
  у него нет по определению — ветка ремонта требовала `SKILL.md` для бэкапа и падала
  `SPUB_OWNERSHIP_CONFLICT: … has no recoverable pre-image`, из-за чего ЕДИНСТВЕННЫЙ путь
  восстановления был недостижим: обычный `sync` отказывался (drift), `--repair` умирал.
  Наблюдено на живом проекте (`plan-protocol` пропал из `.claude/skills`). Теперь при
  отсутствующих локальных байтах бэкап просто не создаётся (нечего сохранять), копия
  восстанавливается, evidence несёт `observed: sha256:<missing>`; поведение при живых
  локальных правках не изменилось — бэкап `SKILL.md.provider-artifact.bak` по-прежнему
  обязателен. Регрессионный тест —
  `test_repair_restores_managed_skill_deleted_from_project`.

- **Резолвинг пути плана после архивации: `core.resolve_plan_dir` (P10.3, `2026.07.25-ECO-OPT`).**
  `scripts/provider-docs.py` жёстко читал живой путь `plans/2026.07.19-DUAL-PROVIDER/…` и падал
  `FileNotFoundError` после архивации того плана (файл фактически лежит в `plans/archive/…`), а
  `packages/skiller/lib/skiller/doctor.py` те же две диагностики (`capability-reference-coverage`,
  `trace-quality`) молча деградировали в `unknown` с неразрешимым `next_command: cat …` —
  дерево несло ДВЕ конвенции на один факт («план `<ID>` — это `plans/<ID>` ЛИБО
  `plans/archive/<ID>`»), и следующая архивация ломала следующего читателя. Новый хелпер
  `core.repo.resolve_plan_dir(repo_root, plan_id)` — единый резолвер (живой каталог, иначе
  архивный, иначе `FileNotFoundError` с ОБОИМИ проверенными путями); переведены четыре
  функциональных читателя: `scripts/provider-docs.py`, `scripts/test-provider-docs.py`,
  `packages/harness/lib/harness/instructions.py`, `packages/skiller/lib/skiller/doctor.py`.
  `python3 scripts/provider-docs.py --check` — зелёный.

### Added

- **`maind.codegraph.check_schema_connectivity`: офлайновый гейт связности «пин Serena ↔ схема `.serena/project.yml`» (P5.4, `2026.07.25-ECO-OPT`, D111).**
  Версия Serena живёт в репо двумя независимыми местами (`constants.SERENA_SRC` и шаблон
  `render_project_yaml`) — они уже расходились молча (D109) и упали фаталом только у живого
  сервера. Новая функция сверяет пин (`SERENA_SRC` + `code_graph.args`/`index_args` конфига)
  с обязательными ключами схемы (`constants.SERENA_SCHEMA_FIELDS`, офлайновая копия факта,
  без сети) против того, что реально печатает рендерер — не значение пина, только связность.
  Подключено к `packages/maind/scripts/test.sh` через `tests/test_codegraph.py`.
- **`packages/task/scripts/verify-plan-citations.py`: гейт «ссылка-доказательство резолвится до символа»
  (P10.2, `2026.07.25-ECO-OPT`).** Переносит в репозиторий класс проверки, дыру в котором
  чужой закрытый план назвал своим долгом (`verify_claim_verdicts.py` проверял только
  существование ФАЙЛА из `ref` до `::`, символ после `::` не валидировался — через эту
  дыру прошёл mis-cite H06). Новый stdlib-скрипт проверяет четыре формы ссылок
  (`path:line`, `path:line-line`, `path:line,line`, `path::symbol`) во всех живых планах,
  закрывая заодно второй класс — протухшие линейные якоря на файлы, переписанные другим
  планом (D89). `--strict` для CI/предстартовой дисциплины, отчёт печатается всегда;
  `--selftest` — embedded unittest. Первый прогон на `2026.07.25-ECO-OPT`: 154 цитаты,
  39 находок (документированы в Completion Notes P10.2 — не подогнаны под ноль).
- **maind MCP: tool-result trimming + PARTIAL-receipt (P3.2, `2026.07.25-ECO-OPT`).**
  Единая воронка `_content()` (`packages/maind/lib/maind/mcp.py`) целится ниже
  warning-порога Claude Code (10 000 токенов): (1) над порогом сначала снимается
  `indent=2` (чистая экономия без потери данных); (2) если и компактный JSON не
  укладывается — крупнейший топ-уровневый список урезается бинарным спуском с честным
  receipt (`truncated`/`returned_count`/`total_count`/`hint`), без ветвления по имени
  инструмента. Ответ, укладывающийся в порог, не меняется байт-в-байт. Живой замер
  11 инструментов (`findings/P3.2-maind-tool-result-sizes.md`) показал: снятия `indent=2`
  хватает всем текущим ответам узла флота (крупнейший — `maind_projects_list`,
  ~8,3К оценочных токенов после снятия отступов против ~10,6К с ними) — расчётный путь
  «(2) потолок+receipt» кодом покрыт и протестирован синтетическими фикстурами, но на
  живом узле пока не срабатывает.
- **`review-gate`: гейт с содержанием вместо тихого но-опа (P9.1, `2026.07.25-ECO-OPT`).**
  Содержание проверок переехало в `hooks/review-gate/checks/` (диспетчер `run-checks.sh` +
  `generated-assets`/`plan-lint` strict + `tests-touched` warn); `config.json` объявляет
  ТОЛЬКО набор и per-check режим, `check_command` — одна стабильная строка-вызов
  диспетчера. Глобальный `MODE=warn` понижает strict-класс, не наоборот; защита от петли —
  счётчик диспетчера по (сессия, агент, проверка), третий подряд strict-отказ понижает до
  `warn` с `systemMessage`. `apply-permissions.sh --global` ставит `checks/` всегда и
  мигрирует `config.json` ТОЛЬКО если он байт-в-байт старая заглушка (иначе — локальный
  выбор, skip + точная команда). `harness doctor` печатает одно из трёх состояний
  (`unconfigured (no-op)` / `configured: …` / `disabled (MODE=off)`) вместо молчания.
  Live-прогон субагента подтвердил семантику `exit 2` (принуждает продолжать, не
  прерывает) и снял `[UNVERIFIED]` про `stop_hook_active` (поле реально есть в рантайме) —
  `findings/P9.1-review-gate-proof.md`.

- **`CHECKPOINTED`: отказ item'а обязан нести точную команду возобновления (P8.3,
  `2026.07.25-ECO-OPT`).** Item со статусом `🔴 Blocked` мог закрываться отчётом «не
  смог» без пути назад. Носитель — строка `Возобновление: <точная команда>` в поле
  `Pending Work` item'а (НЕ седьмой статус и НЕ семнадцатое поле — оба варианта сломали
  бы контракт `plan_lint.STATUSES`/`TERMINAL_STATUSES` и межплановый гейт
  `packages/task/scripts/cross-plan-files.py` на всех живых планах). Гейт `plan_lint.py` — opt-in ОДИН
  РАЗ (`Closure Protocol | v1`): `🔴 Blocked` без непустой команды (форма `Возобновление:
  — (внешний блокер: …)` легальна для блокера без локального шага) → ERROR с id item'а;
  `⛔ Skipped by decision` без РОВНО `Возобновление: —` и ссылки `D<номер>` → ERROR.
  Разграничено с формой `waiting:`/`ОЖИДАНИЕ:` (та про шаг плана, эта про item). Канон —
  `plan-protocol` §6; литерал `Возобновление:` в `CANON_LITERALS` + `i18n-keep`;
  инструкции — `plan-exec.md` (эскалация), `plan-close.md` (реконсиляция) (skill
  `2.18.0 → 2.19.0`, units `core`/`general` + skiller package API `0.11.0 → 0.12.0`).

- **`**Consequences:**` в D-записи + словарь зрелости возможности (P8.2,
  `2026.07.25-ECO-OPT`).** D-лог фиксировал решение и причину, но не цену: отменяющая/
  заменяющая D-запись (`supersedes D#`/«отменяет D#»/причастие) теперь несёт инлайн-
  подполе `**Consequences:**` внутри ячейки `Решение` (пятая колонка отклонена — шапка
  D-лога канон-литерал). Гейт `plan_lint.py` — opt-in ДВАЖДЫ (`Closure Protocol | v1` +
  `Дата` D-записи ≥ `2026-07-28`, forward-only — на живом дереве измеренный предикат
  ловит единственную существующую отмену без `Consequences`, и бэкфилл ей запрещён);
  предикат отмены/замены — измеренный (`supersedes D`/«отменяет D»/причастие с
  негативным lookbehind `(?<!не )`), а не спека дословно (та ловила ноль записей на
  плане, ради которого гейт вводится — русское причастие склоняется). Второй приём —
  словарь зрелости ВОЗМОЖНОСТИ (не item'а): РОВНО пять значений — `available` /
  `experimental` / `behind-gate` / `disabled` / `superseded`, канон — `plan-protocol` §6,
  рядом с шестью статусами item'а (разные оси: «item закрыт» ≠ «возможность работает»).
  Канон — `plan-protocol` §4 (D-лог), §6 (словарь); литерал `**Consequences:**` в
  `CANON_LITERALS` + `i18n-keep`, стемы отмены — в `HEURISTIC_LITERALS` (skill
  `2.17.0 → 2.18.0`, units `core`/`general` + skiller package API `0.10.0 → 0.11.0`).

- **Отчёт закрытия фазы `plans/<ID>/closure/<Pn>.json` (схема v1) с классом свидетельства
  (P8.1, `2026.07.25-ECO-OPT`).** `## Phase Handoff` — проза плюс git-хеш: класс
  свидетельства не фиксировался нигде, и синтетика читалась как результат. Теперь фаза
  сдаётся ещё и машиночитаемым отчётом: `evidence_class` — enum РОВНО из трёх (`real` /
  `synthetic` / `baseline_pending`), «нет числа» выражается ЗАПИСЬЮ с причиной, а не
  отсутствием ключа. Включается **opt-in** полем `## 0. Meta` → `Closure Protocol | v1`
  (иное значение = ERROR); плана без поля правило не касается ни одной диагностикой
  (тест аддитивности). Писатель — `plan-close <ID> Pn` (собирает механически из полей
  items); потребители названы и оба исполняются: `plan_lint.py` (схема · `items[]` ↔
  `## Phase Status` · `phase_status` ↔ Status Board · `real` с пустым доказательством ·
  терминальная фаза без файла — ERROR с ожидаемым путём) и `plan-audit <ID> Pn` (первый
  вход ступени 1: перепрогон команд из `evidence` на `git.head_sha`, детект правки ТЗ
  фазы после закрытия по `inputs_sha256`). Наш `evidence_class` РАЗВЕДЁН одной строкой
  канона с закрытым перечнем классов доказательства `recomputed`/`cross-checked`/
  `pinned-not-recomputable`/`unknown` (`source-evidence-verification-v1.md`) — разные оси,
  оба словаря действуют. Канон — `plan-protocol` §8 + `snippets/closure-template.md`
  (skill `2.16.0 → 2.17.0`, units `core`/`general` + skiller package API `0.9.0 → 0.10.0`).

- **docs/plan — canonical docs synchronised and the measured-scope Owner decision
  packet assembled (P4.3, `2026.07.24-AGENT-RELIABILITY`).** Terminal item of the plan.
  Docs now state the three source layers explicitly — canonical (hand-written), generated
  (`skiller registry` / `render-provider-commands.py`, never hand-edited, drift repaired by
  regeneration) and effective (what the runtime actually resolves, read via
  `skiller doctor --effective-source`) — and print measured quality rather than rounding it
  to `ok` (`docs/control-surface.md`). `docs/task/plan-structure.md` gains the compiled
  portability tiers (`brief-acceptance` / `committed-bundle`), the classification rule and
  who applies it, the five lint rejections, the provenance-vs-execution-input test **by role
  rather than by spelling**, the five `committed-bundle` requirements (minimisation with
  named excluded classes; a deterministic manifest AND a committed verifier whose hashes are
  recomputed rather than trusted; complete dependency closure; one neutral semantic carrier
  whose Claude/Codex renderings are projections, never the source of truth; the proof-class
  rule) and the closed proof-class enum — plus the P4.4 machine gate on printed
  `pre_mutation:`/`pre_final:` codes. `docs/task/methodology.md` separates an audit verdict
  from plan acceptance, so a clean record can no longer be read as a met floor.
  `docs/reference.md` records the external `core`/provider architecture audit as adjudicated
  (3 accept → future proposals, 11 reject, 2 unknown) and `docs/rejected-optimizations.md`
  carries its three load-bearing rejections with the code that refutes them.
  `packages/analyst/docs/architecture.md` documents the two public modules the Contribution
  gate was paid for (`analyst.trace`, `analyst.metrics`) and why `plugin.json` does not
  follow `package.json`. Publication closure is proven by command, not by prose: task render
  `--check` and `skiller registry --check` both no-op, the diff-scope guard over adapters /
  bootstrap trees / both marketplaces exits clean, and the private
  `repository-bootstrap@0.2.0` unit is recounted from its own lock — 27 thin root
  projections (26 class-A + class-B `workflow-craft`), one combined lock, **zero** ordinary
  marketplace entries. The packet
  (`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P4.3/owner-decision-packet.md`) states in
  its first sentence that acceptance is formally NOT met, prints what is unproven as numbers
  (`F1 = 0.96`, `F10 = unknown`, declared subset 5/31, F6 on a denominator of 1, Codex side
  never attempted), lists every residual debt with a named carrier, records the rehearsed
  rollback and its measured cost (2/5 → 5/5 first-pass success would be destroyed), and asks
  exactly one owner decision (G1 go/hold) with a **hold** recommendation and falsifiable
  criteria that would change it. One honest gap is recorded rather than repaired:
  `scripts/provider-docs.py` — the generator/checker behind `docs/provider-support.md` —
  still reads `plans/2026.07.19-DUAL-PROVIDER/...` after that plan was archived, so it fails
  closed with `FileNotFoundError` and is wired into no `validate.sh`; that page is therefore
  **not** claimed proven closed, and the repair belongs to the script's owner (D27/D31).
- **skiller — read-only composed effective-source doctor
  (P4.2, `2026.07.24-AGENT-RELIABILITY`).** `skiller doctor --effective-source [--json]`
  composes five read-only diagnostics — active semantic owner/provenance/collisions
  (reused verbatim from the P1.4 gate, `run_effective_runtime_gate`, never re-derived),
  cache (a structural `n/a`: identity detection is repo-derived/cold, D44 — no provider
  cache/profile is read), reference/capability coverage (cites the committed P1.1
  capability-gaps finding), hook ownership (registration source × `.swissknifeman/
  provider-artifacts.lock.json` managed owner × handler locality, per
  `semantic-identity-ownership-v1.md` § Hook identities) and trace-quality (cites the
  committed P3.11 measured scope — declared subset 5/31, `F1=0.96`, `F10=unknown` —
  printed measured, never rounded to `ok`). Each diagnostic carries owner/source/status/
  evidence/quality/`next_command`; `build_effective_source_report` fails closed on a
  missing key or an out-of-vocabulary status. No new public subcommand or write path
  (Scope Excluded, D92): an extension of the existing `skiller doctor` facade only,
  proven no-write by `git status --porcelain=v1` before/after in Validation.
- **analyst/harness — Contribution gate minor bumps paid (P4.5,
  `2026.07.24-AGENT-RELIABILITY`, `analyst@0.2.0`, `harness@0.4.0`).**
  Package-API minor bumps owed by `unified-agent-trace-v1.md` § Contribution gate (D23) —
  `analyst 0.1.0 → 0.2.0`, `harness 0.3.0 → 0.4.0` — were recorded as debt in P3.1
  Pending Work / P3.2 Completion Notes (the contract's own consumer-surveyed SemVer/ADR
  result) but left unpaid because `package.json` sat outside those items' declared
  `Files`. This item pays exactly that debt: `analyst`'s bump reflects the new public
  module `analyst.trace` (P3.1's normalized `TraceRecord` schema owner) plus
  `analyst.metrics` (P3.2's paired reliability digest layer); `harness`'s bump reflects
  the new public module `harness.provider_trace` (P3.1's thin Claude/Codex readers).
  Neither package's `.claude-plugin/plugin.json` moves — that is a separate publication
  surface not derivable from `package.json` (measured: `harness` package `0.3.0` sat
  against plugin `0.2.0` before this bump) — and no generated artifact drifts
  (`skiller registry --check` and diff-scope guard both confirm a no-op).
- **task/general — machine gate for printed pre_mutation/pre_final boundary codes
  (P4.4, `2026.07.24-AGENT-RELIABILITY`, `plan-protocol@2.15.0`, `skiller@0.8.0`).**
  `plan_lint.py` gains a new rule: a `🟢`/`🟠` item whose `Updated` cell (Phase Status
  table) is ISO-dated `≥ 2026-07-27` must print BOTH `pre_mutation:`/`pre_final:` codes
  in its Completion Notes, and both must read `allow` (D76: `n/a` is not green) — a
  missing code, or a code other than `allow` on either boundary, is now an ERROR
  instead of a prose checklist item (`plan-audit.md`) an auditor has to remember to
  recompute by hand. Repairs `findings/P3.11-terminal-audit-2.md` § Ф2 (reopen of F3,
  event 2 of 2): five consecutive items (P3.6-P3.10) closed `🟢`/`🟠` after the
  write-site canon already existed without ever printing the codes — the gate itself
  held (the audit's own recomputation of the predicate on all five returned
  `allow`/`allow`) but the RECORD was silently absent, and a real `block:*` under a
  `🟢` would have stayed invisible until the next audit, which this phase no longer
  has. The scope anchor is the ITEM's own `Updated` date, not the plan's — a
  plan-dated cutoff would miss this very plan's own future `P4.*` items (D91); items
  closed before the cutoff are never diagnosed at all (forward-only, no existing
  fleet plan is repainted retroactively). `plan-protocol` §8 canon gains one line
  (both languages) naming the machine check; `pre_mutation:`/`pre_final:` are
  registered in `CANON_LITERALS` with matching `i18n-keep` directives (test T2).
- **skiller — system-bank adapter for the P0.3 reliability bank (P3.3,
  `2026.07.24-AGENT-RELIABILITY`).** `skiller.quality.eval` gains a second,
  distinct deterministic grading vocabulary alongside its existing per-skill
  `ASSERTION_TYPES` (which grade one free-text string): eight structured
  transcript/outcome operators (`event_present/absent/order/count_max/
  count_min`, `outcome_field_equals/list_contains/list_excludes`) matching
  `reliability-acceptance-v1.md` § Graders exactly — no LLM judge anywhere in
  this path (D15). `apply_system_operator`/`grade_system_case` grade a case
  against a structured transcript+outcome record; `validate_system_graders`/
  `validate_system_cases` structurally validate ANY `reliability-bank/v1`-
  shaped document, not only the frozen P0.3 one; `compute_system_metrics`
  reimplements (independently of, never importing) the frozen bank's own
  `run_bank.py::compute_metrics` — so this regression surface survives the
  plan's own eventual archival — and is verified **byte-identical** against
  `bank-manifest.json::layer1_metrics` (zero mismatches across ten metrics
  plus `same_finding_loop_depth`) when run against the real 31-case bank.
  `seeded_system_sample` reproduces the same `sha256(seed|case_id)`-ascending,
  baseline-passing selection rule the frozen bank uses — confirmed to
  reproduce `bank-manifest.json::sample.selected` exactly (the same five
  control cases). `provider_capability_matrix` is a deliberately narrow
  presence-only Claude/Codex probe (native only on resolved binary — an
  unconfirmed capability must fail closed, D46, never claim more). `classify_
  portability_tier` cites `task.task_contract.classify_tier` via an optional
  import (mirrors `analyst.doctor`'s existing `task.route_evidence` pattern;
  returns `(None, reason)` rather than guessing when `task` isn't importable).
  `pair_system_metric` mirrors `analyst.metrics.pair_metric`'s discipline
  (candidate `None` → `deferred`, a `pinned-not-recomputable` baseline can
  never ground a comparison) as its own small local implementation, per that
  module's own stated cross-package-boundary rule. `build_system_benchmark`
  orchestrates all of the above into the P3.3 benchmark artifact
  (`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P3.3/benchmark.json` +
  `benchmark-manifest.json`, generated against the real frozen bank,
  candidate-less/`deferred` — no live paired (layer-2) transcript-capturing
  harness exists yet for the bank's multi-round, typed-event cases; that gap
  is named as Pending Work, not fabricated). Two new local test fixtures
  (`packages/skiller/tests/fixtures_data/system-reliability-{bank,graders}-
  v1.json`) exercise all eight operators and every `compute_system_metrics`
  path without touching the frozen plan-owned bank.
- **analyst — reliability metric arithmetic and paired digest (P3.2,
  `2026.07.24-AGENT-RELIABILITY`).** `analyst.metrics` derives paired reliability
  metrics only from committed `analyst.trace.TraceRecord`s and the frozen P0.3
  reliability bank, never by re-parsing provider logs a second way. `build_metric_record`
  emits the numerator/denominator/exclusions/completeness/source-trace-IDs/baseline-proof-
  class shape every metric must carry; `pair_metric` pairs a baseline against a candidate
  (or `None` when the P3.3 live paired run has not produced it yet — reported `deferred`,
  never a silent zero) and fails closed (`METRIC_PINNED_BASELINE_FORBIDDEN`) if the
  baseline's proof class is `pinned-not-recomputable`/`unknown`, so a historical pinned
  quantity (e.g. `journals.classified_lifecycle_events`) can never be silently promoted to
  a recomputed comparator (D30). `slice_by` groups by project/plan/item over a caller-side
  `{project_id, trace}` wrapper — the frozen `TraceRecord` carries no `project_id` field of
  its own, so slicing does not widen that closed schema. `build_digest`/`digest_to_json`
  produce the one compact, byte-stable JSON shape Code Guidance asks for (no dashboard, no
  ranking). `findings/P3.2-metric-reconciliation.md` reconciles this against the committed
  P0 bank: the four already-recomputed layer-1 floors it can re-express today (F1/F7/F13/
  F14) all resolve to `deferred` pairs (no layer-2 candidate exists yet), and F6
  (`trace_completeness`) gets its record shape with `value=None` rather than a fabricated
  pass — no new central `analyst <cmd>` is wired (`cli.py` is outside this item's declared
  `Files`); `doctor.py`/`test_provider_readers.py`/`test_cli.py` were declared in scope but
  left untouched for lack of a concrete requirement against any of them.
- **analyst/harness/task — Unified Agent Trace v1 (P3.1, `2026.07.24-AGENT-RELIABILITY`).**
  New versioned, stdlib-only trace schema
  (`plans/2026.07.24-AGENT-RELIABILITY/root/contracts/unified-agent-trace-v1.md`)
  links a requirement to its contract identity, route, dispatch state, findings and
  public outcome in one closed-field record, distinct from the unrelated D90
  normalized analytics envelope (`analyst.events`/`runs`/`readers`). `analyst.trace`
  is the sole schema owner: `build_trace_record` validates provenance/sha256, fails
  closed on any raw key plausibly carrying chain-of-thought/tool-payload/secret
  content (`TRACE_PRIVACY_VIOLATION`), scores `quality.completeness` over six nullable
  field groups with an explicit `reasons` entry for every missing one, and
  `dedup_records` collapses resumed/forked duplicates by a natural-key `trace_id`
  (provider/project/session identity/turn), keeping the higher-completeness record.
  `harness.provider_trace` supplies thin Claude/Codex readers that map already-
  captured provider structures into the RAW payload the schema owner consumes — no
  Codex hook in this repository captures a comparable structure yet, so every
  Codex-sourced field degrades to `null` + `codex-hook-not-integrated` rather than a
  guessed value. `task.journal` gains one additive optional `trace_ref`/`--trace-ref`
  linkage (outside `REQUIRED_FIELDS`; a call that omits it writes a byte-identical
  entry to before this field existed) so a journal line can point at a trace identity
  without duplicating its metrics. `analyst`/`harness` package-API minor bumps
  (`0.1.0`→`0.2.0`, `0.3.0`→`0.4.0`) are owed but deferred to the next item touching
  those manifests — `package.json` is outside this item's declared `Files`.
- **task/general — pre-final boundary closes fail-closed on both closing paths
  (P2.11 reopen-remediation, `2026.07.24-AGENT-RELIABILITY`, `task@0.9.0`,
  `plan-protocol@2.14.0`, `skiller@0.7.0`).** `task:plan-close`'s pre-final
  checkpoint (step 4) no longer greenlights `n/a`: the gate is now the binary
  `pre_mutation == "allow" and pre_final == "allow"`, with `n/a` reported by
  its own code→action table row spelling out the contract-SSOT semantics
  ("a blocked session has nothing to declare done") — before this fix the
  literal `in ("allow", "n/a")` predicate greenlit every real item, because
  the actual route substituted was the closing command's own pin
  (`implementation/low`), below every item's required route, so
  `pre_mutation` always failed and `pre_final` always reported `n/a` (M1,
  `findings/14`). The `actual_route` on pre-final is now resolved as the
  item's EXECUTOR route (D75) via a fail-closed ladder — Completion Notes
  routing-adherence line, cross-checked against the item's terminal
  `journal.jsonl` entry — instead of the closing command's pin; an
  unresolvable or mismatched route stops with a named PASS rather than
  guessing. `task:plan-exec`'s own step 7 (routine self-close — the path most
  items actually take) gains the SAME executable pre-final call: before this
  fix the boundary was never crossed there at all (M5) — `plan-exec` closes
  the item itself and `plan-close Pn.m` is never invoked on that path.
  `plan-run.md` and `plan-audit.md` are synced to the same binary gate and
  dual-boundary reporting requirement. Both checkpoints now name what
  `pre_final` actually asserts (D77): a property of the item spec's FORM —
  whether at least one publicly checkable acceptance entry rests on a
  deterministic proof class — never that the item was executed well. §13 of
  `plan-protocol` (both languages) is rewritten to state all of this
  truthfully, and the literal test in `test_canon_literals.py` gains a new
  class asserting the DIFFERENTIATING predicate (D79) rather than mere
  identifier presence — every new assertion was verified red against the
  pre-fix command bodies before being added (M6: the pre-existing literal
  test passed green through the `n/a` and missing-step-7-call defects both).
- **task — compiler reads all §3 Routing forms and never crashes
  (P2.10 reopen-remediation, `2026.07.24-AGENT-RELIABILITY`, `task@0.8.0`).**
  `task_contract._find_routing_row` now recognizes a closed literal set of
  route-column headers — the canon `Model class/effort` plus the two legacy
  spellings `Model/effort`/`Model/Effort` `plan-protocol` §9 Back-compat already
  declares valid — instead of the single hardcoded canon header (D78:
  `findings/14` M4/M4.1 measured 11 of 14 root `plans/` failing this call, 9 of
  them with an unhandled `ValueError`). A provider model name in the cell (the
  FOREMAN §3 form, e.g. `opus/high`) is resolved to its frozen class ONLY
  through the committed `command-routing.json::mappings.*.class_selectors`
  carrier (`command_catalog.load_routing_metadata`) — never a second name
  table. Every unparseable/unrecognized/ambiguous form now raises
  `TaskContractBuildError` naming the item, field and offending cell instead of
  fabricating an empty `required` route or crashing; `pre_mutation`'s own
  `_rank` lookup is guarded on both axes and both sides of the route (closing
  D74's `.index(None)` root cause defensively, for any contract reaching `check`
  regardless of producer) and returns the frozen `ROUTE_UNDERSHOOT` code rather
  than raising. New committed probe
  `plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.10/routing_form_coverage.py`
  reproduces the walk over all 14 root plans and exits 1 on any unhandled
  exception (none observed after the fix — 9 `ok`, 5 typed refusals, 0 `EXC`).
- **task/general — Task Contract write-site and truthful canon
  (P2.7 reopen-remediation, `2026.07.24-AGENT-RELIABILITY`, `task@0.7.0`,
  `plan-protocol@2.13.0`, `skiller@0.6.0`).** `task:plan-exec`'s pre-mutation
  checkpoint and `task:plan-close`'s pre-final checkpoint now CALL the P2.6
  compiler — an executable step (build a live Task Contract v1 payload via
  `task_contract.build(..., actual_route=…)`, evaluate it, fail closed on any
  non-`allow` code with a named code→action table) — replacing the F1 prose-only
  cross-reference and the always-false "when a Task Contract JSON happens to be
  mounted" condition. `task:plan-run` substitutes the session's observed route;
  `task:plan-audit` gains a checklist bullet requiring the printed
  `pre_mutation`/`pre_final` result in a closed item's Completion Notes. §13 of
  `plan-protocol` (both languages) is rewritten to state this truthfully and is
  now protected by a literal test in `test_canon_literals.py` that fails if the
  wording diverges from the command bodies. New
  `snippets/source-evidence-template.md` delivers the evidence-bundle Files
  entry P2.2 left undelivered — manifest structure, required fields,
  verification command via `task_contract.bundle_lint` (P2.6), and the
  explicit forbidden-content-class list — cited from, not duplicating,
  `plan-portability-v1.md` §Bundle requirements (also newly cited by the
  canon). Discovered along the way: the CLI form `task_contract build` (no
  `--actual-route` flag) always leaves `route.actual` unresolved by design
  (cross-process determinism) — feeding that straight into `check` crashes
  `pre_mutation`'s `ROUTE_UNDERSHOOT` check with an uncaught `ValueError`
  (`.index(None)`), so the write-site calls the compiler's documented Python
  API (`build`/`evaluate`) instead of a literal `build | check` shell pipe.
- **task — compiler producer, bundle predicate, cross-session cap, actor repair
  (P2.6 reopen-remediation, `2026.07.24-AGENT-RELIABILITY`, `task@0.6.0`).**
  `packages/task/lib/task/task_contract.py` gains `build(plan_dir, item_id, …)`
  — the Task Contract v1 PRODUCER a transaction can actually call before
  `pre_mutation`/`pre_final` existed only as predicates over a hand-authored
  JSON: compiles `phases/Pn.md` + `plan.md` §3 fields into the exact 15-key
  schema, deterministic across repeat calls on the same committed tree, and
  fails closed with a typed `TaskContractBuildError` on an empty item field
  rather than fabricating a placeholder. Full field mapping:
  `plans/2026.07.24-AGENT-RELIABILITY/findings/P2.6-contract-mapping.md`.
  `bundle_lint(bundle_dir, …)` computes minimization and content-class evidence
  (secrets/chain-of-thought/tool-payloads/raw-transcript-bodies, by signature
  scan over actual bundle bytes) instead of trusting a self-declared
  `portability.privacy` block, two new reason codes
  `BUNDLE_ARTIFACT_MISSING`/`BUNDLE_PRIVACY_MISMATCH`.
  `packages/task/lib/task/review_policy.py`'s `LoopBudget` gains
  `from_committed(plan_dir, phase_id, finding)` — reconstructs one finding's
  cross-session occurrence count from `journal.jsonl` + `## Audit Pn` blocks
  instead of always starting a fresh in-process counter at zero (the exact
  defect that let three independent `plan-audit` rounds each see
  `occurrences() == 0` for the same recurring finding). `canonical_actor`
  (`route_evidence.py`) is a breaking signature change: it now carries the
  concrete provider MODEL (`sonnet/high`), never the route-evidence class —
  `model_class` stays a separate `route.actual` axis; `capture_actual` gains
  an optional `model` evidence field; `journal.py --route-evidence` repaired
  to match (a historical evidence blob lacking `model` renders `unknown/…`,
  never crashes).
- **task — route/budget evidence (P2.4, `2026.07.24-AGENT-RELIABILITY`).** New
  `packages/task/lib/task/route_evidence.py`: normalized `required`/`actual` route
  capture with a named source (`self-attested`/`provider-doctor`/`cli-flag`) and
  timestamp — never inferred from static config, an actor string or the requested
  model. `classify` gives the four-way `exact/over/under/unknown` label (one axis
  never compensates the other — an unresolved model class outweighs a generous
  effort); `dispatch_guard` is the fail-closed boundary strictly upstream of
  `task_contract.pre_mutation` (P2.2) — it reuses the two frozen P0.2 `route` deny
  codes verbatim (`ROUTE_UNDERSHOOT` also for an `unknown` axis, `CAPABILITY_UNSUPPORTED`)
  and is what prevents that predicate's `.index()` lookup from ever seeing a `None`.
  `build_task_contract_route` assembles the exact `task-contract-v1.schema.json`
  `$defs/route` shape once the guard already allowed. Also: `capture_budget`
  (token/duration/tool-call evidence only, no pricing — axis names match
  `analyst.readers` `usage.totals`), `route_change_boundary`, and
  `canonical_actor` — the one `<model_class>/<effort>` journal actor spelling
  (`findings/02-telemetry-2026-07-20-24.md` — 34 observed spellings). `task.journal
  append` gains `--route-evidence PATH` (mutually exclusive with `--actor`) to derive
  the actor from a captured evidence file instead of hand-typing it. `harness doctor`
  and `analyst doctor` each gain one informational/optional line naming where route
  evidence can come from (`analyst doctor`'s is the existing `task.route_evidence`
  importability pattern already used for `maind`).
- **task — typed finding/review enforcement and loop breaker (P2.3,
  `2026.07.24-AGENT-RELIABILITY`).** New `packages/task/lib/task/review_policy.py`
  implements `risk-review-loop-budget-v1.md` as executable policy: seam-derived
  `finding_id` (file/rule-locus/defect-class, split-ban — cosmetic re-wording never
  resets the loop-budget cap), the `reopens_product` predicate (product-typed, security
  blocker, or evidence invalidating acceptance), and `same_finding_max = 2` — the third
  occurrence of one stable identity becomes an `INCIDENT` with no inline repair, its cap
  subject parameterized by authority profile (`owner-gated` → owner, `self-host` → agent,
  never hardcoded). `task_contract.py` (P2.2) gains one lazy-imported hook,
  `evaluate_finding`, so the independently-green compiler's own tests never need the new
  module importable. Task plugin/routing bumps `0.4.0` → `0.5.0`; full adapter/lock/golden
  regeneration proven no-op on the second check.
- **task — Task Contract v1 compiler and tiered-portability lint (P2.2,
  `2026.07.24-AGENT-RELIABILITY`).** New `packages/task/lib/task/task_contract.py`: the
  single checked seam owning content-hash recomputation, the precedence/conflict-resolution
  ladder, the twelve pre-mutation and three pre-final reason codes of
  `task-contract-v1.md`, plus the portability tier classification/lint layer of
  `plan-portability-v1.md` (`PORTABILITY_TIER_MISCLASSIFIED`). Canonical plan commands
  (`plan-design`/`plan-exec`/`plan-close`/`plan-audit`) now cite this compiler at their
  pre-mutation/pre-final checkpoints instead of restating the predicate in prose.
  `plan_lint.py` gained a tiered-portability check (role-based — never a `tmp/` substring
  match, D47) that rejects a committed-bundle-tier plan without a committed execution input
  or with an external (host/chat/mAInd/tmp/foreign) one; severity is ERROR only for plans
  dated `2026.07.27` or later (back-compat, existing fleet plans stay WARNING). Versions:
  `plan-protocol@2.12.0`, skiller package API + `general`/`core` publication units to
  `0.5.0`, task plugin/routing to `0.4.0`.
- **skiller — effective-runtime conformance gate (P1.4, D51/D62/D63).** New
  `skiller doctor --effective-runtime`: cold per-provider install/discover of the declared
  positive fixture (every repository-marketplace unit minus exactly the three donor buckets
  `general`/`research`/`oss-dev`) into a `tempfile.TemporaryDirectory`, proving catalog-wide
  identity uniqueness (216 Codex / 204 Claude identities, 0 collisions, 0 undeclared root
  directories) rather than checking a named ID list. A companion negative fixture proves the
  nine `core`↔donor D42 pairs and the class-B `workflow-craft` precondition still fail
  closed when their donor bucket is enabled. `--fixture-out`/`--carrier-out` persist the
  declared fixture (`fixture-unit-set.json`) and the measured identity→carriers map
  (`effective-carrier-set.json`), the latter reconciling every one of the 29 frozen
  collision records from P1.1's `remediation-map.json` as `resolved` or `still-measured`
  (0 `unowned-or-unexplained`).
- **skiller — root-bootstrap class-B publication and collision closure (P1.5, D40/D42/D43).**
  Four duplicate `architect` root identities (`architecture`, `codebase-design`,
  `domain-modeling`, `package-contribution-protocol`) removed from `.agents/skills/` after
  per-identity ownership proof against the installed `architect` bucket unit. `workflow-craft`
  (public-bucket canon whose unit is not enabled) gets a generated thin Codex-only root
  projection with provenance/hash under a new class-B extension to the root-bootstrap
  renderer — declared asymmetry, no copied body, no Claude projection. `repository-bootstrap`
  publication unit bumps `0.1.0` → `0.2.0` (`skiller` package API `0.4.1` → `0.4.2`); the 13
  class-A canonical sources, their 26 projections and lock bytes stay byte-identical (a new
  D38-frozen `class_a_content_version` decouples the class-A embedded stamp from the umbrella
  unit version). The generator and `skiller registry --check` now assert each provider's root
  skills directory equals exactly the declared target set (undeclared directory → hard
  failure). `skiller doctor --provider-distribution` gains a read-only D42 diagnostic naming
  every identity the curated `core` unit shares with a donor bucket (`general`/`research`/
  `oss-dev`) under the worst-case declared set — never a live-profile read, never a repair.
- **plan — agent reliability and SSOT recovery.** Добавлен исполнимый план
  `2026.07.24-AGENT-RELIABILITY`: полевая root-cause модель по четырём проектам,
  единый task contract, runtime-dedup skills/hooks, bounded review loop,
  unified traces, behavioral evals и self-host canary до fleet-гейта.
- **harness/core — dual-provider environment and instruction projections.** Provider-neutral
  profile, security, hook, MCP, agent and instruction catalogs now render independent native
  Claude/Codex artifacts. Artifact contract v1.1.0 preserves generic semantic metadata in the
  authoritative lock while exact v1.0.0 callers and records remain supported.
- **task — dual-provider command surface.** Immutable semantic command catalog,
  generated Codex adapters, byte-compatible Claude projection, fail-closed neutral
  routing and exhaustive parity/operator reference for the full task inventory.
- **skiller — `plan-protocol` 2.11.0.** Semantic `Next`, model class/effort/capability
  gates and provider-rendered Claude/Codex invocations are now provider-neutral.
- **skiller:** provider-aware Claude/Codex distribution preflight, provider-qualified
  vendor locks and explicit `skiller codex-install`; normal connect/update/doctor and
  dry-runs never invoke the native user-global installer.
- **task/harness — root task-adapter dedup (P1.3, D28/D40).** `task` publication bumps to
  `0.3.1`: regenerated Codex adapter tree (24 artifacts), `provider-artifacts.lock.json` and
  `publication-lock.json` via a new stdlib CLI front
  (`packages/task/scripts/render-provider-commands.py --write --repair-owned` /
  `--check`) wrapping the existing `command_render.py` planning/apply API — no new
  translation logic. Six duplicate root task identities
  (`task-design`, `task-plan-{audit,close,design,exec,run}`) removed from `.agents/skills/`
  after proving the generated `task@0.3.1` bundle covers them. `harness` package bumps to
  `0.3.0` (plugin `0.2.0`) alongside. `AGENTS.md` now describes `.agents/skills/*` as
  generator-owned bootstrap-only projections for identities not served by an authoritative
  installed bundle, sourced from the private `repository-bootstrap` bucket.
- **skiller — root-bootstrap class-A publication (P1.2, D31/D38).** 13 private/source-only
  bilingual canonical skills (`skills/repository-bootstrap/<id>/{SKILL.ru.md,SKILL.md}`)
  replace the 13 hand-maintained duplicate root copies with 26 thin generated
  `.claude/skills/<id>/`+`.agents/skills/<id>/` projections (trigger metadata + canonical
  path/hash, no copied body) plus one combined `publication-lock.json`. `registry.py` →
  `publication.py` is the sole producer; `build_publication_catalog` excludes the private
  bucket from every ordinary Claude/Codex/marketplace unit and `skillset.py` rejects it from
  vendor/connect selection outright. `configs/publication-versions.json` (D27) now separates
  the skiller package API SemVer from finite per-unit manifest versions — `core`/`skm` bump to
  `0.4.1` alongside the package API, every other unit stays byte-identical at the frozen
  `0.4.0` baseline. Six duplicate root `core` identities
  (`anti-drift`/`context-economy`/`plan-protocol`/`query-craft`/`session-handoff`/`verify-claims`)
  removed from `.agents/skills/` after proving the generated `core@0.4.1` bundle covers them.

### Fixed

- **harness/maind — self-host Codex hook lifecycle: unmanaged target и пропавший
  handler.** `.codex/hooks.json` нёс только рукописный memory-хук вне артефакт-лока
  (`harness hooks --provider codex --observer` рефьюзил как `ownership-conflict`), а
  наблюдатель `context.observer` не был зарегистрирован вовсе — `harness doctor`
  сообщал `missing → create`. Композиция через уже существующий D104
  bootstrap-transfer (`maind.provider_deploy.plan_d104_bootstrap_transfer`) сохранила
  memory-хук байт-в-байт и добавила наблюдателя вторым `SessionStart`-хуком +
  `.codex/hooks/lifecycle.py`; `.swissknifeman/provider-artifacts.lock.json`
  теперь владеет обоими. `run-report/_lib.py` в `~/.claude/hooks/` синхронизирован
  повторным `harness hooks --global` (протух после последнего апдейта).
- **harness — protracted stale path после архивации `2026.07.19-DUAL-PROVIDER`.**
  `instructions.py:contract_path()` и один тестовый фикстур несли путь до
  архивации плана (`5b79f926`), из-за чего `test_provider_instructions.py`,
  `test_instruction_compatibility.py` и `packages/harness/scripts/validate.sh`
  падали целиком независимо от текущей задачи. Путь синхронизирован на
  `plans/archive/2026.07.19-DUAL-PROVIDER/...`.
- **harness — `agent-packs upgrade` сверяет факт файлов, а не только версию пака.**
  План апгрейда строится из хэшей (источник и диск против `base_sha256` лока), поэтому
  забытый бамп `pack.json:version` больше не даёт тихого «уже актуален» (изменение
  доезжает + warn автору пака), а пропавший target восстанавливается и при равной версии.
  Совпадающее состояние печатается как «нечего делать»; локальные правки по-прежнему не
  затираются (`conflict` → `*.pack-new`). `agent-packs doctor` дополнительно предупреждает
  о targets, на которые претендуют 2+ установленных пака (корень тихой потери файлов при
  `remove` соседа), и отдаёт их в `--json` полем `shared_targets`.
- **skiller — единый Codex carrier при update.** Если внешний проект уже получает
  self-contained Codex marketplace под `.agents/plugins/`, `skiller update`
  обновляет независимый Claude vendor-канал, но больше не дублирует те же
  скиллы и lock-записи в `.agents/skills/`.
- **skiller — идемпотентный vendor sync.** Неизменившийся skill manifest сохраняет
  исходный `installed_at`, поэтому повторный dual-provider `sync` больше не меняет
  snapshot при переходе между секундами.
- **maind — текущая схема Serena.** Генератор `.serena/project.yml` использует
  канонический ключ `language_servers`; мультиязычные и пустые конфигурации больше
  не создают legacy `languages`, который Serena мигрировала при активации.
- **skiller — внешний Codex connect bundle.** Repo-contained bundles выбранных
  plugins теперь включают runtime-файлы скиллов с consumer exclusions; native
  install/cache/enable остаются отдельным явным действием.
- **core/harness/maind — clean-runner compatibility.** D108 tests now use a committed sealed
  MCP preimage instead of a gitignored local file; harness agent-pack and maind provider-config
  projections import on Python 3.9, and the provider rollback/deploy paths pass the Ruff gate.
- **core/harness/maind — provider project sync.** Managed provider-artifact locks now
  retain records owned by other packages; Codex observer deployment, agent templates and
  provider MCP projection preserve independent managed surfaces during check/apply/repair.
- **task/skiller — Codex plugin activation.** The native marketplace now publishes
  package-owned Codex siblings with a Codex-compatible local source shape; `task` 0.3.0
  includes its generated `task-plan-*` skills, versioned provenance and cold-session coverage.
- **skiller:** dual-provider `sync` now rejects an unmanaged selected-provider target
  before any provider skill copy, lock write or project registration; `--force` remains
  the explicit overwrite path.

### Added

- **task — historical journal exception v1.** Owner-gated append-only sidecar for one exact
  historical `friction` schema error; strict writer/linter validation and negative tests.
- **skiller — `plan-protocol` 2.9.0 → 2.10.0.** Documents the sealed D51 exception lifecycle.

### Added (2026.07.18-FOREMAN P1.4 — plan-protocol 2.9.0)

- **skiller — `plan-protocol` 2.8.0 → 2.9.0.** Scope-payload launch-block'а для `RED`/`ATTENTION`
  аудитов (`РЕЖИМ:`/`ВХОД:`/`СКОУП:`/`НЕ ТРОГАТЬ:`), литерал `Вердикт:`; журнал
  `journal.jsonl` и опциональный `index.md` в раскладке плана; snippets
  `journal-template.md`, `index-template.md`.
- **skiller — `check-translations.sh`.** Двусторонний гейт `i18n-keep`: литерал обязан быть
  употреблён в теле `SKILL.ru.md`, не только в директиве.
- **task — `plan_lint.py` + `plan-audit.md`.** Гейты scope-payload в блоках `## Audit Pn`,
  валидация `journal.jsonl` (ERROR от 2026.07.18) и `index.md` (WARNING); unittest'ы.
- **docs — `reference.md`.** Карточки gstack, last30days-skill, llm-council, codex-plugin-cc;
  roadmap `codex-subagent-offload.md`, `plan-design-vs-exec-status-check.md`.

### Added (2026.07.13-PLAN-PROTOCOL-GAP — кластер protocol-gap plan-протокола)

- **task — скилл `plan-protocol` 2.4.0 → 2.7.0.** Итог кластера (F7/m7/m8/A5/B1, эскалация REGHUB):
  **2.4.0** — routing-гейт (§9 колонка `Exec`: `plan-exec`/`manual`/`plan-design`, деривация по
  тир-порядку model/effort), status-rule §6 (material vs process-отклонения, 6-й триггер —
  посторонний дифф в item-коммите), enum форм `Next` + порядок закрытия §8 (дифф → validate →
  bookkeeping → handoff → `plan-lint` → атрибутированный счёт → коммит), секция Contracts §7/§11
  (Exported/Consumed, cross-plan notification), носитель развилок `## Обсуждение` §3. **2.5.0** —
  гейт непереводимых литералов (`CANON_LITERALS`) + обязательный якорь дерева для чисел в
  Completion Notes/Validation/Update Log. **2.6.0** — канон-текст команд `plan-{exec,close,audit,
  design,run}` (§13). **2.7.0** (реопен-волна) — предикат «Phase Handoff протух» проверяется по
  ПЕРВОЙ строке + отрицанием (не substring), единственный носитель статуса фазы — Status Board
  (не Phase Handoff), гейты линтера исполнимы на своих артефактах + расширенный сборщик корней,
  числа по ЧУЖИМ корням `plans/` — только дельтой парного прогона на одном снимке, форма `Next`
  первой строкой + существование фазы `after Pn.m` в handoff. **2.8.0** — «мягкий пункт
  Validation» (soft-пометка ТЗ, снимающая красный пункт без эскалации) запрещён явно: красный
  пункт Validation ВСЕГДА material (§6) либо эскалация владельцу за новым D# (§10); OQ-1 плана
  закрыт D58.
- **task — `plan_lint.py`.** Синхронный со скиллом: enum форм `Next`, `--baseline`/`--gate`,
  сверка секции Contracts, регресс по 30 живым планам в 10 корнях `plans/` — 0 новых ERROR.
- **skiller — смена дефолта auto-approve `strict` → `bypass`** в бандлах `recommended`/`full`
  (решение владельца, `365079c`).

## [0.9.0] - 2026-07-12

### Added (2026.07.12-CONTEXT-ECONOMY — тощий старт сессии + footprint-доктор + bootstrap + доктрина)

- **maind — digest-бюджет project-only + байт-кап (P1.1).** `select_digest_items`: байт-бюджет на
  дайджест памяти + `shared_max=0` по умолчанию (D10 supersede D5) — межпроектные (`ns:*`) факты в
  дайджест не попадают без явного запроса; `--shared-max`/config-флаги для точечного включения.
- **maind — тихий health-хук + digest-шаблон v2 (P1.2).** `session-start-hook.sh` больше не печатает
  ничего при OK (только `--strict` даёт rc-гейт); `memory-digest-hook.sh` — компактный шаблон v2.
- **maind — гайдлайн межпроектной памяти (P1.3).** `ecosystem-mcp` + доки `guide/{memory,namespaces}.md`:
  межпроектная задача → `graph` → `recall --scope ns:<имя>` → `remember --scope ns:<имя>`, дайджест —
  только project-only (D10).
- **harness — agent-router policy v2 (P2.1).** Policy-конфиг сжат до терс-EN ≤400 ток (было RU ≈600–900
  ток каждую сессию), семантика (6 инвариантов роутинга) сохранена полностью.
- **skiller — диета описаний скиллов + desc-гейт (P3.1/P3.2).** 24 самых длинных описания сокращены;
  новый жёсткий гейт `validate.sh` (`DESC_WARN_MAX=300`/`DESC_ERROR_MAX=450`) + burn-down-рэтчет
  (`scripts/desc-burndown.txt`, one-way, протухшая запись — warn) для оставшихся скиллов.
- **harness — диета agent-packs (P4.1/P4.2).** Описания субагентов всех 10 паков сжаты (1 пример вместо
  2–3 + одна анти-триггер-фраза), regression cap-тест на реальном реестре + `.bak`-warn в `agent-packs
  doctor`.
- **skiller — `budget --first-turn` (P5.1).** Замер always-on футпринта проекта первого хода: skills
  tier-0, agents, CLAUDE.md/rules без paths, живой fail-soft прогон SessionStart-хуков, MCP tool-defs;
  вердикт OK/ELEVATED/WARN (пороги 7K/10K), `--json`/`--strict`.
- **maind — `doctor --context` (P5.2).** Флот-агрегация `_fleet_context`: subprocess `skiller budget
  --first-turn --json` по всем `_enabled_projects`, fail-soft `n/a` при недоступности.
- **analyst — сессионная токен-аналитика (P5.3).** `core/usage.py` — `first_turn_overhead` (первая
  assistant-запись, главный транскрипт); run-report `usage.first_turn_overhead`/`usage.turns`; новая
  команда `analyst sessions [--project ID] [--weeks N] [--json]` — недельные ISO-медианы из живых
  transcript-jsonl с trend-warn (week-over-week >20%, только календарно смежные недели).
- **root — bootstrap-machine.sh (P7.1/P7.2).** Идемпотентный скрипт развёртывания новой машины/команды
  (`swissknifeman setup --machine`): install → hooks/permissions --global → MCP soft-skip → maind
  service install → doctor, плюс манифест-шаг `--projects FILE` (клонирует только отсутствующие
  проекты, не трогает существующие); `docs/deploy.md` + `docs/machine-manifest.example.json`.
- **root — доктрина budget-гейта (P8.1).** root CLAUDE.md «Рамки»: любой новый always-on инжект (hook
  additionalContext/description скилла-агента-команды/CLAUDE.md-блок/MCP-сервер) до раскатки проходит
  `skiller budget --first-turn` и вписывается в бюджет (target 3–7K, warn 10K); компактная запись в
  память mAInd (`ns:axioma`).
- **Локальные скиллы/доки синхронизированы с релизом (P8.2).** `package-architecture`/
  `project-tooling-runbook`/шаблон `ecosystem-setup` (maind) + CLI-доки `analyst`/`maind`/`skiller`
  дополнены новыми командами (`budget --first-turn`, `doctor --context`, `analyst sessions`,
  bootstrap-machine); устаревшая формулировка «дайджест топ-8» (без `project-only`-оговорки) в
  `docs/develop.md` исправлена.

### Changed

- **P5.4 (OTEL-пресет) — ⛔ Skipped by decision (D7).** Без работающего внешнего коллектора — мёртвый
  код; спека сохранена в `roadmap/otel-preset.md`. Новый каталог `docs/rejected-optimizations.md` —
  осознанно отклонённые идеи (не «отложено», как `roadmap/`).


### Added (maind — fleet-измерение settings)

- **`maind doctor --audit settings|all`**: измерение `settings` в fleet-аудите — subprocess к
  `harness doctor --settings --target <path> --json` по каждому зарегистрированному проекту
  (D10, maind не импортирует harness). Fail-soft как `--channel-drift`: harness недоступен/упал/
  отдал не-JSON → `settings·n/a`, код возврата аудита не меняется. Печать: `settings✓` (ноль
  error/warn) · `settings⚠(err:N warn:M)` · `settings·n/a`. `--json` кладёт `{"error","warn","info"}`
  или строку `"unavailable"` в строку проекта.

### Внедрено (settings-doctor — SKM-ROADMAP-005 P1 закрыт)

- Конфликт-линтер настроек Claude Code (`roadmap/settings-doctor.md`) полностью внедрён:
  таксономия 13 проверок, 2 policy-профиля, CLI `harness doctor --settings` + фасад
  `skiller doctor --settings` + fleet `maind doctor --audit settings`. Полевой кейс 2026-07-10
  ловится целиком (интеграционный тест P1.5); реальный прогон по флоту (21 проект) подтвердил.

### Added (harness — settings-doctor CLI + фасад skiller)

- **`harness doctor --settings [--target P] [--json] [--profile NAME]`**: вывод движка
  settings-doctor в CLI. Отдельная от диагностики окружения ветка (ранний return): читает
  слои настроек Claude Code целевого проекта, репортит таксономию проверок человекочитаемым
  отчётом либо единым JSON-документом. exit-code `0` (чисто/только info) / `1` (warn) / `2`
  (error); `--json` кода не меняет и печатает РОВНО один документ в stdout (контракт для
  fleet-скана). Аудит read-only — ничего не пишет на диск.
- **`skiller doctor --settings [--target P]`**: фасад того же аудита из реестра скиллов —
  делегирует в `harness doctor --settings` через subprocess (без логики проверок), прокидывает
  код возврата; harness не установлен → warn и graceful skip (rc 0).

### Added (skiller — ecosystem-reuse-gate + бакет axioma)

- **`architect/ecosystem-reuse-gate`**: гейт против переизобретения функционала — перед
  проектированием нового проекта/фичи обязательна сверка с реестром экосистемы и прогон
  vendor-vs-build правил (дефолт — переиспользование). `tech-stack-selection` и `founder/new-project`
  получили `requires: [ecosystem-reuse-gate]` и шаг вызова гейта в алгоритме (Step 1 / Step 0
  Idea-gate).
- **Бакет `axioma`**: `axioma-doctrine` (пять столпов-императивов экосистемы Axioma) +
  `axioma-stack` (привязка reuse-gate к живому `Ecosystem_Tech_Radar.md`) — читать при
  проектировании любого нового проекта/пакета Axioma до архитектурных решений.

### Fixed (maind — `derive`/`probe` падали на list-формате `skills-lock.json`)

- `derive.derive_skills`/`probe.probe_project` предполагали `skills-lock.json::skills` только
  как `dict {name: entry}` (формат `skiller sync`) и падали `AttributeError` на альтернативном
  формате — списке (напр. собственный lock-генератор Brain-валта). Пойман при первом онбординге
  проекта с таким lock-файлом в mAInd (`maind onboard`/`maind sync --only graph` рушились,
  `maind health --project <id>` тоже). Нормализация списка в dict перед итерацией; тест на оба
  формата в `test_derive.py`.

### Added (maind@0.x — провиженер Laravel PAO + fleet-гейт)

- **`maind pao`**: новый провиженер (`lib/maind/pao.py`, детект по файловым фактам + `php -v`),
  подключён шагом `pao` в онбординге PHP/Laravel-проектов (`provision/onboard.py`). Интерактивно
  предлагает `composer require laravel/pao --dev`; на `--yes`/неинтерактиве — громкий warn, не
  молчаливая установка; opt-out `project.pao_opt_out`. `onboarding-decision-tree.md` получил
  секцию «PHP-инструменты: PAO».
- **`maind doctor --audit pao|all`**: новое измерение fleet-audit, переиспользует `pao.status()`
  (детект-логика не задублирована). Печатает `pao⚠(missing: composer require laravel/pao --dev)`
  для php/laravel-проекта без PAO, `pao✓`/`pao·<state>` для installed/n-a/opt-out/php-too-old.
  Закрывает дыру контракта «доставка скилла ≠ установка зависимости»: онбординг Agelto прошёл
  GREEN без реально установленного `laravel/pao`.

### Fixed (harness — perplexity-web больше не промптит permission)

- **`settings.global.json`**: два независимых класса пермишен-промптов устранены одним изменением
  — allow `mcp__plugin_core_perplexity-web` (плагинный `core` дублирует `perplexity-web` под другим
  именем) + top-level `enabledMcpjsonServers: ["perplexity-web"]` (project-scoped `.mcp.json`-сервер
  вечно `Pending approval`). Семантика верифицирована context7. `apply-permissions.sh` получил
  union-merge для `enabledMcpjsonServers` + тест. Репро на 4 проектах (botkit/flexcrm/agelto/
  dterema-app): `⏸ Pending` → `✓ Connected`.

### Fixed (skiller — SKILL_MANAGED_MARKER byte round-trip, registry idempotence)

- **`SKILL_MANAGED_MARKER`/`_mark_skill_managed`/`strip_skill_managed_marker`** реализованы в
  `lib/skiller/common.py` (байт-режим, BOM-safe, идемпотентно) — импорт падал (`ImportError`),
  `skiller registry` не был идемпотентен (`git status` оставался грязным после повторного прогона).
- **PAO skill**: опечатка пакета в тексте (`nunomaduro/pao` → `laravel/pao`, внешне верифицировано)
  в `SKILL.ru.md`/`SKILL.md`, `skills.json` перегенерирован.

### Fixed (analyst — Laravel-раннеры и guard-паттерны в сигнале A)

- `_RUNNER_EXEC` (`lib/analyst/digest.py`) научился резолвить `php artisan test`/`sail test`
  (Sail-shortcut); убран бланкетный отказ по `||` + добавлена ветка `xargs` — разведочные команды
  без реального прогона теста/линта больше не засчитываются как «сигнал A».

### Fixed (maind — `norm_path` резолвит симлинки при дедупе проектов)

- `provision/workspace.py`: `norm_path` переведён на `os.path.realpath` — повторный онбординг
  проекта через симлинк больше не создавал дублирующую запись в `projects.json`.

### Changed (docs — пакет `task` в корневом CLAUDE.md, CORE_SKILLS 8→9)

- Корневой `CLAUDE.md`: строка `task` в таблице «Пакеты» + раскладка + пояснение в CLI-блоке,
  почему `task` не роутится через `swissknifeman` (plugin-only, без `bin/`); новый
  `packages/task/CLAUDE.md`. `install.sh` — комментарий, поясняющий исключение `task` из установки.
- `packages/skiller/CLAUDE.md`: `plan-protocol` девятым в `CORE_SKILLS` (резидент 705/750 ток,
  в рамках `RESIDENT_BUDGET_TARGET`); устаревшая фраза «резидент превышает target» поправлена.

### Changed (harness@0.5.0 — Lean-tiering агент-паков + whole-server MCP allow)

- **agent-packs `python-backend`/`node-frontend`/`dart-flutter` → Lean-tiered (0.4.1 → 0.5.0).**
  `workflows/dev-loop.js` этих трёх паков наследовали модель и жгли `effort:'high'` на КАЖДОМ
  `agent()`; теперь — паритет с `backend-laravel`/`laravel-package`: helper-лейны `implLane`
  (impl `LOW→haiku` иначе `sonnet`) и `reviewLane` (`LOW→sonnet/medium · MED→opus/high ·
  HIGH→opus/xhigh`), setup/type-check/verify → `sonnet`; `SLICE_RESULT_SCHEMA` обогащена
  `risk_level`/`risk_markers`/`workarounds`/`tool_failures` (risk-адаптивный review-gate по
  оценке test-writer); durable-light handover прошлых срезов. `pack.json` MODEL_* дефолты
  `inherit` → tiered (reviewer/ffi-reviewer `opus`, builder/test/spec `sonnet`).
  Мотив (RAG-подтверждён): per-stage model tiering — дешёвые исполняют, дорогая проектирует/
  арбитрирует (Anthropic orchestrator-worker + advisor pattern). Наследование родительской
  модели фан-аутом = весь флот на топ-модели (инцидент Flex: 93% недельной квоты за день).
- **`settings.global.json`: whole-server auto-approve `mcp__perplexity-web` + `mcp__playwright`.**
  Bare-server форма покрывает все текущие+будущие инструменты (incl. `perplexity-web login`,
  недостающие playwright-tools). Раскатывается `harness permissions --global` в `~/.claude/
  settings.json` → перестаёт переспрашивать во ВСЕХ проектах (раньше — россыпь per-tool записей,
  промпт на каждый новый инструмент). Грамматика подтверждена доками Claude Code.

### Added (harness@0.5.0 / skiller — доктрины токен-экономики мультиагентных workflow)

- Раннбуки паков `docs/subagents-and-workflows.md` (все 5) + скилл `general/context-economy`
  §8: **no-polling** (не поллить фоновые агенты — уведомление приходит само, `ScheduleWakeup`/
  циклы опроса жгут кэш), **resume-стабильность** (детерминированные промпты + model/effort-
  override отдельным параметром → `resumeFromRunId` отдаёт стадии из кэша), **budget-log**
  (`budget.remaining()` после волны в больших фан-аутах). Три доктрины отсутствовали дословно;
  RAG-валидны (Anthropic context-engineering: progressive disclosure/compaction).

### Added (harness@0.x — safe-dirs: path-scoped разрешение rm/rmdir в auto-approve)

- **safe-dirs**: `rm`/`rmdir` с целями строго внутри доверенных директорий проходят мимо
  `deny_hard` auto-approve-хука (раньше — безусловный deny). Allowlist **machine-owned**,
  живёт **в корне монорепо** — `safe-dirs.json` (gitignored; шаблон `safe-dirs.example.json` —
  паттерн `config.json` узла maind), лестница поиска хуком: `$SKM_SAFE_DIRS_CONFIG`
  (эксклюзивный override) → корень монорепо (realpath PATH-лаунчера swissknifeman/skiller/
  harness/maind, маркер `.claude-plugin/marketplace.json`) → legacy `~/.swissknifeman/
  safe-dirs.json` (`init` мигрирует его в репо, home остаётся памяти/реестру). Формат:
  `dirs[]` + авто-включение онбордженных проектов из `projects.json` + `exclude[]`;
  project-override `.claude/auto-approve.config.json` на allowlist НЕ влияет (враждебный
  репозиторий не может разрешить себе rm). Вердикт —
  новый `hooks/auto-approve/lib/safedirs.py` (stdlib-only, fail-closed): argv через shlex
  (не regex по строке), realpath против symlink-escape и `..`, containment по компонентам,
  cd-трекинг для относительных путей, глобы по статическому префиксу (`allow_globs`),
  защита `.git` (`protect_git`) и самого корня safe-dir; `$VAR`/`$( )`/backticks/`xargs rm`/
  неизвестные флаги/многострочность → deny как раньше. Обработчик ЦЕНТРАЛЬНЫЙ: один файл
  в `~/.claude/hooks/auto-approve/` (ставит `harness hooks --global`), проекты лишь ссылаются.
- **CLI `harness safe-dirs`** (`lib/harness/safedirs.py` + slash `/harness:safe-dirs`):
  `init` (создаёт в корне монорепо; legacy из home мигрирует автоматически, старый файл →
  `*.migrated`) / `list` (эффективный allowlist глазами хука — importlib того же ядра, без
  второй реализации) / `add|remove [--exclude]` (гарды: `/`, `$HOME`, предки `$HOME` — отказ) /
  `prune-ask [--global] [--target P] [--all-projects]` — снятие статических ask-правил rm
  из settings уже применённых проектов (merge-only их сам не удалит). Новый хелпер
  `settings.remove_permission_rules` (точные совпадения, «снимаем своё»).
- Тесты: +34 (`test_safedirs.py` — юнит ядра: symlink escape, `..`, глобы, `--`, `.git`,
  exclude, cd-ветвления; сценарные через реальный `auto-approve.sh` с tmp-$HOME, включая
  иммунитет к враждебному project-override; `test_safedirs_cli.py` — CLI+prune-ask).

### Changed (harness@0.x — пресеты: rm управляется хуком, не ask-правилами)

- Из `settings.base.json`/`settings.global.json` убраны `ask: Bash(rm -r *)`, `Bash(rm -rf *)`:
  hook-`allow` НЕ пробивает статический ask (официальная семантика permissions — deny > ask >
  allow между слоями), т.е. с ними rm в safe-dirs всё равно промптил бы. Вне safe-dirs rm
  по-прежнему жёстко блокирует deny_hard — защита не ослабла. Заодно убран мёртвый
  `allow: Bash(rmdir *)` из global (его всегда перекрывал deny_hard). Для уже применённых
  проектов правила сами не уйдут (merge-only) — снять: `harness safe-dirs prune-ask
  --global --all-projects`.

### Added (skiller@0.x — профиль platform-service · скилл voice-ai · пресеты polyglot · гайд polyglot-monorepo)

- **Профиль `platform-service`** (`packages/skiller/profiles/platform-service.json`): externalized
  runtime platform, полиглот-монорепо (`services/` + `packages/js|php|flutter/` + `apps/` + `infra/`) —
  10 бакетов (architect/ai/oss-dev/general/php/php-packages/frontend/frontend-vue/frontend-backend/devops),
  `harness_presets:[base]`, `mcp:[context7]`. `agent_pack`/`model_tiers` осознанно не заданы (нет
  подходящего generic-пака; аналоги тоже их не задают).
- **Новый скилл `voice-ai`** (`skills/voice-ai/voice-ai/`, бакет `voice-ai`): voice-агенты
  (WebRTC media + WebSocket control, 3-слойный turn-detection VAD+семантика+LLM, barge-in <500ms,
  латентность <800ms — 1200ms явно помечена LEGACY/IVR, session state-machine, RU-стек Yandex
  SpeechKit/SaluteSpeech/YandexGPT/GigaChat + offline-алternativы, ремарка 152-ФЗ). Двуязычный
  (`SKILL.ru.md` источник → `SKILL.md` EN-канон), `upstream.json` strategy=notify (референс
  спек/паттернов, без вендоринга кода). Реестр перегенерирован: **208 скиллов**, 53 плагина.
- **4 полиглот-пресета** (`packages/skiller/presets/polyglot-{node-php-flutter,node-php,node-go,
  python-node}.json`) — только из существующих бакетов (buckets.json), без ссылок на
  несуществующие node/go/flutter-бакеты.
- **Гайд `docs/guide/polyglot-monorepo.md`** (skiller docs): монорепо vs отдельные репо,
  структура `services/+packages/js|php|flutter/+apps/+infra/`, dependency direction, contracts-as-SSOT
  + codegen, per-package vs unified semver, отдельные lockfiles, CI multi-lang.

### Changed (skiller@0.x — presets[] в `.swissknife.json` теперь резолвятся в connect-канале, БЫЛО no-op)

- **Поведенческое изменение контракта `.swissknife.json`:** ключ `presets[]` раньше был
  зарезервирован, но **игнорировался** (`_RESERVED`, no-op). Теперь connect-канал разворачивает
  пресеты в бакеты по формуле `buckets = (resolve_presets(presets) ∪ buckets) − exclude` —
  симметрично тому, как `presets` уже работали в vendor-канале (`skillset.resolve_presets`,
  extends/cycle-detection переиспользованы, не задублированы). **Проекты, у которых в
  `.swissknife.json` уже лежал `presets[]` (ранее молча игнорировался), при следующем `skiller
  connect` получат соответствующие бакеты** — до применения стоит свериться с текущим набором
  бакетов проекта. Precedence сохранена: явные CLI-флаги > `.swissknife.json` (buckets/presets) >
  autodetect по профилю. Неизвестный пресет → warn+skip (не die); skill-only пресет в
  bucket-канале → warn+no-op (пресеты работают на уровне бакетов, не отдельных скиллов). 13 новых
  тестов (`tests/test_presets.py`).

### Changed (schema — `memory_brain` теперь принимает объект с `sync{direction,patterns}`)

- **`memory_brain` в `.swissknife.json`** расширен с чистой строки (path) до `oneOf[string,
  {path, sync?{direction:push|pull|bidirectional, patterns?, on_integrate?}}]` — string-конфиги
  старых проектов остаются валидными без изменений. Новый модуль `lib/skiller/brain_sync.py`
  (stdlib-only): нормализация конфига, `sync_pull` (копирует по glob-паттернам из BRAIN, сохраняя
  относительные пути, soft-skip при отсутствии BRAIN — не ломает офлайн-работу), генерация
  `.claude/sync-brain.sh` (атомарная запись, `chmod 755`). `integrate` вызывает `sync_pull`
  только для объектного конфига с `direction: pull|bidirectional`; строковый конфиг оставлен
  под старый memory-хук без изменений поведения. Три drift-гейта (`test_schema`, `doctor`,
  `test_registry_state`) обучены трактовать мульти-тип поля (`(str, dict)`) как `oneOf`, не
  ослабляя проверку. Новый `tests/test_brain_sync.py`.

### Added (maind@0.x — кэш BRAIN-доков в памяти namespace)

- **`packages/maind/scripts/cache-brain-docs.sh`** — bash-хелпер, кэширующий доки из Brain-валта
  в память namespace через реально существующие флаги `maind memory remember --scope
  project:<ns> --type docs:<key> "<содержимое>"` (в предыдущем аудите фигурировали
  несуществующие `--key`/`--file` — сверено по коду `memory.py`, использованы фактические флаги).
  Раздел «Кэш BRAIN-доков в памяти» добавлен в `packages/maind/docs/guide/namespaces.md`
  (таблица рекомендуемых `--type`-ключей: `docs:brd`/`docs:architecture`/`docs:api`/`docs:glossary`,
  пример `recall`). Не интегрирован в `onboard.py` — остаётся ручным/скриптовым шагом.

### Changed (рефакторинг раскладки + core-дедуп)

- **core-дедуп:** три кросс-пакетных дубля сведены в общий `core`. `core.repo.sibling_bin`
  (единый резолвер лаунчера соседа `env→PATH→<monorepo>/packages/<pkg>/bin`) заменил три
  разошедшиеся копии (`skiller.harness_bin`, `analyst._resolve_maind_bin`); `core.io.backup_file`
  (merge-only `*.bak`, параметризуемый суффикс) заменил `maind.common.backup_file` + инлайны в
  `harness.settings`; управляемый markdown-блок и urllib-HTTP-клиент вынесены в `core.block`/
  `core.http` (`maind.blocks`/`maind.http` — тонкие re-export-shim'ы, back-compat импортов).
  +12 core-тестов.
- **Группировка flat-lib по доменам** (за порогом flat-lib smell): `maind/lib/maind` —
  слабо-связанные окраины в подпакеты `provision/` (deploy·sync·onboard·orchestrate·migrate·
  service·start·workspace·skilldoc) и `analysis/` (fleet·analyze·audit); плотно-связное ядро
  (память/граф/федерация/namespaces/derive + cli/common/config/mcp/health) осталось в корне.
  `skiller/lib/skiller` — анализ в `quality/` (eval·audit·analyze). Импорты: `maind.provision.*`/
  `maind.analysis.*`/`skiller.quality.*`. `cli/common/__main__` — на верхнем уровне (launchers
  не тронуты). `harness`/`analyst` оставлены плоскими (ниже порога). validate всех 4 зелёный
  (core 151 · maind 380 · analyst 175), CLI-smoke ок.

### Changed (интеграционный контракт `perplexity-web-mcp` — снят версионный дрейф)

- **`research/query-craft`, `general/mcp-advisor`, `docs/reference.md`:** инструкция интеграции моста
  `perplexity-web` расходилась с фактическим кодом пакета (доки застряли на «демон v1.3.0», код ушёл
  вперёд). Сверено **по коду** `perplexity-web-mcp` (`src/{config,resilience,dispatcher}.ts`, 2026-07-03),
  привязка к версии снята, добавлено недокументированное поведение: **client-side resilience** (авто-retry
  с backoff 3× на транзиентных `BROWSER_BUSY`/`TIMEOUT`/`INTERNAL`; desktop `notify-send` и структурный
  JSONL error-log `$XDG_STATE_HOME/…/errors.jsonl` при финальном отказе; kill-switch'и `PERPLEXITY_WEB_MCP_*`),
  код ошибки `INTERNAL`, **login grace-window** (демон сам открывает окно логина ~3 мин + cooldown, параллельные
  запросы fail-fast с `LOGIN_REQUIRED`), дефолтные таймауты (`search` 60s / `deep` 600s) и авто-фолбэк в legacy.
  Совет «ручной retry на BROWSER_BUSY/TIMEOUT» переформулирован — мост ретраит **сам**. Регенерён реестр.

### Added (документация — Diátaxis-каркас + закрытие дыр)

- **Пользовательские гайдлайны:** новый landing-каталог (`docs/index.md` — карта 4 пакетов
  «что это + когда брать»), сквозной **`docs/getting-started.md`** (установка → онбординг →
  первая задача) и **`docs/tasks.md`** — гайд «какая `/task:*` в каком случае» + **plan-протокол**
  (мастер-планы `plans/<ID>/`, 4 команды, 6 статусов, handoff, эскалация, `plansDirectory`),
  которого раньше на сайте не было вовсе.
- **Разделы `task` и `core`** на сайте (`packages/{task,core}/docs/index.md` + docs-sync);
  reference телеметрии run-report (SCHEMA=2, `core/usage.py`) — в core-разделе.
- **Закрыты дыры:** `develop.md` синхронизирован (per-project `plans/`, `/task:plan-*`);
  `analyst/docs/guide/cli.md` получил `token-report`/`ingest`/`proposals`; `plansDirectory`
  operator-доки в `maind/sync.md` и `skiller/integration-checklist.md`; `bucket-audit` в sidebar.
  Каркас Diátaxis введён навигацией (nav/sidebar), без массового переписывания 100+ страниц.
  Провенанс Diátaxis — `docs/reference.md`. Сборка VitePress зелёная (без мёртвых ссылок).

### Added (SKM-MASTER-003 — plan-система per-project · хвосты рецензии)

- **Plan-система per-project (P1, дизайн A–F):** планы plan-протокола живут В ПРОЕКТЕ.
  Ключ `plansDirectory: "plans"` раскатывается тремя слоями — `harness hooks --plans-dir`
  (новый `block_plans_dir` через `set_setting_key` в `.claude/settings.json`; чужое значение
  ключа не перезаписывается), провиженеры `maind sync --only plans-dir,plans-doc`
  (ретроактивно, опт-аут `project.plans_dir="off"`; `plans-doc` — hashed-блок конвенции
  `maind:plan-conventions` в CLAUDE.md), `skiller integrate` (новые онбординги). Активный
  план — `plans/ACTIVE.md` (ведут `plan-design`/`plan-close`, валидирует `plan-lint`
  root-режимом: несуществующий план → ERROR, залежавшиеся черновики → WARNING с подсказкой).
  Мост встроенного plan mode → протокол: режим **`/task:plan-design from-draft <файл>`**
  (плоский черновик в `plans/` → `plans/<ID>/` по шаблонам, provenance в Decision Log,
  черновик удаляется). Цикл владельца «фаза → handoff → /clear» закреплён строкой в
  Expected output `plan-exec`/`plan-close`, §6 скилла и CLAUDE.md-блоке. Скилл
  `plan-protocol` вошёл девятым в CORE_SKILLS (резидент 705/750 ток). Пилот end-to-end
  на azguard — 7/7 шагов зелёный (артефакты в azguard не закоммичены — решение владельца);
  эффект `plansDirectory` в живом plan mode headless не проверяется — первое живое
  планирование владельца. Фан-аут на ~17 проектов — `maind sync` после обкатки.
- **Хвосты рецензии волн 1–4 (P2, 9 items):** `skiller budget` учитывает `references/`
  как ⌥ on-demand (симметрично `snippets/`); `bucket-audit` получил канал **`resident`**
  (CORE_SKILLS ∪ активные наборы зарегистрированных проектов; dead → keep, честная
  пометка «резидентный» — 9/9 CORE больше не ложно-dead; периметр шире CORE: флип
  122 скиллов, учесть перед P7.4); 8 RU-монолитов (architect/legal/marketing/operator/
  pm/research/security/sales) ужаты до RU-навигаторов (полные переводы — git-история);
  upstream `quality/tdd-discipline` чист — удалённый в upstream файл убран из `files[]`
  (0 failed); BC-строка Verify в dev-loop `laravel-package` под `pack:if/ifnot
  BC_CHECK_CMD` (пак 0.1.1); `analyst token-report` — инвариант «ERROR:» ⇔ exit≠0
  закреплён тестом; дока pack-guard в `agent-packs.md` (+58 строк); roadmap-доки
  синхронизированы с реализацией (analyst-suggest/self-learning-memory/README —
  «реализовано», остаток — event-stream capture).
- **Догфудинг и починка протокола по field-feedback пилота (D9):** сам план волны —
  `plans/SKM-MASTER-003/` (транскрибирован первым агентом, закрыт целиком 19/19,
  `plan-lint plans/` 0/0, ACTIVE → «—»). По находкам пилота: узаконен bootstrap-заголовок
  handoff `after P0.0` (plan-design), `plan-close` при закрытии плана целиком обновляет
  `Meta.Status` и пишет `Next: план закрыт`, `plan_lint` допускает «план закрыт» только
  при полностью терминальном плане (+2 теста). Deferred: honest `changed` у `plans-dir`
  (F3), per-skill сигнал в SCHEMA=2-тренде (Known Deviations P2.2).

### Added (SKM-MASTER-002, волна 4 — pack-guard · живой цикл протокола · метрики ДО)

- **pack-guard (P5.6, слой 2 mutation-защиты, опциональный):** PreToolUse-хук
  `hooks/pack-guard/` (off | warn | strict; по умолчанию НЕ ставится) — ловит правку
  generated-файла пака ДО того, как она случилась (решение по `.claude/agent-pack.lock.json`,
  user_owned-файлы пропускаются; strict → блок с русским объяснением, любая ошибка/нет lock →
  тихий пропуск, exit 0). Подключение: `harness hooks --target . --pack-guard MODE`;
  физическая доставка — в `apply-permissions.sh --global`. 16 тестов. Рекомендован для
  overnight/unattended dev-loop.
- **Живой цикл протокола (P1.8/P1.10 — фаза A закрыта 10/10):** реальные item'ы P5.6 и P8.1
  исполнены sonnet-операторами с холодным контекстом строго по `/task:plan-exec`, аудированы
  opus по `/task:plan-audit`. Главный риск не подтвердился: sonnet не «дорисовывает» план —
  исполнитель P8.1 сам поймал реальный дрейф (протухший глобальный хук) и честно отказался
  пинить baseline на пустом окне; cold-start подтверждён (работа только из файлов plans/).
  По findings аудитов протокол ужесточён: plan-close — гейт незапланированных файлов в дереве
  закрываемой фазы + «🟢 требует коммита» + реконсиляция устаревших deviations; plan-audit —
  явная сверка committed vs working-tree; plan-design — правило «тайм-гейтовый Deliverable —
  отдельный item» (применено к самому плану: выделен P8.5 «пин baseline пилотов»).
- **Метрики ДО (P8.1):** глобальный хук run-report обновлён до SCHEMA=2 (стоял протухший
  SCHEMA=1 от раскатки 1 июля — реальный дрейф, пойманный исполнителем; `harness doctor`
  чист); телеметрия включена на пилотах azguard и chatom (ENABLED=on + SessionEnd);
  SCHEMA=2-механика проверена на реальном транскрипте в изолированном scratch-cwd (пилотные
  baseline не засорены синтетикой). Пин baseline — тайм-гейт P8.5 (≥1 недели окна).

### Fixed (волна 4)

- Восстановлен из HEAD некоммиченный регресс-ревёрт `docs/routing.md` (потерян слой analyst,
  «зонтик из трёх пакетов») и `docs/reference.md` (−24 строки провенанс-карточек) —
  HIGH-находка adversarial-аудита P5; в `plan-close` добавлен гейт, ловящий такой класс
  контаминации при закрытии фазы.

### Added (SKM-MASTER-002, волна 3 — analyst learning loop · bucket optimization)

- **Analyst learning loop (фаза D):** команда **`analyst token-report`**
  (`[--sessions N] [--by model|role] [--vs-baseline] [--all-projects] [--json]`) — срезы
  usage-trend, rolling-baseline (медиана+p90 последних 20 сессий), regression-флаг
  (>1.3×медиана или >p90), pinned-снимок `--baseline set --note …` → `.claude/analyze/baseline.json`
  (формат совместим с уже читающим его `maind analyze`; 21 тест). **Агент-аналитик**
  `packages/analyst/agents/analyst.md` (opus, read-only) + команда **`/analyst:deep`** —
  digest-first (D16): скрипты собирают JSON-выжимки (`maind analyze` / `token-report` / `review`)
  в `.claude/analyst/deep/`, агенту передаются пути; raw-транскрипты запрещены промптом; выход —
  findings под контракт **`analyst ingest --file F`** (валидация целиком до первой записи;
  ТОЛЬКО ephemeral-уроки, detector=agent-finding — enforced кодом; промоут за человеком;
  10 тестов). **`analyst proposals`** — черновики системных улучшений
  (stack-pack | project-override | docs) в `~/.swissknifeman/analyst/proposals/<type>/<id>/`
  (детерминированный слаг-id, edit-safe writer как suggest.py), статусы draft|accepted|rejected
  через append-only audit, печать handoff-последовательности; тест-инвариант «ноль записей вне
  ~/.swissknifeman/analyst/» (27 тестов). Плагин analyst теперь раздаёт и агента
  (`"agents"` в plugin.json, marketplace перегенерён — 52 плагина).
- **Bucket optimization (фаза G):** команда **`skiller bucket-audit`** (`lib/skiller/audit.py`) —
  размер (реюз budget) · overlap (Jaccard≥0.4 по description, 5-gram shingle ≥0.3 по телам) ·
  usage (фан-аут по projects.json, `--since N`, честная пометка «не использовался в окне») →
  вердикты keep/thin/retrieval-only/merge/dead (структурные факты приоритетнее usage-сигнала;
  20+ тестов). **Решение-документ** `docs/guide/bucket-audit-2026-07.md`: 206 скиллов / 45
  бакетов / 21 проект, вердикты с числами (dead=180 · keep=13 · thin=8 · merge=3 ·
  retrieval-only=2), эскиз топологии 45→~34 (только эскиз), раздел «что НЕ делаем» (D13/D14).
  **10 монолитов → thin-navigator** (D13): тела 55–102KB перенесены байт-в-байт в
  `references/full.md`, SKILL.md — компактный EN-навигатор с картой якорей; аддитивное поле
  **`body_path`** в upstream-схеме + гейты в validate.sh/update-upstreams.sh (sha/дрейф — по
  телу, не по навигатору). Итог по budget: **on-trigger ярус 512 608 → 279 802 ток
  (−232 806, ~45%)**, резидентный ⊕-ярус не вырос. **Alias-механизм слияний бакетов** (D14,
  код без применения): `alias_of`+`skills[]` в buckets.json → marketplace-запись по прецеденту
  core-плагина, миграционные подсказки в `skiller update`/`status` (15 тестов; живой реестр
  алиасов не объявляет — дифф генерёжки пуст). Критерий **always-on vs retrieval-only** записан
  в `docs/guide/methodology.md` (3 условия + правило обратимого exclude по 2 окнам).

### Fixed (волна 3 — попутные находки)

- **`bin/analyst`**: жёсткий whitelist лаунчера не знал зарегистрированных команд
  `status`/`compact` (и нового `token-report`) — команды были недостижимы через установленный
  CLI; whitelist и usage синхронизированы.
- **`bin/skiller`**: та же болезнь — `analyze-run` и новый `bucket-audit` отсутствовали в
  whitelist лаунчера; добавлены.
- **`skiller registry`**: provenance-запись external-скилла теперь предпочитает
  `body_path`-файл (`references/full.md`) записи `SKILL.md` — иначе провенанс thin-navigator
  скиллов зависел от порядка `files[]`.

### Known gaps (честно, волна 3)

- `analyst token-report --by phase` невозможен на текущей схеме run-report: `workflows[]` не
  несёт токенов per-workflow — CLI принимает флаг и вежливо объясняет; добор формата хука —
  отдельная волна (harness).
- `budget.py` не учитывает `references/` ни в одном ярусе — экономия −232K частично «уход из
  учёта», а не honest-переклассификация в on-demand; модельное решение по tier-2 учёту
  references/ — follow-up.
- usage-источник bucket-audit — транскрипт-скан по явным Skill-вызовам (не SCHEMA=2-тренд):
  структурная слепая зона на auto-trigger/CORE-скиллах (8/8 CORE показывают «dead» при
  заведомой раздаче) — вердикты dead читать с этой поправкой; интеграция с трендом — follow-up.

### Added (SKM-MASTER-002, волна 2 — каталог патологий · стек-пак laravel-package + пилоты)

- **Каталог патологий (фаза C):** `core/pathology.py` — чистый защитный детектор workflow-патологий
  (`detect(run_report) → findings {code, severity: info|attention, metric, threshold, evidence}`),
  10 детекторов: file-reread, tool-error-loop, no-op-run, no-verify (+`no-verify-devloop`),
  cache-miss, overthinking, retrieval-stuffing, protected-write, static-context, fanout; пороги —
  константы с честной пометкой «эвристики, не откалиброваны» (36 тестов). Маршрутизация строго
  Detect ≠ Gate: `maind analyze` — `pathology_slice` (attention → reasons/ATTENTION, info → секция
  «Эффективность»; RED от патологий невозможен, инвариант в докстрингах); `analyst digest` —
  извлекатель `extract_pathologies` с правилом рецидива (окно 5 последних run-report'ов, урок
  только при ≥2 попаданиях кода; разовая патология — сигнал analyze, не урок), в уроки идут только
  4 кода с готовой ремедиацией. Каталог-док `packages/analyst/docs/guide/pathologies.md`
  (все классы, формулы/пороги = константы кода, remediation, честная колонка «детектируемо/добор»).
- **Стек-пак `laravel-package` 0.1.0 (фаза F):** отдельный пак для Laravel-ПАКЕТОВ
  (composer library / монорепо пакетов) — reviewer с центром «публичный контракт» (Public API/
  BC-SemVer + roave/bc-check, register-vs-boot, publishables, `env()` вне config → HIGH,
  composer-констрейнты, Testbench, multi-version matrix), slice-builder («фича пакета»,
  @internal/final), test-writer (Testbench + version_compare-ветки), новый recon `api-surface`,
  4 rules, dev-loop-форк (risk-adaptive сохранён, +public-api маркер, preflight
  `composer validate --strict`). Анти-дубль двумя слоями: движковый **`src_pack`** в files[]
  (review-gate.sh/env.ini/settings.fragment — байт-в-байт из backend-laravel без копий) +
  **parity-тест shared-блоков** `test_agentpacks_shared.py` (6 блоков прозы reviewer'а размечены
  `<!-- shared:X -->` в обоих паках, дрейф = красный тест). Новая команда **`harness agent-packs
  remove`** (чистые файлы удаляются, modified/user_owned/merge остаются с warn, lock атомарно).
  `backend-laravel` 0.11.2 — shared-разметка + фикс `app/Repositories` → `{{ACCESS_ROOT}}/…`.
  Профиль `php-package` получил `agent_pack: ["laravel-package", "_common"]`; roadmap
  `php-package-stack-pack.md` → «реализовано»; доки harness + docs/reference.md (roave — adopt;
  spec-kit/beads/planning-with-files — reference).
- **Пилоты (фаза F, rendered в рабочих деревьях azguard/chatom, там не коммитим):** azguard —
  remove backend-laravel → render laravel-package чисто + 4 доменных оси в
  `.claude/rules/azguard-reviewer-overrides.md` (panel_id isolation, epoch-invalidation,
  wildcard semantics, extension API idempotency) + path-scoped `azguard-domain.md`; chatom
  (монорепо `packages/*/src`) — та же миграция с `HAS_MIGRATIONS=true`/Pest. Acceptance-грепы
  app-канона по обоим — 0 попаданий; `doctor --drift` чисто. Регрессия непилотных (F-8):
  upgrade-канал 0.11.0→0.11.1 (worktree-эмуляция «до headers») — 0 conflict; dry-run на живом
  app-проекте — conflict'ы только от реальных ручных правок generated-core (ровно тот паттерн,
  который теперь ловит ось `generated-core-edited`).

### Fixed (полевые находки пилотов волны 2 — движок agent-packs)

- **`_probe_allowed` резал детект-пробы по `;` без понимания кавычек** — проба
  `PACKAGE_NAMESPACE` (php -r) тихо skip'алась при `shell_policy=safe` и переменная
  оставалась пустой; проба переписана одним PHP-выражением без `;` (терминатор `?>`),
  плюс фолбэк на `packages/*/composer.json` с кратчайшим psr-4 (монорепо-кейс).
- **`categorize_file_change`: файл пака в lock, но отсутствующий на диске**, при upgrade
  давал бесполезный `conflict`/`*.pack-new` вместо простой установки → теперь `new`/
  `new-optional` (missing + base-unchanged остаётся `nochange`). +2 теста.
- **`do_render` не переписывал lock при `changed=False`**, даже если у файла реально
  сменился флаг `local_modified` (внешняя реконсиляция файла к базе пака) — `doctor`
  вечно показывал протухший `modified: true` → lock пишется при отличии свежей записи
  от сохранённой. +1 тест.

### Added (SKM-MASTER-002, волна 1 — plan-протокол · токен-телеметрия SCHEMA=2 · защита generated-ассетов)

Мастер-план `plans/SKM-MASTER-002` (операционная система планов): сильная модель проектирует,
дешёвая исполняет, телеметрия делает утечки токенов видимыми, generated-ассеты защищены.

- **Plan-протокол (фаза A):** скилл `general/plan-protocol` (SSOT: схемы `plans/<ID>/{plan.md,
  phases/Pn.md,handoff.md}`, 6 канонических статусов, rolling handoff, routing-матрица
  model/effort, эскалация с greppable-артефактами) + snippets-шаблоны; 4 команды
  `/task:plan-{design,exec,close,audit}` с пинами (opus/high · sonnet/medium · sonnet/low ·
  opus/xhigh); детерминированный `plan-lint` (`packages/task/lib/task/plan_lint.py` + тонкий
  `scripts/plan-lint.py`, 45 тестов) и первый `validate.sh` пакета task; сам мастер-план
  транскрибирован в `plans/SKM-MASTER-002` (dogfooding, lint зелёный).
- **Токен-телеметрия end-to-end (фаза B):** `core/usage.py` — единый самодостаточный
  транскрипт-парсер usage (вендорится байт-в-байт в хук как `_usage.py`; `sync-usage.sh` +
  cmp-гейт в validate.sh harness — дрейф копии валит валидацию); run-report **SCHEMA=2**
  (only-additive: `usage` per-agent включая sidecar-субагентов, `reads`, `error_loops`,
  `retrieval`, `protected_writes`); тренд `.claude/analyze/usage-trend.ndjson` (~200 байт/сессия,
  ретеншн 4000→2000); `skiller analyze-run` переведён на `core.usage` (суммы идентичны,
  регресс-фикстура); `maind analyze` — блок tokens (сессия vs медиана K=20/p90 тренда + pinned
  `baseline.json`), регрессия токенов → ATTENTION (RED от токенов невозможен); `harness doctor`
  детектит протухший установленный хук. USD сознательно не считаем — сырые токены model-keyed.
- **Защита generated-ассетов (фаза E):** детерминированный provenance-header
  `swissknifeman:generated` (Pack@version/Template/Edit-policy/Extension-points, БЕЗ timestamp —
  хеш вместе с header, матрица `_decide`/`categorize_file_change` не тронута) во всех rendered
  файлах паков; `user_owned` в lock (schema 1, аддитивно); `harness agent-packs doctor --drift
  [--strict]` + самодостаточный `pack_drift` в `maind analyze` → ATTENTION при локальной правке
  generated-файла; overlay-модель расширения (`.claude/rules/<prefix>-reviewer-overrides.md`,
  user_owned, `role:override`) во всех стек-паках + правило `_common/rules/generated-assets.md`
  + ось `generated-core-edited` (HIGH) в reviewer'ах + HARD_GATES в dev-loop. Бампы паков:
  `_common` 0.4.0, `backend-laravel` 0.11.1, `node-frontend`/`python-backend`/`dart-flutter`
  0.4.1, role-паки +0.0.1.

### Added (output-style=lean + skills-catalog — автоматическая раздача на все проекты)

- **`skiller integrate` ставит `output-style lean` во ВСЕХ бандлах** (`minimal`/`recommended`/
  `full`/`custom`, дефолт `True`) — новый блок `_block_output_style` делегирует `harness hooks
  --output-style lean` (по образцу `_block_autoapprove`/`_block_memory`). Раньше терсе-голос
  агента был чисто ручной операцией (`harness hooks --output-style lean`), ни одна из точек
  входа (`maind onboard`, `skiller integrate`) его не вызывала — capability `env:hooks` в
  `orchestrate.py` не имела ни одного вызывающего. Токен-экономия нужна «для всех проектов»
  независимо от объёма остальной автоматизации бандла — единственный пункт, включённый и в
  `minimal`.
- **`maind sync` — два новых провиженера** для уже онбордженных проектов (закрывают
  тот же разрыв ретроактивно, без полного re-onboard): `output-style` (тот же `env:hooks
  --output-style lean`, опт-аут per-project `project.output_style: "off"` — иначе регулярный
  `maind sync --all` затирал бы локально выбранный стиль) и `skills-catalog` (`skiller update`
  — пере-резолв buckets/exclude с диска, поэтому новый скилл уже выбранного бакета, например
  `php/pao`, доезжает до давно онбордженных PHP-проектов без ручного `skiller update`/`connect`/
  `vendor`). Оба — в дефолтном наборе `--all`.
- **`skm:update` добавлен в `orchestrate.DRY_CAPABLE`** — `skiller update` умеет свой честный
  `--dry-run`, теперь `maind sync --dry-run` даёт реальный превью для `skills-catalog`, а не
  fake print+rc0 (та же ловушка, которую `DRY_CAPABLE` уже чинил для `agent-pack`).
- Контекст: `php/pao` (агентно-оптимизированный вывод PHPUnit/Pest/PHPStan для PHP-проектов) уже
  входил в дефолтный профиль `php-package`/`laravel-project` и доезжал на новых онбордингах;
  реальный `composer require laravel/pao --dev` **сознательно не автоматизирован** нигде (мутация
  `composer.json`/`composer.lock` без подтверждения человека) — агент выполняет его сам по
  инструкции скилла, когда реально начинает гонять тесты («skill-on-demand»).

### Fixed (пакет `skiller` — аудит registry/budget/vendor/connect: дублирование, ложно-зелёные гейты, надёжность)

По итогам `research/Глубокий аудит пакета skiller (registry-budget-vendor-connect).md` (22 находки,
все закрыты — код-фикс либо документированный осознанный отказ от фикса, если он ломал существующий
инвариант).

- **R-1 [CRITICAL] — токен-экономия `connect` подтверждена, не предположена.** Комментарий в
  `registry.py` утверждал «подтверждено докой Claude Code v2.1.x» без реальной проверки. RAG
  (perplexity-web + прямая цитата `code.claude.com/docs/en/plugin-marketplaces#advanced-plugin-entries`):
  для marketplace-записи, чей `source` резолвится в корень marketplace, явный `skills[]`
  **заменяет** дефолтный скан, а не дополняет его — риска резидентной загрузки всех 219 SKILL.md
  репозитория нет. Комментарий переписан с точной цитатой и датой проверки.
- **V-2/V-3 [HIGH] — ложно-зелёные install/lock (`vendor.py`, `skillset.py`).** `safe_copy_skill`
  мог вернуть `False` (containment-стоп/TOCTOU-гонка) — пропуск тихо проглатывался, `sync`/`vendor`
  рапортовали план как факт. Теперь считаем и печатаем ФАКТ (`plan['installed']`/`skip_copy`).
  Структурно битый `skills-lock.json` (не путать с легитимно пустым после ручной чистки — тест
  `test_manual_lock_cleanup_*` остался зелёным) восстанавливает managed-набор из манифеста, а не
  обнуляет его.
- **V-1 [HIGH] — дубль резолва `requires`.** `skillset._pull_requires`/`vendor.resolve_requires`
  были независимыми, уже разошедшимися BFS (RU/EN тексты warn) — сведены к общему
  `common.resolve_requires_bfs` с адаптером источника узла (FS-кортеж / registry-entry).
- **V-4/V-5 [MEDIUM] — дубли writer'а манифеста и сбора бакетов.** Единый
  `common.write_skill_manifest` (было два независимых писателя с разной схемой: date-only без
  `version` у vendor, `now_iso`+`version` у skillset). Сбор бакетов (FS-rglob vs registry) оставлен
  архитектурно раздельным (осознанно — принудительное слияние ввело бы жёсткую зависимость `vendor`
  от прогнанного `skiller registry`), но добавлен golden-тест паритета (`test_channel_parity.py`),
  ловящий будущий дрейф каналов.
- **B-1/B-2 [MEDIUM] — калибровка токен-оценки + недобор в `--check-core`.** Константы
  `CHARS_PER_TOKEN_CYR/LAT` (2.2/4.0) откалиброваны по RAG (perplexity, 3 источника: ~2.9 для
  кириллицы, ~3.4 компромисс EN-прозы/кода) — старые занижали RU-токены и завышали code-heavy тела.
  `budget --check-core --strict` теперь фейлит и на НЕДОБОРЕ CORE-скиллов (переехавший/опечатанный
  путь раньше молча УМЕНЬШАЛ резидент, гейт «зеленел» вместо ошибки). Пересчёт по калиброванным
  константам вскрыл реальный факт: резидент CORE (8 скиллов) — 696 ток, что честно превышает старый
  target 600. `resident_budget_target` поднят до 750 в `configs/core-policy.json` (осознанное
  решение, не откат калибровки).
- **R-2 [MEDIUM] — drift-гейт не видел `graph.md`/`budget.md`.** `scripts/generate-graph.sh` (bash+
  heredoc) портирован в `registry.render_graph`/`write_graph` (in-process, без subprocess) — теперь
  `registry.check_drift` сравнивает оба артефакта, а не только `skills.json`/`_index.md`/манифесты.
  Старый shell-скрипт оставлен в дереве с deprecation-шапкой (`rm` заблокирован политикой окружения
  сессии — безопасно удалить вручную: `git rm packages/skiller/scripts/generate-graph.sh`).
- **V-6 [MEDIUM] — диагностируемость частичной копии при краше.** Конфликт с sha256, совпадающим с
  реестром (похоже на прерванный sync), теперь получает отдельное сообщение с явной подсказкой
  «`--force` безопасно» вместо пугающего «занят чужим скиллом». Авто-усыновление НЕ включено —
  сломало бы тестируемый инвариант «ручная чистка lock требует `--force`».
- **C-1/C-3 [MEDIUM/LOW] — `connect.py`.** Пропуск CORE-плагина при необъявленном marketplace
  (`--no-core` не задан) теперь явный `warn`, не тишина. `DEFAULT_COMMAND_PLUGINS` покрыт тестом.
- **U-1 [MEDIUM] — `update --all` не падает на битом манифесте.** Необёрнутый `json.loads` ронял
  необработанным исключением весь батч на первом же проекте с битым `.swissknifeman-manifest.json`
  (не ловится `except SystemExit`). Тот же класс дефекта найден и починен в `vendor.load_manifest`
  (регрессия всплыла через тест на `update --all`).
- **Doc-1/Doc-2 [MEDIUM/LOW] — `doctor.py` не диагностировал harness.** Добавлена проверка
  `harness_bin` + лёгкий `harness --help`-пробинг: отсутствие — не FAIL (опциональная зависимость),
  поломка — FAIL. Schema-check в doctor раньше сверял только имена ключей (`⇄ ключи`), теперь и типы
  (`⇄ типы`) — паритет с `test_schema.py`.
- **Т-2 [MEDIUM] — устаревшая цифра CORE («7 ≈ 480 ток») везде.** Синхронизировано (`connect.py`,
  `config.py`, `CLAUDE.md`, `docs/guide/{archetypes,skills-architecture}.md`) на актуальный факт
  (8 скиллов) без хардкода нового снапшота — указывает на `skiller budget --check-core` как источник
  истины, чтобы не протухнуть повторно.
- **V-8/V-9 [LOW] — надёжность.** Битый `boost.json` в `lock._boost_skills` теперь warn, не тихий
  `[]`. Смена `skills_path` в конфиге больше не оставляет осиротевшую копию по старому пути (новый
  проход prune по `installed_path` из lock).
- **B-3/B-4/R-3/R-4 [LOW] — точечные.** Детектор кириллицы расширен на Cyrillic Supplement
  (U+0500–052F). `_split_frontmatter`/дубль-«мёртвая» ветка имени в `registry.py` — документированы
  как осознанные, не слиты/не удалены (реальной пользы от слияния не было, риск — был).
- **Тесты:** +18 unit-тестов (233 всего, было бы больше номинально — часть находок покрыта
  расширением существующих ассертов), включая новый `test_channel_parity.py`. `validate.sh` зелёный
  (`skiller registry` перегенерирован, `registry --check` чист).

### Changed (дисциплина: RAG-делегирование + подробность плана/хендоффа)

- **RAG-ступень не делегируется тул-бедному субагенту** (канон `general/verify-claims` — новый
  подраздел «Делегирование: не ронять ступень»; указатель в root-скилле `decision-verification`;
  клауза в `CLAUDE.md` «Методология решений»). Первопричина: верификация внешнего факта была
  делегирована субагенту `claude-code-guide` (тулсет без `perplexity-web`) → лестница молча
  просела до `WebSearch`. Правило: RAG-ступень исполняется там, где доступен приоритетный движок;
  делегируешь — делегат обязан нести `perplexity-web`/`context7`, иначе держи проверку в основном
  контексте (делегировать МОЖНО, ронять ступень молча — нельзя). **Регресс-гарант** — новый
  pressure-кейс в `verify-claims/evals/pressure.json` (ловит соблазн через `skiller eval`).
- **Контракт `task`-пакета: план максимально подробный, хендофф короткий** (`task/design.md`,
  `task/dev.md`). План — самодостаточный (всё для исполнения В ФАЙЛЕ, переживает падение сессии),
  не «коротко по фазам»; спорное → отдельный блок `## Обсуждение` в плане (плюсы/минусы + явная
  рекомендация), а не popup; хендофф на `/task:dev` — короткая ссылка на план, не бриф на 2 страницы;
  `AskUserQuestion` — крайний случай и всегда с рекомендованным вариантом.

### Added (пакет `analyst` — P4: cross-project паттерн → ЧЕРНОВИК скилла)

- **`analyst suggest <pattern_id> | --all [--bucket B] [--min-weight N] [--dry-run] [--json] [--force]`**
  — детерминированный (stdlib, on-demand) мост `scan` → переиспользуемый скилл: читает **только**
  абстрагированный индекс `index/by_pattern/<id>.json` и генерит staged-ЧЕРНОВИК
  `~/.swissknifeman/analyst/drafts/<pattern_id>/` = `SKILL.ru.md` (RU-источник-заготовка с
  frontmatter-скелетом + инертный провенанс-штамп) + `draft.meta.json` (паспорт + `seed_sha256`).
  **Инвариант удержан:** НЕ пишет в `skills/`, НЕ генерит EN-канон, НЕ регистрирует, НЕ раскрывает
  raw/секреты (приватность СТРУКТУРНА — индекс уже абстрагирован). Промоут в бакет — человек; вывод
  печатает **точную** repo-grounded последовательность skiller (mkdir → `claude-canon-from-ru.md` →
  `check-translations.sh --stamp` → `validate.sh` → `skiller registry`).
- **Edit-safety (идемпотентность):** ре-suggest не затирает ручные правки — `seed_sha256`-детект
  (тело == последнего сгенерённого → перегенерим; правлено руками → тело не трогаем, освежаем лишь
  провенанс meta; `--force` перезаписывает). Осиротевшие черновики (паттерн исчез) — **WARN, не
  delete** (≠ scan-prune: черновик человеко-редактируем).
- **Гейты:** `name`-кандидат по офиц. правилам скиллов (≤64, `[a-z0-9-]`, без ведущих/хвостовых
  дефисов и reserved `claude`/`anthropic`; кириллица не образует name → латинский токен/`skill`,
  финализирует человек); `--min-weight` (индекс не несёт confidence → `--min-tier` отложен, D7).
  Чистые генераторы (`build_skill_ru`/`build_meta`/`_slug_name`) + writer с I/O в `cmd_suggest`;
  +13 offline-тестов. Дизайн: [`roadmap/analyst-suggest-draft-skill.md`](roadmap/analyst-suggest-draft-skill.md).
  Заодно исправлены устаревшие указатели «промоут = `skiller integrate`» в `scan.py`/CHANGELOG
  (integrate вшивает скиллы В проект, не регистрирует новый).
- **Документация пакета `analyst`** — добавлен `packages/analyst/docs/` (VitePress: index + guide
  cli/lifecycle/suggest + architecture + roadmap) и линковка в зонтичный сайт (`scripts/docs-sync.sh`,
  корневой `docs/.vitepress/config.mts` nav+sidebar+Пакеты, `docs/routing.md` слой «Обучение»,
  `.gitignore`). Standalone и агрегатный build зелёные. Раньше analyst был единственным пакетом без
  своих доков.

### Added (пакет `analyst` — P1 MVP + P2 scan: continuous learning, слой-1)

Новый четвёртый пакет монорепо **`analyst`** (CLI `analyst`, плагин-только-команды) — детерминированный
(stdlib-only, **on-demand, без демона**) слой захвата «выстраданных уроков» из прогонов Claude Code с
**человеком в гейте** (авто-запись в скиллы запрещена). Реализует P1 контура continuous learning:

- **`analyst digest`** — детерминированно извлекает КАНДИДАТ-уроки из свежего `run-report` прогона по
  высокоточным сигналам (resolved-failure «сработало после N попыток»; явные dev-loop workarounds) →
  `.claude/analyst/lessons/ephemeral/` (LOCAL). Не «угадывает инсайты» — осознанная граница MVP.
- **`analyst review`** — уроки по состояниям (ephemeral/candidate/curated/deprecated) + structured diff
  против активных (Jaccard, stdlib). Read-only.
- **`analyst promote <id>` / `deprecate <id>`** — конвейер `ephemeral→candidate→curated` с **человеко-гейтом**
  (переход в curated — только явное согласие: confirm на tty либо `--yes`); curated всплывает в память
  mAInd (`maind memory remember`, graceful — демон лёг → урок на диске, повторим позже). Soft-деприкейт.
- **Провенанс:** каждый урок несёт `source`/`session_id`/`scope`/`evidence`; каждый переход — запись в
  append-only `.claude/analyst/audit.ndjson`.
- **`analyst scan` (P2)** — cross-project агрегатор: пакет сам обходит реестр `config.json:projects[]`,
  читает per-project уроки, greedy-Jaccard-кластеризует и детектит паттерны, повторяющиеся в **≥N
  проектах** (по умолчанию 3) → draft-**предложения** (не скиллы!) в `~/.swissknifeman/analyst/suggestions/`
  + индекс `index/by_pattern/`. **Namespace-изоляция** (наследуется от maind): уроки кластеризуются
  только среди проектов, делящих namespace — паттерн из `ns:axioma` не течёт в чужой. Детерминизм
  (сортировка по id). Черновик скилла из предложения — `analyst suggest` (P4); промоут в бакет — человек.
- **Обвязка:** root-router `swissknifeman analyst …` + `doctor` fan-out; зонтичный `install.sh`;
  marketplace-запись (авто-подхват `skiller registry`). `Env(BaseEnv)`, atomic JSON, тесты offline (37).
- **Реконсиляция `analyst scan` (P2-долг закрыт)** — после записи артефактов детерминированный прун
  осиротевших `index/by_pattern/<id>.json` + `suggestions/<id>.md` (паттерн исчез: проект disabled/удалён,
  урок deprecated, кластер упал ниже порога). Прун СТРОГО в scope прогона: `scanned_namespaces` =
  `{--namespace}` если задан, иначе union namespace всех enabled-проектов; чужой namespace не рескан →
  его файлы не трогаются (классификация — из ПОЛЯ `namespace` индекса, не из имени файла; битый индекс →
  SKIP, не удаляем и не роняем scan). Флаги: `--no-prune` (прун по умолчанию ВКЛ), `--dry-run` (только
  would-prune, ничего не удаляет); `pruned:[…]` в `--json`, «снято сирот: N» в human. Нестандартные
  `--min-projects/--threshold` авто-прун пропускают (защита от churn). Чистые `stale_pattern_ids` (тесты
  без I/O) + `list_existing_patterns`/`prune_artifacts`; +11 offline-тестов (adversarial S2).
- Отложено на P5 (по дизайну, не долг): скилл `analyst-capture` + `observe.sh` PostToolUse-поток.

### Added (пакет `analyst` — P3: confidence-жизненный цикл)

Реализует **P3** контура continuous learning: детерминированный,
**восстановимый-из-логов** пересчёт уверенности урока + **числовая** state-machine, **без демона**
(on-demand) и **без нарушения инварианта** «`candidate→curated` — только человек».

- **`events.ndjson`** (новый append-only поток сигналов, рядом с `audit.ndjson`) — `digest`/`promote`
  дописывают скаляры наблюдений (`sessions_total/success`, `tests_total/passed`). Источник истины
  пересчёта: снапшот воспроизводим только из этого лога.
- **`confidence.py`** — ЧИСТАЯ арифметика (stdlib, без I/O/часов, тестируемая по точкам): Beta-среднее
  `p=(S+α)/(N+α+β)` × volume `(1−e^{−N/k})` × time-decay `λ^days`; тиры применения
  `0.3` tentative · `0.5` moderate · `0.7` strong · `0.9` core. Константы (`α=β=1`, `k=20`, `λ=0.95`
  ≈ полураспад 14 дн, bucket=1 день) — **тюнинг-параметры модуля** (калибруются по false-positive rate).
- **`analyst recompute [--now ISO] [--dry-run] [--json]`** — читает `events.ndjson` → decay по времени →
  агрегат `S/N` (+ `S_decayed`/`N_decayed`) → `confidence` → числовая state-machine → **атомарный** снапшот
  в урок (аддитивные поля, P1-схема не ломается). Детерминирован и восстановим (при фикс. `--now`). Гейты:
  `ephemeral→candidate` — **авто** при `N≥15 && conf≥0.6 && tests_total≥1`; `candidate→curated` — **всегда
  человек** (числа лишь помечают «готов», авто-переход запрещён — инвариант P1); просадка `conf<0.6` →
  **soft-deprecate** (файл не удаляется).
- **mem0-консолидация в human-gate** — `review`/`promote` считают таксономию **ADD/UPDATE/NOOP/CONFLICT**
  (Jaccard по trigger/action, stdlib) против активных. Противоречие (та же ситуация, иное действие) →
  **flag-and-ask** (промоут блокируется до явного `--supersedes ID` | `--force`, авто-резолва нет).
  `--supersedes` — **soft-invalidate** замещаемого (`supersedes`/`superseded_by`+timestamp, move в
  deprecated, файл сохранён).
- **Обвязка:** `recompute` в `cli.py`/`bin/analyst`/`commands/analyst.md`; тесты offline (+33 = 70).
  Демона нет. Реальный round-trip surfacing в память mAInd — проверен ещё в P1.

### Docs (аналитика и continuous-learning в витрине README + раннбуке)

Витрина не упоминала аналитику/самообучение, хотя реальный слой уже есть, а полный контур —
спроектирован и в roadmap. Отражено честно (real vs roadmap):

- **README** — строка «📈 Аналитика и обучение»: реальное (захват `run-report` → `maind analyze`
  с метриками памяти/графа; экспериментальный `session-observer`; петля `field-feedback-loop` с
  ручным промо) + кросс-проектный **Continuous Learning** помечен как спроектированный/roadmap
  (ссылки на `roadmap/self-learning-memory.md` и дизайн `research/analyst-package-design.md`).
- **`docs/develop.md` §9** — блок «Самообучение — контур и статус»: ручная петля с человеком в гейте
  сейчас; автоматический кросс-проектный контур — отложен (confidence + ручное промо как guardrail).

### Added (developer-раннбук + витрина README + наблюдаемость памяти/графа)

Документация процесса разработки отставала, а память/граф mAInd были «чёрным ящиком» (пишет ли,
читает ли, помогает ли — померить нечем). Разобрано чтением кода + RAG-верификацией внешних фактов
(нативная авто-память Claude Code и семантика `/compact` — офиц. доки; Serena-инструменты — context7).

- **`docs/develop.md`** — единый operator-раннбук «Разработка с Claude Code + swissknifeman»: фазы
  плана, `/compact` vs новая сессия (канон по офиц. докам), task-плагин, роли/agent-packs, токен-рычаги,
  **демистификация памяти** (два слоя: agentmemory-демон vs нативная память Claude Code) и **графа**
  (ручной скан + pull-модель), измерение эффективности, RAG-лестница, сценарии-FAQ. Спина-коннектор —
  ссылается на глубокие доки, не дублирует. Врезан в VitePress (nav + sidebar `/develop`).
- **README → витрина** — feature-обзор «что даёт» (плагины+скиллы, роли+workflow, токен-рычаги,
  задачи, память+граф, окружение, RAG) вместо повтора CLAUDE.md; заметная ссылка на раннбук.
- **Наблюдаемость памяти/графа** (отвечает на «работает ли или просто жрёт токены»):
  - run-report (`_lib.py`) считает вызовы `maind_memory_*`/`maind_graph_*` из транскрипта (матч по
    хвосту после `__` — переживает `mcp__maind__`/`mcp__plugin_core_maind__`) + найдено фактов/соседей →
    аддитивный ключ `maind` (SCHEMA не бампан, back-compat со старым `analyze`).
  - `maind analyze` показывает `память: recall×N→M · граф: query×K` и подсвечивает **«код-граф не
    использовался при тяжёлом сканировании»** (косвенная эвристика: много Read/Grep/Glob при графе ×0).
  - `maind memory count [--project]` — сколько фактов в памяти по scope (по scope-маркеру, не весь пул).
- **graph-first nudge** — скилл `ecosystem-mcp` (maind) теперь явно советует граф/Serena
  `find_symbol`/`get_symbols_overview` перед широким `grep` (с оговоркой про ручной скан/устаревание);
  кросс-ref из `context-economy` (лестница рычагов).

### Added (token-economy — base deny-rules для крупных артефактов; трек A план-A ROI-1)

Токен-экономия (аудит `research/swissknifeman-token-audit.md`): большие низкоценные файлы не должны
попадать в контекст через случайный `Read`/glob. Расширен `permissions.deny` в
`configs/claude-code/settings.base.json` (был только `.env`/keys/ssh/sudo): добавлены
`Read(**/CHANGELOG.md)`, `Read(**/skills.json)`, `Read(**/package-lock.json)`,
`Read(**/composer.lock)`, `Read(**/*.lock)` — анкорены `**/` (матч на любой глубине downstream).
- **Behavior change:** `**/*.lock` теперь запрещён на уровне base (subsumes laravel-пресетный дубль;
  merge аддитивен и дедуплит точные совпадения). Пресеты стеков без изменений.

### Added (maind analyze — пост-ран разбор прогона «всё ли сработало» + SessionEnd-хук run-report)

Field-feedback: после задачи-с-планом (напр. на azguard) нужно через логи проверить, всё ли отработало,
но источники исхода читались по отдельности — единой команды не было. Верификация механизма захвата —
целиком через `perplexity-web` (нашла 2 ошибки первого черновика: транскрипт — first-class артефакт,
парс поддерживаем; SessionEnd-хук может писать отчёт generic'ом → правка `dev-loop.js`/паков НЕ нужна).

- **Хук `run-report` (SessionEnd, harness)** — `configs/claude-code/hooks/run-report/`
  (`run-report.py` + `_lib.py`): строчно (без слурпа) и защитно парсит транскрипт → пишет
  `<project>/.claude/runs/<sid>.json` (тесты/линт с `ok` из `is_error`, изменённые файлы, tool-провалы,
  воркфлоу, best-effort dev-loop `tool_failures`/`deferred`/`workarounds`). Generic — любая задача, не
  только dev-loop. Никогда не барьер (ошибка/битый stdin → exit 0). Ретеншн `RUNS_KEEP`.
- **`harness hooks --run-report on|off`** (`block_run_report`) — env.ini (ENABLED/RUNS_KEEP) + merge-only
  регистрация SessionEnd. `apply-permissions.sh --global` копирует `run-report/` в `~/.claude/hooks`.
- **`maind analyze [--project|--cwd] [--session] [--base] [--json] [--no-health]`** (новый
  `lib/maind/analyze.py` + `cli.py` + `bin/maind` whitelist + `commands/analyze.md`): агрегирует
  run-report (первично) + bash-лог (форензика, БЕЗ кодов возврата — честно) + observer + git + health →
  вердикт **GREEN/ATTENTION/RED** (+`confidence` low, если run-report нет). Смычка с RAG: dev-loop
  `tool_failures` → блок «**Непроверено → ПОВТОРНЫЙ ПРОХОД**». RED → exit 1 (гейт для скриптов).
- Тесты: `harness/tests/test_run_report.py` (+12: парсер, поведение хука, ретеншн, block_run_report),
  `maind/tests/test_analyze.py` (+11: вердикт, поиск run-report, форензика, сборка+JSON).
  **Честные лимиты:** схема транскрипта не заморожена → парс защитный; bash-лог без pass/fail;
  SessionEnd = 1 запись/сессия; `devloop`/observer — best-effort.

### Added (intent-router — свободный текст → оптимальная команда; активация roadmap-хука)

Field-feedback: владелец забывает ставить задачи через `/task:*` (замеренный мисроут → триггер
активации отложенного `roadmap/agent-command-router-hook.md`). Верификация капабилити — целиком через
`perplexity-web` (нашла 2 ошибки в исходном плане: auto-run первоклассный через `SlashCommand`;
SessionStart-политику слать через `additionalContext`, не `systemMessage`).

- **Пара Python-хуков `agent-router`** (первый Python-хук репо):
  `configs/claude-code/hooks/agent-router/` — `session-policy.py` (SessionStart инжектит статическую
  политику роутинга через `additionalContext`) + `router.py` (UserPromptSubmit: keyword-прескор →
  крошечная idempotent-подсказка при score≥THRESHOLD, иначе тишина; escape-hatch `~`). Гибрид:
  прескор — bias, финальную классификацию (вопрос vs задача) делает модель. Никогда не барьер.
- **`harness hooks --router propose|auto_dispatch|off`** (`block_router`) — включает пару хуков
  per-project (env.ini + merge-only регистрация UserPromptSubmit+SessionStart).
- **`harness router --generate --target P`** (новый модуль `lib/harness/router.py` + `cli.py`) —
  генерит `.claude/agent-router.config.json` из `/task:*` + `.claude/agents/*.md` + локальных
  `.claude/skills/*/SKILL.md` (низкий вес — бэкстоп). Зонтичный `swissknifeman env router` даром.
- **maind:** `env:router` capability + провиженер `router-config` в `maind sync` (opt-in: генерит
  каталог только для проектов с включённым хуком; идёт после `agent-pack`).
- **Глобальная раздача:** `apply-permissions.sh --global` копирует `agent-router/` в `~/.claude/hooks`
  (env.ini не затирает). `validate.sh` получил py_compile-шаг для Python-хуков конфигов.
- Тесты: `harness/tests/test_router.py` (+10: block_router, --generate, поведенческие хуков),
  `maind` `TestRouterConfigProvisioner` (+4). roadmap помечен активированным + исправлен устаревший
  тезис про авто-активацию команд. **Честный лимит:** хук команду не запускает; `auto_dispatch`
  может оверфайрить → дефолт `propose`; marketplace-команды пакетов — follow-up (в README).

### Added (RAG-дисциплина формирования плана — агрессивный perplexity-web + footer «Проверка» + честность)

Field-feedback: агенты неохотно жмут RAG при формировании плана, хотя план 100% должен стоять на свежих
данных; отказ движка (perplexity-web залочен/timeout, MCP лёг) не выносился на повторный проход; не было
клаузы честности «костыль называть костылём». Scope: CORE-скиллы + CLAUDE.md + docs + агент-паки (зубы).

- **CORE-скилл `verify-claims` 0.2.0** (раздаётся в каждый проект): лестница — токен-экономия
  (`perplexity-web` flat-rate → **агрессивный дефолт**; на промах context7 фолбэк на perplexity-web, НЕ на
  WebSearch); новый **footer «Проверка»** (RAG · непроверенное→**ПОВТОРНЫЙ ПРОХОД** · обходки-`[POSSIBLE-DEFECT]`);
  клауза честности «не правки ради правок, костыль называть костылём». RU-источник правлен → EN-канон регенерён.
- **CORE-скилл `query-craft`**: нота токен-экономии (жать `perplexity-web` агрессивно) + как записать отказ
  движка в footer «Проверка» (кросс-реф на `verify-claims`).
- **Root `CLAUDE.md`**: «Методология решений» переписана под агрессивный perplexity-web + footer «Проверка»;
  новый тезис философии **«RAG-делегирование (токен-экономия)»**.
- **Root-скилл `decision-verification`**: триггер «формирование плана» + footer «Проверка» + честность.
- **Агент-паки (зубы): `_common` 0.3.0** — `orchestrator.md` получил RAG-правило плана + выходной блок
  `VERIFICATION`; **`backend-laravel` 0.10.0** — `dev-loop.js` `SLICE_RESULT_SCHEMA` получил опциональный
  `tool_failures[]` (движок недоступен → повторный проход, не маскировать).
- Провенанс — `docs/reference.md` (industry prompt-engineering RAG-forcing/verification-footer, верифиц.
  `perplexity-web` 2026-07-01). **Честное ограничение:** интерактивный plan mode не хардгейтится (нет хука) —
  фикс поведенческий; зубы только в workflow-слое `dev-loop.js`.

### Added/Changed (harness — agent-pack мигратор: монорепо-детект + анти-false-green)

- **Движок `agentpacks.py` — пост-рендер валидация путей (`expect_globs`).** Новое поле
  манифеста пака: список single-brace-глобов критичных путей; `render`/`upgrade` после
  рендера проверяют `target.glob(...)` и **печатают WARN на 0 совпадений** —
  детерминированная сеть безопасности против **ложно-зелёного** access-layer (когда
  захардкоженные пути не матчат раскладку проекта), независимо от detect-проб.
- **Движок — итоговая сводка conflict/.pack-new в `do_upgrade`** (`⚠ N conflict → ручной
  мерж: …`) — повышает видимость незаехавших правок (был только per-файловый warn).
- **Движок — условие `<!-- pack:ifnot KEY -->…<!-- pack:endif -->`** (зеркало `pack:if`,
  «иначе»-ветка; из PR #96) — нужно для двух-режимных блоков (`SCAFFOLDS_SCHEMA`).
- **`backend-laravel` 0.9.0** (детали — в его CHANGELOG, **supersedes PR #96**): `ACCESS_ROOT`
  авто-детект (`app`/`src`/`packages/*/src`) — вытеснил `IS_LARAVEL_PACKAGE` (тот не умел
  монорепо) + layout-aware пути (дроп `/Api`-сегмента) + `expect_globs`; **сохранён
  `SCAFFOLDS_SCHEMA`** из #96 (ортогональная ось: scaffold vs готовая схема, `pack:if/ifnot`).
  **Монорепо Laravel-пакетов рендерится верно на автомате** (пилот chatom вскрыл пробел).
  Принцип: каждая ручная итерация апгрейда флота дорабатывает базовый мигратор.

### Added (harness — авто-allow инструментов оркестрации `Workflow`/`Agent`/`TodoWrite`)

- **Пресеты `base` и `global` теперь авто-разрешают `Workflow`, `Agent`, `TodoWrite`.** Это
  универсальные (вне-стековые) инструменты оркестрации, поэтому добавлены в оба общих слоя:
  `settings.base.json` (накатывается в `.claude/settings.local.json` каждого проекта) и
  `settings.global.json` (машинный `~/.claude/settings.json` — действует во всех проектах сразу).
  Первопричина: запуск `Workflow` на каждой фазе спавнит субагентов (`Agent`) и ведёт план
  (`TodoWrite`), и без правил Claude Code просил подтверждение **после каждой стадии** —
  многофазный воркфлоу превращался в череду промптов. Безопасность не страдает: разрешён лишь
  сам вызов инструмента, субагент исполняет свои Bash/Read/Edit через тот же permission-слой.
  Затронуты `packages/harness/configs/claude-code/settings.{base,global}.json`, доки
  `docs/configs/claude-permissions.md` и `docs/setup/claude.md`.
### Added (skiller — пост-ран наблюдаемость: `skiller analyze-run`)

- **`skiller analyze-run`** (`lib/skiller/analyze.py` + `cli.py`) — детерминированный
  разбор прогона по JSONL-логам Claude Code, **без запуска агентов/трат токенов**.
  По агентам: факт-токены `in/out`, **cache-hit%** (из поля `usage`), модель,
  wall-clock, инструменты, ретраи, tool-ошибки. Скиллы: активный набор
  (`resolve_active_set`/`budget_for_set`) × реально загруженные (`Skill`-вызовы) →
  **эффективные / DEAD** (в наборе, 0 загрузок → чинить триггеры/снять) / вне набора.
  Плюс скан рантайм-отказов (`Rate limited`/`SingletonLock`/…, эвристика).
  Флаги `--last|--session|--project|--json|--store` (`--store` → JSON в
  `.claude/analyze/`, задел под кросс-сессионный тренд). Закрывает разрыв
  «budget (теория) ↔ eval (синтетика) ↔ реальный прогон». Дополняет качественный
  скилл `system/session-observer` (числа vs «почему»). +14 офлайн-тестов
  (`tests/test_analyze.py`); гайд `docs/guide/analyze-run.md`. Честное ограничение:
  детект загрузки скиллов частичный (только `Skill`-tool; нативный `skills:`-preload
  не виден).

### Added/Changed (harness — токен-экономия: downstream `deny` + agent-pack backend-laravel 0.5.0)

> План: `~/.claude/plans/idempotent-snacking-nest.md` (свод ретроспективы chatom + ответа Perplexity +
> токен-аудита; верифицировано RAG). Это P0-волна (publish-surface + workflow).

- **Downstream `permissions.deny`-пресеты (publish-surface, самый дешёвый ROI).** `deny` — реальный
  токен-барьер (на встроенные Read/Edit и на `cat/head/tail/sed`), `.claudeignore` не официальна.
  `settings.laravel.json` += `storage/framework/**`, `bootstrap/cache/**`, `**/node_modules/**`,
  `vendor/bin/**` (НЕ `vendor/**` целиком — vendor-исходники нужны для сверки реального API),
  `**/package-lock.json`, `**/.phpunit.cache/**`, `**/*.sqlite[3]`. `settings.base.json` += `~/.claude/logs/**`
  (лог-файлы хуков). `settings.python.json` получил deny-набор (`__pycache__`/`.venv`/`.mypy_cache`/
  `.pytest_cache`/`.ruff_cache`/`*.egg-info`/`dist`/`build`). Логи целиком НЕ денаим — чтобы не ломать
  `tail`-slice (selective-input).
- **agent-pack `backend-laravel` 0.5.0** (детали — в его CHANGELOG): risk-адаптивный review-gate
  (severity-enum, adversarial на HIGH, config-honesty, fresh-context), Lean-tiered model/effort-лейны,
  честность тестов `[POSSIBLE-DEFECT]`, env-preflight в Setup, layout-agnostic globs правил + per-layer
  risk-аннотации; фикс ложного «проект НЕ на Pest» (chatom F2) → `{{TEST_FRAMEWORK}}`, хардкод pint →
  `{{CHECK_CMD}}`.
- **Миграция: `agent-packs upgrade` теперь ставит НОВЫЕ файлы версии** (не только safe-apply/conflict). Файлы,
  добавленные в новой версии пака (recon-агенты 0.6.0), доезжают до онбордженных проектов на `upgrade` (а не
  только на полном `render`) — цель не существует, запись безопасна; явно удалённые optional (`removed_optional`)
  не возвращаются; локальные правки существующих файлов по-прежнему не затираются (`conflict`→`.pack-new`). Важно,
  т.к. `maind sync` зовёт именно `upgrade`. +unit-тест. Гайд пака дополнен разделом «Как ставятся задачи» +
  **mermaid-диаграммой** процесса dev-loop.

### Added/Changed (skiller — токен-экономия: плагин `task` + docker-router + context-economy/session-handoff)

- **Новый плагин `task`** (`packages/task/`, commands-only, авто-регистрация в marketplace, 51 плагин):
  интент-команды `/task:design|dev|review|research|fix`. Имя плагина `task` + файлы `commands/dev.md`
  и т.д. дают ровно `/task:<verb>` (Claude Code именует команды плагина как `<plugin>:<file>`; вариант
  `tasks`+`task-dev.md` дал бы `/tasks:task-dev` — исправлено). Каждая пинит `model:`+`effort:` (frontmatter) под
  профиль, перебивая настройки сессии — закрывает «забыл переключить модель/effort/режим». dev→Opus/high
  (планирование) + Lean-tiered субагенты по риску; fix→Sonnet/medium single-agent; review→Opus/xhigh adversarial;
  design/research→Opus/high + research-fanout.
- **`task` — default-on в КАЖДОМ проекте** (`skiller.config.DEFAULT_COMMAND_PLUGINS = ["task"]`): connect
  включает плагин `task` автоматически (как курируемый `core`) — marketplace-guarded (на старом
  marketplace / в тест-реестре тихо пропускается), `--no-core` его НЕ трогает, точечный opt-out —
  `enabledPlugins["task@swissknifeman"]=false`. Новые онбордженные проекты получают `/task:*` без ручной
  правки. Резидентного tier-0 налога нет (описания команд не инжектятся в каждый запрос).
- **Доктор фиксирует пропуск** (`maind doctor --audit core`): дименсия `core` теперь помимо CORE-скиллов
  проверяет и командные плагины по умолчанию — `cmd⚠(нет: /task:*)` на проектах без `task`. Чеклист
  интеграции (`integration-checklist.md`) дополнен пунктом про `core`/`task` в connect.
- **`devops/docker` → тонкий router-скилл** (v0.2.0, `risk: read`): description-триггер + маршрутная таблица по
  всем 6 под-скиллам (docker-php/postgres/dev-prod/services/vite/makefile) + порядок сборки (DAG в
  requires/produces_for); глубокая экспертиза — в `snippets/docker-expert.md` on-demand (progressive disclosure).
  «Фоновый» кластер: резидентно только router-описание, специалисты грузятся по нужде.
- **`general/context-economy` v1.2.0**: §8 — recon-субагенты (тяжёлое чтение в изолированном окне, наверх только
  сводка), selective-input (срез вместо файла целиком; `tail`/`grep`/`git diff`; нюанс: `deny` блокирует и
  `tail`), видимость стоимости (`/usage`, не `/cost`); back-ref на плагин `tasks`.
- **`general/session-handoff`**: `outputs: []`→`[".claude/handoffs/*.md"]` + стандартный путь
  `.claude/handoffs/YYYY-MM-DD-<topic>.md` (индексируется maind). RU→EN перестамплены, `skiller registry` прогнан.
  Аудит рекомендовал `risk:draft→stable` — **отклонено** по верификации (`stable` не в
  `RISK_VALUES={read,draft,write,external}` → сломал бы validate; зрелость — отдельное поле `level`, не `risk`).
- **F8 budget-governance — `skiller budget --check-core`** (+ `--strict` для CI) и константа
  `RESIDENT_BUDGET_TARGET=600` (config.py): гейт резидентного ⊕ tier-0-бюджета `CORE_SKILLS` (грузится в КАЖДЫЙ
  запрос) против таргета; выведен в хвост `validate.sh` (информационно). Замер вскрыл: резидент CORE сейчас
  **592/600 ток** — у потолка (комментарий обещал ~480), так что гейт против тихого роста ядра предметен.
- **D4 — 5 новых production-readiness-скиллов** (из ретроспективы chatom; локальные, двуязычные RU→EN, 205 скиллов):
  `php:transactional-outbox-relay` (persist+outbox в одной tx, единственный владелец retry, идемпотентность,
  after-commit), `php:production-readiness-checklist` (атомарность/гонки/config-honesty/cursor/queue-семантика —
  класс дефектов, который маскируют зелёные тесты), `php:cursor-pagination-design` (keyset по non-nullable ключу,
  composite-tiebreak), `php:namespace-refactor-safety` (трёхфаза alias→use→rename, префиксные ловушки, контракт-seam),
  `laravel-architecture:config-driven-abstraction` (Registry+Builder, config:cache-safe, per-variant ≠ runtime `$table`).
  Ретроспективные #5 (state-machine-race) и #6 (env-driven-test) **свёрнуты** в production-readiness-checklist +
  dev-loop env-preflight (анти-bloat: не дублировать существующие `enum-state-machine`/`db-test-preflight`).
- **F2 — `skiller doctor --downstream`** (аудит publish-surface онбордженных проектов — там основной runtime-расход
  токенов, не в реестре): per-project гигиена always-loaded слоя — `CLAUDE.md` ≤200 строк, scoped vs unscoped
  `.claude/rules`, наличие `permissions.deny`-пресета. Замер по реальным проектам вскрыл over-budget CLAUDE.md
  (sova 1214, cms 813, flexcrm 738 строк, …) против здоровых (chatom 123, corex 169) — операционализирует
  ключевой тезис аудита (мерять сгенерированный артефакт, не шаблоны). +unit-тест (202 теста).
- **A2/A3 — thin-orchestrator + skill-on-demand задокументированы/проброшены:** `docs/guide/skill-taxonomy.md`
  получил раздел «Router-скилл» (тонкий оркестратор фонового кластера — образец docker); orchestrator-агент паков
  (`_common/orchestrator.md`) — поля `risk:`+`skills:` в PLAN (минимальный набор под тип задачи + risk→модель/
  effort/глубина ревью), вместо полного preload. (C — durable per-phase handover: реализован «лёгкой» версией —
  компактные сводки в брифах + plan-file-primary + нативный resume воркфлоу; on-disk-дубль избыточен, не вводим.)

### Changed (skiller — `perplexity-web-mcp` v1.3.0: демон-конкурентность в скиллах)

- **`research/query-craft`**: раздел «Надёжность keyless-моста» (lock/сериализация, запрет
  «не параллелить») переписан в «Конкурентность и устойчивость `perplexity-web` (демон v1.3.0)».
  Параллель разрешена до `maxConcurrency` (дефолт 3); пулы (`--pool`) как конфиг MCP; таблица кодов
  ошибок (`BROWSER_BUSY`/`TIMEOUT`/`LOGIN_REQUIRED`/`PROTOCOL_MISMATCH`); не-контрактные обрывы
  (`ECONNRESET`/«connection closed» → недокачанный Chromium → `npx playwright install`); `search_deep`
  до ~10 мин и не блокирует параллельные `search`; чеклист обновлён. Прежний обход «не параллелить»
  снят как legacy.
- **`general/mcp-advisor`**: пул-нота к keyless `perplexity-web` (демон v1.3.0, изоляция через
  `--pool=<проект>`).
- **`docs/reference.md`**: строка про integration-note `perplexity-web-mcp` v1.3.0 (вердикт **adopt**).
- RU→EN регенерирован + `check-translations.sh --stamp`; `skiller registry` (`skills.json`, `budget.md`).
  Контракт сверен end-to-end вживую: 3 параллельных `search` изолированы (no cross-read), фикс
  анти-троттлинга фоновых вкладок подтверждён.

### Changed (maind — переименование проекта экосистемы DocVault → Vaulter)

- **Проект `docvault` переименован в `vaulter`** (продукт DocVault → Vaulter). `derive.py`:
  `FIRST_PARTY_VENDORS` `docvault`→`vaulter`; `DOC_ALIASES` — новый канон `vaulter`,
  плюс **back-compat алиас `docvault` → `vaulter`** (старые doc-backlinks Brain резолвятся).
  Примеры/комментарии (`namespaces.py`, `design-notes.md`, скилл `cross-project-optimizer`)
  обновлены. Хаб-состояние (`config.json` id/scope/path, граф, `.mcp.json` scope `project:vaulter`,
  память, agent-pack `vaulter-*`) перекатано вне VCS; потребитель `flexcrm` и сам пакет —
  отдельными репозиториями/PR.

### Added (maind — opt-in эмит `.mcp.json.example` + гигиена `.gitignore`)

- **`maind deploy`/`sync` при `mcp.emit_example: true`** эмитит рядом с реальным `.mcp.json`
  портируемый `.mcp.json.example`: machine-specific абс. пути → плейсхолдеры (`<ABS_PATH_TO_PROJECT>`,
  `<HOME>`), индирекция `${MAIND_BIN:-maind}` сохранена. Один генератор → два выхода из одного `data`
  (`mcpconfig.write_example`) — расхождение real↔.example невозможно by design.
- **Гигиена `.gitignore`** (`reconcile_gitignore`): реальный конфиг → в `.gitignore` (append-if-absent),
  его `.example` → вне (remove-if-present, чтобы шаблон коммитился); идемпотентно; warn, если реальный
  файл уже трекается git. **Opt-in** (по умолчанию выключено — не трогаем чужие репо без флага).
  Закрывает машинно-специфичный серена-путь `--project <abs>`, который индирекция `maind` (PR #94) не
  решала. +тесты `test_mcpconfig`; статус `roadmap/mcp-config-example-emit.md` → реализовано (opt-in).

### Fixed (skiller — ложный `[ПЕРЕЕХАЛ]` в `skiller status` на монорепо-реестре)

- **`skiller status` сравнивал источник marketplace с `env.root` (каталог пакета), а не с корнем
  монорепо.** В монорепо `marketplace.json` лежит в КОРНЕ (туда же `connect`/`update` пишут
  `source` через `find_repo_root`), поэтому сравнение с `env.root` (`packages/skiller`) давало
  вечный ложный флаг `[ПЕРЕЕХАЛ — починить: skiller update]`, который `skiller update` физически
  не способен погасить (он пишет корректный корень репо). Теперь `status` резолвит ожидаемый
  источник так же — `find_repo_root(env.root) or env.root`. Затронут `lib/skiller/status.py`.

### Added (skiller — CORE-скилл `research/query-craft`: дисциплина формулировки поисковых запросов)

- **Новый скилл `research/query-craft`** — как ФОРМУЛИРОВАТЬ запрос к поисковому/доковому движку
  (Perplexity Web · WebSearch · context7): железное правило «никогда не голый запрос по библиотеке
  без версии+контекста» (анти-паттерн «Laravel как сделать X?» → «Laravel 11: … на 2025»); 5 слотов
  запроса (глагол · субъект+версия · контекст · конкретика · формат/лимит); выбор движка и режима
  Perplexity (`search`/`search_advanced`/`search_deep`, `sources` web/academic/social); раздел
  «Надёжность keyless-моста» (lock/таймаут на тяжёлых запросах → не параллелить, дробить, эскалация
  на WebSearch/context7, системно — API-key вариант).
- **Завершает RAG-дисциплину-трио в `CORE_SKILLS`** (раздаётся в каждый проект, on-trigger):
  `mcp-advisor` (что подключить) · `verify-claims` (когда/что верифицировать) · `query-craft` (как
  спросить). Скилл физически в бакете `research`, в CORE — по ссылке. `verify-claims`/`mcp-advisor`
  получили back-reference на него, роли разрезаны (verify-claims = «когда», query-craft = «как»).
- Двуязычный (RU-источник → EN-канон); факт-основа — официальный Perplexity Prompt Guide,
  верифицирована RAG (WebSearch+WebFetch) 2026-06-29 (см. `docs/reference.md`). 200 unit-тестов OK,
  `validate.sh` зелёный (201 скилл).

### Added (skiller — локаторы экосистемы: навигация агента к узлам Brain/swissknifeman)

- **Два скилла-локатора** в бакете `system` (on-trigger, НЕ в CORE — резидентный токен-бюджет не растёт):
  `system/brain-locator` (из любого проекта дойти до Brain-волта) и `system/swissknifeman-locator`
  (из внешнего репо дойти до управляющего монорепо). Цель — агент больше не угадывает, где узлы экосистемы.
- **Нехардкод-резолюция пути.** brain-locator повторяет канон `maind` (`projects.py::brain_path`):
  `integrations.brain.path` → проект `id==brain` → `$MAIND_BRAIN_VAULT` → кандидаты от `$HOME`
  (`~/Vaults/Brain` первым); swissknifeman-locator — через установленный бинарь (`readlink` до репо) →
  `$SWISSKNIFEMAN_ROOT` → `$HOME`-кандидаты. У каждого готовая `cd`-команда и проверка-признак узла.
- **Тезисы связи.** brain-locator несёт маркер «скилл подключён → проект синхронен на Brain», объясняет
  каталог `.projects.json` / control-ноты / `CLAUDE.md` / wikilinks; swissknifeman-locator — `config.json`
  как реестр связанных проектов (двусторонность) и опознание связи по
  `.swissknifeman/config.json` / `skills-lock.json` / `enabledPlugins`.
- **Связаны с картой.** `requires: [local-topology]`; `local-topology` получил их в `produces_for` +
  заметку про fallback-резолюцию узла без `~/.swissknifeman/topology.json`.

### Added (maind — синк-защита visibility + явная модель владения каталогом)

- **`sync_from_brain` предупреждает о смене visibility** doc-папки существующего проекта
  (`_warn_visibility_changes`) — частый признак протухшего brain `.projects.json` (его надо
  регенерировать из frontmatter перед синком). brain по-прежнему «выигрывает» (поле затирается):
  источник истины каталога/visibility — frontmatter control-нот → `.projects.json` → `config.json`.
- **Явная модель «три слоя + владелец факта»** в `docs/guide/config.md`: frontmatter Brain (источник)
  → `.projects.json` (gitignored кэш) → `config.json` (импорт + maind-поля). Разведена семантика
  `repo` (GitHub-slug) ≠ `local_path` (путь к коду) и инверсия brain-схемы (`repo` = путь → `local_path`
  при импорте). `config.example.json` — каноничный `docs_folders` `{id,vault,repo,visibility}`.

### Changed (maind — индирекция бинарника в `.mcp.json` вместо абсолютного пути)

- **`deploy.py::_maind_entry` пишет `"${MAIND_BIN:-maind}"`** вместо `<abs>/packages/maind/bin/maind`.
  Claude Code раскрывает индирекцию из окружения процесса (дефолт `maind` по PATH — `~/.local/bin`
  от `install.sh`); тот же `MAIND_BIN`, что у health-хуков. Переносимо на другую машину/CI и при
  переносе репо — в `.mcp.json` больше нет захардкоженного `/home/...`. Тест-замок на `command`
  (`test_deploy.py`), пример в `docs/guide/mcp.md` обновлён.
- Уже онбордженные проекты мигрируются идемпотентно: `maind sync --only mcp --all` (недеструктивный
  merge + `.bak`). Серена-путь `--project <abs>` остаётся машинно-специфичным — отдельная фаза
  (`roadmap/mcp-config-example-emit.md`).
- Гайды приведены в соответствие реальности: `project-tooling-runbook` §«Гигиена» (нюанс
  `${VAR:-default}` — Claude Code раскрывает из окружения процесса, не из проектного `.env`; maind-путь
  индиректирован, остаётся серена-путь) и `roadmap/mcp-config-example-emit.md` (проблема сужена до серена-пути).

### Added

- **`laravel-architecture/eloquent-accessors`** (новый скилл) — канон современных Eloquent
  accessors/mutators через `Attribute::make(get:, set:)` вместо legacy `getXxxAttribute()`:
  синтаксис/именование/видимость/типизация, размещение в классе (после relations, перед scopes),
  миграция legacy, граница с `casts()`. Сниппет `accessor.php` (getter, getter+setter с
  нормализацией, многострочный, миграция). Промоут project-local скилла из проекта agelto
  (анонимизирован, поднят в реестр по правилу универсальности) через `field-feedback-loop`.

### Changed

- **`project-tooling-runbook`** — новая секция «Гигиена machine-specific конфигов»: конфиг с
  абсолютными локальными путями или секретами (`.mcp.json` любого провайдера, `.cursor/.vscode/mcp.json`,
  `.claude/*`) не коммитить как есть. Двухуровневое правило: индирекция через `.env` (предпочтительно,
  конфиг остаётся портируемым) либо gitignore реального + **синхронный** `.example` с плейсхолдерами
  (как `.env`↔`.env.example`). Кросс-ссылка из `ecosystem-integration` (шаг deploy: `.mcp.json` несёт
  абс.пути maind/Serena). Триггеры обоих скиллов расширены.

- **`harness` agent-pack `backend-laravel` 0.2.0 → 0.3.0** — деуниверсализация шаблонов: убрана
  зашитая среда одного проекта (machine-specific `php8.5`/`pgsql`/`Postgres`/`/usr/bin/php8.4` и ложные
  для большинства «phpstan не установлен», «миграции не добавлять — схема полная»). Тест-фреймворк
  теперь параметричен (`{{TEST_FRAMEWORK}}` — раньше интервью-переменная игнорировалась, хардкод
  «PHPUnit-native, НЕ Pest»); идентичность slice-builder смягчена до «Laravel/REST API **или пакет**».
  Поймано на полевом онбординге azguard (Pest+Testbench-пакет) → `field-feedback-loop` путь 1 (фикс
  генератора, не артефакта). Затронуты agents/rules/workflow/docs пака.

- **Doc-папки: имя ↔ видимость развязаны (Brain doc-sync + maind + core).** Раньше «публичность»
  папки кодировалась её именем (хардкод `docs-public`), имена сторон vault/repo были жёстко
  симметричны. Теперь — единая модель папки `{id, vault, repo, visibility}`: имена сторон могут
  отличаться (в валте `docs-public` ↔ в репо `docs`), статус `public|private` независим от имени,
  wikilink-гейт публикации — по `visibility`. Дефолт видимости **по типу проекта**
  (`core.docs_visibility_for`): пакет/библиотека → `docs` public, продукт → private. Источник
  истины — frontmatter control-ноты Brain; maind кэширует `docs_folders` (нормализация плоского
  legacy-списка на лету, полная back-compat). Поймано на онбординге пакета chatom →
  `field-feedback-loop`. Затронуты `core/project.py`, `maind/{config,onboard,common}`, Brain
  `lib/brain/{folders,engine,config,status,listing,syncing,watch,discovery}` + доки/тесты.

- **`harness` agent-pack `backend-laravel` 0.3.0 → 0.4.0** + `python-backend`/`node-frontend`/
  `dart-flutter` 0.1.0 → 0.2.0 — **AI-гайд `subagents-and-workflows.md` переехал из публичного
  `docs/05_AI/guidelines/` в `.claude/guidelines/`** (дефолт `DOCS_DIR`). Это внутренний артефакт
  для агентов, не публичная VitePress-документация пакета (иначе утекал в публикацию и в Brain-валт).
  Из шаблона backend-laravel убран ошибочный Brain-frontmatter (`parent: [[05_AI]]`) и вики-ссылка.
  Миграция установленных проектов: новый гайд в `.claude/guidelines/`, старый путь удалить вручную.

### Roadmap

- **`roadmap/mcp-config-example-emit.md`** — отложено: научить `maind deploy/sync` самому эмитить
  `.mcp.json.example` (плейсхолдеры) + вести `.gitignore` (механизм вместо дисциплины агента).
  Критерий внедрения — повторная утечка абс.путей/секретов или невозможность поднять MCP без `.example`.
  Маршрутизировано через `field-feedback-loop` из полевого кейса agelto (настройка playwright-MCP).

### Added (аудит волна 3 — docs, эргономика, дедуп)

- **`analyst status` / `analyst compact`** (S16). `status [--json]` — read-only сводка стора:
  счётчики по состояниям, `curated-ready`, `promote_failed`, число событий, даты последнего
  `digest`/`recompute`. `compact [--before ISO] [--dry-run]` — детерминированно сводит старые
  события `events.ndjson` в один snapshot-event на урок; суммы (S/N/tests) и возраст последнего
  события сохраняются, поэтому `recompute` до и после даёт **ту же** confidence (проверено e2e:
  0.7968 → 0.7968). Провенанс операции — в `audit.ndjson`. Новый модуль `analyst/status.py` (+10 тестов).
- **`packages/analyst/docs/guide/tuning.md`** (S13) — единый справочник всех порогов (confidence-
  арифметика, тиры, state-machine, Jaccard-дедуп/консолидация): параметр · файл · значение ·
  эффект↑/↓ · метод калибровки. Линкован в сайдбаре (standalone + зонтичный агрегат) и из
  `lifecycle.md`.
- **`core.paths.state_dir(home, app=None)`** (S15) — единый источник литерала `.swissknifeman`
  для зонтичного state (корень `~/.swissknifeman` — skiller; подкаталог `~/.swissknifeman/analyst`).
  `maind` намеренно НЕ входит (его state `~/.maind` — отдельный node-state, документировано). +3 теста.

### Changed (честность + провенанс)

- **Коммент `analyst/confidence.py` — честный** (S13, D3-дисциплина): убрано ложное «verified
  perplexity, tune by false-positive rate» → «эвристики, подобранные по форме кривой, НЕ
  откалибровано по FP-rate» (реальной калибровки не проводилось — отдельная research-задача).
- **`docs/reference.md`: карточка mem0** (S17, провенанс F-RAG-2) — таксономия консолидации mem0
  = ADD/UPDATE/DELETE/NOOP; `analyst` адаптирует как **ADD/UPDATE/NOOP/CONFLICT** (`CONFLICT`
  вместо `DELETE` — авто-удаление нарушило бы инвариант «человек в гейте»). Строка в таблице
  уточнена + отдельная карточка.

## [0.7.1] - 2026-06-28

### Added

- **`founder/idea-audit`** — сквозной деструктивный аудит идеи / концепта / готового ТЗ: First-Principles
  Decomposition → рыночный скептицизм (5 векторов) → архитектурный pre-mortem (вкл. AI-specific) →
  Kill-or-Build Scoring + вердикт. Мост idea→architecture между `idea-discovery` и `brd`/`architecture`.
  Двуязычно (SKILL.ru.md → SKILL.md). Внешние факты выверены через RAG (Founder's Playbook — реальн.;
  CB Insights ~42% — классика, 2026 ~43% PMF); провенанс — `docs/reference.md`.
- **`provider-skills/` — SSOT навыков-капабилити для внешних агентов (paste-in).** Текст, который
  человек копирует в UI провайдера (Perplexity → My Skills), а не доставляет реестром connect/vendor;
  канон versioned здесь, потребители (Brain) держат provenance-linked копию. Первый навык —
  `perplexity/idea-architect.md` (режимы Idea/Spec/Architecture). Реестр учитывает их как `references`.
- **Внутренний скилл `field-feedback-loop`** (`.claude/skills/`, не экспортируется) — петля обратной
  связи из полевой работы: отклонение тулинга/раннбука от обещанного при внедрении/синхронизации
  проекта маршрутизируется в очевидный-баг→фикс-сразу либо новое/сомнительное→предложение
  (`roadmap/`/issue + захват в память), а не глотается. Механизм принципа «по факту измеренной
  проблемы» (`roadmap/README.md`); связан с `release-discipline`/`decision-verification`.

### Changed

- **`pm/requirement-critic`** — режим Spec Audit: Optimism Bias Detector, `[UNVERIFIED]`-метки для цифр без
  источника, чеклист полноты для продукта/стартап-ТЗ (target customer, kill-criteria, метрика PMF).
- **`founder/adversarial-check`** — секция **stage-context** (idea→рынок, mvp→retention, launch→CAC/LTV).
- **`founder/idea-discovery`** — **falsification signals** (измеримый порог) к каждому kill-criterion.
- **`architect/architecture`** — обязательное поле **`business_rationale`** в каждом Options-блоке.
- **`founder/startup-lifecycle`** — гейт доказательности: **≥1 внешний сигнал** на каждый exit-criterion.
- **`founder/risk-assessment`** — 6-я категория рисков **AI/Agentic** (hallucination/drift/injection/cost
  creep/eval-gaps/single-provider); тег `agentic`.

## [0.7.0] - 2026-06-28

### Added

- **Единый control-surface проектов (4 слоя, строго + машиночитаемо).** Одной командой — полный
  инвентарь проекта/флота по слоям *скиллы · роли/agent-packs · MCP · память-граф* с drift→fix
  подсказками; точечный re-sync уже даёт `maind sync --only <cap>`.
  - `maind projects status` теперь инвентаризует **слой ролей** (`probe_project` читает
    `.claude/agent-pack.lock.json` → поле `agent_packs`) и печатает **drift→fix** (`probe.drift_hints`:
    `{layer, issue, fix}` — напр. «профиль ожидает пак X → `maind sync --only agent-pack`»). `--json`
    несёт `agent_packs` + `fixes` по каждому проекту.
  - **`swissknifeman status [<id>|--all] [--json]`** — зонтичный фасад единого 4-слойного статуса
    (→ `maind projects status`); bare/`--target` → `skiller status` (back-compat сохранён).
  - **`--json`** добавлен в `skiller status` (каналы/профиль/бюджет/overlap) и
    `harness agent-packs doctor` (каталог паков + установленные) — машиночитаемо для агента.

### Docs

- **Корневой `CLAUDE.md` — раздел «Философия и рамки»:** разрозненные по тексту принципы сведены в
  явные **тезисы** (зонтик≠инструмент, единый источник истины, stdlib-only, детерминированная
  доставка, faithful-first+провенанс, изоляция namespace, спекулятивное→`roadmap/`) и жёсткие
  **рамки** («за них не выходим»: pip/JS-рантайм, дубли примитивов, переименование зонтика/префиксы
  плагинов, ломать пути `maind`, Proprietary-вендоринг, утверждать внешние факты по памяти).
- **Раздел «Референсы и провенанс»:** `CLAUDE.md` теперь указывает на каталог провенанса
  [`docs/reference.md`](docs/reference.md) (изученные внешние источники: вердикт adopt/reference/skip
  + что взято) и per-skill паспорта `upstream.json`, с правилом «использовал внешний ресурс — отметь».
- **Раннбук `project-tooling-runbook` — раздел «Агенты/роли (agent-packs)»:** настройка проекта
  теперь явно = скиллы **И** agent-packs (роли/агенты — отдельная подсистема `harness agent-packs`:
  субагенты + workflow + review-gate). В «Порядок „дать проекту всё“» добавлен шаг agent-packs;
  зафиксирован авто-путь (`maind onboard`/`setup` с типом проекта ставит пак из `profiles/<type>.json`)
  и причина пропуска при ручном `connect`/нетипизированной записи. Закрывает пробел «у проекта нет
  ролей/код-ревью при большой задаче».
- **Новая умбрелла-страница [`docs/control-surface.md`](docs/control-surface.md):** таблица
  «слой → статус-команда → fix/re-sync → lock» + операционный цикл `status --json → fixes[] →
  maind sync --only <cap>`. Раннбук `project-tooling-runbook` дополнен секцией «Control-surface»,
  явными шагами MCP/память/граф, а «Проверка» сведена к `swissknifeman status <id>`.

## [0.6.0] - 2026-06-27

**Аудит репозитория (многоагентный, 122 подтверждённые находки) → ремедиация в 7 фаз.**
Headline — **умное подключение**: connect раздаёт курируемый плагин `core` (РОВНО 7 `CORE_SKILLS`
по ссылкам, без копий) вместо целых бакетов general+oss-dev → резидентный ⊕ tier-0 **~1956 → ~480
ток/проект** на каждый запрос; budget-aware connect показывает цену набора; кириллица убрана из
EN-описаний (−643 ток) + CI-гейт. Плюс: надёжность логики подключения (TOCTOU, валидация lock,
действенный дрейф пути), кросс-пакетный дедуп примитивов в `core`, изоляция maind (scope-маркеры,
recall-crowding, рабочий graph-namespace), +18 тестов и ruff на `tests/`, доки приведены в
соответствие коду. Совместимость сохранена (онбордженным проектам — миграц.-подсказка, merge-only).

### Docs (аудит 2026-06 — Phase 7: точность доков и DX)

- **Доки больше не врут про CORE-политику.** `skiller/CLAUDE.md`, `docs/guide/skills-architecture.md`,
  `docs/guide/archetypes.md` и корневой `CLAUDE.md` обновлены под умное подключение: connect раздаёт
  курируемый плагин `core` (а НЕ бакеты general+oss-dev). Счётчик плагинов marketplace ~50.
- **Задокументирована команда `harness agent-packs`** (`list|render|upgrade|doctor` + флаги) в
  `harness/CLAUDE.md` — раньше отсутствовала в справке CLI.
- **`research/README.md`** (новый): индекс рабочих записей с явной пометкой «НЕ канон» и указателем
  на источники истины (docs/CHANGELOG/CLAUDE.md) + напоминание методологии (до-проверять аудиты).

### Added (аудит 2026-06 — Phase 6: тесты и CI)

- **Юнит-тесты на новое поведение:** `core.load_json_db` (missing/corrupt-backup/version-die),
  `core.is_within`/`is_within_lexical` (traversal), `core.atomic_write_*` mode=0600;
  `maind.split_scope` (strip-all маркеров, неподделываемый владелец); `harness.categorize_file_change`
  (матрица new/user-owned/conflict/safe-apply/nochange); skiller registry эмитит курируемый `core`-плагин;
  connect пушит `core` (не бакеты), `--no-core`, graceful-skip без core в marketplace. (+18 тестов.)
- **CI ruff теперь линтует и `tests/`** (раньше — только `lib/`, в тестах копился мусор: F401/F841).
  Прежний долг вычищен; планка теперь едина для тестового кода.

### Fixed (аудит 2026-06 — Phase 5: корректность и изоляция maind)

- **`memory.split_scope` — больше не утекают marker-артефакты:** снимаем ВСЕ ведущие `[[s:…]]`
  (на случай вложенных/повторных в контенте), владелец scope = первый маркер (подделать нельзя).
- **`memory` RECALL_LIMIT 50 → 200 + предупреждение о насыщении:** пул общий на все проекты
  экосистемы, узкое окно вытесняло релевантные факты scope чужими (crowding). При насыщении
  (демон вернул весь пул) — `warn`, что факты scope могли не влезть.
- **MCP `maind_graph_query`/`neighbors`: параметр `namespace` ТЕПЕРЬ работает** — раньше был
  объявлен в схеме, но молча игнорировался, и обход федерировал ВСЕ проекты (узлы чужих namespace
  утекали на depth>1). Теперь сужает union; стартовый узел по-прежнему под `_project_blocked`.
- Проверено и НЕ менялось (находки переоценены/уже закрыты): `cmd_sync` уже fail-soft с ненулевым
  rc и видимостью провалов (per-project `failed`); `deploy` уже health-WARN'ит (блокировать нельзя —
  `.mcp.json` статичен и валиден независимо от демона); абсолютные пути в `.mcp.json` —
  намеренны (CLAUDE.md «не ломать», 17 проектов), env-индирекция — отдельный аддитивный PR.

### Changed (аудит 2026-06 — Phase 4: кросс-пакетный дедуп → core)

- **`core.paths`** (новый): `is_within`/`is_within_lexical` — единый containment-примитив
  (был только в `skiller.common`, дублировал паттерн в connect/vendor/skillset/eval). Экспортирован
  из `core`; `skiller.common` реэкспортит для back-compat.
- **`core.io.load_json_db`** (новый): JSON-БД с восстановлением (битый → бэкап `.corrupt.<date>` +
  warn; version > max → die). Свёл дословные копии `skiller.state.load_db` и
  `maind.common.load_json_db` (расходились в имени бэкапа/тексте) к одному источнику.
- **`skiller.common.safe_copy_skill`** (новый): единый безопасный copy скилла (containment +
  снятие symlink/файла/каталога + TOCTOU-перепроверка + `SKILL_IGNORE`) — общий для
  `vendor.copy_skill` и `skillset.sync_skillset` (раньше дублировались, расходясь в безопасности;
  TOCTOU-фикс Phase 3 теперь и в vendor). Legacy `vendor` re-copy стал clean-replace (как skillset).
- Осознанно НЕ тронуто: `apply_permissions` (skiller→harness — это граница делегирования через
  subprocess, не дубль); консолидация 3 валидаторов конфигов (schema-расходящиеся — отдельный
  риск/PR).

### Fixed (аудит 2026-06 — Phase 3: надёжность логики подключения)

- **TOCTOU в `skillset.sync_skillset`:** между удалением `dst` и `copytree` чужой процесс мог
  пересоздать путь симлинком наружу (copytree пошёл бы по нему). Добавлена пере-проверка после
  удаления: `dst` существует → гонка, пропуск (fail-closed).
- **Валидация `skills-lock.json` (`load_lock`):** битый/неструктурный lock больше не трактуется
  МОЛЧА как пустой (это вело к перекопированию всех managed-скиллов). Теперь `warn` + пересборка
  из конфига; проверяется наличие dict `skills`.
- **`connect`: дрейф пути marketplace — действенная подсказка.** Directory-источник с ДРУГИМ путём
  (репозиторий переехал → плагины не грузятся) теперь даёт `⚠` с командой `--fix-path`/`update`,
  а не молчаливый «keeping it». Иной тип источника (github/…) оставляем как осознанный выбор.
- **`apply_permissions`: видимость провала.** Ненулевой rc harness с ПУСТЫМ stderr раньше молчал
  (пресеты deny/allow не легли незаметно) — теперь `warn` всегда, с командой перезапуска.
- **Порядок lock→manifest задокументирован как намеренный** (lock — источник истины детекта
  `plan_sync`, пишется авторитетно; manifest — производная): защита от «починки наоборот».

### Added (аудит 2026-06 — Phase 2: умное подключение, экономия токенов)

- **Курируемый лёгкий `core`-плагин (connect-канал).** CORE-политика `connect` теперь раздаёт в
  каждый проект ОДИН лёгкий плагин `core` (== `CORE_SKILLS`, 7 скиллов) ВМЕСТО целых бакетов
  `general`(19)+`oss-dev`(10). marketplace-запись `source:"./"` + явный `skills[]` грузит РОВНО
  эти 7 скиллов (скиллы физически остаются в своих бакетах — без копий/симлинков; механизм
  подтверждён докой Claude Code). **Экономия резидентного ⊕ tier-0: 1956 → 476 ток ≈ −1480
  ток/проект на КАЖДЫЙ запрос.** `--no-core` отключает; `registry.py` эмитит плагин, `validate.sh`
  гейтит (skills-пути существуют). Миграция: онбордженным проектам со старыми `general/oss-dev`
  `connect` подсказывает снять их (merge-only, сами не трогаем).
- **Budget-aware connect.** `connect` печатает строку `Резидент: ~N ток ⊕ tier-0 (M скиллов)` —
  цена набора видна ДО записи (источник математики — единый `budget.skill_budget`). «Умное
  подключение»: меньше плагинов / `--no-core` → дешевле.
- **Кириллица убрана из 21 EN-описания** (резидентный tier-0): 20 скиллов + `generate-skill`
  переведены на английский канон (RU-источник остаётся в `SKILL.ru.md`), триггеры активации
  сохранены. tier-0 по всем 195: 12375 → 11732 ток (−643). EN дешевле RU у токенайзера.
- **CI-гейт описаний** (`validate.sh`): кириллица в `description`/`name` SKILL.md → ERROR
  (SKILL.md — EN-канон, резидентный tier-0); `description` > 450 симв → WARN (раздутый налог).
  Предотвращает регресс — экономия закрепляется.

### Fixed (аудит 2026-06 — Phase 1: quick wins)

- **Коллизия имён скиллов устранена:** `php/naming-conventions` → frontmatter `name:
  php-naming-conventions`. Реестровая by-name карта (`lock._registry_map`,
  `vendor.build_requires_index` через `setdefault`) молча роняла один из двух скиллов с именем
  `naming-conventions` (general+php). Обновлена ссылка в агенте `php/agents/laravel-implementer`,
  реестр перегенерён, EN-маркер перештампован.
- **Валидация `project.id` (maind):** id ограничен `[A-Za-z0-9._-]` (`config.PROJECT_ID_RE`) —
  он идёт в scope-маркер памяти `[[s:project:<id>]]` и namespace; спецсимволы (`]`, пробел,
  перевод строки) ломали парсинг scope при recall/forget и могли подменить чужой scope.
- **`config.json` пишется с правами `0o600`** (секреты узла): `core.atomic_write_text/json`
  получили опц. `mode=` (chmod на `.tmp` ДО `os.replace` — без окна world-readable);
  `projects.write_config` применяет `0o600`.
- **eval-ассершены `file_exists`/`file_absent` защищены от traversal** (`is_within`): `value`
  из `evals.json` (в т.ч. внешних скиллов) не вырвется за каталог прогона (fail-closed).
- **MCP-обработчик ошибок логирует КЛЮЧИ аргументов** инструмента (не значения — память/секреты)
  для диагностики; голые `except: pass` в `probe`/`memory` снабжены поясняющими комментариями.
- **`agentpacks.do_upgrade`:** логика категоризации файла вынесена в чистую `categorize_file_change`
  (тестируемая матрица new/user-owned/conflict/safe-apply/nochange).
- **Маркер ручных счётчиков** в `docs/index.md` («195/45» — сверять с `skiller registry`).

### Fixed (skiller — drift-устойчивость путей и корень marketplace)

- **`connect`: source marketplace указывает на КОРЕНЬ монорепо**, а не на каталог пакета
  (`env.root`). `marketplace.json` генерируется в корне репо с относительными `source`-путями;
  раньше `connect` объявлял marketplace под `packages/skiller`, где Claude Code не находил
  `.claude-plugin/marketplace.json` и плагины не подключались. Добавлен флаг `--fix-path` для
  обновления протухшего пути в существующих настройках.
- **`resolve_skillset`/`_match`: drift-устойчивость после раскола бакетов** — старый путь
  `oldbucket/skill` (напр. `frontend/vue` → `frontend-vue/vue`) больше не теряется молча: при
  промахе по полному ключу токен-путь добивается по базовому имени, а вызывающий печатает
  migration-warning со старым→новым путём (`обновите .swissknifeman/config.json`). Регресс-тест.

### Changed (аудит — добивка отложенного: super-skill + Serena-пин)

- **3 vendored super-skill демотированы в «навигаторы»** (`pm/product`, `architect/engineering`,
  `operator/operations-cx`) — они дублировали зрелые гранулярные нативные скиллы (9/13/5) и
  перехватывали весь бакет over-broad триггером («any … work»). `description` сужен до «обзор
  бакета; для конкретной задачи → granular skill», в тело добавлен блок обратных ссылок на
  гранулярные. Конфликт триггеров устранён, провенанс (upstream `notify`) сохранён.
- **Односторонние границы Group B закрыты:** `research/research`→`general/verify-claims` (RAG),
  `legal/legal`→`architect/legal-compliance`, `security/security`→`architect/security-design`
  (run-time ↔ design-time). 7 super-skill-only бакетов (creative/finance/legal/…) оставлены —
  они единственное покрытие домена.
- **Serena запиннована на тег релиза** (`constants.SERENA_SRC = git+…/oraios/serena@v1.5.3`,
  было bare-main) — breaking-изменение в main не сломает код-граф у всех проектов внезапно. Один
  bump-пойнт. Версия **верифицирована через RAG** (последний релиз v1.5.3, 2026-05-26;
  `@agentmemory/agentmemory ^0.9.26` и jscpd-`npx --yes` проверены — актуальны, действий не нужно).

## [0.5.0] - 2026-06-26

### Fixed (аудит — устойчивость фан-аута, гейты CI, хвосты)

- **maind sync — fail-soft фан-аут** (`sync.run_sync`): падение одного провиженера больше НЕ валит всю
  раскатку — остальные отрабатывают, упавший помечается `status=failed` per-project (виден в выводе,
  код возврата `cmd_sync` ненулевой). `_agent_pack_run`: `rc!=0` → `failed` (был `skip` — провал
  рендера пака был невидим); `harness недоступен` остаётся graceful `skip`.
- **validate.sh: гейт двуязычной свежести** (секция 14) — `check-translations.sh --strict`: правленый
  `SKILL.ru.md` без регенерации `SKILL.md` (или без `ru-source-sha256`) теперь падает в CI, а не молчит.
- **bin/swissknifeman:** убран мёртвый алиас `validate` (skiller-команды такой нет — роутинг давал
  «Неизвестная команда»).
- _Проверено, НЕ баг:_ `config.example.json` `type=node-package` + `code_language=python` — намеренная
  демонстрация override смешанного репо (есть `_comment_code_graph`), не дефект.
- _Отложено (tracked):_ RAG-верификация актуальности внешних пинов (`@agentmemory/agentmemory ^0.9.26`,
  Serena git-pin, jscpd, ruff) — по методологии `decision-verification` делается ПЕРЕД bump'ом
  зависимости; bump'а здесь нет. Аудит upstream-super-skill (name=dir, обратные ссылки) — отдельный
  per-skill пасс.

### Added (аудит — покрытие локальных скиллов + сценарные рецепты архетипов)

- **Новый governance-скилл `harness-operations`** (`.claude/skills/`) — у пакета `harness` не было ни
  одного операционного скилла. Карта команд (`permissions`/`mcp`/`hooks`/`agent-packs`/`doctor`),
  каталог пресетов (`settings.*` по стекам, `mcp/<name>.json`, режимы auto-approve), и недокументированная
  подсистема **agent-packs** (4 стек- + 4 роль-пака с `pack:if`-шаблонизацией). Чтобы агент не гадал
  при задаче на окружение Claude Code.
- **`maind-overview` расширен:** `maind verify` (пруф-оф-лайф vs `health`), команды реестров/оркестрации
  (`projects`/`agents`/`namespaces`/`workspace`/`run`/`fleet`/`migrate`/`deploy`), таблица 11 MCP-инструментов
  с заметкой об изоляции scope (per-project сервер ограничен своим проектом).
- **Архетип Blender** — был пробел: `.blend`/`bpy`-проект детектился как `standalone`. Добавлены
  `blender` в `core.PROJECT_TYPES`/`LANGUAGE_BY_TYPE` (python) + детект (`*.blend`/`blender_manifest.toml`/
  `import bpy`, раньше python-backend) + `profiles/blender.json` (бакеты blender/blender-modeling/python/
  quality). Тесты — `core/tests/test_core.py` (+3).
- **`docs/guide/archetypes.md`** — рецепты 9 архетипов (детект → бакеты/MCP/пресеты/agent-pack) +
  **неочевидные развилки** (connect vs vendor, CORE, память, namespace, Serena, Nuxt-vs-Vue-SPA) — чтобы
  онбординг типового проекта не порождал вопросов. В nav skiller-доков.
- **Сценарные тексто-кейсы (eval-харнес)** заведены для CORE-скилла `general/compact-responses`
  (`evals/{evals,pressure,triggers}.json` — типовые задачи + соблазны + точность триггера). Покрытие
  `evals/` 3→4; механизм и расширение задокументированы в `archetypes.md`.

### Fixed (аудит — свод дрейфа документации после раскола бакетов php/frontend)

- **862 протухших ссылки `php/<skill>` / `frontend/<skill>` переписаны** на актуальные бакеты по
  `skills.json` (`laravel-*`/`frontend-*`/`php-packages`/`azguard`/`botkit`/`general`) — после раскола
  ядер `php`/`frontend` на тонкие бакеты сотни кросс-ссылок в `routing.md`, `boost-compatibility.md`,
  `guide/*`, телах скиллов и `snippets/`/`references/` указывали в несуществующие пути. Свод name-driven
  (только известные скиллы, словные границы → без ложных замен), бакеты — соседние каталоги, поэтому
  относительные ссылки переписываются корректно. SKILL.ru.md правились синхронно с SKILL.md,
  ru-source-sha256 перепроставлен (`check-translations` чист). **Регресс-гейт** в `validate.sh` (секция
  13): протухшие `php/<skill>`/`frontend/<skill>` в `skills/`+`docs/` пакета → ошибка.
- **Счётчики и hero-ссылки выправлены:** корневой `CLAUDE.md` «20 плагинов» → «49»; `docs/index.md`
  hero `/guide/`→`/skiller/guide/` (был 404), «65+ скиллов в 10 bucket-ах» → «195 скиллов в 45».
- **skiller `CLAUDE.md`:** добавлен модуль `skillset.py` (vendor-канал `sync`/`do_sync`), исправлена
  атрибуция `sync` (была `update.py`/`vendor.py` — реально `skillset.py`), CORE-список vendor доведён
  до 7 (== `CORE_SKILLS`: добавлены `mcp-advisor`, `verify-claims`).
- **Governance-скиллы (always-loaded):** `ecosystem-integration` — починен битый канонический линк на
  `onboarding-decision-tree.md` (`../../../packages/maind/docs/guide/`); `release-discipline` — `./scripts/
  validate.sh` (в корне нет) → пер-пакетный `packages/<пакет>/scripts/validate.sh`.

### Changed (аудит — дедуп реестра: token-efficient вне CORE)

- **`general/performance` (`token-efficient`) перенесён `general` → `ai`** (`skills/ai/performance/`).
  Это Perplexity-environment super-skill (get-zeked, `notify`), дублирующий нативный
  `general/compact-responses` и сидевший в бакете `general` = CORE → раздавался плагином в КАЖДЫЙ
  connect-проект. `general` обязан быть минимальным/кросс-стек (skill-taxonomy); среда-специфичный
  дубль там не место. Перенос непокусочный (провенанс `upstream.json` сохранён, путь относительный),
  `presets/agent-context.json` перенаправлен на `ai/performance`, реестр перегенерирован
  (`skills.json`/`_index.md`/`graph.md`/`budget.md`).
- _Отложено отдельным upstream-проходом:_ 10 vendored super-skill имеют `name != каталог`
  (`pm-super-skill` vs `pm/product` и пр.) и не линкуются на гранулярные нативные скиллы. Правка
  затрагивает upstream-канон + провенанс каждого — это аккуратный per-skill пасс (и, возможно,
  отдельное решение, нужны ли эти композитные super-skill в реестре наряду с гранулярными), а не
  быстрый свод. `reka-ui-cva` уже `requires: [tailwind-conventions]` (находка аудита неактуальна).

### Fixed (аудит — логика раздачи скиллов: requires / update / CORE)

- **`sync` теперь резолвит транзитивные `requires`** (`skillset.resolve_skillset`). Skill-granular
  `include` молча терял зависимости (64/195 скиллов их объявляют): `include: [api-design]` копировал
  api-design, но не его `requires: [data-schema]`. Добавлен транзитивный обход (паритет с
  `vendor.resolve_requires`): `exclude` по-прежнему побеждает зависимость с warning. Регрессия —
  `test_skillset.py::{test_sync_pulls_transitive_requires,test_sync_exclude_beats_requires}`.
- **`skiller update` распознаёт sync-канал** (`update.update_one`). sync и legacy-vendor пишут
  ОДИН `.swissknifeman-manifest.json`, поэтому на sync-проекте `update` уходил в legacy `do_vendor`
  (bucket-granular из `.swissknife.json`/профиля), игнорируя skill-granular `.swissknifeman/config.json`.
  Теперь при наличии sync-конфига `update` пере-применяет его через `do_sync` (как уже делает
  `integrate`). Регрессия — `test_update.py::test_update_routes_sync_config_to_sync`.
- **CORE-фолбэк канал-независим** — `MINIMAL_BUCKETS` (набор для нераспознанного типа проекта) втягивал
  бакет `system` целиком, включая `system/{shared-memory,cross-project-coordinator}` — ровно дубли
  хаба maind, что CORE-политика гонит через `DEFAULT_EXCLUDE`. Теперь `MINIMAL_BUCKETS == CORE_BUCKETS`
  (general+oss-dev) — фолбэк не противоречит политике.
- **Зарезервированные ключи `.swissknife.json` честно помечены** (`config.validate_config`) — `shape`/
  `stacks`/`coordinator_ignore`/`presets` валидировались, но не читались connect/vendor; теперь
  предупреждают «зарезервирован/не действует» (как `skills_map`), а не молчат. Удаление ключей не
  делаем (валидация строгая — сломало бы существующие конфиги); `memory_brain` реально потребляется
  (integrate↔harness) и не трогается.

### Fixed (аудит — фундамент-дедуп раздачи скиллов: единые примитивы)

- **Утечка `SKILL.ru.md` (русский SSOT) в downstream-проекты через `sync`** — канонический
  Claude-канал `skillset.sync_skillset` копировал каталог скилла, исключая лишь
  `upstream.json`/`.claude-plugin`, но НЕ `SKILL.*.md`/`evals/` (в отличие от `vendor.copy_skill`).
  Полный русский источник и поведенческие тесты ехали в каждый из 195 скиллов потребляющего
  проекта. Введён ЕДИНЫЙ `common.SKILL_IGNORE = (upstream.json, .claude-plugin, SKILL.*.md, evals)`
  — `vendor` и `sync` теперь игнорируют один список (раньше дублировали и разъехались). Регрессия —
  `tests/test_skillset.py::test_sync_excludes_ru_source_and_evals`.
- **Дедуп containment-хелпера** — `connect`/`vendor`/`skillset`/`doctor` дублировали
  `str(p.resolve()).startswith(str(root.resolve()) + os.sep)`. Сведено к `common.is_within`
  (резолвит symlink — для prune) и `common.is_within_lexical` (без резолва финального symlink —
  для install-гейта против traversal через `../` в имени скилла). `vendor.copy_skill` теперь снимает
  symlink на месте назначения до `copytree` (иначе писал бы сквозь него в чужую цель).
- **Атомарная запись JSON** — `vendor.write_manifest` писал манифест сырым `write_text` (краш
  оставлял битый файл, ломающий `update`/`connect`/`status`); `skillset.write_lock`/`lock.cmd_lock`/
  `topology.save_topology` вручную дублировали `tmp+os.replace` без подчистки `.tmp`. Все переведены
  на `core.io.atomic_write_json`. `harness/apply-permissions.sh` пишет settings атомарно (tmp+`mv -f`)
  и падает с русской ошибкой (а не traceback) на битом входном JSON.

### Security (аудит — закрыты 2 бреши: RCE и обход namespace-изоляции памяти)

- **maind MCP: серверный энфорс изоляции namespace** (`lib/maind/mcp.py`, `memory.py`). Раньше
  `scope = args.get("scope") or default_scope` отдавал приоритет КЛИЕНТУ: агент проекта A,
  передав `{"scope":"project:B"}`, читал/писал/удалял приватную память проекта B (а графовые
  инструменты — топологию по произвольным `from`/`project`), хотя сервер раскатан запинненным к
  своему проекту (`maind mcp --scope project:<id>`). Теперь сервер, запинненный к проекту,
  ограничен бакетами СВОЕГО проекта (`recall_scopes`: приватный + `ns:<его группы>` + `global`);
  графовые инструменты режут доступ к проектам, не делящим namespace (`namespaces.shares`);
  `forget` подтверждает владение фактом по маркеру `[[s:<scope>]]` до удаления (memoryId глобален).
  Хаб-режим (`default_scope=global`) и явный `MAIND_MCP_ALLOW_CROSS_SCOPE=1` — без ограничений
  (back-compat/админ). Регрессия — `tests/test_mcp.py::TestScopeIsolation` (+9).
- **harness review-gate: устранён RCE при открытии чужого репо** (`configs/claude-code/hooks/review-gate/review-gate.sh`).
  Хук на `SubagentStop` (ставится глобально) исполнял `check_command` из project-local
  `.claude/review-gate.config.json` через `bash -c` — любой посторонний репозиторий получал
  произвольное исполнение кода. Теперь `check_command` берётся ТОЛЬКО из machine-owned
  `$HOOK_DIR/config.json`; project-local конфиг честно исполняется лишь при явном opt-in владельца
  машины (`ALLOW_PROJECT_CONFIG=1` в `$HOOK_DIR/env.ini`).
- **harness auto-approve strict: интерпретаторы и awk/sed больше не авто-одобряются**
  (`configs/claude-code/hooks/auto-approve/config.json`). `_normalize` вырезает тело в кавычках,
  поэтому `python -c "<код>"` / `awk 'BEGIN{system(…)}'` виден анализатору лишь головой команды —
  одобрять её = одобрять произвольный код. `trust_inline_interpreters` → `false` по умолчанию;
  `awk`/`sed` убраны из `allow` (включение inline-интерпретаторов — осознанный per-project выбор).
  Регрессия — `harness/tests/test_security_hooks.py` (+5, реальные хуки через subprocess).

### Added (skiller — eval-харнес скиллов + composite-upstream `merge`)

- **`skiller eval <bucket>/<name>`** (`lib/skiller/eval.py`) — поведенческое тестирование скиллов,
  которого не было (валидация была только структурной). Формат `evals/`: `evals.json` (кейсы +
  **детерминированные** ассершены `contains`/`not_contains`/`regex`/`not_regex`/`file_exists`/
  `file_absent`/`min_words`), `pressure.json` (сценарии-соблазны «пропустить скилл» — TDD для
  документации), `triggers.json` (точность срабатывания `description`). Прогон with-skill vs
  `--baseline` через `claude -p` → `benchmark.json` (pass-rate, токены/тайминги mean±stddev, Δ);
  `--static` пишет HTML-отчёт; `--scaffold` создаёт стабы; `--triggers` — оптимизация описания
  (≤150 симв., правка через `SKILL.ru.md`→EN). Адаптировано (методология, не код) из Anthropic
  `skill-creator` + obra/superpowers `writing-skills`. **CI офлайн:** нет `claude` → мягкая деградация.
- **Гейт и покрытие в `validate.sh`** — жёсткая валидация формата заведённых `evals/*.json` + сводка
  `evals coverage: X/Y` одной строкой (без per-skill шума). `generate-skill` и root-скилл
  `skill-authoring` переведены на **eval-first**. `evals/` НЕ вендорится (`vendor.copy_skill`) и
  исключён из `skill_content_hash`. Сиды: `general/verify-claims`, `general/anti-drift`,
  `quality/code-review`. Юнит-тесты — `tests/test_eval.py` (офлайн).
- **upstream.json `strategy: merge`** — скилл, собранный из **нескольких внешних источников**:
  `origins[]` с ролями (ровно один `base` + ≥1 `supplement`/«suggest», с подсказкой `note`/`suggest`
  чем дополнил). Синк **ручной под управлением агента**: на дрейфе любого origin
  `merge.review_pending=true` блокирует `validate.sh`/`registry`/релиз до ручного пере-merge
  (как гейт `fork`), авто-overwrite запрещён. Валидация в `validate.sh`; DX-схемы
  `schema/{evals,upstream}.schema.json`; доки `docs/guide/evals.md` + `upstream-sync.md`.

> Контекст: рецензия трёх внешних skill-репозиториев (anthropics/skills, obra/superpowers,
> affaan-m/ECC) — закрыт крупнейший пробел реестра (поведенческое тестирование скиллов) и добавлен
> провенанс composite-скиллов из нескольких источников с ручным agent-merge.

### Added (verify-claims — RAG-верификация внешних фактов в ревью и планировании)

- **Скилл `general/verify-claims`** (CORE, двуязычный RU→EN) — эпистемический гейт против решений по
  устаревшему знанию. Классифицирует заявление: **repo/code-grounded** (читаю код — без проверки) ·
  **стабильное общее знание** (без проверки) · **внешнее + staleness-чувствительное** (версии/API,
  «ещё актуально», best practice, рынок, возможности чужого сервиса/MCP, цены) → **верифицировать через
  RAG**. Лестница движков (дешёвый первым): **context7** (доки библиотек) → **Perplexity** (native MCP при
  `PERPLEXITY_API_KEY`, иначе keyless `perplexity-web`) → **WebSearch/WebFetch** → эскалация в `research/research`.
  Цитата + confidence (high/medium/low). Спец-клауза: при разборе чужого аудита внешне-мировые вердикты
  до-проверять **даже если аудит «полный»**. Добавлен в `CORE_SKILLS`.
- **`general/mcp-advisor`**: строка `perplexity` в карте серверов + кросс-ссылка на `verify-claims`
  (комплементарны: *что подключить* ↔ *когда/как доставать факт*).
- **Каталог harness**: `configs/claude-code/mcp/perplexity.json` (`@perplexity-ai/mcp-server` + env
  `PERPLEXITY_API_KEY`). Имя пакета **верифицировано через RAG** (текущий официальный `@perplexity-ai/mcp-server`,
  не legacy `server-perplexity-ask` — ровно та staleness, что ловит `verify-claims`).
- **Цепочки планирования**: `verify-claims` `produces_for: [architecture, tech-stack-selection]` (граф-рёбра) +
  house-style запрет «фиксировать внешние факты по памяти — сначала `verify-claims`» в `architect/architecture`
  и `architect/tech-stack-selection`.

> Контекст: запрос — встроить проверку внешних фактов через RAG (знание модели имеет порог, бывает неполным/
> ошибочным) в **ревью аудитов** и **большое планирование**. Repo-grounded вердикты (чтение кода) безопасны;
> внешние факты — верифицировать движком по лестнице. Дисциплина зафиксирована скиллом и применяется в процессе.

### Added (skiller — рецензия плана Perplexity: mcp-advisor, github-ops, слои)

- **Скилл `general/mcp-advisor`** (CORE, двуязычный RU-источник→EN-канон) — чеклист **подбора
  MCP-серверов под проект** при онбординге/синке. Закрывает пробел: профили/онбординг прикручивают
  MCP статично (почти всем — только `context7`), без предложений что подключать. Меню = каталог
  harness (context7/playwright/github/fetch/sequential-thinking/filesystem) + хаб `maind`; по каждому —
  когда нужен/не нужен и цена (схема в каждом запросе + permissions + Node/uvx-деп). Правила: память/граф
  через `maind` (не generic `memory`-MCP), рутинный GitHub-review через `gh` CLI (не тяжёлый `github` MCP).
  Добавлен в `CORE_SKILLS`; кросс-ссылка с `context-economy` (подбор ↔ обрезка).
- **Пресет `github-ops`** — бандл разбросанного GitHub-набора: `roles/open-source-maintainer` +
  `oss-dev/{github-flow,gh-review,issue-triage,release-engineering,oss-governance}` + `devops/ci-cd`.
  Единственный реальный пробел из «Этапа 3» плана (скиллы были, единого пресета — нет).
- **Доки**: `routing.md` — секция «Архитектурные слои: что куда» (4-слойное правило-стоп на реальном
  3-пакетном сплите skiller/maind/harness, ссылки на канон пакетов); `skiller/docs/guide/upstream-sync.md`
  — кросс-ссылка на каталог источников `references/README.md` (дискаверабилити каталога из сайта доков).

> Контекст: рецензия `research/swissknifeman_final_plan.md` (внешний аудит Perplexity). Большинство
> «этапов» оказались уже сделаны (MCP-façade `maind` 11 tools, профили/пресеты, upstream-каталог, качество
> кода `cde47b8`) или переосмыслены на 3-пакетный сплит; форма-дубликаты (`config.engines/packs`, `swiss.*`
> переименование MCP, ручной `capability-matrix`, `docs/upstream/`) **отклонены** как параллельные реестры.
> Взяты только не-дублирующие слайсы (этот блок). Полный разбор с фаворитами —
> `research/swissknifeman_final_plan_review.md`.

### Added (skiller — рецензия аудита архитектуры: init, JSON-схемы, level, доки-истина)

- **`skiller init`** — новая команда: создаёт `.swissknifeman/config.json` (vendor) из
  автодетекта типа проекта + профиля, **без** копирования скиллов (это делает `sync`).
  Идемпотентна (существующий конфиг не перетирается без `--force`), `--dry-run`. Логика —
  общий хелпер `materialize_skillset_config` (вынесен из `do_sync`, чтобы init и sync не
  разъезжались). Зарегистрирована в `cli.py` + лаунчерах `bin/skiller`/`bin/swissknifeman`.
- **JSON-схемы конфигов** (`schema/swissknife.schema.json`, `schema/swissknifeman-config.schema.json`)
  — DX/IntelliSense через `$schema`. Рантайм-валидация остаётся ручной и **stdlib-only** (без
  pip `jsonschema`); синхрон схемы↔код держат гейт `tests/test_schema.py` (гоняется в `validate.sh`)
  и две проверки `skiller doctor`. Валидаторы конфигов теперь пропускают ключи на `_`/`$`.
- **Опц. поле фронтматтера `level`** (`core|foundation|extension`) — само-документирование слоя
  иерархии; пишется в `skills.json` (omit-when-empty), enum-гейт в `validate.sh`, tally-потребитель
  в `skiller registry`, добавлено в preserve-list генератора канона и `SKILL_TEMPLATE.md`. Opt-in:
  ни один скилл пока не помечен (нулевой churn sha256 у потребителей).
- **`content_sha256` — дрейф-хеш по всему каталогу скилла** (`common.skill_content_hash`,
  пишется в `skills.json` рядом с `sha256`). Закрывает дыру: инкрементальный `sync` детектил
  дрейф только по `SKILL.md` и **пропускал** правки в `snippets/`/`references/`. Теперь `plan_sync`
  ловит их и обновляет скилл. Игноры — как у vendor (`upstream.json`/`SKILL.*.md`/`.claude-plugin`),
  хешируется ИСТОЧНИК (копия отличается игнорами). Старые локи без `content_sha256` деградируют
  корректно (дрейф по `SKILL.md`), поле доpopulated при следующем sync **без** перекопирования.
  Единственный принятый пункт из аудита `research/skiller_delivery_modes_and_manifest.md`.
- **Документация-истина**: новый канон `docs/guide/skills-architecture.md` («реальное состояние»,
  читается первым — против straw-man) + запись в навигацию (standalone + зонтичный VitePress).
  Truth-up локальных скиллов `package-architecture`/`project-tooling-runbook` (два конфига; тела
  скиллов читает Claude Code, не Python). Decision-record в шапках обоих research-доков аудита
  (были помечены «Готов к реализации» — теперь «отрецензировано, НЕ как есть»).

### Rejected (рецензия аудита — обоснованные отказы)

- **3-уровневый рефакторинг скиллов** (core/foundation/extension) — отклонён: иерархия/зависимости/
  уровни уже есть; «бери подскиллы» решено skill-granular vendor; цена churn (193 двуязычные пары,
  49 плагинов, локи) несоразмерна. Выгода взята дёшево полем `level`.
- **Подсистема кэширования** (`SkillMemoryCache`/disk-cache/команды `cache`) — отклонена: нет
  вызывающего (тела скиллов читает Claude Code, не Python; `load_skill` не существует). Prompt
  caching у Claude Code автоматический. Микро-мемоизация парса фронтматтера тоже не внедрена
  (конфликт с конвенцией «без модульных глобалей», выигрыш ниже порога восприятия).

### Added (skiller — двуязычные скиллы: компактный EN-канон + полный RU-источник)

- **193 скилла переведены в двуязычную модель.** Локальные (139): `SKILL.ru.md` — полный русский
  ИСТОЧНИК (его правит человек, SSOT), `SKILL.md` — компактный английский канон (генерируется из RU,
  грузит только его агент; русский в контекст не попадает). Внешние (54): EN-канон от upstream не
  тронут, добавлена `SKILL.ru.md`-справка. Все 139 EN-канонов прошли adversarial-верификацию фиделити
  (ни одно правило/условие/порог/код/путь не потеряно, ничего не добавлено).
- **Экономия ~32% токенов** на телах локальных скиллов (≈268K→182K ток): английский у токенайзера
  Claude плотнее кириллицы. `budget.py` — языко-зависимая оценка (кириллица ~2.2 / латиница ~4.0
  chars/tok); карта `docs/guide/budget.md` показывает эффект.
- Поток правок: правишь `SKILL.ru.md` → регенеришь `SKILL.md` (`prompts/generate/claude-canon-from-ru.md`)
  → `check-translations.sh --stamp`. Когерентность канона метит `<!-- ru-source-sha256 -->`.
- `*.ru.md` НЕ вендорятся в проекты (едет только EN-канон); генерация выполнена многоагентным Workflow.

### Added (skiller — внедрение mattpocock/skills: инженерная методология + встраивание в цепочку)

- **9 импортированных скиллов** из [mattpocock/skills](https://github.com/mattpocock/skills) (MIT),
  fold-in в существующие бакеты (без нового бакета), `strategy: notify`:
  `quality/diagnosing-bugs` (6-фазная отладка: feedback-loop до гипотез, тег `[DEBUG-xxxx]`),
  `quality/tdd-discipline` (red-green-refactor вертикальными срезами, не горизонтально),
  `architect/codebase-design` (глубокие модули Ousterhout/Feathers: depth/seam/deletion-test;
  свёрнут HTML-report из improve-codebase-architecture),
  `architect/domain-modeling` (глоссарий `CONTEXT.md` + ADR инлайн, мульти-контекст),
  `general/implement` (цепочка implement→tdd→review, **user-invoked**),
  `oss-dev/to-issues` (план→issue вертикальными срезами + поля Affected projects/Environment, **user-invoked**),
  `oss-dev/issue-triage` (стейт-машина триажа + роль `needs-device-access` для железа, **user-invoked**),
  `oss-dev/resolving-merge-conflicts`, и центральный `general/grill-with-docs` (грилинг + доменная
  модель против внешних API/RFC-спек, **user-invoked**).
- **Уровень + условия активации на каждый скилл** (ответ на «не папки, а в цепочку»): компактный
  `description`-роутер (ярус-0 always), lean-тело (ярус-1 on-trigger), под-файлы mattpocock →
  `snippets/` (ярус-2 on-demand); сайд-эффектные (implement/to-issues/issue-triage/grill-with-docs) —
  `disable-model-invocation: true`; `general/git-safety` — `lifecycle: init`. НЕ в CORE — opt-in.
- **Встроены в цепочку рёбрами `requires/produces_for`**: grill-with-docs→{spec-interview,domain-modeling};
  to-issues→github-flow, produces_for→implement; implement→{tdd-discipline,code-review};
  diagnosing-bugs→code-review; codebase-design→{refactoring-plan,architecture};
  domain-modeling→{architecture,api-design,data-schema}; resolving-merge-conflicts→git-commit-rules.
  Плюс секции «Связанные скиллы» в каждом теле.
- **Раздача через presets** — новый `presets/engineering-workflow.json` (сквозной конвейер) +
  расширены `agent-tasks` (grill-with-docs/implement/to-issues), `code-quality` (tdd-discipline/
  diagnosing-bugs), `system-design` (codebase-design/domain-modeling).
- **Расширен `general/spec-interview`** (наш грилинг) — ссылки на `grill-with-docs`/`to-issues`/`implement`.
- **git-guardrails → harness, не скилл** (поправка к аудиту): PreToolUse-хук
  `block-dangerous-git.sh` (+`force-with-lease`/`rebase --onto`) в
  `packages/harness/configs/claude-code/hooks/git-guardrails/`, обёртка-скилл `general/git-safety`.
- **Агенты грузят новые скиллы через `skills:`**: `issue-triager`←`issue-triage`,
  `sprint-planner`←`to-issues`, `review-gatekeeper`←`diagnosing-bugs`/`tdd-discipline`
  (harness agent-packs `role-maintainer`/`role-tech-lead` → 0.2.0).
- **Провенанс**: источник зарегистрирован в
  [references/mattpocock-skills.md](packages/skiller/references/mattpocock-skills.md) (`imported`) +
  per-skill `upstream.json` (sha256/fetched_at, HEAD `5d78bd09`).

### Added (skiller — токеновый бюджет + карта-диаграмма + промты + задел переводов)

- **Команда `skiller budget`** — трёхъярусная модель раскрытия контекста: **⊕ always**
  (`name`+`description`, резидентно в каждом запросе — постоянный «налог»), **↻ on-trigger**
  (тело `SKILL.md`), **⌥ on-demand** (сниппеты). Режимы: `--config F.json`, `--compare a,b`,
  `--json`, `--profile/--buckets/--exclude`, `--no-core`, `--write-map`. Модуль
  [budget.py](packages/skiller/lib/skiller/budget.py) — **единый источник** токен-математики
  (переиспользует `resolve_selection`/`collect_skills`/`resolve_requires`, без дублирования
  выборки). +9 unit-тестов (`tests/test_budget.py`).
- **Карта токенового бюджета** — сгенерированная mermaid-страница
  [docs/guide/budget.md](packages/skiller/docs/guide/budget.md): узел на скилл (по бакетам),
  heat-цвет по ⊕ always, рёбра `requires` = транзитивный налог, таблицы по бакетам и топам.
  Регенерится `skiller registry` (in-process, после графа); пункт в VitePress sidebar.
- **Строка бюджета в `skiller status`** — ⊕ always/↻ bodies набора проекта + топ-3 описаний.
- **Промт-библиотека** [prompts/](packages/skiller/prompts/) (audit/review/generate) — шаблоны
  для сопровождения реестра (то, что `validate.sh` не ловит: пересечения, водность, дубли).
- **Задел переводов** — `SKILL.<lang>.md` gitignored (агент грузит только `SKILL.md`); чекер
  покрытия [check-translations.sh](packages/skiller/scripts/check-translations.sh) (`--lang`,
  `--generate-stubs`).
- *Из аудита Perplexity — отклонено как дубль:* `generate-graph.ts` (= существующий
  `generate-graph.sh`) и `drift-check.ts` (= `validate.sh`); токен-модель аудита исправлена
  (тело ≠ «всегда загружено» → трёхъярусная).

### Added (skiller — пресеты/кластеры скиллов + тонкие бакеты для конфиг-управляемого per-project sync)

- **Слой пресетов** — `presets/<name>.json` (`{name, description, extends?, buckets?, include?}`):
  именованные кластеры скиллов для vendor-выборки. Раскрываются в `resolve_skillset`
  ([skillset.py](packages/skiller/lib/skiller/skillset.py)) ДО формулы **`(presets ∪ buckets ∪ include) − exclude`**,
  с рекурсивным `extends`. Конфиг проекта `.swissknifeman/config.json` ссылается на `presets: [...]`
  (+ `include`/`exclude` оверрайды) → `skiller sync` → `.claude/skills/` + `skills-lock.json`. Только vendor
  (connect бакет-атомарен). Валидация в [validate.sh](packages/skiller/scripts/validate.sh) (refs резолвятся,
  ацикл `extends`); +5 unit-тестов (`tests/test_skillset.py::TestPresets`). `presets`-ключ в `SKILLSET_KEYS`/`CONFIG_KEYS`.
- **Тонкие бакеты вместо монолитного `php`** (44→13 core): `php` стал линяным ядром (laravel, structure,
  conventions, DI, database, repositories, patterns, static-analysis), а feature-области вынесены в отдельные
  бакеты-плагины — `laravel-testing`, `laravel-filament`, `laravel-livewire`, `laravel-data-layer`,
  `laravel-auth`, `laravel-architecture`, `laravel-extras`. Filament/Livewire больше **не тянутся по умолчанию**
  (включаешь точечно). `php-packages` — разработка Laravel-пакетов (9 скиллов). `azguard`/`botkit` — отдельные
  одиночные бакеты (под будущий перенос скилла внутрь самого пакета).
- **Тонкие бакеты вместо монолитного `frontend`** (35→3 core): ядро `frontend` (web-design-guidelines,
  document-writer, filepond-upload) + feature-бакеты `frontend-{vue,nuxt,tailwind,naive-ui,reka,vite,linting,
  animations,figma,wayfinder,backend}`. Nuxt/Naive-UI/Figma и пр. — отдельные плагины, не по умолчанию.
- **19 пресетов** (сквозные стеки): php — `laravel-admin`/`laravel-enterprise`/`laravel-inertia`/`laravel-livewire-stack`;
  frontend — `vue-spa`/`figma-to-frontend`; + кластеры `architect`/`pm`/`general`/`quality`.
- **Профили** под линяный дефолт: `laravel-project` = ядро + `laravel-testing`/`laravel-auth`/`laravel-data-layer`;
  `node-frontend` = ядро + `frontend-vue`/`frontend-vite`/`frontend-linting`/`frontend-tailwind`;
  `php-package` += `php-packages`/`laravel-testing`. Feature-бакеты (Filament/Livewire/Nuxt/…) — opt-in.
- **buckets.json** +21 бакет; **docs**: новый `docs/guide/presets.md`, обновлены `vendor-mode.md`/`profiles.md`/
  `skill-anatomy.md` + раннбук `project-tooling-runbook`. Регенерация `skiller registry` (49 плагинов).
- *Отклонено (Perplexity, с аргументацией):* skiller как PHP-приложение (`src/*.php`) и `.swissknife.yml`/`.lock`
  с нуля — механизм уже есть (Python + JSON); мерж `laravel-package-*` — это upstream-скиллы (мерж рвёт трекинг);
  новые домен-скиллы (fintech/fiscal) — project-local.

### Added (skiller — `strategy: fork`: сопровождение доработанных вендорных скиллов)

- **Новая стратегия `upstream.json` — `fork`** (помимо `replace`/`notify`): внешний скилл с нашими
  правками, который **нельзя автообновлять**. `files[].path` указывает на **pristine-зеркало**
  (напр. `references/source.md`), правки живут в тонкой обёртке `SKILL.md`; на дрейфе апстрима
  ставится `review_pending: true`. Эскалация `replace` (зеркало) → `notify` (сообщить) → `fork`
  (правки + базлайн + ручной перенос + жёсткий гейт).
- **`validate.sh`**: enum стратегий расширен `fork`; **гейт** — `review_pending: true` → ERROR
  (блокирует `skiller registry`/релиз, пока дрейф не перенесён вручную). Проверка bool/`last_review`.
- **`update-upstreams.sh`**: ветка `fork` — `--check` сообщает о дрейфе (exit 10), `--apply`
  стейджит свежий апстрим в `upstream/<name>.incoming.md` и поднимает `review_pending` (зеркало и
  `SKILL.md` НЕ трогаются); новый режим **`--resolve`** — после ручного переноса продвигает incoming
  в зеркало, обновляет `sha256`/`fetched_at`/`last_review`, снимает флаг (работает оффлайн).
- **`ai/ai-agents` переведён `notify` → `fork`**: монолит (2722 стр. в `SKILL.md`) → тонкая
  обёртка-навигатор `SKILL.md` (грузится при активации) + полный апстрим в `references/source.md`
  (грузится по требованию). Закрывает обе оси: context-economy (lazy-load) и трекинг (1 файл ↔ 1 url,
  тривиальный перенос диффа). Блокировка дрейфа — **только в реестре**; в проекты по-прежнему
  вендорится чистая копия (`upstream.json` вырезается). +1 тест (provenance fork через путь
  `references/source.md`, fallback `files[0]`); `*.incoming.md` в `.gitignore`. Доки:
  `upstream-sync.md` (раздел fork), `creating-skills.md`.

### Fixed (skiller — мелочь по аудиту)

- **`context-economy`**: перекрёстная ссылка на скилл `pao` приведена к стандартному формату
  (`` `pao` (bucket: php) `` вместо нестандартного `laravel/pao`).

### Added (skiller — vendor-канал «опубликовать скиллы в репо» на онбординге)

- **`integrate --skills-channel connect|vendor|skip`** + интерактивный вопрос канала (TTY). Канал
  `vendor` для Claude-проекта теперь роутится в **современный `sync`** (`skillset.do_sync`):
  `integrate` материализует `.swissknifeman/config.json` из профиля проекта и применяет `sync` —
  физ. копии скиллов в `.claude/skills/` + `skills-lock.json` (`managed`). Закрывает кейс
  **внешних разработчиков**: проект отдают в команду без доступа к реестру swissknifeman, скиллы
  едут файлами в самом репо (у `connect` marketplace указывает на локальный путь к реестру → у
  чужого разработчика плагины не подключатся). Legacy `do_vendor` (`.ai/.cursor`) остаётся только
  для `--agent cursor|generic`. Выбор канала касается **только скиллов** — память/граф/MCP хаба не
  затрагиваются. +6 тестов (do_sync: материализация конфига / уважение курированного / dry-run;
  integrate: vendor→sync, skip, невалидный канал).
- **`maind onboard --skills-channel` / `swissknifeman setup --skills-channel`** — проброс канала в
  `skiller integrate`; `onboard` интерактивно спрашивает канал (как и механизм памяти), флаг — для
  неинтерактива (дефолт `connect`).
- **Гигиена каналов в `skiller status`**: предупреждение `ДУБЛЬ КАНАЛОВ`, если один бакет активен
  ОДНОВРЕМЕННО как плагин (connect) и вендорен (vendor) — скиллы раздавались бы дважды. Проверка
  (`channel_overlap`) живёт ТОЛЬКО в skiller (владелец скиллов) и доступна из зонтика через
  `swissknifeman skills status` — не дублируется по пакетам. +4 теста.
- **Тесты гигиены `skills-lock.json`** (managed vs чужое): запись, добавленная в lock вручную
  (свой скилл / другой хаб, `managed!=true`), переживает `sync` и не удаляется даже при пустом
  конфиге; ручная чистка managed-записи при живой папке → без `--force` путь считается чужим
  (пропуск), с `--force` скилл чисто пере-усыновляется (одна managed-запись, без хвостов/дублей).
  +3 теста. Закрепляет инвариант «синхронизируем только своё (`managed: true`)».

### Security / Fixed (maind — портабельность генерируемых хуков, без утечки пути)

- **Хук-скрипты maind больше не зашивают абсолютный путь к лаунчеру.** Шаблоны
  `templates/health/*.sh` (memory-digest · session-start · feature-log) резолвят `maind` в рантайме
  (`env MAIND_BIN → command -v maind`), а не подставляют машинно-специфичный
  `<…>/packages/maind/bin/maind` через `_maind_bin` (удалён). Генерируемый артефакт теперь одинаков
  на любой машине; лаунчер не найден → тихий no-op (как при лёгшем демоне). Конфигурируется через
  env `MAIND_BIN` (можно из `.claude/*.env.ini`). Бэк-совместимо: уже раскатанные хуки работают,
  `command -v maind` резолвит тот же `~/.local/bin/maind`. +3 теста (нет abs-пути, есть env→PATH).
- **`.claude/maind-*.sh` (+ `.maind-feature-log.last`, `scheduled_tasks.lock`) в `.gitignore`** —
  генерируемые per-project хуки/рантайм-state не попадают в репо, как `.mcp.json`. Закрывает утечку
  абсолютного пути автора при `git add .claude/`.
- **Аудит MCP** (без изменений — уже чисто): пресеты `packages/harness/configs/claude-code/mcp/*.json`
  портабельны (`npx`/`uvx`/`http`, без abs-путей); `.mcp.json` (с abs-путём maind) уже gitignored,
  шаблон — `.mcp.json.example` с `{{REPO_ROOT}}`, реальный файл генерит `maind` на деплое.

### Fixed (третий аудит skiller — харденинг тихих отказов)

- **`_registry_index` больше не теряет скиллы молча**: запись в `skills.json` без `name`/`path` и дубль
  короткого имени между бакетами теперь логируются `warn` — раньше немой `continue`/`setdefault` ронял скилл
  из синка без следа (по полному пути `bucket/rel` дубль доступен, по короткому имени — первый). +тесты.
- **subprocess в harness с таймаутом** (`common.apply_permissions`, `integrate._run_harness`): `timeout=30`
  + stderr в `warn` — зависший harness (NFS/сеть) больше не морозит `skiller sync` молча; stdout оставлен
  живым (прогресс harness виден). Дополняет returncode-проверку из прошлого аудита.
- **манифест атомарен и трассируем** (`skillset._write_manifest`): запись через `core.io.atomic_write_json`
  (tmp+`os.replace` вместо raw `write_text` — нет полузаписанного файла при крахе) + `installed_at` через
  `now_iso()` (время, не голая дата) + `version` схемы. +тест.
- **frontmatter читает YAML-блок-скаляры** (`common.parse_frontmatter`): `description: |`/`>` (многострочные)
  больше не теряются молча — stdlib-разбор без `pyyaml`, с защитой от значений, начинающихся с `|`/`>`. +тесты.
- **`skills_map` не молчит** (`config.validate_config`): зарезервированный, но нереализованный ключ
  помечается `warn` вместо тихого игнора.

> Отклонено как ложное (проверено по исходнику): path-traversal в `contained()` — код уже добавляет
> `+ os.sep`, пример `/skills_extra` не проходит против `/skills/`; «обрезанная `parse_inline_list`» — функция
> целая; «ввести профили как first-class» — 8 профилей + флаг `--profile` уже есть; рекурсивный `_dir_sha256`
> — намеренно зеркалит per-file хеш реестра (рекурсия рассинхронит lock с `skills.json`); `import yaml` —
> нарушает stdlib-only, заменён stdlib-хендлером.

### Fixed (второй аудит skiller — реальные баги)

- **`integrate` больше не глушит ошибки harness**: `_run_harness` проверяет returncode и `warn`-ит при
  ненулевом — раньше визард молча рапортовал «готово», даже если блок не применился. Graceful
  degradation сохранена (визард не падает).
- **frontmatter устойчив к BOM** (`common.parse_frontmatter`): чтение `SKILL.md` через `utf-8-sig` —
  файл с BOM больше не игнорируется молча. +тест.
- **`projects.json` без дублей**: `upsert_project`/`db_records` нормализуют путь через `Path.resolve()`
  (раньше разные repr одного каталога — `./`, `..`, симлинк — плодили дубли). +тест.
- **`boost.json::skills` сортируется целиком** (`sorted(existing + added)`, не только `added`) —
  детерминированный порядок.

> Отклонено как ложное/over-engineering для Linux-only single-user (с обоснованием в плане): «double-nesting
> `extraKnownMarketplaces`» — это корректная схема Claude Code (подтверждено реальными конфигами);
> frontmatter «режет на `:`» (там `split(":",1)`); TOCTOU/атомарность `copy_skill`; Windows-пути; mmap/
> чтение-частями мелких файлов; ротация `.bak`; `deque` вместо `pop(0)`.

### Security / Fixed (аудит репозитория — зонтик, core, CI)

- **`.mcp.json` выведен из-под git** (`git rm --cached` + `.gitignore`): машинно-специфичный файл
  с абсолютными путями к `maind` (утечка пути автора + ломал клон у других). Шаблон —
  `.mcp.json.example` (плейсхолдер `{{REPO_ROOT}}`); реальный файл генерит `maind` (sync/deploy).
- **`core.atomic_write_text`**: при ошибке записи/`os.replace` подчищает осиротевший `.tmp`
  (`try/except → unlink`) — иначе мусор копился в долгоживущих процессах (напр. `No space left`). +тест.
- **`bin/swissknifeman doctor`**: больше не прерывается на первом отсутствующем лаунчере
  (`need()` бил `exit 1`) — fan-out на все три пакета с агрегацией итогового exit-кода.
- **`install.sh`**: собирает упавшие пакетные установки и завершает `exit 1` со списком — раньше
  печатал «Готово» и выходил 0 даже если пакеты не установились.
- **`scanner-pr.yml`**: имя ветки берётся из репозитория (`git rev-parse --abbrev-ref HEAD`), а не из
  продублированной формулы `$(date +%Y%m%d)` (гонка на границе суток); снят `|| true` с `git push`
  (реальный сбой push больше не маскируется перед `gh pr create`).
- **`core/env.py`**: `BaseEnv.home` default_factory зовёт `Path.home()` при создании (а не модульный
  снимок) — подменённый `$HOME` подхватывается в тестах. Глобал `HOME` сохранён (публичный API). +тест.

### Changed (документация и CI — аудит)

- **README**: добавлен пакет `harness` (таблица + CLI) и корневой роутер `swissknifeman`/`setup`;
  убрана устаревшая фраза «единой консоли-обёртки нет».
- **`CONTRIBUTING.md`** (корневой) — новый: раскладка, dev-установка (stdlib-only/без pip, IDE
  extraPaths вместо pip), тесты/валидация, конвенции, релизная дисциплина.
- **CI `test.yml`**: матрица Python расширена 3.9–3.12 → 3.9–3.13.
- **`MERGE-PLAN.md`** удалён (рабочий артефакт процесса слияния, ценности для пользователя нет).

### Added / Tooling (follow-up аудита — улучшенные варианты)

- **`pyrightconfig.json`**: Pylance/pyright резолвят `from core import …` и межпакетные импорты
  из коробки (`extraPaths`: корень `.` + `packages/*/lib`, `typeCheckingMode: off`) — IDE-DX без pip,
  stdlib-only цел. PyCharm — Sources Root (см. `CONTRIBUTING.md`).
- **`swissknifeman --version` / `-V`**: версия монорепо из `git describe` (фолбэк «dev»). Заодно
  убран висячий `version` из роутера — он делегировал в `skiller version`, которой не существует.
- **Линтер ruff в CI** (job `lint`): `pipx run ruff==0.15.19 check` — эфемерно, ruff НЕ зависимость
  репо; конфиг `ruff.toml`, набор `F,B`, `target-version=py39` (B905 не конфликтует с 3.9). Разовая
  зачистка: 6 неиспользуемых импортов, 8 пустых f-строк, 9 unused loop-vars, 1 broad-except в тесте.
- **Per-project `code_language(s)`** (maind/codegraph): override языка код-графа (str|список) поверх
  `language_by_type` — смешанный репо (python-код + TS-доки при `type:node-package`) граф­ится верно
  без правки общих констант; swissknifeman → `python`. `render_project_yaml` рендерит и список
  (мульти-язык). +тесты.

### Added (harness — режим памяти `maind`)

- **Хук памяти получил режим `MODE=maind`** (`hooks/memory/modes/maind.sh`): делегирует
  `remember`/`recall` в `maind memory` (демон :4111 + изоляция по scope на стороне maind).
  brain игнорируется, scope берётся из проекта (`CLAUDE_PROJECT_DIR` → `match_cwd`). Чинит
  раскол «хук пишет в файлы `core`, MCP читает пустой scope демона»: теперь оба пути идут
  в один стор. Рекомендуется для прикладных проектов; глобальный дефолт пока `federation`.

### Changed (session-observer 0.3.0 — авто-включение логгера)

- **`/observe on` теперь полный чеклист**, который Claude выполняет автоматически:
  установка хука глобально → проводка пресета `observer` в проект → `ENABLED=true`
  → gitignore `.claude/observer/` → напоминание про рестарт сессии. Раньше скилл
  подразумевал только `ENABLED=true`, чего недостаточно для активации логгера.
  Добавлен `/observe off`.

### Docs (мультипровайдерная раздача — dev-план)

- **`skiller/docs/multi-provider-distribution.md`** — dev-план: увести раздачу
  локального `.ai/` контента (CLAUDE.md/AGENTS.md/Cursor) из Laravel Boost в skiller
  (Boost → только MCP). Фиксирует гэп (`vendor.py`/`skillset.py` резолвят реестр, не
  локальный `.ai/`), целевой дизайн и reference-пилот `sibintek-insiders`. Кросс-ссылки
  из `boost-compatibility.md` и `index.md`; пункт в сайдбаре VitePress.

### Added (Observer capture-слой — план agent-skill-binding, Stage D)

- **`harness` observer-хук** (PreToolUse/PostToolUse/Stop), ЭКСПЕРИМЕНТАЛЬНО,
  per-project (`.claude/observer.env.ini` → `ENABLED`, дефолт `false`): пишет
  компактный project-local `.claude/observer/runtime.jsonl` + алерт `LOOP`
  (3+ ошибки подряд), архивирует на `Stop`. **Никогда не блокирует** (наблюдатель,
  не гейт). Проводка — opt-in пресет `settings.observer.json` (`harness hooks
  --preset observer`), не глобально. Разбор — скилл `system/session-observer`.
- **`system/session-observer` 0.2.0** — добавлен `runtime.jsonl`/`archive` в
  источники данных + как включить capture-слой.

### Added (детерминированная привязка скиллов к агентам)

- **Поле `skills:` во frontmatter агентов бакетов** (`skills/<bucket>/agents/*.md`) —
  нативный preload Claude Code (v2.0.43+): полный контент перечисленных скиллов
  инжектится в субагента на старте, без надежды на model-invocation. Привязаны
  `php/laravel-implementer`, `laravel-reviewer`, `laravel-test-writer`. Закрывает
  корень сбоя «агент проигнорировал скилл» (6/7 пропустили `repositories`).
- **Валидация (`scripts/validate.sh`, 10c):** каждый `skills:`-элемент агента обязан
  резолвиться в реальный скилл реестра (`bucket:name`); ненеймспейснутый — warning.
- **`php/laravel-implementer`:** прозовый «ПЕРВЫЙ ШАГ — load via Skill» заменён на
  декларативное поле `skills:`; жёсткие правила оставлены L4-страховкой.

### Added (гейт принуждения + Observer — план agent-skill-binding, Stage B–D)

- **`harness` review-gate** — детерминированный гейт архитектуры на `SubagentStop`
  (`off|warn|strict`, дефолт `warn`): прогоняет настроенную проектом проверку
  (`check_command`), `warn` → подсказка в `additionalContext`, `strict` → блок
  субагента. Без проверки — no-op. L5-рубеж под `skills:`-preload. (Stage B)
- **`system/session-observer`** (skiller, ЭКСПЕРИМЕНТАЛЬНО, per-project toggle
  `.claude/observer.env.ini`) — пост-фактум разбор сессии по JSONL-логам с
  3-осевой аналитикой слабых мест: **агенты** (skill-skip/drift/циклы), **скиллы**
  (gap/thin/dead/correction-after-load), **настройки** (хуки/права). Находки →
  learnings через memory-хук, промоция человеком; замкнутый цикл самопочинки.
  Сниппет `analyze-session.md` (jq/grep-рецепты). Read-only по коду, не live. (Stage C–D)

### Changed (валидация: строгий frontmatter + битые ссылки)

- **`validate.sh` ужесточён** (секция 1a) — раньше проверялось только *наличие*
  обязательных полей; теперь:
  - `risk` ∈ {read, draft, write, external}; `adapters` ⊆ {claude, cursor, fable};
  - `version` — semver (`\d+.\d+.\d+`); frontmatter `bucket` == каталог бакета (для локальных);
  - объявленные в frontmatter `snippets:` обязаны существовать на диске;
  - **внутрискилловые ссылки** `snippets/…` / `references/…` в теле SKILL.md обязаны
    резолвиться (битая ссылка → error).
- Намеренно НЕ проверяем: равенство frontmatter `snippets:` ↔ `index.json` (принятая
  конвенция — index.json самодостаточен, frontmatter-список опционален; 34 скилла),
  и общие `../`/`.agents`-ссылки (раскладка проекта-потребителя у upstream/imported —
  ложные срабатывания). Все новые проверки дают 0 нарушений на текущем реестре.

### Changed (core: дедупликация + защищённый subprocess)

- **`parse_flags`/`parse_args` сведены в `core/cli.py`** — раньше `parse_flags`
  дублировался в skiller и harness байт-в-байт, `parse_args` (надмножество с
  позиционными) жил в maind. Теперь один источник истины, пакеты реэкспортируют из
  своих `common.py` (импорты `from .common import parse_flags|parse_args` не тронуты).
- **`core.cli.run_cmd`** — защищённый запуск подпроцесса (argv-список, без shell):
  `FileNotFoundError`/`TimeoutExpired`/ненулевой код → чистый `die` вместо
  трейсбэка. Применён к `registry`/`hub` (вызовы `generate-*.sh` с `check=True`
  больше не падают трейсбэком).
- **`core.io.safe_load_json`** — единый graceful-ридер JSON (битый/отсутствующий →
  default, опц. `on_error`). Для БД с бэкапом битого файла остаётся доменный
  `maind.common.load_json_db`.
- **Сплит `maind/common.py`**: HTTP-клиент (`http_get_json`/`http_post_json`/`ping`)
  → `maind/http.py`, управляемый markdown-блок (`managed_block`/`upsert_block`/
  `content_hash`) → `maind/blocks.py`. Реэкспорт из `common.py` — импорты
  `from .common import ...` не тронуты (non-breaking).
- Аудит subprocess-вызовов: остальные уже защищены (`shutil.which`-гварды,
  `try/except OSError`, health-poll демона памяти с детектом раннего выхода) —
  не трогали (рекомендация аудита про `shlex.quote` оказалась ложной: argv-списки
  не инъектируемы шеллом).
- **Тесты:** core 12→28 (parse_flags/parse_args/run_cmd/safe_load_json), harness
  14→28 (новое покрытие `doctor`/`settings`/`cli`-диспетчер).

### Added (скиллы дисциплины именования)

- **`general/naming-conventions`** (бакет `general` — CORE-connect, авто-раздаётся в каждый
  проект) — язык-агностичные правила: имя раскрывает намерение, борьба с шумовыми словами
  (`Manager`/`Helper`/`data`/`process`) и комбинаторным взрывом методов (`findByX…OrFail`/
  `…OrNull`). Сниппет `naming-gallery.md` (плохо → хорошо).
- **`php/naming-conventions`** (бакет `php`) — Laravel-конкретика: именование Action/Repository/
  DTO/VO/Enum/Event/Job, таблиц/колонок, разбор анти-паттерна `findByCodeOrFail`-взрыва
  (→ route binding / model scopes по намерению / критерий / один канонический `findByIdOrFail`).
  Сниппеты `naming-antipatterns.php`, `repository-method-naming.php`. Перекрёстные ссылки в
  `repositories`, `code-style-spatie`, `named-arguments`; уточнён чеклист `repositories`
  (единственный канонический lookup, не плодить метод-на-поле).
- Имя `naming-conventions` намеренно живёт в двух бакетах (`general` + `php`): legal под
  plugin-namespaces (connect), в vendor-режиме flat-имена разводятся префиксом бакета.

### Changed

- **Бакет `blender` разрезан на два плагина:** `blender` (универсальный bpy+MCP —
  `version-gotchas`, `mcp-blender`) и `blender-modeling` (параметрический CAD под
  FDM/SLA — `parametric-config`, `threading`, `model-rules`, `config-conventions`,
  `scene-conventions`, `build-loop`). Раньше один бакет смешивал универсальный
  Blender, методологию CAD и приватный workflow проекта DiaBox; диабокс-специфика
  (слой C) вырезана из плагина. Имена деталей в скиллах обезличены
  (`lens/glass/rocket → part/insert/model`). `blender-modeling` зависит от `blender`
  (`mcp-blender` от B не зависит); потребителям модельных скиллов подключать оба плагина.

### Added (agent-framework — каркас агент-практик + continuous-audit)

- **Документация каркаса агентов** (`docs/skiller/agent-framework/`): обзор,
  `framework-overview` (текущее состояние — вход аудита), `decisions-ledger`
  (принято/отклонено + проверенные факты Claude Code), `roles`,
  `skills-index-and-hub`, `post-integration-checklist`. Стойка: **данные + скилл,
  не движок-генератор**.
- **Переиспользуемый аудит-промт** `docs/skiller/workflows/framework-audit.md` —
  периодическая ревизия каркаса через Perplexity (вход: overview + ledger; выход:
  строгие дельта-таблицы); самоякорящаяся петля, не перепредлагает готовое.
- **Архив аудитов** `docs/skiller/audits/` (raw verbatim + триаж двух прогонов
  2026-06-23: universal-framework, agent-teams+ponytail) + ledger
  `references/framework-audits.md`. Sidebar обновлён (standalone + агрегат).

### Changed (hub — видимость агентов и скиллов, Фаза 1)

- **`generate-hub.sh`**: в хаб добавлен срез **«Агенты проекта»** (таблица из
  `.claude/agents/*.md`: роль → назначение → преднагруженные `skills:`) — роли и их
  скиллы теперь видны оркестратору. Каждое имя в `skills:` сверяется с реестром;
  неизвестное помечается `⚠` (preload молча no-op) + WARNING в stderr. Добавлен
  **freshness-штамп** `<!-- swissknifeman:registry sha=… skills=N -->` для сверки
  дрейфа «реестр изменился — хаб не перегенерён» (doctor — Фаза 5). Парс блок-списка
  `skills:` — инлайн в скрипте; общий хелпер в common.py придёт с валидатором (Фаза 3).

### Added (agent-packs — версионируемая pack-система, Фаза 2)

- **Скилл `system/agent-packs`** — playbook установки и версионного апгрейда паков в
  проект-потребитель: детект стека → интервью → рендер+копия → lock; upgrade по
  CHANGELOG-дельте с 3-way reasoning через sha256 в lock (без diff-движка). Стойка:
  агент-driven, не движок-генератор.
- **Пак `backend-laravel` v0.1.0** (`harness/configs/claude-code/agent-packs/`):
  агенты slice-builder/test-writer/reviewer + workflow dev-loop + review-gate хук +
  settings-фрагмент + guideline; обобщены плейсхолдерами (`{{PACK_PREFIX}}`,
  `{{PHP_RUNNER}}`, `{{TEST_RUNNER_CMD}}`, `{{TEST_DB}}`, `{{CHECK_CMD}}`,
  `{{PROJECT_DIR}}`). `pack.json` (manifest) + per-pack `CHANGELOG.md` + README паков.
- **Lock-схема** `.claude/agent-pack.lock.json` (версия + ответы интервью + per-file
  `base_sha256` отрендеренного) — основа upgrade без diff-движка.

### Added (Фаза 3 — роли, path-scoped rules, ponytail-дисциплина)

- **Роль `spec-writer`** (опц.) в паке `backend-laravel` — пишет `docs/specs/<feature>.md`
  (tech-spec) на крупные фичи, НЕ глобальный гейт. Path-scoped `rules/{api-controllers,
  migrations,tests}.md` — нативная авто-загрузка `.claude/rules/` по путям; тонкие
  триггеры, ссылаются на скиллы (без дублирования текста).
- **ponytail-дисциплина впитана в `quality/code-simplifier`** (0.2.0→0.3.0): лесенка
  YAGNI до кода (7 ступеней) + delete-list формат (теги `delete:`/`stdlib:`/`native:`/
  `yagni:`/`shrink:`). Внешний плагин ponytail НЕ подключаем (конфликт с boost).
  Reviewer-роль пака ссылается на over-engineering-проход.
- **`.swissknife.json` схема** (`CONFIG_KEYS`): `shape`/`stacks`/`skills_map` — данные
  профиля для универсальности back/front/fullstack (не движок).
- Сверка имён `skills:` у агентов уже покрыта hub-проверкой (Фаза 1) — отдельная
  команда `validate-agents` не понадобилась.

### Added (Фаза 5 — doctor freshness-дрейф)

- **`skiller doctor`** сверяет штамп `swissknifeman:registry sha=…` в хабе каждого
  зарегистрированного проекта с текущим sha реестра → флагит устаревшие хабы («реестр
  изменился — хаб не перегенерён»). Проекты без штампа (старый хаб) пропускаются.
  Замыкает continuous-audit петлю на детект дрейфа.

### Added (Фаза 6 — Agent Teams, опц.)

- **Пресет `settings.agent-teams.json`** (harness) — opt-in включение экспериментальных
  Agent Teams: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` + `teammateMode` (merge-only,
  сосуществует с auto-approve/review-gate). Предпосылка: Claude Code ≥2.1.178; конфиг
  форвард-совместим.
- **Doc `agent-framework/agent-teams`** — когда брать Teams vs субагенты, spawn-шаблоны
  (full-stack фича, параллельный дебаг), module-boundaries (зоны путей под роли, БЕЗ
  file-lock), опц. quality-gate хуки `TeammateIdle`/`TaskCompleted` (переиспользуют
  review-gate). Роли каркаса годятся как teammates. Sidebar обновлён.

## [0.4.0] - 2026-06-22

> **Зонтичная единая версия монорепо.** Накопленное с `v0.3.0`: выделение пакета
> `harness` (окружение Claude Code), корневой управляющий слой `swissknifeman`,
> доки по пакетам + зонтичный агрегат, гранулярная оркестрация окружения и
> standalone-сборка доков пакетов. Тег `vX.Y.Z` — единый маркер всего репозитория;
> версии плагинов Claude Code резолвятся в git SHA и от тега не зависят, per-package
> `plugin.json` (harness 0.1.0 · maind 0.2.1 · skm 0.3.0) — информативны.

### Added (Фаза 3 — гранулярная оркестрация окружения)

- **Capability `env:mcp` / `env:hooks`** в `maind/orchestrate.py` рядом с `env:apply` —
  точечная раскатка MCP-серверов / хуков через пакет `harness` (`maind run <project>
  env:mcp|env:hooks`, router `swissknifeman env mcp|hooks` — полный passthrough в
  harness). Раньше окружение настраивалось только цельным шагом (`skiller integrate`
  или `env:apply` для permissions); теперь «зонтик = единое управление» покрывает и
  MCP/хуки гранулярно. Whitelist `CAPABILITIES` расширен, тесты orchestrate дополнены
  (sibling=harness, подкоманда, `{path}`-подстановка).

### Changed (Фаза 3 — standalone-сборка доков пакетов)

- **Доки skiller/harness собираются и standalone, и в агрегате** (как уже умеет
  maind). У каждого пакета — своя `docs/.vitepress/config.mts` (base `/skiller/`,
  `/harness/`); зонтичный `scripts/docs-sync.sh` по-прежнему отбрасывает per-package
  `.vitepress` и собирает единый сайт. Внутренние ссылки доков переведены на
  **относительные** (`./`, `../`, без `/skiller/`·`/harness/`-префикса) — один
  источник валиден в обеих сборках; кросс-пакетные ссылки skiller→harness/`/routing`
  резолвятся только в агрегате и в standalone помечены `ignoreDeadLinks`. `harness`
  получил `package.json` (docs-скрипты), skiller — `docs:standalone:*`. Проверено:
  агрегат + оба standalone-сайта собираются без dead links.

### Changed (docs: maind влит в единый сайт)

- **maind-доки вошли в зонтичный VitePress** — `scripts/docs-sync.sh` теперь
  агрегирует и `packages/maind/docs`; в меню «Память и граф» ведёт внутрь сайта
  (`/maind/…`), не наружу. Внутренние ссылки maind-доков переведены с абсолютных
  (база `/maind/`) на **относительные** — пакет собирается и standalone (свой
  `.vitepress`), и в агрегате (общая база `/swissknifeman/`). Единый сайт зелёный
  (`vitepress build`, без dead links); standalone-сборка maind тоже зелёная.

### Added (корневой управляющий слой `swissknifeman`)

- **`bin/swissknifeman`** — тонкий router + setup-фасад над тремя пакетами (зонтик =
  единое управление, пакеты = возможности): `swissknifeman skills|env|maind …` →
  skiller/harness/maind; `swissknifeman setup <project>` → `maind onboard` (полный
  онбординг: скиллы+окружение+память+граф); `swissknifeman doctor` → fan-out трёх.
  Логику не реализует — делегирует; цепочка онбординга одна (`maind/onboard.py`).
- **Back-compat алиаса**: исторические `swissknifeman <cmd>` (connect/vendor/integrate/
  update/sync/lock/status/list/registry/topology/validate/version) router проксирует в
  `skiller` — онбордженные проекты и привычка не ломаются.
- **Владение алиасом перешло зонтику**: `swissknifeman`→`bin/swissknifeman` ставит
  зонтичный `install.sh` ПОСЛЕ пакетов; из `packages/skiller/install.sh` установка
  алиаса убрана (иначе re-run skiller install затирал бы router). Standalone-skiller
  без зонтика — только `skiller` (алиаса нет).
- **maind**: capability `env:apply` (sibling `harness`) — прямое применение окружения
  (`maind run <p> env:apply`, router `swissknifeman env`); `onboard --skip-skills` теперь
  всё равно настраивает окружение через harness (раньше оно шло только внутри
  `skiller integrate`).

### Added (пакет `harness` — настройка окружения Claude Code)

- **Новый пакет `packages/harness`** (CLI `harness`): настройка харнеса Claude Code —
  пресеты permissions, режимы auto-approve/bypass, MCP-серверы, хуки (memory/notify/log).
  Выделен из `skiller`, потому что к управлению скиллами не относится. `git mv`
  `configs/claude-code/` и `scripts/apply-permissions.sh` из skiller → harness (история
  сохранена). Команды: `harness permissions|mcp|hooks|doctor`. Пакет stateless
  (пишет в `.claude/` целей и `~/.claude/hooks/`); зонтичный `install.sh` ставит
  `skiller · harness · maind`.
- **skiller делегирует окружение в harness через subprocess** (как maind → skiller):
  `apply_permissions` и env-блоки `integrate` (permissions/MCP/auto-approve/memory)
  зовут `harness …`; резолв лаунчера — `SKM_HARNESS_BIN` →
  `<монорепо>/packages/harness/bin/harness`. Сигнатура `apply_permissions` не менялась —
  `connect`/`vendor` не трогались; harness не установлен → graceful skip (как раньше при
  отсутствии скрипта). Политика выбора MCP (`_default_mcp`/dev-гейт) осталась в integrate.
- **marketplace: поле провенанса `package`** у каждой записи плагина (`skiller`/`harness`/
  `maind`) — `skiller registry` проставляет автоматически; harness подхватывается как
  соседний пакет (плагин `harness@swissknifeman`, только команды `/harness:*`). Имена
  плагинов и имя marketplace НЕ менялись (back-compat: `<plugin>@swissknifeman`).
- **PR-шаблон** переписан под монорепо (затронутые пакеты skiller/harness/maind/core,
  per-package validate, regenerate-marketplace, docs). Память хуков делит state со skiller
  (`~/.swissknifeman/`) — пути в установленных хуках не менялись.

### Changed (модель имён и топология MCP)

- **Пакет `packages/swissknifeman` → `packages/skiller`** (CLI `skiller`). Репо/зонтик остаётся
  `swissknifeman` (= контейнер-«швейцарский нож»); имя пакета теперь явно про управление СКИЛЛАМИ
  и не путается с репозиторием. `git mv` каталога + `lib/swissknifeman`→`lib/skiller` (импорты
  пакета относительные — менялись только absolute-импорты в `tests/`) + `bin/swissknifeman`→
  `bin/skiller` (`python3 -m skiller`). `install.sh` ставит `skiller` **и back-compat алиас
  `swissknifeman`** в PATH — доки/привычка/онбордженные проекты не ломаются. **НЕ менялись**
  (бренд зонтика): имя marketplace `swissknifeman`, state-каталог `~/.swissknifeman/`,
  `.swissknifeman-manifest.json`, `.swissknife.json`, репо-URL; `skm`-плагин и `/skm:*`.
  `orchestrate.py` (maind): путь sibling-лаунчера → `packages/skiller/bin/skiller`.
- **Плагин `maind` → только команды (`/maind:*`), без MCP-сервера.** Снято поле `mcpServers`
  из `plugin.json`, удалён `packages/maind/.mcp.json` (сервер `maind-hub --scope global`). Раньше
  user-global плагин тащил `maind-hub` в КАЖДУЮ сессию поверх per-project сервера `maind` — две
  одинаковые `maind`-строки в `/mcp` с разными scope (промах «пишем в global вместо project»).
  Теперь MCP-инструменты хаба даёт только per-project сервер `maind` из `.mcp.json` проекта;
  граф/`projects_*`/`links` scope-независимы, ecosystem-факт пишется явным `scope:"global"`.
- **maind MCP: дефолт-scope из cwd, а не глухой `global`.** При запуске без `--scope`/`MAIND_SCOPE`
  сервер определяет `project:<id>` по текущему каталогу (резолвер общий с `health --cwd`), падая
  в `global` только вне известного проекта — argless-сервер пишет в бакет своего проекта.
- **Дедуп включения плагина в `~/.claude/settings.json`** (user-config): снят дубль
  `maind@academici` (+ stale marketplace `academici`, указывавший на pre-monorepo standalone-клон);
  оставлен единый `maind@swissknifeman`.
- **Решение: maind остаётся единым** (память+граф связаны namespace-моделью; memory `agentmemory`
  и graphify уже отдельные MCP-серверы — дробить нечего). Зафиксировано в CLAUDE.md.

### Added

- **Аудит практик round-2 + 4 дельты реестра скиллов.** Продолжение
  `docs/research/practices-audit-2026-06.md` — новый док `practices-audit-2026-06-r2.md`
  (карта покрыто/частично/гэп/отклонено + бэклог, Dart отложен как 1 проект). Заавторены:
  - **NEW `php/enum-state-machine`** — граф переходов доменного статуса единым источником
    (`transitionDefinitions()` на enum) + рантайм-реестр (`allowedFrom`/`canTransition`) +
    исполнение перехода в Action под `DB::transaction()` с событием `ShouldDispatchAfterCommit`.
    Гэп: `enum-attributes` исключает state-machine, `ticket-workflow` проектно-специфичен.
  - **EXTEND `devops/ci-cd` 0.3.0 → 0.4.0** — coverage-gate отдельным CI-job (GitHub Actions
    + GitLab `.php-base`/`php-coverage`); парсер/конфиг переиспользованы из `php/laravel-testing`,
    не дублируются. Сниппет `github-actions-coverage-gate.yml`.
  - **EXTEND `quality/test-strategy` 0.1.0 → 0.2.0** — композиция именованных тест-сюитов
    (Arch/Unit/Feature/Context) + архитектурные тесты Pest Arch. Сниппеты `pest-arch-test.php`,
    `phpunit-testsuites.xml`.
  - **EXTEND `php/spatie-settings` 0.1.0 → 0.2.0** — паттерн «рантайм-инфраконфиг (websocket/
    Reverb) из админки → во фронт публичным DTO», граница секретов.

### Changed

- **Конфиг узла: `.maind.json` → `config.json` в корне монорепо (общий).** Конфиг переехал
  из пакета в корень монорепо и переименован (шаблон — `config.example.json`). Резолвер
  `Env.default_config` ищет `config.json` вверх по дереву (до каталога с `packages/`), с
  обратной совместимостью на legacy `.maind.json`. Добавлена лёгкая обёртка `Config`
  (подкласс dict: `Config.load(env)`/`.save(env)`/`.projects`/`.project(id)` — единая точка
  логики конфига; старый доступ `cfg["projects"]` сохранён). `config.json` — gitignored,
  `0600`. Резолв brain в оркестрации сделан консистентным с синком (через
  `integrations.brain.path` → vault → дефолт `~/Vaults/Brain`, нормализация к каталогу) —
  `maind run brain:*` работает без записи проекта brain. Документация и сообщения обновлены.

- **Плагин maind 0.2.0 → 0.2.1.** Bump версии, чтобы Claude Code перекэшировал плагин со
  свежим кодом (исправленный `.mcp.json` → `maind` из PATH, `from core`); кэш по прежней
  версии не перестраивался. `package.json` синхронизирован.

### Removed

- **Убрана консоль-обёртка `bin/academici`.** Зонтичный роутер `academici maind/skm <cmd>`
  удалён — остаются два независимых CLI в PATH (`swissknifeman`, `maind`). Зонтичный
  `install.sh` теперь только делегирует установку пакетным `install.sh`; CLAUDE.md/README
  описывают два CLI без обёртки. (Имя экосистемы «academici» как бренд сохранено.)

### Changed

- **Общий core: `academici_core` → пакет `core`.** Убрано слово `academici` из путей/имён.
  Каталог `core/` сам стал python-пакетом (`core/__init__.py`, `core/env.py`, …); импорт
  `from core import ...`. PYTHONPATH теперь указывает на корень монорепо (где лежит `core/`),
  а не на сам `core/` — обновлены лаунчеры, `test.sh`, `validate.sh` обоих пакетов и
  real-spawn тест maind (`CORE_DIR` → `MONOREPO_ROOT`).

### Fixed

- **Валидный формат `plugin.json` для установки из marketplace.** Текущий Claude Code
  ужесточил схему — старый формат не ставился (`commands: Invalid input,
  mcpServers: Invalid input`): `commands` теперь массив путей (`["./commands"]`),
  `mcpServers` — путь с `./` (`"./.mcp.json"`). Битый YAML-frontmatter команд (`description`
  с двоеточием `academici: …` парсился как вложенный ключ) обёрнут в кавычки. Затронуты оба
  командных плагина (maind, skm) — проходят `claude plugin validate`. Тест `test_plugin.py`
  ловит эти дефекты до установки.

### Changed

- **Монорепо academici: верификация + массовый re-deploy потребителей (этап 7).** MCP-конфиги
  проектов перенацелены на новый путь хаба: `maind deploy` прогнан по 15 проектам реестра —
  14 обновлены (corex/azguard/edufy/memster/vintera/… → `packages/swissknifeman/packages/maind/`),
  1 пропущен (agelto: предсуществующий битый `.cursor/mcp.json` с дублем JSON — не трогаем).
  `swissknifeman update --all` обновил скиллы потребителей. Проверка `maind health` на проекте:
  статус `connected`. Доделаны хвосты этапа 4: тест `test_plugin.py` и `validate.sh` maind
  больше не требуют собственный marketplace.json пакета (он в корне репо).

### Added

- **Монорепо academici: зонтичная навигация (этап 6).** Корневой `CLAUDE.md` (карта
  монорепо: пакеты, консоль, core, marketplace) и корневой `README.md` зонтика. README
  swissknifeman перенесён в `packages/swissknifeman/README.md`. `docs:*`-скрипты
  swissknifeman нацелены на корневой `docs/` (`../../docs`). docs/ пакетов и два VitePress
  оставлены на местах (полное слияние сайтов — отдельная задача).

- **Монорепо academici: единая консоль `bin/academici` + зонтичный `install.sh` (этап 5).**
  `academici` — тонкий bash-роутер: `academici maind <cmd>` / `academici skm <cmd>` →
  под-бинарник пакета; уникальные команды авто-роутятся без префикса; конфликтные имена
  (`status`/`doctor`) дают сводку по обоим пакетам, `sync` требует домен. Под-бинарники
  `maind`/`swissknifeman` остаются самостоятельными (не ломаем `.mcp.json` и мышечную память).
  Зонтичный `install.sh` ставит `academici` и делегирует установку пакетных CLI их
  собственным `install.sh` (с пакетной пост-настройкой). Все три симлинка указывают в монорепо.

### Changed

- **Монорепо academici: единый marketplace + плагин maind под зонтиком (этап 4).** Корневой
  `.claude-plugin/marketplace.json` теперь объявляет 19 плагинов — 18 swissknifeman
  (бакеты + generate-skill + skm) и `maind` (`source: ./packages/maind`). Генератор
  `registry.py` сканирует соседние пакеты `packages/<name>/.claude-plugin/plugin.json`
  (источник истины — их манифест) и добавляет их в marketplace; `validate.sh` учитывает
  sibling-плагины в match-проверке. Собственный `packages/maind/.claude-plugin/marketplace.json`
  удалён (его роль берёт корневой). Плагин maind (`commands/` + `.mcp.json` с
  `${CLAUDE_PLUGIN_ROOT}`) переносим без правок. Миграция кэша Claude Code
  (`maind@maind` → `maind@swissknifeman`) — вручную в панели `/plugin`.

- **Монорепо academici: общий `core/academici_core` (этап 3).** Дословные дубли,
  исторически копировавшиеся между swissknifeman/maind/brain байт-в-байт, вынесены в
  общий stdlib-only пакет: `die/warn/now_iso/confirm` (`term`), `sanitize` (`text`),
  базовый `BaseEnv` (ядро root/cmd/home + `__post_init__`, `env`). `Env` каждого пакета
  теперь наследует `BaseEnv` и добавляет только свои path-property. Подключение — через
  PYTHONPATH (без pip): лаунчеры, `test.sh`, `validate.sh` добавляют `<repo>/core`
  (опционально — fallback на standalone-раскладку). `parse_args`/`parse_flags`, atomic
  JSON, HTTP, frontmatter, managed-block остаются в `common.py` пакетов (расходятся по
  контракту — не дословны). 5 smoke-тестов core; 113 (skm) + 235 (maind) зелёные.

- **Монорепо academici: maind внесён в `packages/maind/` (через `git subtree`, история
  сохранена).** Хаб памяти/графа теперь живёт под зонтиком рядом с реестром скиллов.
  `node_modules` (демон `@agentmemory/agentmemory`) переустановлен в новом месте (`npm ci`);
  systemd unit `maind-memory.service` перегенерён на новый путь (`maind service install`),
  демон памяти жив (порты 4111/4112). `.maind.json` (конфиг узла, `0600`) перенесён в пакет.
  `orchestrate.py`: путь к лаунчеру swissknifeman обновлён на `packages/swissknifeman/bin/...`
  (local_path остаётся корнем репо). `maind doctor` и 235 тестов зелёные из нового места.
  Re-deploy `.mcp.json` потребителей (≈18 проектов держат старый абсолютный путь) — этап 7.
- **Монорепо academici: переезд в `packages/swissknifeman/`.** Репозиторий становится
  зонтиком экосистемы — содержимое реестра (`lib/`, `bin/`, `skills/`, `skm/`,
  `generate-skill/`, `scripts/`, `configs/`, `buckets.json` …) переехало в
  `packages/swissknifeman/`; в корне остаются зонтичные артефакты (`.claude-plugin/`,
  `docs/`, `README`, `LICENSE`, `CHANGELOG`). Один `marketplace.json` в корне репо теперь
  объявляет плагины с `source: ./packages/swissknifeman/...` (генератор `registry.py`
  разводит корень-пакета vs корень-репо через поиск `.git`; `validate.sh` и
  `generate-graph.sh` адаптированы). `bin/swissknifeman` больше не требует marketplace.json
  в корне пакета. Симлинк переустанавливается `install.sh` из нового пути. Готовит почву
  для пакета `packages/maind/` под тем же зонтиком.

- **Ревью внешнего аудита: дизамбигуация overlap-кластеров + CI security-гейты.**
  По разбору `Audit.md` (вердикт — `docs/research/audit-2026-06-review.md`): из
  всех рекомендаций реальны 3 (остальное — already-done/дубли/вне scope/против
  stdlib-only инварианта). `frontend/vue-composition-api` (0.2.0) обрезан до дельты
  (ref-first + composables), базовый синтаксис отдан upstream `vue`/`vue-best-practices`
  (не удалён — служит якорем «паттерн composable» для ≈13 frontend-скиллов).
  `php/laravel-permissions` (0.3.1) и `frontend/vitest` (0.1.1) — острые
  description-триггеры против путаницы роутинга (vs `azguard`/`attribute-authorization`
  и vs `vitest-vue`). `devops/ci-cd` (0.3.0) — секция «Security gates» (SAST/PHPStan-taint,
  `composer`/`npm audit`+Dependabot, Trivy скан образа) + сниппет `github-actions-security.yml`.
- **Анти-bloat в существующих скиллах (вместо новых дублей).** `anti-drift`
  (0.2.0) — секция «Граница зависимого пакета: спроси перед расширением» +
  обновлён сниппет CLAUDE.md; `code-simplifier` (0.2.0) — чеклист
  speculative-generality (YAGNI) по свежему диффу; `api-design` (0.1.1) —
  cross-ref на эволюцию контракта пакета; внутренний `skill-authoring` —
  стандарт ревью скилла (универсальность, без имён проектов/пакетов).
  `CLAUDE.md`/`CONTRIBUTING.md` — указатели на методологию и анти-bloat гейты.

### Fixed

- **auto-approve: ложные `deny_hard` на `git rm` и `*-init`** — общий токен `rm`
  ловил `git rm` (обратим, файлы в индексе/истории), а токен `init` — `git init`/
  `npm init`/`composer init`/`swissknifeman topology init`. Теперь `analyze.sh`
  маскирует `git rm` перед deny_hard-проверкой (голый `rm`/`xargs rm`/`rm -rf`
  по-прежнему блокируются; `git rm` идёт как мутация — промпт в strict/permissive,
  разрешён в bypass), а `init` убран из общего списка и заменён точечным паттерном
  рантлевела (`telinit`/`init [0-6sS]`). `git rm` добавлен в `deny_block_approve`.
  Файлы хука обновляются `apply-permissions.sh --global` (для `config.json` —
  перезалить вручную, т.к. он не перезатирается)

### Added

- **Каталог интеграций `docs/integrations/` + курированные MCP-пресеты.** По разбору
  внешнего аудита (`CLAUDE_INTEGRATION_TASK.md`): новый раздел VitePress «Интеграции» —
  индекс + 11 страниц (context7, playwright, filesystem, fetch, memory,
  sequential-thinking, github, task-master, spec-kit, claude-code-router), приведённых к
  реальности хаба (remote-HTTP context7, механизм пресет→`integrate`, актуальные пакеты:
  fetch — `uvx mcp-server-fetch`, github — remote `api.githubcopilot.com/mcp/`; без
  устаревших model-id и выдуманных схем). Курированный сабсет пресетов в
  `configs/claude-code/mcp/` (`playwright`/`filesystem`/`fetch`/`memory`/
  `sequential-thinking`/`github`) — **opt-in** через новый флаг `swissknifeman integrate
  --mcp <a,b>` (в интерактиве — отдельный вопрос); `DEV_MCP` по умолчанию не расширен.
  `claude-code-router` — страница «инструмент есть, но под сомнением». **Скиллы из аудита
  сознательно не созданы** (анти-bloat): `playwright-e2e-tester` дублирует
  `quality/playwright-e2e`, `git-flow-ru` — `git-commit-rules`+`github-flow`+`writing-style`,
  а `context7-dart-flutter`/`fintech-api-context`/`pos-fiscal-assistant` нарушают запрет на
  имена конкретных продуктов в теле скилла и попали бы в CORE-бакет `general` — их место в
  `.ai/skills/` конкретных проектов.
- **`integrate`: MCP-серверы в среды разработки (context7).** Новый блок визарда
  `_block_mcp` вливает пресеты MCP-серверов в `<project>/.mcp.json` (merge-only,
  чужие серверы целы, бэкап `*.bak`, `--dry-run`). Пресеты —
  `configs/claude-code/mcp/<name>.json`; первый — `context7` (remote HTTP
  `mcp.context7.com/mcp`, up-to-date docs библиотек). Гейт «среда разработки»:
  раздаётся во всё, кроме `obsidian-vault`. Бандлы `recommended`/`full` включают
  по умолчанию, `minimal` — нет, `custom` — спрашивает.
- **Семантика loop'ов поверх скиллов (без отдельного реестра `loops/`).** По
  аудиту [loops.elorm.xyz](https://loops.elorm.xyz/loops): страница
  `docs/guide/loop-semantics.md` (VitePress, в сайдбаре «Гайд») — модель loop'а
  (Goal/Run mode/Max iterations/Between-check/Exit condition + anti-gaming
  guardrails), маппинг фаз на существующие скиллы и граница «скилл даёт гейты,
  раннер встроен (`/loop`, `/schedule`)». Скилл `task-brief-template` (0.4.0):
  поля `Loop verifier`/`Exit condition`/`Hard stop trigger` в шаблоне + сниппет
  `loop-kickoff.md` (стартовый шаблон итеративной задачи для `.claude/commands/`).
  Сознательно без дублей: iteration/stop уже в `anti-drift`, session-split — в
  `context-economy`, shared-code gate — в `package-contribution-protocol`.
- **`swissknifeman sync` догнал `vendor`/`connect`: манифест, CORE-политика и
  индекс скиллов.** Раньше `sync` только копировал скиллы и писал
  `skills-lock.json` — без `.swissknifeman-manifest.json` (контракт переустановки
  и источник для `generate-hub.sh`), без CORE-скиллов и без обновления
  managed-блока в корне проекта. Теперь `sync`: (1) пишет манифест в `skills_path`
  (`layout: flat`, `flat_name`/`source_path`); (2) раздаёт `CORE_SKILLS` по
  умолчанию и применяет `DEFAULT_EXCLUDE` (флаг `--no-core` отключает), как
  остальные каналы; (3) обновляет индекс скиллов (managed-блок `CLAUDE.md` /
  `.ai/guidelines/swissknifeman-hub.md`), если он уже есть в проекте или передан
  `--hub` (`--no-hub` отключает). `generate-hub.sh` дополнительно ищет манифест в
  `skills_path` из конфига (находит нестандартные раскладки вроде `.agents/skills`).
- **Методология против раздувания кода + скилл `architect/package-contribution-protocol`.**
  По аудиту практик разработки экосистемы «проект ↔ зависимый пакет» добавлен
  generic-гейт против Speculative Generality: главный вопрос (Rule of Three +
  YAGNI), принцип «остановись и спроси / субагент go/no-go перед расширением
  пакета», двухступенчатый gate (proposal → ADR), таблица «что НЕ идёт в пакет»,
  направление зависимостей и SemVer контрактов. Сниппеты: `proposal-issue.md`,
  `adr-template.md`, `claude-md-priority.md` (ручной «первый приоритет» в
  CLAUDE.md потребителя), `permissions-deny.md`. Скилл **opt-in** (бакет
  `architect`), без имён конкретных проектов/пакетов. Базовый рефлекс «спроси
  перед расширением» — в CORE-скилле `anti-drift` (едет во все проекты);
  глубокий протокол подключается выборочно (гибридная раздача).
- **Permissions-пресет `product-boundary`** (`configs/claude-code/settings.product-boundary.json`):
  deny на запись в зависимый пакет (`Write/Edit(vendor/**)`); вариант для
  path-репо (`packages/**`) — в сниппете скилла. Opt-in (не в автодетекте),
  применяется через `apply-permissions.sh --preset product-boundary`.
- **Страница `docs/guide/methodology.md`** (VitePress, в сайдбаре «Гайд») —
  методология анти-bloat с картой «принцип → скилл/конфиг» и гибридной раздачей.
- **Figma MCP-скиллы + новый бакет `mobile`.** Три скилла прокачивают работу
  агента с подключённым Figma Dev Mode MCP: `architect/figma-mcp-core` —
  фреймворк-агностичная дисциплина (реальные инструменты `get_metadata`/
  `get_variable_defs`/`get_code`/`get_code_connect_map`/`get_screenshot`/
  `search_design_system`, запрет извлечения значений из скриншотов,
  selection-driven алгоритм, W3C `tokens.json`, аудит design-system);
  `frontend/figma-to-vue` — маппинг в Vue + Tailwind v4 (`@theme`, cva, `.dark`);
  `mobile/figma-to-flutter` — маппинг в Flutter (`ThemeData`, Row/Column/Expanded,
  Stack/Positioned). Новый бакет `mobile` (Flutter) в `buckets.json`.
- **Vendor-режим `swissknifeman sync` — физический перенос скиллов по единому
  конфигу.** `.swissknifeman/config.json` — источник истины (правила:
  `include` конкретных скиллов + `buckets` целиком − `exclude`); `sync`
  разворачивает их в плоский набор по `skills.json`, копирует файлы в
  `skills_path` (по умолчанию `.claude/skills`) и пишет производный
  `skills-lock.json` с пометкой `managed`. Безопасный prune: удаляются только
  `managed=true` записи, исчезнувшие из конфига — чужой/ручной вендоринг
  (наследие Boost, другой хаб) не трогается. Конфиг распознаётся как маркер
  корня проекта; пример — `.swissknifeman.example/config.json`; доки —
  `docs/guide/vendor-mode.md`. Read-only композитор `lock` остаётся для
  проектов без vendor-режима.
- **Management-плагин `skm@swissknifeman`** — командное лицо CLI: каталог
  `skm/` со статичным `plugin.json` + slash-команды (`skm`, `skills`,
  `integrate`, `status`, `doctor`). Не бакет скиллов — `registry` добавляет
  запись в `marketplace.json` синхронно, `validate.sh` проверяет как обычный
  плагин. Install `skm@swissknifeman` даёт команды управления скиллами проекта.
- **Реализация бэклога аудита — ещё 14 универсальных скиллов + 1 расширение
  (batch-2).** Добиты все отложенные §5 кандидаты из
  `docs/research/practices-audit-2026-06.md`; всё обобщено (проект — только
  эвиденс, в скилл идёт переносимый паттерн + анонимизированные снипеты).
  **Фронтенд (7):** `frontend/reka-ui-cva` (headless-примитивы Reka UI + cva),
  `frontend/dark-mode` (composable light/dark/system, без вспышки, SSR-cookie),
  `frontend/naive-ui-theming` (GlobalThemeOverrides), `frontend/laravel-echo-client`
  (Echo/Reverb composable, X-Socket-ID), `frontend/filepond-upload` (vue-filepond
  + rahulhaque/laravel-filepond), `frontend/vue-dynamic-icons` (динамическая иконка
  по имени), `frontend/pinia-stores` (setup-сторы, композиция). **PHP (4):**
  `php/livewire-blade-attributes` (дельта-гочизы к Boost livewire),
  `php/spatie-settings`, `php/health-checks` (spatie/laravel-health),
  `php/laravel-data` (spatie/laravel-data DTO + `#[TypeScript]`). **Quality (2):**
  `quality/playwright-e2e`, `quality/mutation-testing` (Infection). **Blender (1):**
  `blender/parametric-config` (config-dataclass → profile/check без bpy).
  **Расширен** `php/laravel-testing` (Pest-композиция: трейты + fake/freeze/dataset).
  `skills.json` 138 → 152; Boost-границы соблюдены (complementary: `laravel-data`,
  `spatie-settings`, `livewire-blade-attributes`); `boost-compatibility.md` обновлён;
  `validate.sh` зелёный (0 warnings, 76 tests).
- **Скиллы из практик констелляции (аудит + 10 скиллов, фокус — фронтенд).**
  Read-only аудит всех проектов из `~/Vaults/Brain/.projects.json` + `unbox`,
  `art-kombinat/frontend`, `sova` (6 Explore-агентов, сверка кандидатов с живым
  реестром, чтобы отсечь вендоренные копии). Разбор — в
  `docs/research/practices-audit-2026-06.md` (стек-фингерпринты, поправка
  vendored-vs-local, авторённое, отложенный бэклог, вне охвата). **7 новых
  скиллов:** `frontend/tailwind-conventions` (Tailwind v4: CSS-first `@theme`,
  токены, тёмная тема, `cn()`, prettier-plugin-tailwindcss), `frontend/backend-type-sync`
  (`spatie/laravel-typescript-transformer` + `#[TypeScript]` → `App.Enums.*`/`App.Data.*`,
  в паре с `wayfinder`), `frontend/eslint-flat-config` (ESLint 9 flat для Vue/TS:
  `@stylistic`, границы импортов, цепочка Prettier), `php/test-isolation-guard`
  (bootstrap-страж против тестов по боевой БД/медиа-диску), `php/attribute-authorization`
  (`#[CheckPermission]` + reflection-middleware поверх Gate), `general/writing-style`
  (тон/язык комментариев, коммитов, описаний тестов — расширенная версия, объединена
  с одноимённым скиллом из flexcrm-экстракции ниже), `devops/db-test-preflight`
  (пре-флайт Postgres-БД перед тестами — аналог `node-pnpm-preflight`). **3 расширены:**
  `frontend/inertia-vue` (доменные срезы `features/<домен>/` + границы импортов, →0.3.0),
  `php/enum-attributes` (секция `#[TypeScript]` + экспорт типов, →0.2.0),
  `php/modular-architecture` (реализация на `nwidart/laravel-modules` + Filament discovery, →0.3.0).
  Снипеты анонимизированы; `validate.sh` зелёный (0 warnings).
- **Экстракция универсальных скиллов из flexcrm** (источник: local, авторские):
  `quality/testing-safety-report` (отчёт безопасности после миграций/рефакторинга),
  `php/php-upgrade-checklist` (чеклист апгрейда версии PHP — образ/CI, composer,
  phpstan-baseline, rector, RFC), `general/writing-style` (живой язык комментариев
  и текстов коммитов, дополняет `git-commit-rules`). Boost-владения (tailwind/mcp/
  pest) и уже существующее в реестре не дублировались; `fortify-development` оставлен
  локальным в проекте по решению владельца
- **Док-предупреждение про чистую переустановку** (`docs/guide/cli.md`): `vendor`/
  `update` удаляют ранее вендоренные скиллы, выпавшие из набора реестра, включая
  **незакоммиченные** локальные копии — проектные скиллы держать в git; превью
  удаляемого — `--dry-run`. (Острый угол, всплывший при онбординге flexcrm)
- **Визард интеграции `swissknifeman integrate`** (`lib/swissknifeman/integrate.py`)
  + [чеклист](docs/guide/integration-checklist.md) — единая точка входа: проходит
  чеклист «выбери, что хочешь из максимального функционала» и применяет выбранное,
  переиспользуя `do_connect`/`do_vendor` (скиллы), `apply-permissions.sh` (permissions),
  `generate_hub` (hub) + пишет per-project hook-JSON (auto-approve на PreToolUse
  Bash/ExitPlanMode) и `.swissknife.json:memory_brain` (членство в memory-brain).
  Бандлы `minimal|recommended|full|custom`; безопасно — `--dry-run`, merge-only с
  бэкапами `*.bak`, идемпотентно, пререквизиты (`topology init`, `--global`) только
  с подтверждением. Зарегистрирован в `cli.py`/лаунчере; тесты `tests/test_integrate.py`.
  В `CONFIG_KEYS` добавлены `memory_brain`/`coordinator_ignore` (валидны в `.swissknife.json`)

- **Гибкая «единая память» констелляции** — самодостаточная папка-хук
  `configs/claude-code/hooks/memory/` по образцу auto-approve: переключатель
  `memory.sh` (remember/recall/members/status/sync), режим в `env.ini`
  (`MODE=file|federation|agentmemory|off`), группы и участники в `config.json`,
  бэкенды в `modes/`. **Membership:** общий «мозг» (brain) видят только участники
  из его `members` (резолв узлов/проектов через топологию). Режимы взаимозаменяемы
  (file/federation на markdown без демона; agentmemory — прокси к стороннему
  демону на Brain, деградирует при недоступности), конфиг переопределяется
  per-project (`<project>/.claude/memory.{env.ini,config.json}` + `.swissknife.json:
  memory_brain`). Схема факта совместима с нативной памятью Claude Code, поэтому
  `federation` читает и `~/.claude/projects/<slug>/memory/` участников. Агент-обвязка —
  скилл `system/shared-memory`; установка через `apply-permissions.sh --global`.
  `validate.sh` теперь `bash -n`-ит все хук-скрипты `configs/claude-code/hooks/`
- **Межпроектный координатор кода** — `system/cross-project-coordinator` (скилл) +
  агент `system/agents/code-coordinator` (read-only). Поверх топологии обходит
  связанные проекты, перечисляя только git-отслеживаемые файлы (`git ls-files` —
  уважает `.gitignore`/`.git/info/exclude`, секреты и вендор/генерёжку не читает),
  и ищет по семи критериям: дубли между репо, расходящиеся реализации одного
  концепта, дрейф от реестра скиллов, копия-вместо-зависимости, расхождение
  конвенций/документации/зависимостей. Критерии переиспользуют `quality/`-скиллы
  (tech-debt-audit, refactoring-plan, code-simplifier, code-review). Выдаёт
  приоритизированный (impact×effort) отчёт с `file:line` по проектам и named
  extraction target; правок/PR не делает. `requires: local-topology`
- **Топология локальной среды** — корневой узел системы. Новый бакет `system`
  со скиллом `local-topology` (раздаётся всем проектам: добавлен в профили
  laravel-project/php-package/obsidian-vault), команда `swissknifeman topology
  [init|show]` (`lib/swissknifeman/topology.py`) и глобальный конфиг
  `~/.swissknifeman/topology.json` (version 1): три узла-хаба
  Brain-волт/swissknifeman/база-проектов (роли docs-hub/skills-hub/workspace).
  `init` — интерактивный сбор с авто-детектом дефолтов, атомарная запись с
  бэкапом `.bak`, сохранение `created_at`; предлагается при `install.sh` (TTY).
  Скилл объясняет схему и резолвит узлы по конфигу — любой агент в любом проекте
  видит, где лежат узлы, и доходит до кода/документации соседних проектов.
  Тесты `tests/test_topology.py` (+10). Roadmap: межпроектный агент-оптимизатор
- **Notification-hook `configs/claude-code/hooks/notify/notify.sh`** — ОС-уведомление,
  когда Claude Code ждёт человека: запрос разрешения на инструмент, утверждение
  плана (ExitPlanMode) или простой промпта дольше ~60 сек. Кросс-платформенно
  (Linux `notify-send`, macOS `terminal-notifier`/`osascript`, WSL/Windows toast).
  Регистрируется пресетом `global`, ставится через `apply-permissions.sh --global`,
  никогда не блокирует (`exit 0`)

### Added (продуктовая готовность)

- **`LICENSE` (MIT)** + поле `license` в `package.json` — юридическая основа для
  распространения; внешние (imported) скиллы сохраняют лицензии источников
  (`upstream.json`)
- **`SECURITY.md`** — порядок раскрытия уязвимостей, модель доверия импортируемых
  скиллов (sha256 в `upstream.json`, стратегии `notify`/`replace`), правило
  «нет секретов в snippets», приоритет «проект > источник > реестр»
- **`.github/workflows/test.yml`** — отдельный CI с матрицей Python 3.9–3.12
  (раньше тесты гонялись только хвостом `validate.sh` на одной версии)
- **Покрытие ядра CLI тестами** (38 → 57): `registry` (`build_registry`,
  `write_plugin_manifests`, provenance внешних скиллов, die без `buckets.json`),
  `state` (CRUD `projects.json`, сохранение `first_connected_at`, атомарность),
  `doctor`, `status`, `update` (реплей выбора, идемпотентность) — теперь у каждой
  команды есть прямой тест; хелпер `write_upstream` в `tests/fixtures.py`
- **`docs/guide/troubleshooting.md`** — диагностика (`command not found`, Claude
  Code не видит скиллы, конфликт `settings.json`, коллизии вендоринга, битый
  `projects.json`) и обновление (реестр, vendor `update`/`--all`, смена схемы);
  добавлена в sidebar
- **Бейджи в README** (Tests / Validate / Docs / License) + разделы
  «Безопасность» и «Лицензия»

### Changed (рефакторинг CLI: lib/ + тесты)

- **`bin/swissknifeman` → тонкий лаунчер**: вся Python-логика (раньше — heredoc
  на 1300 строк внутри bash) вынесена в пакет `lib/swissknifeman/` и разложена
  по модулям (`common`, `config`, `state`, `connect`, `vendor`, `update`,
  `status`, `listing`, `registry`, `doctor`, `boost`, `hub`, `cli`). Бинарник
  делает preflight-проверки и `exec python3 -m swissknifeman <root> <cmd>`.
  Поведение байт-в-байт прежнее (`registry` даёт идентичные `skills.json` и
  манифесты); установщик и симлинк не затронуты. Модульные глобали
  `root`/`cmd`/`argv` заменены явным `Env` — функции стали импортируемыми

### Added (тесты CLI)

- **`tests/` (stdlib unittest, без зависимостей)**: 27 юнит-тестов
  (frontmatter, парсинг флагов, sanitize, autodetect, precedence
  `resolve_selection`, транзитивный `requires`, коллизии flat-имён) и
  11 интеграционных — фейковый Laravel-проект в tmpdir, кейсы `connect`/`vendor`
  (autodetect, явные плагины, сохранение `false`, dry-run, bucket/flat-layout,
  pull `requires`, `--exclude`, синк `boost.json`, чистая переустановка).
  Синтетический реестр (`tests/fixtures.py`) — тесты не зависят от контента
  скиллов
- **`scripts/test.sh`** — раннер тестов (`-v` для подробного вывода), встроен в
  `scripts/validate.sh` (группа 12: импорт пакета + прогон сьюта). Тот же
  скрипт гоняет CI

### Added (gh-driven ревью и экономия контекста)

- **`oss-dev/gh-review` (0.1.0)**: ревью и хендофф изменений через GitHub CLI
  с экономией контекста — `gh pr diff/view/comment/review` отдают точечный срез
  (дифф, треды), `gh api .../contents` тянет один файл вместо загрузки целиком.
  Чёткая граница: локальный VCS (commit/branch/diff/log/rebase) — за `git`,
  платформа (PR/issue/release/api) — за `gh`. `requires: context-economy`,
  `produces_for: github-flow`; snippet-шпаргалка команд
- **`scripts/update-upstreams.sh` — канал `gh api`**: для GitHub raw-URL и при
  наличии `gh` файл тянется через `gh api repos/{o}/{r}/contents/{path}?ref=...`
  (авто-аутентификация из `gh auth`, rate-limit, один файл). Тихий откат на
  `urllib`+`GITHUB_TOKEN`, если `gh` недоступен; отключение — `UPSTREAM_NO_GH=1`.
  Касается импортируемых скиллов (`source: github`)

### Changed

- **`general/context-economy` 1.0.0 → 1.1.0**: раздел «Платформенный слой —
  через `gh`, не файлами» (`gh` дополняет `git`, не заменяет; экономия на
  точечном срезе) + пункт чеклиста; ссылка на `oss-dev/gh-review`
- **`oss-dev/github-flow` 0.1.0 → 0.2.0**: шаг Review ссылается на `gh-review`
  (`requires += gh-review`); ревью PR — через `gh`, не загрузкой файлов
- **Документация**: этап «dev-review через gh» в межсистемной цепочке
  (`docs/workflows/index.md`), канал `gh api → urllib` в
  `docs/guide/upstream-sync.md`

### Added (интеграция с Laravel Boost — совместимое ядро)

- **`php/named-arguments` (0.1.0)**: правило обязательных именованных аргументов
  в PHP-вызовах с границами применения и исключениями (один аргумент, встроенные
  функции, splat). Извлечено и де-агельтизировано из проектного скилла;
  `source: local`. Дополняет, а не дублирует — реестр раньше только *использовал*
  именованные аргументы в примерах, отдельного правила не было
- **`php/pennant-development` (0.1.0)**: feature-флаги Laravel Pennant
  (`define`/`active`/`for`-scope, директива `@feature`, активация/раскатки).
  Извлечено из `laravel/boost` (`upstream.json` strategy=notify) — единственный
  чистый static-`.md` generic-кандидат без версионной развилки; Blade-скиллы
  Boost (`folio`/`volt`/`mcp`) остаются за Boost (нужен render-контекст)
- **`php/laravel` → `eloquent-model.md`**: секция «Accessors и mutators» дополнена
  правилами `Attribute::make()` (видимость `protected`, camelCase→snake_case,
  позиция в классе, миграция с legacy-аксессоров) — слито из проектного
  `laravel-attributes` вместо создания дубля

### Added (CLI и хаб — установка в Boost-проекты)

- **Boost-aware `vendor`/`update`**: при наличии `boost.json` в целевом проекте
  CLI (1) автоматически использует **flat-раскладку** `.ai/skills/<name>/SKILL.md`
  — Boost обнаруживает user-скиллы через `glob('.ai/skills/*')` на один уровень,
  bucket-подпапки он бы не нашёл; (2) идемпотентно дозаписывает вендоренные
  скиллы в `boost.json::skills` (по frontmatter-`name`) и подсказывает
  `php artisan boost:update`. Скиллы автоматически расходятся по всем агентам
  Boost из единого источника `.ai/skills/`
- **`generate-hub.sh --root-files A,B`**: managed-блок хаба (между маркерами
  `swissknifeman:hub:start/end`) дополнительно пишется в указанные корневые файлы
  (`AGENTS.md`, `GEMINI.md`, …) для тулз вне Boost; контент вне маркеров не
  трогается

### Fixed

- **Рассинхрон маркера хаба**: `bin/swissknifeman` искал
  `<!-- swissknifeman:hub:begin -->`, тогда как `generate-hub.sh` пишет
  `:start`/`:end`. Из-за этого `hub_artifacts_exist()` не находил managed-блок в
  `CLAUDE.md`, и `update`/повторный `connect` не понимали, что хаб уже стоит.
  Приведено к единому `hub:start`

### Changed (документация концепции ядра)

- **Политика совместимого ядра** зафиксирована явно: `docs/guide/index.md`
  (принцип №6 «Совместимое ядро» + таблица прецедентов), `README.md`,
  `references/laravel-boost.md` (критерий извлечения static/версионность/generic,
  что извлечено, что нет и почему), `docs/guide/installation.md` (раздел
  «Проект с Laravel Boost»). Поток обновлений инвертирован: generic-скиллы
  внешнего источника обновляются сначала в реестре, затем подтягиваются в проекты

### Added (субагенты Laravel)

- **`php/agents/` — первые агент-определения в плагине**: бакет-плагин теперь
  несёт каталог `agents/` (Claude Code обнаруживает его в корне плагина
  автоматически; реестр и валидатор каталоги без SKILL.md игнорируют;
  доступно только в plugin-канале — `vendor` агентов не копирует).
  Агенты: `laravel-reviewer` (read-only ревью свежим контекстом:
  PHPStan/Pint/целевые Pest, Laravel-критерии, структурированные находки без
  правок) и `laravel-test-writer` (Pest-тесты по готовому коду в стиле
  существующих тестов проекта; прикладной код не меняет — расхождения
  репортит)
- **`php/laravel-subagents` (0.1.0)**: протокол оркестрации субагентов на
  крупных Laravel-задачах — порог срабатывания (≥3 слоёв/доменов или целая
  фича; мелкое/среднее — напрямую, явный анти-триггер), исследование через
  Explore-агентов, архитектурный код пишет оркестратор, параллель только для
  независимых подзадач (иначе worktree), `laravel-reviewer` после каждой
  единицы, `laravel-test-writer` по готовому коду, анти-паттерны конвейера
  ролевых агентов

### Added (github-flow)

- **`oss-dev/github-flow` (0.1.0)**: процессная цепочка Issue → Branch → PR →
  Merge → Tag → Release на GitHub — naming Issue/веток/PR, labels, SemVer-оракул
  по типам коммитов, контрольные точки с обязательными вопросами агента;
  PHP/Packagist-гейт в `references/php-package-gate.md`; snippets с шаблонами
  PR/Issue; `requires: git-commit-rules, release-engineering` (формат коммитов
  и changelog/pipeline не дублируются)

### Changed (github-flow)

- **`general/git-commit-rules` 0.1.0 → 0.2.0**: расширен список типов
  (`perf`, `style`, `build`, `ci`, `revert`), раздел «Conventional Commits:
  scopes и breaking changes» (источник scope — commitlint, footer
  `BREAKING CHANGE` / `!` после типа), ссылка на SemVer-оракул github-flow

### Added (CLI swissknifeman + внутренние скиллы)

- **CLI `bin/swissknifeman`**: единая точка входа — `connect` (marketplace
  Claude Code), `vendor` (вендоринг), `update [--all]` (детект каналов по
  маркерам диска, adopt незарегистрированных проектов, починка path-drift
  marketplace при переезде реестра), `status`, `list [--prune]`, `registry`
  (бывший `sync.sh --update-registry`), `validate`, `doctor`, `version`.
  Корень проекта ищется вверх от CWD (`.swissknife.json` → `.claude/` →
  `.git`) — флаг `--target` больше не нужен
- **Карта проектов `~/.swissknifeman/projects.json`** (schema v1, ключ
  path+channel): пополняется автоматически при connect/vendor/update; явный
  выбор (`--profile`/`--plugins`/`--buckets`) воспроизводится при `update`,
  автодетект пере-резолвится с диска; атомарная запись, самовосстановление
  adopt-ом после потери файла
- **Внутренние скиллы `.claude/skills/`** (не экспортируются): полная карта
  пакета (`package-architecture`), процедура авторинга скиллов с проверкой
  пересечений и обязательным upstream.json для внешних (`skill-authoring`),
  дисциплина завершения изменений (`release-discipline`), решение об
  обновлении docs/ после задач (`docs-maintenance`)
- **validate.sh секции 10–11**: мягкий линт внутренних скиллов
  (name+description, kebab-case == каталог, warning при коллизии с реестром);
  `bash -n` всех скриптов + исполняемость CLI
- **`docs/guide/cli.md`**: справочник команд CLI, схема projects.json,
  поиск корня проекта, troubleshooting

### Changed (CLI swissknifeman)

- **`install.sh` перепрофилирован в установщик CLI** (симлинк
  `~/.local/bin/swissknifeman` → `bin/swissknifeman`, идемпотентен,
  PATH-подсказка под шелл); **breaking**: legacy-вендоринг
  `./install.sh <dir> <bucket>` удалён — `swissknifeman vendor`
- `scripts/connect-claude.sh` и `./sync.sh --update-registry` —
  deprecation-wrapper'ы на один релиз, переадресуют в CLI
- `docs/guide/installation.md` переписан под двухшаговую установку
  (CLI один раз → `connect`/`vendor` из проекта); README и остальные
  страницы docs переведены на команды CLI

### Removed (CLI swissknifeman)

- **Brain-sync** (`sync_to_brain`, `BRAIN_PATH`, workflow
  `.github/workflows/sync-to-brain.yml`): зеркалирования в brain больше нет —
  brain подключается как обычный проект
  (`cd <brain> && swissknifeman vendor`, дальше `swissknifeman update`)

### Added (improvement report v2: граф зависимостей + методология)

- **Dependency resolution в install.sh**: frontmatter `requires` разрешается
  транзитивно при выборочной установке (`--buckets`/`--exclude`), в том числе
  кросс-бакетно; `--exclude` побеждает зависимость с предупреждением; дотянутые
  скиллы помечаются в `--list`/`--dry-run` как `(dependency of <skill>)`
- **Валидация графа в validate.sh** (секция 9): существование имён в
  `requires`/`produces_for`, self-reference, циклы по `requires` (DFS);
  warning на не-inline списки
- **`scripts/generate-graph.sh`**: Mermaid-граф зависимостей →
  `docs/guide/graph.md` (subgraph на бакет, только связные узлы, изолированные —
  таблицей); вызывается из `sync.sh --update-registry`; в VitePress подключён
  `vitepress-plugin-mermaid`
- **Реестр skills.json v5**: поля `tags`, `requires`, `produces_for`
  в записях скиллов (опциональны, опускаются если пусты)
- **`general/anti-drift` (0.1.0)**: методология Karpathy (think-before-coding,
  simplicity-first, surgical-changes, goal-driven) + circuit-breaker пороги;
  сниппет-блок для CLAUDE.md целевого проекта
- **`general/spec-interview` (0.1.0)**: grill-me-style интервью перед кодом —
  вопросы по одному, агент сам читает кодовую базу, рекомендованный ответ
  к каждому вопросу; итог — заполненный task-brief-template
- **`general/session-handoff` (0.1.0)**: протокол передачи контекста между
  сессиями/агентами; сниппет handoff-template.md
- **`quality/code-simplifier` (0.1.0)**: упрощение свежего диффа без изменения
  поведения; сниппет GitHub Actions `simplify-on-push.yml`
- **`php/laravel-security-audit` (0.1.0)**: sharp-edges-аудит Laravel
  (raw-запросы, mass assignment, XSS в Blade, CSRF/redirect,
  сериализация/авторизация) с references/ по каждой грани; сниппет
  GitHub Actions `security-audit-scheduled.yml`; requires: static-analysis
- **`docs/workflows/background-agents.md`**: фоновые агенты в CI — шаблоны,
  требования, ограничение стоимости, анти-дрифт правила

### Changed (improvement report v2)

- `general/task-brief-template` 0.2.0 → 0.3.0: секции «Явные предположения»,
  «Out of Scope», «Definition of Done» в шаблоне ТЗ
- `oss-dev/dependency-audit` 0.1.0 → 0.2.0: `references/composer.md` —
  composer-специфика аудита (composer audit/outdated/licenses,
  roave/security-advisories, reproducible installs, composer-грабли, SBOM)
- `php/filament`: `produces_for: [backend-dev, fullstack-dev]` → `[]` — таких
  скиллов не существует (поймано новой валидацией графа)
- `docs/boost-compatibility.md`: ссылка на карточку laravel-boost ведёт на
  GitHub (относительный путь вне docs-корня ломал сборку VitePress)

### Rejected (improvement report v2, по итогам анализа)

- `registry.json` — уже существует как `skills.json` (богаче: sha256,
  provenance, upstream)
- Tier-система (0–4) во фронтматтере — дублирует ось бакеты+профили+requires
- `caveman`-скилл — покрыт `general/compact-responses`
- `composer-audit` как отдельный скилл — расширение `dependency-audit`
- Фоновые workflow в самом реестре — только шаблоны для целевых проектов

### Added (token optimization wave)

- **`php/pao` (1.0.0)**: скилл по laravel/pao — агентно-оптимизированный вывод
  PHPUnit/Pest/PHPStan/Rector/Artisan (~20 токенов JSON вместо тысяч);
  установка, проверка, ограничения
- **`general/context-economy` (1.0.0)**: экономия контекста Claude Code —
  CLAUDE.md ≤200 строк, path-scoped `.claude/rules/` с `paths:`, /compact vs
  /clear, Plan→Clear→Execute, аудит MCP, нативная маршрутизация моделей;
  сниппеты: шаблон правила, команды /prime //plan //execute, чеклист аудита
  CLAUDE.md
- deny-блок «токен-шума» в пресетах `configs/claude-code/settings.laravel.json`
  и `settings.node.json` (`storage/logs`, `node_modules`, `*.lock`, кэши,
  бандлы); `vendor/` сознательно не блокируется — там Boost-гайдлайны

### Changed

- **`php/filament` 0.2.0 → 1.0.0**: переписан с v3 на Filament v5 — структура
  v5-генератора (Schemas/ + Tables/), таблица корректных namespaces
  (`Filament\Actions\*`, `Filament\Schemas\Components\*`), CLI-справочник
  `make:filament-*`, union-типы свойств, типичные ошибки из официальных
  Boost-гайдлайнов; snippets обновлены под v5 + новый
  `forms-tables-reference.md`; upstream.json отслеживает
  filamentphp/filament `boost/guidelines/core.blade.php` (strategy=notify)
- `general/compact-responses` 0.1.0 → 0.2.0: поведенческие шаблоны цикла
  разработки (`✓ tests passed (N)`, только упавший тест при ошибке) и формат
  единственного развёрнутого финального отчёта
- `general/task-brief-template`: раздел Plan→Clear→Execute (план и выполнение —
  раздельные сессии)

### Rejected (по итогам фактчека отчётов Perplexity)

- `.claudeignore` — не существует в Claude Code (рабочий механизм —
  `permissions.deny: Read(...)`)
- `paths:` frontmatter для SKILL.md — `paths:` работает только в
  `.claude/rules/`; скиллы и так загружаются лениво
- claude-code-router — сторонний прокси; нативный `/model` достаточен
- waaseyaa/agent-output как стандарт — перекрывается laravel/pao
- `deny Read(vendor/**)` — ломает чтение Boost-гайдлайнов

## [0.3.0] - 2026-06-11

### Added

- **Нативный plugin marketplace Claude Code**: `.claude-plugin/marketplace.json`
  + `plugin.json` на каждый bucket (генерируются `sync.sh --update-registry`,
  метаданные в `buckets.json`); плагин = bucket, скиллы с неймспейсом
  `<bucket>:<skill>`, версия плагина = git SHA
- **`scripts/connect-claude.sh`**: подключение проекта к marketplace —
  автодетект профиля, идемпотентный merge `extraKnownMarketplaces` +
  `enabledPlugins` в `.claude/settings.local.json`, `--dry-run`/`--list`,
  миграция со старого вендоринга (`--cleanup-vendored` удаляет только
  манифестные копии)
- **`buckets.json`**: description/category/tags на bucket; описания попадают
  в plugin-манифесты и skills.json (registry v4)
- **Схема-валидация `.swissknife.json`** в install.sh и connect-claude.sh:
  неизвестный ключ/тип → ошибка с подсказкой (`did you mean 'buckets'?`)
- **Манифест и коллизии в bucket-режиме install.sh**: `.swissknifeman-manifest.json`
  теперь пишется и в generic/cursor-режиме (чистая переустановка), существующие
  чужие папки — ошибка-коллизия, перезапись только с `--force`
- validate.sh: проверки buckets.json, свежести plugin-манифестов,
  уникальности имён скиллов

### Changed

- `generate-skill/` реструктурирован в layout плагина
  (`generate-skill/generate-skill/SKILL.md`)
- `--agent claude` в install.sh — deprecated (предпочтителен marketplace);
  `.claude-plugin/` исключён из вендоринга и brain-sync
- Документация: адаптер Claude Code переписан вокруг marketplace,
  гайд установки разделён на каналы Claude Code / Cursor-generic
- Ссылки на `references/` в `oss-dev/oss-development` исправлены на
  относительные к скиллу (`../references/...`)

### Added (docs & configs wave)

- **Документация на VitePress** (`docs/`): гайд (принципы, установка, профили,
  анатомия скилла, upstream-sync, реестр, сканер, CI), конфиги, адаптеры,
  примеры, roadmap; деплой на GitHub Pages (`docs.yml`)
- **Пресеты permissions для Claude Code** (`configs/claude-code/`):
  base/laravel/php-package/node/python/docker/yolo +
  `scripts/apply-permissions.sh` (merge в settings.local.json, автодетект стека,
  dry-run, бэкап)
- **Vendor-skills**: универсальный механизм публикации скиллов из Composer-пакета
  потребителю через `vendor:publish` — док-страница + переработанный скилл
  `php/laravel-packages` (v0.3.0) со сниппетом `boost-skill-publisher.php`
- **Спецификация адаптерных дельт**: формат `Override:`/`Additional:`,
  pre-flight хуки, критерии «когда дельта нужна»
- Критерии качества сниппетов для сканера (порог 60/100) в документации
- Roadmap: ближайшие фазы + стратегические/технические/экспериментальные идеи
  (перенесено из tmp-черновиков master-plan v3, черновики удалены)

## [0.2.0] - 2026-06-11

### Added

- **Upstream-sync система**: per-skill `upstream.json` (source, strategy replace/notify,
  sha256, fetched_at), `scripts/update-upstreams.sh` (--check/--apply/--force, exit-коды
  для CI), еженедельный workflow `upstream-sync.yml` с PR-ревью
- `upstream.json` + baseline для всех 12 `skills/imported/*` (get-zeked super-skills)
- **Контекстная установка**: `install.sh` v2 — автодетект типа проекта, `profiles/*.json`
  (obsidian-vault, laravel-project, php-package, standalone), `.swissknife.json` override,
  `--agent claude` с плоской раскладкой под `.claude/skills/` и manifest-cleanup
- **`references/`** — каталог 15 внешних источников с принципом выборочного отбора
- `scripts/validate.sh` — единая валидация (frontmatter, upstream.json, profiles,
  реестр, snippet-манифесты) локально и в CI
- Provenance в `skills.json`: `source: local|github|http`, `upstream`, `fetched_at`
- `.swissknife.example.json`

### Fixed

- `validate.yml`: glob `skills/**` не работал в bash без globstar — CI фактически
  не валидировал скиллы
- `sync.sh`: name/description парсились по всему файлу, а не только из frontmatter
- `skills/pm/prd-from-brd`: отсутствовало поле `version` во frontmatter

## [0.1.0] - 2026-06-11

### Added

- Skills registry v3 with 65 skills across 10 buckets
- Migration of 36 skills from `academici/brain`
- New buckets: devops, php, roles, imported
- 12 perplexity super-skills in `skills/imported/`
- PHP skills: laravel, laravel-permissions (with AzGuard patterns), laravel-testing, laravel-packages, php-patterns, botkit, filament
- DevOps skills: docker (php, vite, postgres, dev-prod), ci-cd, gitops
- Roles: startup-cto, tech-lead, open-source-maintainer, solo-founder
- `install.sh`, `sync.sh`, scanner pipeline
- CI: validate, sha256-update, sync-to-brain, scanner-pr
- Adapters: cursor, claude-code, perplexity
- `generate-skill/` meta-skill
