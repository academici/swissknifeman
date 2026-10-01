# Perplexity — research and initial technical specifications

> Role in work flow: **analytics engine** at the initial stage. The task is to collect
> current data, find references, identify best practices and form
> primary technical specification with sources.

## Settings before work

- **Response length**: `Detailed` (Long) — more text to parse, less gaps.
- **Search mode**: Pro Search — pulls up fresh sources.
- **Focus**: default or `Academic` for highly specialized topics.

## Promt template

```
I need to develop [task description].

Perform in-depth analysis:
1. Existing solutions and packages for [technology/ecosystem]
2. Best practices for implementation on [year]
3. Architectural patterns applicable to the problem
4. Comparison of approaches (if applicable)

Response requirements:
- Use the latest data (latest releases, current versions)
- The answer must be detailed and meaningful - without any confusion
- Enable block **Resources and references** with direct links to GitHub-repositories
- If there are known reference-implementations (for example, Spatie Permission for
  Laravel) — disassemble their architecture
- Specify: what patterns are used, how the file structure is organized,
  what interfaces are published

Project context:
- Technology: [Laravel / PHP / Python / etc.]
- Packet type / applications: [description]
- Key requirements: [list]
```

## Required resource block

Perplexity should end the response with a section like:

```markdown
## Resources and references

| Title | Link | Why is it important |
|----------|--------|--------------|
| Spatie Laravel Permission | https://github.com/spatie/laravel-permission | Reference implementation RBAC for Laravel |
| ...      | ...    | ...          |
```

> **Important:** This block becomes the knowledge base for the next stage. The more
> links to real code - the more accurate Claude will be able to work out the architecture.

## Promt for review of relevance

Used after development is completed - check if the approaches are outdated:

```
Check if there are more relevant approaches to implementation [task]
in the ecosystem [Laravel/PHP] on [current year]?
Look for changes in best practices over the past 6-12 months.
The Resources block is required.
```

## Wording rules

- **Always request block «Resources»** — is not an optional part, but a required one.
- **Indicate year and ecosystem** — otherwise the results may be out of date.
- **Long answer in settings** — removes «water» better than short: no need
  compress as needed.
- **Request comparison** — «Compare approaches A and B» gives more information for the solution.

## What we get at the output

- Brief primary technical specification (problem statement + key requirements).
- List of technologies and packages.
- Reference implementations with GitHub-links.
- Understanding architectural options.

Next: the entire response is transmitted to [Claude](./claude).
