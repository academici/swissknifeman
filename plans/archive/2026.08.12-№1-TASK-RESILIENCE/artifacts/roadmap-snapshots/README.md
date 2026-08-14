# Roadmap inputs and follow-up dispositions

Снимки сохраняют roadmap-входы, использованные планом `2026.08.12-№1-TASK-RESILIENCE`, и
Task follow-up 2026-08-13. Они являются историческими артефактами плана, а не активной очередью.
В корневом `roadmap/` остаются только незакрытые записи; полностью реализованные источники удалены.

| Snapshot | SHA-256 | Disposition 2026-08-13 |
|:--|:--|:--|
| `catalog-at-follow-up.md` | `230f686cbdacfc0eb21ffd5e45f6be46c1024ec6a65c4b99bbabbe7225983c8b` | каталог после классификации |
| `2026.08.09-plan-roadmap-batching-gate.md` | `22d93b2e5868be7043ef4f7608ea7fb60662e81c200a6555afc727aae05cbfed` | superseded единственным активным batch-selection SSOT |
| `2026.08.10-adaptive-plan-governance.md` | `9271bab4d9e691876009a70c2fb08e6c957885a19fc503738eab8006328818da` | реализовано |
| `2026.08.10-audit-before-close-phase-gate.md` | `cc19b4921464a2e7a0d0ce02adbba28e10d99d496e4ae13d046bf2f9b02e78a6` | реализовано планом |
| `2026.08.10-plan-run-routing-blocked-terminal-loop.md` | `75975ab8e756345ef61f1ff39640324870284b0ea005e79729a210798c63e26b` | реализовано планом |
| `2026.08.10-plan-evidence-anchor-audit-loop.md` | `2acd80f7d7cfb2efd1cc59b8d72b8344cb988d5765ddda096b4e90a8ae1c946b` | material-fingerprint slice реализован; полный anchor graph остаётся активным |
| `2026.08.11-codex-effective-route-observability.md` | `fd528a573cd5ea49d52c0e0b0987be46cba471d6a7cc67430ef14f8fa48cf0b2` | реализовано |
| `2026.08.11-local-repair-vs-escalation-classifier.md` | `994b02a73a1cfedf62732f1e9ae6ae9f3803698a268fc55f40000c5477908d09` | частично; all-five/Files enforcement и метрики остаются активными |
| `2026.08.11-plan-views-history-cli-contract.md` | `35893c79afe0f26e803244d51dc15fc3eb420c50f1277adc135b19dd028cbd57` | не реализовано, остаётся активным |
| `2026.08.11-roadmap-batch-selection-is-authoritative.md` | `023347b6ddb77f80c5eaa1cbca81cb6390cfb6195ea045e9be1d25d8c95c9602` | не реализован pre-mutation admission, остаётся активным |
| `2026.08.11-terminal-final-continuity-receipt.md` | `354401d85f965bfb0f50cf0f0b172ca87ee503beb34a52f675b4bcda7aa5fbf6` | Task slice реализован; transport lifecycle остаётся активным |
| `2026.08.11-terminal-handoff-recommendation-receipt.md` | `45e9d4877d6343da3825bc12fa95dc3ff6d1933c1be1abe4cc5dd877a2fc329a` | Task slice реализован; final transcript gate остаётся активным |
| `2026.08.12-task-installed-authority-frame-resolution.md` | `7c81fc63b876a6a46b2cdbf85ba3e61dce7172e51bc5d7f5fc19036a7de54caa` | реализовано |
| `2026.08.12-task-orchestration-negation-lint.md` | `8d144e32d7478fab034f988ca6c5cad4bf9316cb8b056d32b9c4c4c0f3b1d4fc` | реализовано |
| `2026.08.12-task-plan-run-installed-command-path.md` | `0b472f44bbb87473f06f717a12ef7f41147cadb7bd3c7ebd49450e1816554709` | реализовано |
| `2026.08.12-task-plan-run-terminal-delivery-gap.md` | `50a58972d866b11eda846e2524d49cc2eff34937411ba2a38aee1ebc28aa7d81` | Task-owned gap реализован; transport residue консолидирован в terminal receipt entries |
| `2026.08.12-task-v2-lint-closed-items-read-budget.md` | `9041e2f92a599f8c675827123d6f2f0a0e003d4ab6ad7e00f419f0b7212dfa03` | реализовано |
| `2026.08.12-terminal-deviation-repair-forward.md` | `ab286680d59034297d30b05be99d3134cfced1d853b822e98779b3296fe0a98e` | реализовано |
| `2026.08.13-claude-code-launch-provenance-adapter.md` | `14794d5881bd2e1deee6d1b8e575de44a534f94fbb74cc3da69ef379dc8c9849` | реализовано |
| `2026.08.13-terminal-deviation-must-not-replace-repair.md` | `8db02220e9f7cf98d31f002eea42b8c2127bfcd617e25028b32f801681683f84` | реализовано |
| `2026.08.13-p10.6-false-terminal-block.md` | `c140a0e33587d24ae0bccb90521a0ba4d30a5b1f8e81f16347ded84a3d6603cf` | реализовано |

Основные implementation carriers: `task.review_policy`, `task.plan_blocking`,
`task.terminal_policy`, `task.validation_admission`, `task.route_evidence*`,
`task.command_catalog`, `task.plan_delivery`, `task.plan_item_state` и `task.plan_gates`.
