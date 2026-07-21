<!-- instruction:analyst.identity-human-gate -->
## analyst.identity-human-gate
`analyst` is an on-demand, stdlib-only learning layer with no daemon; it may propose reusable knowledge but only a human may promote a lesson to curated state.
<!-- instruction:analyst.layer-boundary -->
## analyst.layer-boundary
Keep this package as layer-1 data and pipeline work; prompt-discipline skills remain a separate layer and automatic skill writes are forbidden.
<!-- instruction:analyst.layout -->
## analyst.layout
Keep `bin/analyst` as the launcher, `lib/analyst/` as stdlib-only logic, temporary-directory tests, and package documentation that builds standalone and in the umbrella site.
<!-- instruction:analyst.module-boundaries -->
## analyst.module-boundaries
Keep extractors pure where possible, confine I/O to `cmd_*` paths, and keep proposal, suggestion, digest, review, promotion, confidence, and recompute responsibilities in their named modules.
<!-- instruction:analyst.data-lifecycle -->
## analyst.data-lifecycle
Store lessons in explicit lifecycle directories, append audit and confidence events without rewriting them, and move lessons through `lessons.move_lesson` rather than duplicating state.
<!-- instruction:analyst.privacy -->
## analyst.privacy
Keep raw transcripts local; send only abstracted curated lessons to shared memory and reference secrets without storing their values.
<!-- instruction:analyst.engineering-invariants -->
## analyst.engineering-invariants
Keep runtime stdlib-only, pass frozen `Env` explicitly, write JSON atomically, require human confirmation for curated promotion, and emit Russian diagnostics.
<!-- instruction:analyst.validation-release -->
## analyst.validation-release
Before release run `bash scripts/test.sh` and `bash scripts/validate.sh`; regenerate the umbrella registry after changing analyst plugin commands.
