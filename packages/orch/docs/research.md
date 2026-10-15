# Research sources

`[orch.research]` names where the researcher role and `orch.py research query` look things up (PLAN4 P10.1). Adapters
live in `orch.research.sources`; they use the standard library only.

## Configuration

| Key | Value | Default | Layers | Meaning |
|---|---|---|---|---|
| `research.policy` | `required`, `conditional`, `off` | `conditional` | all | when a piece of work gets a research stage: every piece, only a piece whose research need is `required`, or never (`required` is served by the research stage below; `conditional` waits for the research need of a plan item) |
| `research.sources.<id>.kind` | `command`, `filesystem`, `mcp-stdio` | none (required) | all | adapter of the source; `http` and `vector` do not exist yet |
| `research.sources.<id>.argv` | array of strings | empty | defaults, machine, invocation, flags | command line of a `command` or `mcp-stdio` source; a leading `~` is expanded |
| `research.sources.<id>.tool` | string | `search` | all | `mcp-stdio`: the tool that receives the query |
| `research.sources.<id>.roots` | array of paths | empty | all | `filesystem`: folders searched (absolute, `~…`, or relative to the project) |
| `research.sources.<id>.capabilities` | array of `search`, `citations`, `synthesis`, `deep` | empty | all | what the source can do |
| `research.sources.<id>.timeout_s` | integer | `600` | all | ceiling on one query |
| `research.sources.<id>.concurrency` | integer | `1` | all | queries of the source that run at once in one orch process |
| `research.sources.<id>.order` | integer | `100` | all | place on the ladder: lower first, ties by id |

`argv` chooses the process orch starts, so a project file cannot set it (`CONFIG_LAYER_FORBIDDEN`); a project file may
set `policy`, `roots` and the limits. An `<id>` is lowercase words joined by `-`.

## Adapters

All adapters answer `{source, text, sources, raw_ref}`: the text, the URLs or paths it rests on, and the sha256 of the
raw reply (`sha256:<hex>`).

- `command`: `argv` is started, the query goes to its stdin, a JSON object `{"text": str, "sources": [str]}` is read
  from stdout.
- `filesystem`: a read-only walk of `roots` (symlinks, `.git`, `node_modules`, files over 1 MB and non-UTF-8 files are
  skipped); a line that contains the whole query (case-insensitive) is a match, at most 50 are returned as
  `path:line: text`, `sources` lists the files.
- `mcp-stdio`: a generic JSON-RPC client over the stdio of a server: `initialize` → `notifications/initialized` →
  `tools/call {name: tool, arguments: {query}}`. Lines of the server that are not JSON are skipped. `sources` are the
  URLs found in the text. The message shape follows `docs/research/tools/pplx_stdio.py`.

A reply with `BROWSER_BUSY` (or an MCP error that says so) and a query that exceeds `timeout_s` are asked again by
`retry.decide` (`rate_limit` and `timeout` classes) up to 3 times, with a wait of 5, 10, 15 seconds for a busy answer;
after that, and for every other failure, the result is `SOURCE_UNAVAILABLE`. `concurrency` is held inside one process;
another process (a second conductor) is not counted, so the server's own `BROWSER_BUSY` and the repeats remain the
guard.

Codes: `SOURCE_UNKNOWN`, `SOURCE_INVALID` (no `argv` or `roots`, no `kind`), `QUERY_EMPTY`, `SOURCE_UNAVAILABLE`.

## Command line

```
orch.py research sources [--json]
orch.py research query --source ID --query-file FILE [--json]
```

`sources` lists the policy and the sources on the ladder. `query` prints the text and one `source:` line per source, or
the answer as JSON. A failure prints `CODE: message` to stderr and exits 1.

## The researcher role and the research stage

The role `researcher` (`roles/researcher.md|json`; class `implementation`; filesystem read, shell read-only, network
allowed, no plan API, no write authority) gets a question and the ids of the allowed sources. Its launch entry
(`configs/launch-catalog.json`, `claude-code` only) lists `--tools Bash,Read,Grep,Glob` and allows exactly
`Bash(python3 *orch.py research query *)`; there is no codex route, because a read-only codex sandbox has no network. An
invocation `--config` before the verb would fall outside that allowance, so the sources of a conducted run must come from
the machine or project layers.

It answers a closed `research-result` (`schemas/conductor/v1/research-result.schema.json`):

```json
{"query": "…", "claims": [{"text": "…", "sources": ["https://… or path"]}], "contradictions": ["…"],
 "unknowns": ["…"], "sources_used": ["source id"]}
```

Every claim has at least one source; a statement without one belongs to `unknowns`. `sources_used` may name only the
allowed sources, and claims need a source that was asked (`ROLE_OUTPUT_INVALID` otherwise). The raw replies of the sources
are not stored: the stream of the role keeps them.

The policy decides who wants research. `required`: the conductor adds the steps `research.1` and `research-save.1` before the
executor of every piece. `conditional` (the default): only for a piece whose input says `research.need = required`; the need is the
decision of the plan designer (the `rag.need` and `rag.notes` of a plan item, carried into the execution-input by the
`planner-orch` brief), not a guess of the conductor, so `none` and `optional` get no stage. `off`: never. The question is the
goal and the reason of the piece (see [Conductor](conductor.md)). `research-save.1` has the work source keep the result
(`orch.py source research`): a plan keeps `research/<item>-<n>.json` in its folder and declares it as an input of the item
(through the planner bridge); a file input keeps `research-<n>.json` in its artifacts. A source that cannot keep it leaves the
result in the artifacts of the piece (`RESEARCH_NOT_SAVED`). With no source configured the run stops before any work with
`RESEARCH_NO_SOURCES`.

The result then reaches the executor: its prompt gets a block `research` (`## Research`: the claims, each with its sources, the
contradictions and the unknowns; origin `research-result:<file>`, budget class `retrieval`) in every round of the piece. The
block is a lead for the executor, not an instruction: it does not widen the write set and no acceptance check changes.

## Example: Perplexity (machine file)

The MCP server `perplexity-web-mcp` is a stdio server; it answers `BROWSER_BUSY` when no browser tab is free, hence
`concurrency = 1` and the repeats. Put this in `$SKM_HOME/config/config.toml`, never in a project file:

```toml
[orch.research.sources.perplexity]
kind = "mcp-stdio"
argv = ["~/projects/packages/perplexity-web-mcp/start.sh"]
tool = "search"
capabilities = ["search", "citations", "synthesis"]
order = 1
timeout_s = 600
concurrency = 1
```

For a deep search add a second source with `tool = "search_deep"`, `capabilities = ["deep"]` and a higher `order`.

## The advisor and the sources

The `advisor` role ([Conductor](conductor.md#the-advisor-p104)) may ask the same sources with the same one command
(`orch.py research query`), for what the repository cannot answer; it asks them only when `[orch.research.sources]` names
some, and its launch entry allows nothing else. Its `advice` lists the URLs or paths it rests on in `sources`.
