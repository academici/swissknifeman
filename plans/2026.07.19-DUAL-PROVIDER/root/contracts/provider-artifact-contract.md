# Provider artifact contract

**Version:** v1.3.0

**Status:** frozen

**Approval Owner:** Dmitry Vostrikov

**Approval:** D55, 2026-07-20; backward-compatible additive minors D87, D104 and D110, 2026-07-22

**Vocabulary:** `../CONTEXT.md`, approved D53

## Purpose

Этот контракт нормирует путь Canonical Source → deterministic Adapter → Rendered Artifact
→ Managed Artifact. Он фиксирует identity, provenance, hashes, managed boundary, Override,
Drift и Repair так, чтобы `render`, `check`, `update` и `repair` одинаково понимались в
`skiller`, `task`, `harness` и `maind`.

Контракт не назначает package/module layout, конкретный lock path или provider output paths.
Их выбирают P1/P2 и package contracts, не изменяя invariants ниже. Rendered Artifact никогда
не становится Canonical Source для другого Provider.

D55 заморозил v1.0.0; D87 добавил v1.1.0 generic semantic metadata carrier без изменения
v1.0.0 records, hash/ownership semantics или downstream apply gates. D104 добавляет
v1.2.0 closed bootstrap-transfer admission для ровно одного recorded preimage. D110 добавляет
v1.3.0 exact composition этого sealed D104 predecessor с одним `.mcp.json` record; normal
plan/apply/repair и exact v1.0.0/v1.1.0 lock records не меняются. Запись provider outputs
остаётся запрещена до реализации и прохождения этих gates.

## Vocabulary

Контракт использует D53 terms: Canonical Source, Adapter, Rendered Artifact, Managed Artifact,
Override, Drift и Repair. Дополнительные closed values этого contract являются частью P0.3
Owner Approval:

- managed boundary mode: `whole-file` или `managed-blocks`;
- observation class: `clean`, `missing`, `stale-source`, `managed-drift`,
  `boundary-invalid`, `provenance-invalid`, `ownership-conflict`, `unsupported`;
- action: `noop`, `create`, `update`, `repair`, `refuse`.

`unsupported` здесь означает, что Capability gate запретил artifact operation; это не новый
Support Level и не заменяет capability contract.

`bootstrap-transfer` — closed admission до ordinary observation/action state machine, а не
новая observation class или замена `ownership-conflict`. Его единственный допустимый descriptor
имеет `decision_id = D104`, existing `.codex/hooks.json` с preimage
`sha256:7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`, created
`.codex/hooks/lifecycle.py`, artifact IDs `harness.codex.lifecycle.hooks` и
`harness.codex.lifecycle.handler`, а lock обязан отсутствовать. Любая другая попытка остаётся
`ownership-conflict/refuse` без backup, target или lock write.

## Normative model

### Artifact identity and provenance

Каждый managed output MUST иметь ровно один provenance record:

| Key | Contract |
|:--|:--|
| `contract_version` | Artifact contract SemVer; current freeze — `1.1.0`; exact `1.0.0` records remain supported. |
| `artifact_id` | Stable logical identity, уникальная внутри lock/catalog. |
| `canonical_sources` | Непустой ordered set source identity/path/hash records. |
| `adapter_id` / `adapter_version` | Adapter identity и SemVer implementation contract. |
| `provider_id` | Stable Provider ID из capability contract. |
| `target_path` | Нормализованный project-relative POSIX path; location, не identity. |
| `source_hash` | Digest deterministic source envelope. |
| `rendered_hash` | Digest exact managed bytes. |
| `managed_boundary` | Mode и, для blocks, уникальные ordered block IDs. |
| `override_layers` | Ordered effective Override provenance; MAY быть пустым. |
| `capability_requirements` | Capability IDs и принятые Support Levels Adapter'а. |
| `semantic_metadata` | v1.1.0-only optional generic nested JSON-safe mapping of caller-owned semantic render parameters; absent from exact v1.0.0 records. |

`semantic_metadata` is a provider/content-neutral carrier. Keys are canonically ordered;
nested objects use the same sorted-key canonical JSON rules, arrays preserve declared order,
and floats/non-JSON values are forbidden. The in-memory value is immutable. v1.0.0 with this
key, v1.1.0 without the version-declared shape, malformed nested values, or metadata that does
not match expected provenance is `provenance-invalid`. Removal/change cannot classify clean.

`artifact_id` MUST оставаться стабильным при безопасном переносе target path и MUST NOT
выводиться только из path. Target с другим `artifact_id` является ownership conflict.

Provenance record MUST находиться в machine-readable lock/sidecar вне user-owned bytes.
Inline header/marker metadata MAY дублировать subset для diagnosis, если target format это
допускает, но не заменяет record. Inline metadata MUST совпадать с record; mismatch —
`provenance-invalid`.

### Deterministic hashes

Все hashes имеют вид `sha256:<64 lowercase hex>`.

`source_hash` считается по UTF-8 bytes deterministic JSON envelope со следующими правилами:

