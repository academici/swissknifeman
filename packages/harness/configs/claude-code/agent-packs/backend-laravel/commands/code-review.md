---
description: "Review of the latest diff by project layers and rules .claude/rules: only blocking notes with files/lines"
---
Review the latest diff according to the project canon: rules in `.claude/rules/*` and profile skills.
Specify only blocking comments with specific files/lines. Don't suggest refactoring outside
areas diff.
<!-- pack:if ACCESS_LAYER -->
Separately check the boundaries of the layers: the business logic is not in the controller, the mutation is through Action, access to
data - via Repository/Action, border transaction use-case.
<!-- pack:endif -->
