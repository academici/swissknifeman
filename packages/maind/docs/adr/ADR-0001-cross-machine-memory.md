# ADR-0001 — cross-machine memory mAInd: host, transport, trust, offline degradation

**Status:** Accepted — Approval Owner D80 (clarifies D78)
**Date:** 2026-07-28
**Scope:** P4.1 only. Captures the eight accepted responses of the solution package (`research/06-P4-target-design.md`
§6); implementation - `iii-config.yaml`, `core.http`, `memory.py`, `provision/*` — produce P4.2/P4.3.

## Context

`bootstrap-machine.sh` raises on every new machine **new, empty** local daemon
agent-memory — accumulated memory from other machines is not transferred (shelved idea).
The activation criterion worked: the owner has a second permanent car. Option 1 stub - the only one alive
demon on always-on host, other machines - network clients - selected for implementation; option 2
(event-log export/import) is not implemented.

Intelligence (layer 1; `research/06-P4-target-design.md`, layer 2)
narrowed down the eight operational forks of the solution package to specific facts: `tailscale serve`
only proxies loopback-backend (§1); at the engine `@agentmemory/agentmemory@0.9.27` yes
bearer-authentication `AGENTMEMORY_SECRET`, but ours `core/http.py` does not know how to send headers, and
`ping` interprets `401` like «is alive» (§2); store - directory of 9 JSON-blobs, not SQLite (§4); at the engine
there is a built-in mesh-sync — upstream-implementation «option 2» (§3). The owner answered all
eight points of the package in two passes: seven - `D78` (2026-07-25), eighth (host + transport
next stage) — `D80` (2026-07-25, `finish`). Open forks in this item'is no more -
subject of work: an accurate record of what is accepted, not a choice.

## Decision

Eight points of the package - a specific choice for each, where it was taken from:

1. **Host** → holds **CURRENT car** (not rented hosting, not dedicated always-on node:
   criterion D78 processed - home always-on no node ⇒ thread «machine with the highest uptime» —
   this is the current machine) → **D80**.
2. **Transport** → next stage - **LAN**, bind on **specific LAN-host address** (not
   `127.0.0.1`, not `0.0.0.0`); `tailscale serve` on loopback-backend (option A from D78) not cancelled,
   and delivered **to trigger**: third permanent machine OR work outside LAN → **D80** (clarifies
   `D78`/`D28`).
3. **`AGENTMEMORY_SECRET`** → **enable**. On LAN-stage Tailscale ACL/grants do not work - their
   takes up space firewall-host rule «one port from the subnet LAN»; secret becomes
   **the only one** fuse → **D29** + **D80**.
4. **Token bearer and HTTP-client** → **`secret_file` (0600), NOT env**; authentication - additive
   extension `core.http` (`headers=None` parameter), second HTTP-client in `maind` prohibited →
   **D29**.
5. **Offline degradation** → **fail-soft without local cache/outbox**: read and write honestly
   report memory host unavailable; at `memory.role = client` raise local daemon
   prohibited **code** (not documentation) → **D27**.
6. **Store migration** → **cleared**: host matches the current machine, there is nothing to transfer (item not
   «done» — does not have an item at this stage) → **D80**.
7. **Backup** → app-level export (`GET /agentmemory/export`) scheduled + periodic check
   **recovery** (not having a file); retention **7–30 days + 1–3 monthly dots** → **D30**.
8. **Upstream `mesh-sync`** → existence is known, **do not use** (two writers + LWW-grinding
   against the only writer for whom option 1 was chosen) → **D31**.

## Alternatives (rejected options)

1. **Bind `0.0.0.0` + firewall** — rejected: when bind on all interfaces device key expired
   ceases to be a fuse (service remains available via other interfaces), and the surface
   attack expands to LAN (**D28**).
2. **Bind on tailnet-IP `100.x` (option B)** — removed **D78** in favor `tailscale serve` on
   loopback-backend (transport A); node address may change during reinitialization, controlled
   `iii-config.yaml` would become machine specific.
3. **Upstream `mesh-sync`** — we know that there is, **do not use**: returns two writers and
   LWW-grinding, for the sake of eliminating which option 1 of the stub was chosen (**D31**).
4. **Local cache/outbox deferred write** — not entered: price (duplicates, order out of sync,
   LWW-grinding, loss window) requires versioning and record idempotency, which
   contract `store` no (**D27**).

## Consequences

- P4.2 gets in Scope Included `packages/maind/config/memory/iii-config.yaml` (bind to a specific
  LAN-address - if option A transport this file would not be touched at all) and implements
  `memory.role` (`standalone`|`host`|`client`), prohibition of the second writer by code, additive
  extension `core.http` headers, honest unavailability errors/unauthorized.
- P4.3 reformulates acceptance gate 4: «inaccessibility from outside tailnet» → «unavailability due to
  subnet limits LAN» — at this stage the fuse is checked LAN, not tailnet.
- Trigger `tailscale serve` («third machine OR work outside LAN») is written as the condition being tested:
  when triggered, this is a configuration edit, not a design rediscovery - both transport options
  remain described by this ADR.
- The path of growth beyond this phase is not retold here: return to the difficult part - according to measured need.
- Memory circuit, scope-markers and graph federation do not change - only memory becomes shared; count
  and the project registry remain per-machine.

## Known limitations

Previous (are not changed by host selection/transport):
1. Offline machine (no network to host) works **without memory** — no local cache (see Decision
   p.5).
2. The host must remain alive (reboot/dream/vacation remove memory from all machines at once).
3. Federation graph (`data/graphs/*.db`) and project registry (`~/.swissknifeman/projects.json`)
   remain **per-machine** — only the memory becomes shared, not the graph.
4. Viewer `agentmemory` available **only loopback-ohm** on the host - does not have publications under any circumstances
   transport (engine: «no auth is enforced on the console»).

Added LAN-stage - the price of the nearest stage, named before implementation:
5. On LAN-stage secret (`AGENTMEMORY_SECRET`) — **the only one** access fuse.
6. Automatic revocation when device key expires (like Tailscale) on LAN-stage **no**.
7. Secret rotation - **manual** operation runbook'ah, not automatic.
8. Segment LAN **wider** tailnet: who received the secret and is in the same segment - reads and writes
   memory of ALL projects.
9. Power Trigger `tailscale serve` («third machine OR work outside LAN») — condition to be checked,
   and not «when needed»; until triggered the transport remains LAN-stage with restrictions above.

The path of growth beyond these limitations is not included in this phase: return to the heavy part - by
measured demand.

## Approval condition

`D80` (2026-07-25, `finish`) closes the eighth (last) solution package item - host and
transport of the next stage - and clarifies `D78`/`D28` in the parts named above; seven others
points recorded `D78` (2026-07-25) and do not reopen during execution P4.2/P4.3: change
any of the eight points after accepting this ADR — reopen with new D-owner record
(`supersedes` regarding the relevant paragraph), and not «clarification as we go».
