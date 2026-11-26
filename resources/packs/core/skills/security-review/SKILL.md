---
name: security-review
description: Review a sealed change for authorization, secrets, injection, sandbox boundaries, supply chain, and cryptographic failures without modifying files.
---
# Security Review

Apply this specialization on top of the generic review method. Stay inside the reviewer role and the closed result contract.

## Rules
1. Inspect authorization and trust boundaries touched by the diff, including missing checks and confused-deputy paths.
2. Trace secrets, credentials, and private material through logs, prompts, config, and error output.
3. Check injection surfaces: command, query, path, template, and deserialization inputs that cross a trust boundary.
4. Check sandbox, permission, and supply-chain boundaries, including new dependencies and weakened isolation.
5. Check cryptographic use for algorithm, key, and nonce mistakes that the diff introduces.
6. Report only actionable findings with location, trigger, impact, and proposed resolution. Do not modify files.