1. object keys сортируются lexicographically;
2. separators — `,` и `:` без insignificant whitespace; Unicode не ASCII-экранируется;
3. source paths — project-relative POSIX; source records сортируются по `(source_id, path)`;
4. envelope включает exact source content hashes, `contract_version`, capability catalog
   version, Provider ID, Adapter identity/version, ordered Override records и semantic
   render parameters;
5. timestamp, host path, temp path и process/environment order запрещены.

In v1.1.0 the same semantic render parameters in the source envelope are also copied exactly
to `semantic_metadata`; the carrier does not add a second semantic input. v1.0.0 continues to
hash the same envelope and serialize the same record bytes as before.

Эквивалент canonical serialization — stdlib Python
`json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.

`rendered_hash` считается по exact managed bytes:

- `whole-file`: все bytes target file;
- `managed-blocks`: concatenation полных managed blocks в declared block-ID order, каждый
  от begin marker до end marker включительно; bytes вне markers исключены.

Inline metadata не содержит `rendered_hash`, если попадает в hashed region: self-referential
hash запрещён. Authoritative rendered hash хранится в lock/sidecar record.

### Managed boundary

`whole-file` передаёт manager'у все target bytes только после проверки artifact ownership.
Существующий target без matching provenance нельзя усыновить или overwrite молча.

`managed-blocks` передаёт manager'у только uniquely identified non-overlapping blocks.
Каждый begin marker имеет один matching end marker. Duplicate, nested, missing или reordered
markers дают `boundary-invalid`. Bytes вне blocks user-owned и MUST сохраняться byte-for-byte
при `update`/`repair`.

Изменение boundary mode, block identity или artifact ownership является contract-major
изменением либо отдельной explicit migration; обычный update этого не делает.

### Override precedence

Override является semantic input и разрешается до render. Порядок сверху вниз:

1. explicit operation Override;
2. project-owned Override;
3. caller-supplied named shared/fleet layers в их versioned declared order;
4. Canonical Source defaults.

Operation и project layers нельзя опустить ниже shared defaults. Каждый supplied layer MUST
нести stable layer ID, owner, order и provenance. Duplicate order/owner ambiguity fail closed.
Missing value не равен explicit disable. Rendered Artifact, local edit managed bytes и stale
lock никогда не участвуют в precedence как input.

Package-specific config contract MAY детализировать shared/fleet order, но не может нарушить
operation > project > shared > canonical или превратить output в source.

### Observation and action state machine

`check` вычисляет expected record/bytes и ровно одну observation class до выбора action:

| Observation | Required evidence | Allowed action | Write rule |
|:--|:--|:--|:--|
| `clean` | provenance, source and rendered hashes match expected/observed | `noop` | no write |
| `missing` | target отсутствует и ownership conflict отсутствует | `create` | explicit apply only |
| `stale-source` | observed managed bytes match recorded hash, но source/adapter/override expected hash изменился | `update` | replace managed boundary only |
| `managed-drift` | provenance/boundary valid, observed managed hash отличается от recorded/expected | `repair` | only explicit repair after diff/backup evidence |
| `boundary-invalid` | managed boundary нельзя uniquely extract | `refuse` | no write |
| `provenance-invalid` | record/header отсутствует, malformed, unknown-major или не совпадает | `refuse` | no write |
| `ownership-conflict` | target занят другим artifact или user-owned target | `refuse` | no write |
| `unsupported` | Capability requirement не прошёл capability contract | `refuse` | no write |

Чтобы один observed state не получил два класса, classifier применяет priority order:
Capability gate → ownership → provenance → boundary → managed bytes → source envelope →
`clean`. Отсутствующий target даёт `missing` только после исключения ownership conflict;
существующий user-owned target без matching artifact identity даёт `ownership-conflict`,
а не implicit adoption или generic missing-provenance repair.

`update` MUST NOT repair `managed-drift`. `repair` MUST NOT усыновлять ownership conflict,
чинить invalid boundary догадкой или менять bytes вне managed boundary. Repair сохраняет
recoverable pre-image и публикует expected/observed hashes до write.

`check` и `dry-run` являются strictly no-write: target, lock, sidecar, backup и project config
не меняются. Apply готовит expected target и provenance вместе; после сбоя state не может
объявляться `clean`, пока повторный check не подтвердил оба. Required artifact failure делает
aggregate result non-green и не скрывается успехом другого Provider.

### D104 bootstrap-transfer transaction

Closed v1.2.0 admission доступен только через caller-supplied immutable descriptor и одну
предварительно построенную two-artifact plan. Admission проверяется до backup и повторно перед
каждой subsequent write: decision, two paths, two artifact IDs, absent lock, exact existing
preimage, absent created target и absent backup. The first target is backed up exactly at
`.codex/hooks.json.provider-artifact.bootstrap-transfer.bak`, then replaced; the handler is
created; one canonical P2 lock with exactly those two records is written last. A changed target,
lock or backup refuses before the relevant write.

On an interrupted transaction rollback restores only the captured first target, removes only an
exact transaction-created handler and exact transaction-created lock, and never removes an
unrelated record or target. Ordinary `repair` cannot select this admission. `plan`, `doctor` and
dry-run remain no-write; live application remains a separate owner-gated consumer operation.

### D110 chained bootstrap-transfer transaction

Closed v1.3.0 composition is available only through an immutable descriptor containing the
sealed complete D104 `ArtifactPlan` (exact actions, expected bytes/provenance and two-record
lock), its D104 descriptor, plus `decision_id = D108`, root-relative `.mcp.json`, artifact ID
`maind.provider-deploy.claude-code`, immutable `("whole-file", ())` boundary, preimage
`sha256:cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283`, and the exact server-ID
set `maind`, `perplexity-web`, `serena`. Any different path, ID, boundary, preimage, expected
bytes/server set, D104 predecessor, present lock, created target or backup refuses before write.

The one transaction validates all three records, exact backup destinations and the canonical
three-record lock before its first write, then creates recoverable backups and writes that lock
last. `.mcp.json` bytes remain unchanged on success. A failure restores the byte-exact
pre-transaction root and removes only transaction-created partials. Ordinary plan/update/repair,
implicit adoption, target discovery, force flags, wildcard/hash-list descriptors and live-root
apply/repair/rollback remain excluded.

### Consumer notification

Frozen contract version и artifact provenance MUST быть видны consumers. Contract bump
обновляет donor Contracts row и same-root consumers в том же bookkeeping cycle. Для
cross-repo consumer создаётся explicit mAInd/open-risk notification. Lock/schema consumer
с unknown major отказывает без write.

## Compatibility

- **major**: изменение artifact identity semantics, hash algorithm, boundary modes,
  precedence invariants, observation/action meaning или ownership safety;
- **minor**: additive optional provenance key, compatible observation detail, новый
  boundary mode/action, который old consumer может безопасно отвергнуть, или closed admission
  that old consumers safely refuse;
- **patch**: clarification/diagnostic без изменения bytes, state transition или ownership.

Adapter version меняется отдельно: major — несовместимый rendered contract, minor — additive
provider output при сохранённом intent, patch — byte-compatible defect fix. Любое изменение,
которое меняет expected managed bytes, меняет source envelope через Adapter version и приводит
к `stale-source`, а не к скрытому overwrite.

Unknown artifact contract major, unknown boundary mode, observation или action fail closed.
Exact v1.0.0 records remain readable/writable without metadata. v1.1.0/v1.2.0 readers accept
the exact v1.0.0 and v1.1.0 shapes unchanged; v1.2.0 adds no lock-record shape. Artifact record с более новым minor MAY
читаться только если unknown keys игнорируются без потери ownership/hash semantics; иначе
`provenance-invalid`.

## Validation

Validator/check MUST отвергать как минимум:

1. duplicate/missing `artifact_id`, target ownership collision или absolute/escaping path;
2. unknown Provider ID/contract major/boundary mode;
3. malformed source/rendered hash или non-deterministic source envelope input;
4. duplicate, nested, missing или overlapping managed block markers;
5. provenance/header mismatch;
6. Override ambiguity, duplicate order или rendered output used as input;
7. Capability requirement, не допускающий observed Support Level;
8. automatic update поверх managed drift;
9. repair без explicit operation, pre-image и expected/observed evidence;
10. изменение bytes вне managed boundary;
11. check/dry-run, оставивший filesystem diff.
12. any bootstrap-transfer descriptor/path/decision/digest mismatch, present lock/created target
    or changed preimage before a write; each case leaves target, backup and lock unchanged.

Renderer MUST давать identical managed bytes и provenance hashes на повторном запуске с
identical envelope. Golden conformance включает at least `whole-file`, `managed-blocks`,
project Override, stale source, managed drift и ownership conflict.

## Examples

### Whole-file artifact

```json
{
  "contract_version": "1.0.0",
  "artifact_id": "task.plan-exec.codex-skill",
  "canonical_sources": [
    {"source_id": "task.command.plan-exec", "path": "packages/task/commands/plan-exec.md", "hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
  ],
  "adapter_id": "task.codex-skill",
  "adapter_version": "1.0.0",
  "provider_id": "codex",
  "target_path": ".agents/skills/task-plan-exec/SKILL.md",
  "source_hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "rendered_hash": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "managed_boundary": {"mode": "whole-file", "block_ids": []},
  "override_layers": [],
  "capability_requirements": [
    {"id": "skills.repository", "accepted_levels": ["native", "adapted"]}
  ]
}
```

Identical envelope обязан дать identical target bytes. Existing unowned target по этому path
даёт `ownership-conflict`, а не implicit adoption.

### Managed block with local intent

Project-owned bytes до/после block не входят в `rendered_hash`. Project Override входит в
source envelope и меняет expected block; он не является Drift (S5). Ручная правка внутри
block при прежнем record даёт `managed-drift` (S6) и требует explicit `repair`.

### State transitions

```text
missing --create--> clean
clean --source/adapter/override change--> stale-source --update--> clean
clean --managed bytes edited--> managed-drift --explicit repair--> clean
* --invalid boundary/provenance/ownership/capability--> refuse (no write)
```

Числа P0.1/P0.5, absolute host paths и timestamps не входят в golden records.
