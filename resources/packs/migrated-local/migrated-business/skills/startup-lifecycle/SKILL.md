---
name: startup-lifecycle
description: "4 AI-native startup stages (Idea→MVP→Launch→Scale) with exit-criteria, failure modes, antidotes + stage-gate review method"
---

# Skill: Startup Lifecycle

Apply when: identify **which stage** a project is at, which skills are relevant now, and **whether it's ready to advance** (stage-gate review). Canonical frame from Founder's Playbook (Anthropic 2026); backbone for all other founder/pm skills.

Core principle of agentic coding: bottleneck is no longer "what you can build" but "what you choose to build" — AI erased build cost → validation discipline matters more than ever.

## Do NOT apply when
- A concrete artifact is needed (BRD, GTM, risks) — load the target skill, not the frame.
- Purely technical code question — not a lifecycle decision.
- Project is not a startup (OSS package, agency) — validation stages don't apply.

## 4 stages

### 1. Idea — `stage: idea`
**Goal:** research-oriented validation → **problem-solution fit**. Gather qualitative evidence (mainly from live conversations) that a real problem exists and the solution addresses it — **before** the first line of production code.
**Exit (3 "yes"):**
1. Problem real, specific, frequent enough? (who exactly hits it, how often, how painful, what they do now)
2. Solution hits the **real** problem validation uncovered (not the assumed one)?
3. Enough signal to justify MVP? (not a certificate — a reasoned decision vs act of faith)
**Failure modes:** mistaking building for validating · premature scaling · loss of objectivity (confirmation bias × AI).
**Skills:** `idea-discovery` → `adversarial-check` → `customer-discovery` → `competitive-analysis` → `risk-assessment`.

### 2. MVP — `stage: mvp`
**Goal:** turn validated problem into a **working product** (smallest focused iteration, not full roadmap); move fast **without** accruing tech debt; invest in persistent context (CLAUDE.md) from day one.
**Exit:** genuine PMF — proof that a specific identifiable group values the product enough to **return** (retention), **pay** (revenue), or **tell others** (referral). Pattern across several iterations, not one point.
**Failure modes:** agentic technical debt · false PMF · zero-friction scope creep · insecure by inexperience.
**Skills:** `architecture` (+CLAUDE.md) → `product-roadmap` (scope + amendment-criteria) → `security-design` (gate before first user) → `pmf-diagnostics` → `tech-debt-audit`.

### 3. Launch — `stage: launch`
**Goal:** turn early traction into a **repeatable sustainable growth engine**; harden infrastructure; build company around product.
**Exit (3 parts):**
1. Growth repeatable and channel-driven (known CAC, LTV, payback).
2. Product holds production load (hardened, security, compliance, reliability — not just test conditions).
3. Operations run **without** founder-bottleneck (processes and automation in place).
**Failure modes:** technical debt comes due · founder = bottleneck · security/compliance can't be deferred · expansion before readiness.
**Skills:** `go-to-market` (as function) · `tech-debt-audit` (architectural audit) · `security-design` (SOC2/GDPR/HIPAA workstream) · `capacity-planning` · `oncall-rotation`.

### 4. Scale — `stage: scale`
**Goal:** systematic growth + **defensible moat through accumulated depth**; founder role → public-facing executive.
**Exit (threshold, not milestone):** sustainable profitability (no external capital) / IPO-readiness / acquisition. Litmus: *"If a well-funded incumbent copied the product today — would users stay?"*
**Failure modes:** delegating the operational layer (psychologically and structurally) · scaling org functions · no GTM function.
**Skills:** `defensibility` (data flywheel, workflow lock-in, domain-as-context) · `capacity-planning` · `go-to-market` (analyst/investor/enterprise voice).

## Method: stage-gate review
On "ready to advance?" — run current stage's exit-criteria as a checklist:
1. Determine current `stage:` from control-tower frontmatter.
2. Take this stage's exit-condition (above) → decompose into checkable items.
3. Per item: ✅ done / ⚠️ partial (what's missing) / ❌ no (what to do).
   **Evidence gate:** each ✅ must rest on at least **1 external signal** — market data / live conversation / experiment (not internal opinion or AI inference). No external signal → status caps at ⚠️, not ✅.
4. **Before a "ready" verdict — mandatory [[adversarial-check]]:** "what here is real signal vs wishful thinking?" (see failure mode loss-of-objectivity).
5. Verdict: `PROCEED` (all ✅) / `HOLD` (any ⚠️/❌ + action list) / `PIVOT` (exit unreachable on current hypothesis).
On `PROCEED` — bump `stage:` in project frontmatter.

## Agent adds on its own
- **Activity↔stage mismatch.** If `stage: idea` but already writing production code — name it: "this is building before validating".
- **Stage-aware routing.** By stage, name relevant persona + skill set (idea→Founder, mvp→Architect+Quality, launch→PM+Operator, scale→Operator+PM).
- **Portfolio context.** If many projects in registry are `idea` — flag portfolio risk "building unvalidated".

## Output file structure
`docs/01_Business/Stage_Gate_Review.md`:
```markdown
---
project: [ProjectName]
stage_from: idea
review_date: YYYY-MM-DD
verdict: PROCEED | HOLD | PIVOT
---

# Stage-Gate Review — [ProjectName]: idea → mvp

## Exit-criteria
| Criterion | Status | External signal (source) | Missing / action |
|---|---|---|---|
| 1. Problem real+specific+frequent | ✅/⚠️/❌ | [data/conversation/experiment] | ... |
| 2. Solution hits real problem | ... | ... | ... |
| 3. Enough signal for MVP | ... | ... | ... |

## Adversarial check (mandatory)
- Real signal vs wishful thinking: ...

## Verdict
PROCEED / HOLD / PIVOT — rationale.
```

## Related skills
- `founder/new-project` — sets `stage: idea`, runs idea-gate on project creation
- `founder/idea-discovery`, `founder/customer-discovery`, `founder/adversarial-check` — Idea-stage tools
- `pm/pmf-diagnostics` — measures MVP-exit (PMF)
- `founder/defensibility` — Scale-stage moat work
- `quality/tech-debt-audit` — agentic debt (MVP/Launch failure mode)
