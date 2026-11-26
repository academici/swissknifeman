# Work identity and references

A persisted plan has a stable repository-local Short ID `PLAN<N>`; a standalone task document uses
`TASK<N>`. Allocate the next unused number above every live and archived one; never recycle or
renumber. For plans do not count by hand: `plan.py new --codename <NAME> --title … --actor …`
allocates the directory id `YYYY.MM.DD-№N-CODENAME`, the title prefix `Plan №N —` and the Short ID,
and refuses a collision. A plan item keeps its `Pn.m`; it never receives a standalone `TASK<N>`.

Outside the owning plan directory, qualify every work-specific decision, phase, item or finding:
`PLAN<N>.D35`, `PLAN<N>.P2`, `PLAN<N>.P2.3`, `TASK<N>.D2`. This applies to code comments, docstrings,
PRs, reviews, docs and generated text. Inside the plan directory bare local ids are allowed.
Across repositories prepend the repository identity: `swissknifeman:PLAN<N>.D35`.
`#` is optional presentation, not part of the id. Keep the Short ID when archiving or handing off.
Do not create comments just to cite work.

`plan.py` accepts a plan as its directory id, its Short ID or a path. `plan.py check` reports
unknown local references; qualified references to other plans are checked when authoring or
reviewing.
