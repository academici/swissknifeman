# Provider domain scenarios

> **OWNER-APPROVED — D53.** Весь scenario set утверждён вместе с glossary
> `root/CONTEXT.md` на terminal P0.5 evidence boundary.

**Item:** P0.2  
**Vocabulary:** `root/CONTEXT.md`  
**Approval:** D53, 2026-07-20

Сценарии проверяют смысл терминов до появления schema и implementation. Diagnostic здесь —
обязательное объяснение пользователю, а не имя будущего exception или JSON-поля.

## Scenario matrix

| ID | Given | When | Expected semantics | Required diagnostic |
|:--|:--|:--|:--|:--|
| S1 | Provider напрямую предоставляет Capability своей нативной семантикой. | Capability оценивается для этого Provider. | Support Level = `native`; Adapter сохраняет native binding и не эмулирует другой Provider. | Назвать Capability, Provider, `native` и evidence native binding. |
| S2 | Общий intent достижим только детерминированной provider projection. | Capability оценивается для этого Provider. | Support Level = `adapted`; observable semantic promise сохраняется, provider-specific форма остаётся Adapter detail. | Назвать `adapted`, Adapter identity и проверяемое ограничение projection. |
| S3 | У Provider нет поддерживаемого semantic эквивалента Capability. | Consumer запрашивает Capability. | Support Level = `unsupported`; операция fail-closed или явно исключает capability, но не объявляет parity. | Назвать Provider/Capability, `unsupported` и допустимое следующее действие. |
| S4 | Project не trusted Provider'ом, хотя project config и Rendered Artifacts присутствуют. | Запрашивается project-scoped activation. | Project Trust блокирует activation; Approval Policy и Sandbox Boundary не подменяют trust decision. | Отдельно сообщить untrusted state; не советовать ослабить sandbox как repair. |
| S5 | Managed Artifact имеет разрешённый project-owned Override вне managed boundary. | Drift-проверка видит отличающийся effective intent. | Override сохраняется отдельным input и сам по себе не является Drift; Rendered Artifact вычисляется с учётом него. | Показать provenance Override и подтвердить, что managed/user ownership не смешаны. |
| S6 | Source identity прежняя, но observed rendered hash не совпадает с ожидаемым. | Doctor проверяет Managed Artifact. | Это классифицируемый Drift; Repair разрешён только после проверки provenance и managed boundary. | Назвать stale rendered state, expected/observed evidence и безопасную repair boundary. |
| S7 | Явный provider config отсутствует у legacy проекта. | Определяется effective Provider для compatibility path. | Missing не означает explicit disable; применяется Claude-compatible default, пока P1 contract не задаст иной явный input. | Сообщить default и provenance решения; не записывать config молча. |
| S8 | Один Provider предлагает полезную возможность без semantic аналога у второго. | Capability catalog строит общую matrix. | Возможность остаётся Native Extension этого Provider; общий contract не выравнивается до lowest common denominator. | Отметить extension owner/provider и отсутствие parity claim. |
| S9 | Approval Policy отключает prompts, но Sandbox Boundary остаётся ограниченной. | Операция выходит за sandbox. | Операция остаётся запрещённой; `never` не расширяет доступ и не доказывает Project Trust. | Раздельно показать approval choice, sandbox denial и trust state. |
| S10 | Terminal P0.5 на tree `d8ac22c04fc4d4219dc95244ee9d181e92553a74` показывает umbrella Command Surface `32 = task 11 + skiller 5 + harness 6 + maind 8 + analyst 2`, а P0.1 содержит только task set 11. | Command inventory используется как vocabulary/contract input. | Command Surface означает union пяти explicit top-level roots; Task Command означает semantic `packages/task/commands` subset. Оба counts tree-anchored, не frozen invariants; historical P0.1 не переписывается. | Назвать P0.5 anchor, все пять roots и distinction umbrella/subset; не объявлять package commands skiller/harness/maind/analyst Task Commands и не включать nested agent-pack commands. |

## Cross-context walkthroughs

### W1 — Canonical source to provider output

`task/command-contract` владеет Task Command → `core/providers` определяет Capability и Support
Level → provider Adapter создаёт Rendered Artifact → `core/artifacts` определяет, стал ли он
Managed Artifact → `maind/deployment` применяет lifecycle без получения renderer ownership.

### W2 — Safe autonomy

`harness/rendering` выбирает provider-native Approval Policy и Sandbox Boundary →
`maind/deployment` проверяет Project Trust перед activation → отсутствие approval prompts не
может повысить trust или расширить sandbox.

### W3 — Local intent without canonical fork

Canonical Source остаётся author-owned → project-owned Override меняет effective intent →
Adapter рендерит provider-native форму → Drift сравнивает expected/observed managed state →
Repair меняет только declared managed boundary.

## Approval checklist

- [x] Approval Owner принимает 17 canonical headings, включая разные Command Surface и Task Command.
- [x] Approval Owner принимает три Support Level: `native`, `adapted`, `unsupported`.
- [x] Approval Owner принимает независимость Project Trust, Approval Policy и Sandbox Boundary.
- [x] Approval Owner принимает distinction Canonical Source / Rendered Artifact / Managed Artifact.
- [x] Approval Owner принимает Override ≠ Drift и ограниченную managed boundary семантику Repair.
- [x] Approval Owner принимает terminal P0.5 anchor `d8ac22c04fc4d4219dc95244ee9d181e92553a74`: `32` как current umbrella Command Surface, `11` как current Task Command subset, без превращения counts в frozen invariants.
