# P6.5 pre-restart bootstrap checkpoint

**Checkpoint ID:** `p6.5-bootstrap-b7373334`  
**mAInd record ID:** `mem_mrvm57ek_aa95bdbc51c7`  
**Scope:** `project:swissknifeman`  
**Canonical payload SHA-256:** `22a9c7a82f48ae0e27449ca1be240398b3b8ecd36fbfd50bc2f8bd3a56d60dc9`  
**Git anchor/tree:** `b7373334aa1e56f44cfe89cf04e1ce5e6397d232` / `12632f76f6a49920c193d091b02715f61436b0e6`

The public worktree-local mAInd MCP store and a same-scope recall both returned this checkpoint
ID and canonical payload. The record declares only `project:swissknifeman`.

```json
{"checkpoint_id":"p6.5-bootstrap-b7373334","commit_anchors":{"D93":"884e146b,b7373334","P6.1":"a4987286","P6.2":"a0885ceb","P6.3":"2b253564","P6.4":"91855d6f","P6.5_resume":"b7373334"},"git_tree":"12632f76f6a49920c193d091b02715f61436b0e6","hashes":{"instruction_catalog":"83543c10f3f05a2ff01205c7256229b032144b0705315ab1c230961f5c711b0b","instruction_render":"60686d05fa8bf9830cad8a960782ce12cdcb369a44b49cd9b864db481bde453e","provider_analytics_contract":"218cc703cdf23aa9501e74349c6902e59a2c04db6749d3cc6700527cdaf3451c","provider_capability_contract":"b22e1df11bc31651a2f9a4e4eeaaa2996af1556eac656894e65712cb261c2d56","provider_config_contract":"4456c60713754034050d9ad6e19945b26a3a017ffcda8f3b21924727d7e98a03","provider_deploy_render":"f3b4b1d07e120ede573c6a053615da3c67219ee14483524fcabfd20f1eebd95d","provider_harness_contract":"7309f3a4e80a2398b0fc7b84300c6cd1dd2a7d62d809b15e726ca78e790f1965","provider_instruction_contract":"37ab85d0b0ccc6b59d0fa5b197e17d85c7a31e63381c5f57d7e876ce27251910"},"p6_6_disk_first_reads":["artifacts/P6-bootstrap-checkpoint.md","plan.md","phases/P6.md","provider contracts","P6-integrated-conformance.md","P5-instruction-conformance.md","query-craft","verify-claims","CLAUDE.md","AGENTS.md","package guides"],"plan_id":"2026.07.19-DUAL-PROVIDER","provider_ids":["claude-code","codex"],"verdicts":{"graph":"GREEN","memory_isolation":"GREEN","perplexity":"GREEN","prior_reds":"preserved","serena":"GREEN","terminal":"GREEN"}}
```

## P6.6 cold boundary

Start a genuinely fresh `gpt-5.6-terra/medium` `task-plan-exec` session at the evidence
commit. Before any mAInd recall, read this disk file, then read `plan.md`, `phases/P6.md`, the
five frozen provider contracts, `P6-integrated-conformance.md`,
`P5-instruction-conformance.md`, query/verification skills, root guides, and the five package
guides in the recorded order. Then recall key `p6.5-bootstrap-b7373334` in exactly
`project:swissknifeman` and require the ID and payload SHA-256 above to agree.
