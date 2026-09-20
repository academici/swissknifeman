# P2 design evidence — 2026-09-20

## External method verification

Perplexity `search_advanced` с sources `web` + `academic` и независимый ordinary web search
искали первичные основания для bounded read-only field audit трёх software repositories.
Discovery summaries не считались proof; несущие тезисы сверены с открытыми primary pages.

- RAG:✅ Per Runeson, Martin Höst, *Guidelines for conducting and reporting case study
  research in software engineering*, 2009, access 2026-09-20:
  <https://link.springer.com/article/10.1007/s10664-008-9102-8>. Поддерживает
  observational study в natural context, заранее заданные objectives/selection strategy,
  planned and consistent multi-source evidence, data/method triangulation, explicit validity
  threats и разделение cases, когда их contexts различаютс. Источник отдельно
  предупреждает, что case study не даёт того же causal evidence, что controlled experiment,
  и не даёт statistical significance сама по себе.
- RAG:✅ Nicole Forsgren et al., *The SPACE of Developer Productivity*, ACM Queue 2021,
  Microsoft Research primary publication page, access 2026-09-20:
  <https://www.microsoft.com/en-us/research/publication/the-space-of-developer-productivity-theres-more-to-it-than-you-think/>.
  Поддерживает только multi-dimensional measurement: developer productivity нельзя
  выводить из одной activity-метрики. Для read-only repository evidence satisfaction/well-being
  обычно ненаблюдаемы и должны стать `n/a`, а не выводом из git activity.

Вывод для P2: сначала три отдельных case findings по единой rubric, затем synthesis
с labels `replicated|context-dependent|conflicting|unassessable`; формулировки ограничены
этими тремя case и наблюдаемым coverage.

## Repository/topology baseline

RAG:— 2026-09-20. Paths решались из `~/.swissknifeman/topology.json` и
`~/.swissknifeman/projects.json`, затем сверялись с worktree-local `maind projects status --json`.
Эти host paths — только observed design evidence; P2.1 обязан заново разрешить их в execution.

| Case | Branch/HEAD | Tracked files | Dirty status entries | Design consequence |
|:--|:--|--:|--:|:--|
| corex | `main` / `65441b1` | 4500 | 523 | commit-bound reads; worktree bytes forbidden |
| agentools | `main` / `a39a5cc` | 2073 | 382 | commit-bound reads; worktree bytes forbidden |
| edufy | `feat/edufy-core` / `463ab0a` | 2992 | 1163 | branch is a case property, not a common baseline; worktree bytes forbidden |

Три case имеют разные стеки, масштаб и branch state. Сводный raw mining без
предварительного case isolation смешал бы context и coverage. Все три дерева были dirty;
чистка, checkout, stash, reset и consumer write не авторизованы.

## Environment and evidence-integrity notes

- Perplexity MCP был записан в `.codex/config.toml`, но tool не зарегистрирован в этом
  turn. Первый fallback через system Python упал на `ModuleNotFoundError: mcp`; offline
  `uv --with mcp` не смог добрать отсутствующий cached `cryptography`. Успешный
  запрос выполнен штатным `perplexity-web-mcp/start.sh` через уже установленный cached
  MCP SDK; его ответ был получен до ordinary web verification.
- Первый registry query ошибочно ожидал `projects[].id`; пустые paths заставили
  `git -C ""` прочитать текущий swissknifeman трижды. Эти counts отброшены. Таблица
  выше получена только после unique-path, nonempty и `.git` checks и сверки с maind.
- Первый ordinary web batch упал на transport `connection failed`; более узкий retry и
  прямое открытие primary pages завершились успешно.
- Closeout `packages/task/scripts/validate.sh --plan ...` запустил 1110 tests:
  1 failure, 1 skipped. Упал тот же pre-existing
  `test_generated_model_roles_reference_is_deterministic`; final
  `render-provider-commands --check` также повторил drift
  `packages/task/docs/reference/provider-model-roles.md`. Плановые gates в том же
  запуске остались GREEN: named `plan-lint` и `plan-lint --conflicts` вернули
  0 ошибок/0 предупреждений. Owning generator не запускался: его канон и
  provider locks содержат чужие dirty changes вне P2 scope.
- `plan-delivery.py --kind handoff --subject P2` не смог построить design receipt:
  `PLAN_DESIGN_NOT_NEEDED: phase P3 already has detailed unfinished items`. Это
  owning-tool false positive: P3 содержит канонический маркер `> СКЕЛЕТ — не детализирован`,
  а все 11 stable полей P3.1 равны `—`. `plan-lint` правильно допускает этот skeleton,
  но `task.plan_readiness.validate_design_handoff_target()` считает `—` detailed
  через regex `\s*\S` и не проверяет phase skeleton marker. Тот же дефект
  воспроизводится в installed Task 0.20.3. Semantic Next в `handoff.md` оставлен
  `design-phase: task:plan-design ... P3`; product/runtime repair в P2 design scope не вносился.
