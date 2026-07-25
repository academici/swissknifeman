# P3 recon — skiller publication, marketplaces и provider delivery

**Дата:** 2026-07-19  
**Метод:** read-only repo recon + fresh official Codex manual; package code не исполнялся.

## Repo-grounded baseline

- `packages/skiller/lib/skiller/registry.py::build_plugin_manifests` одновременно строит
  Claude per-bucket `.claude-plugin/plugin.json`, curated `core`, `generate-skill`, `skm`,
  соседние package entries и один корневой `.claude-plugin/marketplace.json`. Semantic
  inventory и Claude rendering пока сцеплены одной функцией.
- `packages/skiller/lib/skiller/connect.py` является Claude-only: пишет
  `.claude/settings{.local}.json::extraKnownMarketplaces/enabledPlugins`, применяет Claude
  permissions и предлагает `/plugin marketplace update`.
- `packages/skiller/lib/skiller/common.py::AGENT_DEFAULTS` знает только `claude`, `cursor`,
  `generic`; Codex `.agents/skills` отсутствует в stable delivery contract.
- `packages/skiller/lib/skiller/skillset.py` реализует managed physical delivery только в
  один `skills_path`, а `update.py` детектирует Claude marketplace либо один vendor marker.
  Provider loop и multi-target transaction отсутствуют.
- `packages/skiller/tests/test_channel_parity.py`, `test_registry_state.py`, `test_skillset.py`
  и `test_update.py` уже дают подходящие seams для parity/backward-compat fixtures, но сейчас
  сравнивают Claude/vendor paths, не два provider outputs.
- Корневая `.agents/skills/` — untracked bootstrap с thin adapters, читающими канон из
  `packages/skiller/skills/` и `packages/task/commands/`. Это полезное self-host evidence,
  но не release baseline и не второй canonical tree.

## Fresh Codex contract facts

Источник: fresh local Codex manual (`/tmp/openai-docs-cache/codex-manual.md`, helper status
`local manual was already current`, 2026-07-19), first-party pages:

- <https://learn.chatgpt.com/docs/build-plugins>
- <https://learn.chatgpt.com/docs/build-skills>
- <https://learn.chatgpt.com/docs/plugins>
- <https://learn.chatgpt.com/docs/developer-commands?surface=cli#cli-codex-plugin>

RAG:✅ 2026-07-19:

- plugin root обязан иметь `.codex-plugin/plugin.json`; bundled skills живут вне
  `.codex-plugin/`, а manifest ссылается на skill root;
- repo marketplace — `$REPO_ROOT/.agents/plugins/marketplace.json`; local `source.path`
  начинается с `./`, остаётся внутри marketplace root и резолвится от root marketplace,
  не от каталога `.agents/plugins/`;
- marketplace entry несёт stable name/source + install/auth policy/category; plugin manifest
  несёт stable name/version/description и component paths;
- Codex CLI имеет stable `codex plugin` и `codex plugin marketplace` surfaces; desktop/CLI
  устанавливают plugin из marketplace, а installed copy грузится из cache, поэтому thin
  adapter не может полагаться на путь за пределами plugin bundle;
- repo skills обнаруживаются под `.agents/skills`; skill identity задаётся `name` и
  `description`, полное тело загружается по progressive disclosure.

## Current-session invocation evidence

Официальный manual показывает `$skill-name` для Codex CLI и `@` для ChatGPT plugin picker,
но текущая ChatGPT/Codex task surface в этой сессии принимает `$ task:plan-design …` с
пробелом и отвергает Claude-форму `/task:plan-design …`. Для текущих launch-block'ов
приоритет имеет проверенное поведение среды и прямое уточнение владельца; долговременный
mapping уходит в P4. RAG:— (owner-grounded: `brief/01-refinements.md`).

## Constraints carried into P3

- Claude Code marketplace bytes/names и существующие `enabledPlugins` keys — back-compat gate.
- Один semantic inventory строит оба provider outputs; преобразование Claude manifest → Codex
  manifest запрещено как скрытый второй source.
- Direct bucket plugins могут читать canonical skill directories; curated/discontiguous bundles
  (`core`) и provider-native management adapters требуют deterministic generated bundle с
  provenance, потому что cache не сохраняет внешние repo-relative ссылки.
- Project-local `.agents/skills` допускает thin adapters только когда canonical files доступны
  в том же repo; vendor consumer без source checkout получает managed rendered copy с lock/hash,
  а не ручной fork.
- Любая user-global plugin installation — отдельная явная operation; обычный project render/
  dry-run не должен молча менять `~/.codex`.

## Verification

- Проверено: current skiller writers/tests; fresh first-party Codex plugin/skill/marketplace
  contract; owner-observed launch syntax.
- Непроверенное → ПОВТОРНЫЙ ПРОХОД: exact frozen provider/artifact/config fields ещё не созданы
  P0–P2; P3 execution fail-closed до terminal/frozen entry gate.
- `[POSSIBLE-DEFECT]`: Codex official generic invocation examples и текущий ChatGPT task syntax
  различаются; P4 обязан закрепить provider renderer и conformance fixture, P3 не угадывает его.
