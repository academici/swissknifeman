# Metrics (choice depends on the task)

Skill reference `eval-design`.


### Generative tasks (text generation, response to student, mem caption)
- **Exact match** — for strictly deterministic parts (numbers, dates)
- **Embedding similarity** — semantic proximity to reference (cosine, threshold ~0.85)
- **LLM-as-judge** — separate model estimates the response by rubric (0–5 scale)
- **Human eval** — for critical domains (pedagogy, financial advice)

### Classification / extraction (tagging, field extraction)
- **Precision / Recall / F1** — standard
- **Per-class confusion matrix** — where the model gets confused

### Tool-use / agentic (Finbrain MCP, Edufy tutor with tools)
- **Tool selection accuracy** — did you select the right one? tool
- **Argument correctness** — are the arguments correct?
- **Recovery rate** — copes with the error tool'a
- **Step efficiency** — how many steps per task (less = better)

### Safety / refusal
- **Jailbreak resistance** — % failure on adversarial prompts
- **False refusal** — % denial of legitimate requests (should not be too high)
- **PII leak rate** — personal data leak in output

### Cost / latency
- **Tokens per task** — for cost tracking
- **p50/p95 latency** — UX

---
