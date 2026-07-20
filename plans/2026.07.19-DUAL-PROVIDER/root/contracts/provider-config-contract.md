# Provider configuration contract

**Version:** v0.1.0-draft  
**Status:** draft; sealing owner-gated in P1.1

Контракт должен определить project/fleet carriers, stable provider IDs, форму provider и
capability selections, deterministic precedence/merge, compatibility default, provenance,
diagnostic codes и golden examples для `.swissknife.json` и `config.json` layers.

До терминальных P0.3/P0.4 и исполнения P1.1 этот файл фиксирует только назначение. Его
поля не являются public API, не разрешают package implementation и не снимают
FOREMAN/fleet no-write gates.
