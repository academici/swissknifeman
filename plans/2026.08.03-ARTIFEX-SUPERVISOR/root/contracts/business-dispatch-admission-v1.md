# Business Dispatch Admission Contract v1

`business-dispatch-admission-v1@1.0.0` is the D108 additive successor to the
immutable G2 smoke contract. It reads, but never rewrites, exactly fourteen
D105 admission bytes. Each accepted admission must be an indexed
`artifex-business-dispatch-admission-v1` for `business-trial`, bind D105,
`P5.2|P5.3|P5.4`, one provider, one unused replay identity, and the immutable
G2 predecessor digest. The currently executing package is accepted separately
only when its complete file set equals the sole G2B digest in the generation
manifest.

The two checks are deliberately not interchangeable: a D105 task's
`g2_package_digest` remains the historical G2 pin, while G2B is the current
runtime pin. Unknown fields or versions, a changed hash/index/cardinality,
revocation, expiry, changed provider/root/files/capabilities, replay reuse,
G2/G2B substitution, or any nonzero use refuse before intent.

Only two D108 non-business capability probes are permitted: one on each
`mktemp:p5-g2b-*` root, each with one fresh process and the D108 caps. They
have no D105 admission, dispatch intent, or usage row. Codex `0.146.0` must use
ephemeral JSONL, isolated user configuration, `workspace-write`, approval
never, disabled network/web/child features and an explicit output schema.
Claude Code `2.1.222` must use one no-persistence JSON request, `dontAsk`, an
empty strict MCP file, excluded child/web tools, and only the disposable-root
file tools. Any version or mechanically enforceable-control mismatch refuses.
