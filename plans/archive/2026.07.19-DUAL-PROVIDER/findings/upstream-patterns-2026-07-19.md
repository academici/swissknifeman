# Upstream multi-provider patterns — 2026-07-19

**Тип источника:** shallow repository audit  
**Маркер:** RAG:✅ 2026-07-19 — прямое чтение checkout'ов по указанным commit

| Repository | Commit | Полезный паттерн | Вердикт |
|:--|:--|:--|:--|
| [affaan-m/ECC](https://github.com/affaan-m/ECC) | `754b8dd76ca8` | canonical skills, legacy command shims, Codex plugin sync | reference; cache-relative paths требуют проверки |
| [wpfleger96/ai-agent-rules](https://github.com/wpfleger96/ai-agent-rules) | `f2208d8329f3` | provider target classes, shared config, per-provider MCP translation | adopt adapter idea; не брать symlink-first и external deps |
| [yzhao062/anywhere-agents](https://github.com/yzhao062/anywhere-agents) | `8380508b4884` | canonical instructions + provider blocks, manifest/lock/hash/drift | adopt packaging controls; текущий dispatch/PyYAML не переносить |
| [wshobson/agents](https://github.com/wshobson/agents) | `c4b82b0ad771` | capability manifest и transformation per harness | strongest reference; capability claims перепроверять first-party |
| [brianlovin/agent-config](https://github.com/brianlovin/agent-config) | `1a9819ebf3fe` | минимальный shared-config sync | слишком узко для SKM |
| [mkXultra/ai-cli-mcp](https://github.com/mkXultra/ai-cli-mcp) | `03632ed70614` | вызов нескольких agent CLI через MCP | future runner reference, не distribution core |
| [raysonmeng/agent-bridge](https://github.com/raysonmeng/agent-bridge) | `a3e927fcaccd` | cross-agent bridge | future Artifex option, не migration dependency |

## Сводный вердикт

Лучше всего требованиям SKM соответствует комбинация:

1. canonical semantic content;
2. versioned capability manifest;
3. deterministic provider renderers/adapters;
4. generated artifacts с provenance, content hashes и drift detection;
5. merge-only project overrides;
6. symlink только как optional local-authoring optimization.

Ни один проверенный upstream не покрывает весь контракт SKM и не должен становиться
runtime dependency. Python implementation в SKM остаётся stdlib-only.

