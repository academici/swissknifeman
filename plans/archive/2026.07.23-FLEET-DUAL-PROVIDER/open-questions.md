# Open Questions — 2026.07.23-FLEET-DUAL-PROVIDER

## OQ1 — Разрешить ли read-only diagnosis `azguard`

**Status:** Resolved → D12

**Предлагаемое решение:** APPROVE — записать D12 и разрешить P2.2 только
read-only diagnosis по spec в `phases/P2.md`: clean-worktree gate, exact
no-write dry-run/health, чтение только diagnostic-named ownership targets и
zero-write evidence.

**Альтернатива:** REJECT/DEFER — оставить P2.2 `🔴 Blocked`; ни один live
consumer не инспектировать и не изменять.

**Не разрешается ни одним выбором:** mutation, normal apply, provider-selection
edit, ownership adoption, `--repair`, `--force`, доступ к другому consumer или
ослабление D5–D7. Для этого потребуется отдельный item и новая Owner Approval.

**Решение владельца:** APPROVE расширено D12 до автономного in-scope
conflict remediation и terminal завершения P2.2. Dirty/unmanaged bytes без
точного безопасного решения, `--repair`, `--force`, D5 target и self-host
остались исключены.
