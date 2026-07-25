# User intent traceability

**Основание:** `brief/00-brief.md`, `findings/repository-baseline-2026-07-19.md`.

| Мысль владельца | Где проектируется | Где доказывается |
|:--|:--|:--|
| Один SSOT, два provider adapter'а | P0.2–P2 | owner-approved glossary + artifact contract + drift tests |
| `AGENTS.md` — semantic Codex-аналог `CLAUDE.md`, оба из common instruction canon | P5.6–P5.7, P6.2 | frozen instruction contract + root/five-package semantic-parity, drift/repair и Claude back-compat conformance |
| Providers в project/fleet config | P1 | schema fixtures + migration/backcompat tests |
| Все skills и marketplaces для обоих | P3 | inventory parity + install/update E2E |
| Все task-команды и фазы плана | P4 | command parity matrix + dual-provider smoke |
| Provider-native фишки, hooks, permissions, cache/context | P5 | capability-aware harness fixtures |
| mAInd, memory, code graph, Perplexity и analytics | P6 | MCP/status/session continuity tests |
| README-таблица возможностей | P7.1 | generated-doc drift gate |
| Сначала миграция, FOREMAN потом | P0.4, P7.4 | frozen migration-gate contract + adversarial release evidence |
| Массовая раскатка только после FOREMAN | Scope Excluded + P7 handoff | отдельный последующий fleet plan |
| Минимум approval prompts | P0.2/P0.4, P5.2, P7 docs | отдельные approval/sandbox/trust semantics + security profiles |
| Перезапуски не теряют состояние | P6.5–P6.6 | committed disk+mAInd checkpoint + обязательный cold-session proof фактических instruction/config/provider hashes |

Трассировка считается полной, когда каждый row имеет хотя бы один детализированный item
с конечными Required Reads, Validation и Deliverables. Post-audit instruction refinement
детализирован в `research/13-instruction-contract-remediation.md`.
