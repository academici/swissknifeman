---
description: "Generate minimal tests for changed behavior (happy path + negative), according to the rules.claude/rules/tests.md"
---
Add minimum {{TEST_FRAMEWORK}}-tests for changed behavior: one happy path and one
negative. Follow `.claude/rules/tests.md` (database isolation, mirror the style of existing tests,
honesty - mark roundabouts `[POSSIBLE-DEFECT]`).
Run only the affected ones: `{{TEST_RUNNER_CMD}} --filter=…`. Existing checks should not be weakened.
