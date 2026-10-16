# Common plan principles

Applies to every plan command after an explicit planner invocation.

1. JSON is the source of truth. Change a plan only through `plan.py`; never edit or rely on the
   human Markdown in `views/`. Read JSON context through the API; plans contain no agent instruction carriers.
2. Deliver the owner-authorized result to its acceptance boundary; a single green check is not
   completion of a larger requested scope.
3. Never manufacture evidence. Record only checks that actually ran; a refusal (`CODE: message`)
   is information to act on, not something to work around.
4. Repair reversible, local problems yourself (`plan.py check`, `plan.py render`). Escalate only an
   owner gate, a missing product decision, an irreversible or external action.
5. Spend effort where it changes the outcome: targeted reads, one focused validation per change,
   long output in files. Existing dirty changes belong to the owner.
6. Name hard risks (security, public API/schema, data, concurrency, publishing) in the report with a
   `planner:review` recommendation; review itself is opt-in.
