---
layout: home

hero:
  name: mAInd
  text: Central node of the ecosystem
  tagline: Agent memory · connection graph · registry of agents and projects · MCP-server
  actions:
    - theme: brand
      text: What is mAInd
      link: /guide/
    - theme: alt
      text: Installation
      link: /guide/installation
    - theme: alt
      text: Architecture
      link: /architecture

features:
  - title: 🧠 Shared memory
    details: One demon agent-memory to the hub, isolation of projects by namespace (scope). General facts - in scope global.
  - title: 🕸 Connection graph
    details: One graph per ecosystem. Projects, agents, memory, skills - nodes; depends_on / belongs_to / uses — ribs. This is it «general communication».
  - title: 🤖 Agent Registry
    details: register / heartbeat / list / kill. Status alive·stale·dead is derived from heartbeat and liveliness pid.
  - title: 📦 Project Registry
    details: config.json (at the root of the monorepo) — superset brain .projects.json, with fallback on legacy and syncom from brain.
  - title: 🔌 MCP-server
    details: maind mcp — stdio JSON-RPC. 11 tools over memory, graph, ecosystem-connections, agents and projects for any agent.
  - title: 🐍 Python + bash
    details: Core on stdlib (like swissknifeman / brain). npm — for memory daemon and documentation only.
---

## Development clone guard

In a development clone of the repository (an untracked `.swissknifeman-dev` marker in the root) `bin/maind`
refuses to run against the real `HOME`: exit code 3 and a `SKM_DEV_GUARD` line in stderr. Use a throwaway
environment (`scripts/dev-sandbox.sh` in the repository root) or `SKM_DEV_ALLOW_LIVE=1` as a conscious
exception. Installed copies and checkouts without the marker are unaffected. See `docs/develop.md`
("Ecosystem split branch").

`bin/maind` finds the `aicore` foundation through the canonical locator fragment: `$AICORE_ROOT`, then
`_vendor/aicore`, then the sibling `../aicore`; a miss ends with `AICORE_NOT_FOUND` and exit code 2. See
`packages/aicore/README.md`.
