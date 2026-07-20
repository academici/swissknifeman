# Provider analytics contract

**Version:** v0.1.0-draft  
**Status:** draft; sealing owner-gated in P6.3

Контракт должен определить provider-neutral event/run envelope, stable provider/session
identity, normalized local storage, explicit provider reader registry, raw-data/privacy
boundary, provenance/redaction, retention, diagnostics, legacy Claude compatibility и
обратимую migration для consumers `analyst`, `maind` и harness capture adapters.

До terminal/frozen P0–P5 entry gate и исполнения P6.3 файл фиксирует только назначение.
Он не разрешает package implementation, не объявляет provider raw payload общим API, не
разрешает удаление `.claude` legacy data и не снимает FOREMAN/fleet no-write gates.
