# Design baseline — 2026-09-22

## Repository identity

- `HEAD`: `8ee2f718d130876ef4eb05088a622d594b7bcebd` — совпадает с baseline аудита.
- Branch: `main`.
- Worktree до design уже содержал unrelated modified/untracked paths в Harness,
  Skiller, Task, CHANGELOG и roadmap; они не являются изменениями этого плана.
- Предварительный symbol scan нашёл все указанные audit surfaces в current tree;
  это evidence релевантности, а не вердикт по N-01…N-17.

## Coverage map

| Findings | Owning iteration | Primary seam |
|:--|:--|:--|
| N-01, N-02, N-04, N-05, N-13 | P2 | false-green, byte binding, batch continuation, CI |
| N-03, N-06, N-10, N-11, N-14 | P3 | owner trust, atomic activation, replay, observed authority |
| N-07, N-12, N-15, N-16, N-17 | P4 | journal/decision/projection integrity and durability |
| N-08, N-09 | P5 | privacy, external paths, symlink/containment |
| reason-code split; prompt/docs/policy consequences; end-to-end behavior | P6 | consumer-visible semantics and field validation |

P1 владеет верификацией всех строк до их попадания в owning iteration.

## External evidence availability

- Current Codex tool surface не экспонирует Perplexity tool; connected-project map
  содержит real package `/home/vostrikov/projects/packages/perplexity-web-mcp`.
- Ordinary web tool в design session дважды вернул transport failure. Direct primary-source
  preflight подтвердил доступность Python `os`/`fcntl`, SLSA attestation model,
  RFC 9449 и GitHub Actions workflow syntax. P1 обязан повторить search и открыть
  primary sources; этот preflight не заменяет verification.

Candidate primary sources, RAG:✅ availability only, conclusions pending P1:

- Python `os` docs: https://docs.python.org/3/library/os.html#os.fsync
- Python `fcntl` docs: https://docs.python.org/3/library/fcntl.html#fcntl.flock
- SLSA attestation model: https://slsa.dev/spec/v1.2/attestation-model
- IETF RFC 9449 replay-resistant proof binding: https://datatracker.ietf.org/doc/html/rfc9449
- GitHub Actions workflow syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax

## Real-project field boundary

Topology resolves at least three heterogeneous connected git repositories suitable for P6:

- `corex` — dirty source worktree at design time;
- `agentools` — clean source worktree at design time;
- `edufy` — dirty/ahead source worktree at design time.

P6 не использует source worktrees для writes. Exact paths разрешаются из
`~/.swissknifeman/topology.json`/`projects.json`, commits пинуются, а paired runs
выполняются в отдельных temporary worktrees.
