# P7 design synthesis — docs, self-hosting и release gate

**Дата:** 2026-07-19

**Основание:** `brief/00-brief.md`, `brief/01-refinements.md`,
`research/01-target-architecture-options.md`, `research/02-sequence-and-boundaries.md`,
`research/10-p6-maind-analytics-bootstrap-design.md`, draft
`root/contracts/provider-{capability,config,harness,analytics}-contract.md`, D1–D37 и
`findings/P7-openai-model-routing-2026-07-19.md`.

## Граница P7

P7 не добавляет provider semantics и не исправляет package implementation. Она принимает
terminal/frozen outputs P0–P6, делает их видимыми оператору, затем доказывает end-to-end
delivery на isolated roots и на самом `swissknifeman`. Только после доказанного self-host
она заменяет временные bootstrap adapters generated outputs и формирует release manifest.
FOREMAN остаётся read-only consumer будущего GREEN gate; fleet остаётся вне scope.

RAG:— (repo-grounded: `brief/00-brief.md`, `research/02-sequence-and-boundaries.md`, D6/D7/D11/D12)

## Alternatives

### Источник capability docs

| Вариант | Плюсы | Минусы | Вердикт |
|:--|:--|:--|:--|
| Ручная README matrix | быстро написать | второй канон, drift с adapters/diagnostics | отклонить |
| Генерировать из фактического provider output | отражает текущие bytes | самоподтверждение ошибочного renderer | отклонить |
| Генерировать из frozen capability/catalog source + независимый exact-set | один semantic source и проверяемый drift | требует source/version/hash markers | принять |

### Порядок self-host

| Вариант | Плюсы | Минусы | Вердикт |
|:--|:--|:--|:--|
| Сразу live apply | коротко | высокий blast radius, rollback не доказан | отклонить |
| Только temp E2E | безопасно | не доказывает реальные root/bootstrap conflicts | недостаточно |
| Isolated matrix → rollback rehearsal → live SKM-only apply/check | ограничивает риск и доказывает реальный pilot | требует строгих anchors/backup | принять |

### Cleanup bootstrap

| Вариант | Плюсы | Минусы | Вердикт |
|:--|:--|:--|:--|
| Удалить `.agents` целиком | нет дублей | разрушает adapters/user-owned surfaces | запрещено |
| Оставить всё | нулевой delete-risk | новый агент не различает bootstrap и release | отклонить |
| Per-path ownership+replacement proof, reversible cleanup | сохраняет канон/пользовательское и снимает обходки | требует инвентаря и post-smoke | принять |

### Кто открывает FOREMAN gate

| Вариант | Плюсы | Минусы | Вердикт |
|:--|:--|:--|:--|
| P7.3 автоматически после release manifest | меньше ручных шагов | исполнитель сам утверждает свой результат | отклонить |
| P7.4 audit без owner D# | независимее | gate всё ещё может открыться без владельца | недостаточно |
| P7.4 adversarial audit + explicit Approval Owner D# | separation of duties и явный blast-radius gate | отдельный запуск | принять |

## Item sequence и orchestration

1. P7.1 строит docs/matrix из frozen sources и независимый exact-set.
2. P7.2 использует docs+terminal operations для isolated/live self-host E2E.
3. P7.3 потребляет точный managed diff P7.2, выполняет guarded cleanup и release manifest.
4. P7.4 cold-start проверяет весь bundle и запрашивает owner verdict.

Items последовательно зависят друг от друга; N≥3 independent scopes отсутствует. Workflow
criterion не срабатывает. Каждый item идёт solo, потому что его terminal evidence является
entry gate следующего, а P7.4 должен быть контекстно независим от исполнителя cleanup.

## ChatGPT/Codex model routing

Official OpenAI guidance из `findings/P7-openai-model-routing-2026-07-19.md` даёт Sol как
flagship complex reasoning/coding и Terra как balance tier. Поэтому весь plan Routing
переводится с Claude model names на current ChatGPT/Codex IDs: design/contracts/audit →
Sol, prescribed implementation → Terra. P7.1 детерминированный docs item идёт на
Terra/medium; P7.2–P7.3 — Terra/high; P7.4, `finish` и design audit — Sol/xhigh.
Luna исключена из release critical path.

RAG:✅ 2026-07-19 (official OpenAI model catalog; `findings/P7-openai-model-routing-2026-07-19.md`)

## Pre-mortem P7

| Отказ | Ранний сигнал | Mitigation | Owner/item |
|:--|:--|:--|:--|
| Docs подтверждают тот же ошибочный renderer | expected matrix построена из output | independent expected inventory из frozen sources | P7.1 |
| Live self-host ломает Claude surface | temp зелёный, live diff касается unmanaged bytes | backup+rollback rehearsal, managed-only apply, Claude goldens | P7.2 |
| Partial provider failure скрыт общим GREEN | нет provider-tagged rows | required-provider fail-closed exact-set | P7.2 |
| Cleanup удаляет канон/user file | path без owner/source hash | per-path provenance+replacement proof, reversible move | P7.3 |
| Bootstrap остаётся вторым каноном | residual adapter без classification | residual ownership is release blocker | P7.3–P7.4 |
| Release manifest ссылается на uncommitted/draft state | placeholder hashes/contract versions | committed anchors + frozen-version gate | P7.3–P7.4 |
| Audit сам открывает FOREMAN/fleet | donor diff или нет owner D# | P7.4 read-only donor check + explicit Approval Owner GREEN | P7.4/Owner |
| Сильная модель потрачена на механику или слабая — на audit | blanket model row | Terra implementation, Sol design/audit, per-item Routing | plan §3/P7.4 |

## Проверка (verification status)

- RAG: official OpenAI model catalog ×1 official-domain fallback — OK; details captured in
  `findings/P7-openai-model-routing-2026-07-19.md`.
- Repo-grounding: использован только заданный cold-start set плюс read-only
  `plans/2026.07.18-FOREMAN/roadmap.md` как форматный образец после уточнения владельца.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: exact P3–P6 public command names и final generated paths
  ещё не существуют; P7 items разрешают их только из terminal predecessor artifacts.
- Обходки/[POSSIBLE-DEFECT]: current bootstrap adapters и draft contracts не считаются
  release evidence; plan-lint не принимает существующую `plan-design <ID> finish` Next-форму,
  поэтому handoff использует manual declaration при сохранённой фактической Codex-команде
  (D41); package code/scripts в design-заходе не исполнялись.
