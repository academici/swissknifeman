# Claude — detailed technical specifications and architecture

> Role in work flow: **architect**. Receives the primary technical specification from Perplexity and
> turns it into a detailed design document - with patterns, class names
> and structure. This is not an implementation, but a design.

> ⚠️ When used **Claude Fable 5** promty draw up according to the official
> guide: [Prompting Claude Fable 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5).
> Details - on the page [Claude Fable 5](./fable-5).

## Recommended models

| Task | Model |
|--------|--------|
| Detailed technical specifications, architecture | Claude Fable 5 / Sonnet |
| Targeted implementation assistance | Claude Sonnet |
| Final code review | Claude Fable 5 |
| Python / 3D with screenshots | Claude Fable 5 (reads better visually) |

## Industrial template - detailed technical specification

```
[Paste entire answer Perplexity in full]

[List of links from the Resources block]

Based on this material, create a detailed technical specification, including:

1. **Project architecture**
   - Directory structure
   - Key classes and interfaces (with names)
   - Design Patterns (Repository, Strategy, Observer etc.)

2. **Description of components**
   - For each class: purpose, public methods, dependencies
   - Contracts (interfaces / abstract classes)

3. **Database structure** (if applicable)
   - Tables, fields, relationships

4. **Technical details**
   - Edge cases
   - Configuration
   - Version compatibility

5. **Brief description of the implementation** of each module
```

## Promt template - code review

```
Run a code review of the package [name].

Pay attention to:
1. Compliance with the original technical specifications
2. Architectural patterns - are they applied correctly?
3. Potential performance issues
4. Security-vulnerabilities
5. Suggestions for improvement with specific code examples

Response format: list Issues (critical / recommended / optional)
```

## Feature of working with visuals

Claude reads screenshots well - you can transfer:

- Layouts UI
- Architecture Diagrams
- Database schemas
- Code examples from other projects (screenshot)

Especially valuable when working on 3D-models and visual components.

## Data transfer rules

- TK from Perplexity transmit **in full**, without summarizing - compression loses context.
- Links from the block «Resources» include in promt.
- Save detailed technical specifications at the output to the repository: `.cursorrules`, `AGENTS.md`
  or `docs/spec.md`.

## What we get at the output

- Detailed technical specifications with class names, patterns, directory structure.
- Ready «drawing» for implementation.
- A document that any developer can clearly understand.

Next: detailed technical specifications are transferred to [Cursor](./cursor).
