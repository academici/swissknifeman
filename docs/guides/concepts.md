# Concepts

## Scopes and access

The work scope chain is instance → workspace → project → plan → run.
A workspace groups projects, members and worker registrations. A project
groups plans and repositories. A binding identifies a particular checkout of
a mounted repository on a host. Hosts branch directly from the instance for
host configuration and local resources.

**The workspace is the read-isolation boundary (SURF-17).** A workspace viewer
can read every project, plan, run and file in that workspace, subject to the
applicable content and credential checks. Project, plan and run memberships
require membership in the ancestor workspace and add permissions. Put projects
in different workspaces when their members require separate read access. The
project filter on MCP and memory selects session context. [Access contract](../../src/skm/modules/access/)

## Planning and execution

| Object | What it records |
| --- | --- |
| Plan | Stable identity for the specification and its revision history. |
| Draft | Mutable, versioned edit of the specification, with a base revision when editing published work. |
| Revision | Immutable published specification. Publishing a draft creates a new revision. |
| Run | Execution of a pinned revision with a frozen execution bundle and current live policy checks. A run tracks tasks and their dependencies. |
| Attempt | One execution try for a run task, with its environment, intermediate results and output. |
| Stage | A workflow step within an attempt, such as environment preparation, agent execution, checks, review or integration. |
| Worker | Registered host process that claims assignments in its workspace and renews leases. Stage and result writes require the current fence. |
| Host operation | Local work such as checkout inspection, Git, runtime launch or projection. It uses a gateway on the host that owns the checkout. |

The control plane persists plans and execution state in PostgreSQL. Workers
use the frozen inputs to execute and report progress. When a run needs a human
answer, approval or check verdict, it opens an Inbox request. A worker can
release its assignment while the run waits. [Planning model](../../src/skm/modules/planning/) ·
[Execution model](../architecture/execution.md) ·
[Host operations](../adr/0021-bus-handlers-and-host-operations.md)
