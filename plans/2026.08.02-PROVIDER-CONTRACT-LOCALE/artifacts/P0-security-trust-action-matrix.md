# P0 security and trust action matrix

**Version:** v1.0.1

**Status:** frozen no-op baseline; recovery contract v1.0.1 approved by D67

| Surface | Evidence reference | Exposure state | Trust state | Action | Authority |
|:--|:--|:--|:--|:--|:--|
| credential containment | redacted P0.4 detector | unknown until fresh detector | n/a | no-op | no mutation authority |
| Claude Code trust | redacted P0.4 provider row | n/a | unknown until fresh check | no-op | no mutation authority |
| Codex trust | redacted P0.4 provider row | n/a | unknown until fresh check | no-op | no mutation authority |

`action_set=[]`. This matrix contains semantic references and boolean states only;
it contains no credential material, account identifier, target root, backup bytes, or
provider-side procedure. A non-empty action set is a P0.4 authority boundary.

Recovery admission is evaluated by corrective contract `v1.0.1`. D67 accepts its exact bytes;
the decision authorizes no containment, credential, trust, provider, Brain, or fleet mutation.
Decision history: `pending exact freeze decision` → D67 accepted.
