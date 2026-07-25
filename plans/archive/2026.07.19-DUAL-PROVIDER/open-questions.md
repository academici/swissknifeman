# Open Questions — 2026.07.19-DUAL-PROVIDER

## OQ-P7.2-1 — live provider selection и `.mcp.json` ownership

**Статус:** Resolved → D108 (`S1+O1`)

Нужен один двухосевой выбор из
`research/25-p7.2-owner-authority-boundary.md`: рекомендованный `S1+O1` явно включает
оба provider только для `swissknifeman` и разрешает design/no-write exact P2 transfer
candidate для текущего `.mcp.json` preimage; `S0+O0` сохраняет status quo и прекращает P7/план.
Смешанные комбинации не открывают P7.2. Standing delegation
`mem_mrwffj6x_4e58b0e7e65d` разрешила агенту зафиксировать логически определённый
contract-preserving/reversible design-only выбор без повторного literal; D108 выбрал
`S1+O1`. Exact remediation — `research/26-p7.2-s1-o1-remediation-design.md`; live state и
package source этой design-сессией не меняются, а live mutation остаётся отдельным P7.2 gate.
