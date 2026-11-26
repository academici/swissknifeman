# Swiss Knife Man — purpose and philosophy

Status: normative. Every module, plan and review in this repository follows this document. A rule that contradicts it
is a defect of that rule; change this document first, through an owner-visible commit.

## Purpose

Swiss Knife Man (SKM) is a local, provider-neutral control layer for AI-assisted software development on one
developer machine. It does three things:

1. **Plans.** It turns work that is too large for one reliable agent session into typed JSON plans: phases, items
   with exact scope, reads, checks, routes and decisions (`planner`, stored in a portable `workspace`).
2. **Executes.** A deterministic conductor (`orch`) drives each item through bounded roles — scout, executor,
   reviewer, triager, advisor, researcher, registrar — that run as coding-agent CLIs (Claude Code, Codex, Grok),
   checks the result with real commands and records evidence, decisions and commits.
3. **Equips.** It keeps the developer environment reproducible across projects: skills (`skiller`), provider
   instructions, permissions and hooks (`harness`), shared contracts and configuration (`aicore`), project memory
   and the project graph (`maind`), run analysis (`analyst`) and a control plane (`gui`).

SKM is **not** a distributed workflow engine, a model provider, an IDE, a hosted service, a formal-verification
system or a replacement for engineering judgement. It runs on one host and owns its state there.

## Principles

1. **Code owns the lifecycle; models propose.** State transitions, authority, external effects, budgets, retries
   and stops are decided by deterministic code after contract and policy checks. A model's output is a proposal: a
   closed, schema-valid document that code accepts, refuses or escalates. No log line, prose answer or confidence
   statement changes state by itself.
2. **Schemas are the law.** Every JSON document that crosses a process or file boundary has a JSON Schema with a
   stable `$id` (`urn:swissknifeman:<module>:<kind>:v<major>`), is validated when written and when read, and its
   Python type is generated from that schema. Within a major version a schema only gains optional fields
   (`aicore schema compat`); a breaking change ships with a migration and a major version.
3. **Fail closed on authority, degrade loudly on capability.** Missing isolation, an unmet gate, unknown token
   usage or an authority conflict stops the work with a reason code and a resume path, or runs in a degraded mode
   that the configuration explicitly admits and the run records. Nothing silently widens permissions, silently
   drops an instruction or silently turns a failure into success.
4. **Evidence over claims.** "Done" means the checks ran against the exact tree that is committed and their
   receipts belong to that attempt. A review counts only with a receipt bound to the reviewed revision. Repair may
   change the form of a result, never its meaning: it never raises a status, removes an escalation, question or
   finding, or lowers a severity.
5. **Proportional assurance.** Tests, reviews, tokens and wall time are spent in proportion to the changed risk.
   Green evidence whose inputs are unchanged is reused, broad checks run once per phase, and cost is part of
   correctness. Safety language never justifies unbounded cost without a concrete failure scenario.
6. **Bounded autonomy.** The executing agent resolves local, reversible, in-scope questions itself; advisors and a
   consilium answer only within granted authority; the owner is asked only for authority, irreversible choices or
   real product decisions. Every loop — retries, review rounds, advice, autopilot — has a bounded exit.
7. **Local-first and durable.** A run survives a crash through leases, started records, receipts and
   reconciliation on one host. Liveness is supervised by deterministic code (heartbeat, supervisor), never by an
   LLM watching logs.
8. **Provider-neutral.** Every role either works on every supported provider or is refused explicitly with a
   reason. Provider specifics live in adapters (launch catalog, stubs, isolation profiles), never in the
   semantics of plans, roles or results.
9. **Honest module boundaries.** Each `packages/<id>/` is an independent module described by `unit.json`; modules
   meet only through bridges, CLIs and events. The core is neutral: personal or organisational defaults, names,
   paths, languages and model pools live in overlay modules (for the author: `axioma`) and configuration layers.
10. **Minimal dependencies.** The runtime is the Python standard library plus `aicore`. External code is a pattern
    to rewrite, never a runtime dependency.
11. **Transparent context.** For every model call SKM can explain what the model saw, where each block came from,
    which skills and stubs were chosen or excluded and why, and which authority it had. Context is assembled by a
    typed policy, frozen for the run, and budgeted by block type; mandatory constraints are never cut.
12. **Measured change.** Optimisations and new machinery answer a measured problem. An idea without a measurement
    goes to the roadmap with an explicit trigger.
13. **A stability promise.** From 1.0.0 the public CLIs, JSON contracts, configuration keys and state layouts
    listed in `docs/architecture/contracts.md` follow Semantic Versioning; a deprecation lives at least one minor
    release and ships a migration path.

## How to decide

- A prompt instruction or a code check? A code check.
- A new subsystem or an extension of an existing contract? Extend the contract.
- A silent fallback or an explicit stop? An explicit stop with a reason code and a resume path — or an admitted,
  recorded degraded mode.
- A bigger prompt or a better selection? A better selection; never cut a mandatory block mid-text.
- A model judgement or a measurement? A measurement whenever one is available.
- Ask the owner or decide? Decide, unless the action needs authority the agent does not have, is irreversible,
  or is a product decision.

## Roles

- **Owner** — sets goals, grants authority, answers product questions, promotes releases.
- **Designer agent** — turns goals into a typed plan whose every item is executable from its context pack alone.
- **Conductor** — deterministic runtime: claims work, assembles context, starts roles, runs checks, applies
  policies, records evidence, registers and commits.
- **Role models** — produce closed results inside their authority: an executor changes code in its write set, a
  reviewer and a triager read, an advisor or a consilium recommends, a researcher retrieves with sources.
- **Supervisor and autopilot** — deterministic processes that keep runs alive and the queue moving within policy;
  they call a model only for a semantic question that code cannot answer.
