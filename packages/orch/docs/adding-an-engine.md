# Adding an engine

1. Добавить значение в enum `defs.binding`. Это minor-изменение exec/v1: документы существующих bindings остаются
   валидными. Записать в «Changelog контрактов» (`packages/orch/docs/contracts.md`).
2. Модуль `orch/bindings/<name>.py` с классом, реализующим `EnginePort`; `prepare` вызывает `prepare_common` и добавляет проекцию.
3. Capability seeds `bindings/capabilities/<name>--<provider>.json` (status `declared`, evidence обязателен).
4. Столбец в `bindings/matrix.json` и таблице docs; тест матрицы требует значение для каждой capability.
5. Добавить binding в конформанс-тест (P5.4) — тест параметризован по `BINDINGS`.
6. Не трогать Task, Skiller, схемы input/policy/role: если пришлось — граница недостаточно универсальна, это дефект контракта.

Capabilities per binding: see the matrix in [engine-port.md](engine-port.md) (`bindings/matrix.json`).
