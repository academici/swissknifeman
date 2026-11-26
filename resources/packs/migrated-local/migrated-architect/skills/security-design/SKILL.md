---
name: security-design
description: "Design or review changed trust, auth, secrets, sensitive-data, or external exposure boundaries."
---

# Security Design

Use for a system launch or a change affecting trust, authentication, authorization, secrets,
sensitive data, or external exposure. Assess the affected boundary during design; a routine
unrelated edit in an app with users does not require a full security document or human gate.

## Identify the boundary

Record assets and data sensitivity, actors/tenants, entry points, privilege changes, external
integrations, and plausible abuse. Use STRIDE when it helps structure an actual threat model:
spoofing, tampering, repudiation, disclosure, denial of service, elevation of privilege.
Read [STRIDE template](snippets/stride-threat-model.md) when writing that model and
[operations checklist](snippets/ops-security-checklist.md) for an operational review.

## Controls to preserve

- Authentication: choose established mechanisms for actual client/session needs. Revocation,
  expiry, recovery, brute-force resistance, and secure session handling matter more than one
  scheme per client. Shared session storage can support multiple app instances; JWT, cookies,
  OIDC, and API keys are design options, not interchangeable proof of safety.
- Authorization: enforce resource, tenant, and action access on the server. Check both allowed
  and denied paths, including a user requesting another user's object by direct ID. RBAC,
  ABAC, and ownership checks may be combined where the domain needs them.
- Input and output: validate untrusted input, use parameterized queries, constrain uploads and
  outbound URL requests, prevent output injection, and return only permitted data. An ORM
  does not make raw queries safe. Bound resource use on exposed operations.
- Credentials: use suitable password hashing, scoped secrets storage, and secure transport.
  Never place secret API keys in client code or credentials in source control/logs. Rotate on
  compromise and under the actual provider/project policy; a fixed annual interval is not a
  universal security guarantee.
- Data: minimize collection, access, retention, and log exposure. Apply encryption, audit,
  backup, deletion, and recovery controls required by the threat model and applicable policy.
  Payment data handling must follow the actual processor/compliance boundary; avoid collecting
  raw payment credentials when the provider can handle them.
- Supply chain and deployment: assess relevant dependencies, debug/default settings, trusted
  build inputs, secret exposure, and recovery. State checks actually performed and gaps.

## Privacy and review boundaries

Verify applicable legal requirements with current primary sources when making a compliance
claim. Consent is not a universal legal basis for all personal-data processing, and deletion,
retention, portability, and payment obligations depend on scope. Use
`architect/legal-compliance` for that decision; do not label this checklist a compliance proof.

Before exposing new risk, resolve demonstrated vulnerabilities and the project's required
release checks. Escalate an unresolved high-impact security decision or a required independent
review to its owner. Merely touching auth/secrets/data code does not require a new human
approval when the authorized repair and adopted checks cover it. AI review is evidence with
limits, not a substitute for qualified review where the risk/policy requires that expertise.

Update existing security design/docs for changed assumptions or controls. Report the relevant
threats, implemented defenses, negative test evidence, and unresolved exposure. Keep safe
independent work moving while a genuine decision is pending.
