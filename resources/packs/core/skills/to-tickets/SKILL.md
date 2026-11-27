---
name: to-tickets
description: "Slice an approved specification into independently verifiable implementation tickets."
---

# To Tickets

Read the approved specification and inspect the codebase for affected entry
points and dependencies. Split the work into small end-to-end slices that can
be implemented and verified independently once their prerequisites are met.

Give each ticket a goal, scope, prerequisites, acceptance criteria, and
verification commands or observations. Link criteria back to the specification.
Name which decisions or prerequisites block a ticket. Order the tickets so
shared contracts and migration dependencies are available when needed.

Check that every specification criterion is covered and remove duplicate
ownership across tickets. Use the requested destination or hand back drafts
for review. Use a tracker only when the user authorizes publishing.
