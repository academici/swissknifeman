+++
schema = "urn:skm:extensions:prompt-block:v1"
block_type = "task_contract"
variables = [
  "plan.display_key", "plan.title", "plan.revision_no",
  "task.display_key", "task.title", "task.work_kind", "task.goal", "task.instructions",
  "task.write_scope", "task.deliverables", "task.outputs", "task.rules", "task.guidance",
  "run.attempt_no", "run.round_no",
]
+++
## Task {{ task.display_key }}: {{ task.title }}

Plan {{ plan.display_key }} "{{ plan.title }}", revision {{ plan.revision_no }}. Attempt {{ run.attempt_no }}, round {{ run.round_no }}.
Kind of work: {{ task.work_kind }}.

### Goal

{{ task.goal }}

### Instructions

{{ task.instructions }}

### Write scope (the only paths you may change)

{{ task.write_scope }}

### Deliverables

{{ task.deliverables }}

### Outputs

{{ task.outputs }}

### Rules

{{ task.rules }}

### Guidance

{{ task.guidance }}
