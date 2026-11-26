# Python / 3D — tools and work cycle

> Development Python-components (especially 3D-modeling, scripts Blender,
> scene generation) has its own specifics and requires a special selection of tools.

## Specifics of tasks

- Complex mathematical calculations.
- Working with libraries: NumPy, Trimesh, Open3D, `bpy` (Blender Python API).
- Visual context: screenshots, renderings, diagrams.
- Iterative debugging of algorithms.

## Recommended Tools

| Task | Tool | Reason |
|--------|-----------|--------|
| Architecture Python-package | Claude | Deep structure analysis |
| 3D-algorithms with screenshots | Claude Fable 5 | Better reading of visual context |
| Implementation of scripts | Cursor + Claude Haiku | Speed and low cost |
| Model aggregation | **Vilis** (or OpenRouter) | Aggregator with access to Claude Code |
| Final code review | Claude Fable 5 | Deep Analysis |

## Vilis and model aggregators

Aggregator platforms (Vilis, OpenRouter etc.) provide:

- Unified interface for different models.
- Access to Claude Code without a separate subscription.
- Flexible switching between models based on task type.

If access is available, use as the main entry point for Python-development.

## Features of working with Fable 5 for 3D

Claude Fable 5 good for 3D-tasks because:

- Reads screenshots and renders as visual context.
- Understands geometric concepts and mathematics of 3D scenes.
- Can generate and analyze `bpy`-scripts.

> ⚠️ When preparing items for Fable 5 — follow the guide:
> [Prompting Claude Fable 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5).
> Details - on the page [Claude Fable 5](./fable-5).

## Typical duty cycle

```
1. Perplexity — analysis of libraries and approaches for the task
2. Claude Fable 5 — module architecture / algorithm
3. Cursor + Haiku — implementation
4. Visual inspection (render / screenshot) → transfer to Claude Fable 5 for analysis
5. Iterate until the desired result is obtained
6. Final code review: Claude Fable 5
```

## What we get at the output

- Python-scripts or a package with a clean architecture.
- Algorithms verified visually through renders.
- Code review taking into account specifics 3D-mathematics.
