"""Base harness of the plugin contract suites (mechanisms/02-plugins §8).

The kind suites (``runtime_contract_suite``, ``check_runner_suite``, ...) belong to the owners of their
Protocols and are added here by them; the same suites run for built-in components.
This module holds what every suite shares: named cases, a report that never stops at the first failure, a test
``PluginContext`` and the manifest suite that a plugin author runs before shipping.

A passing manifest suite proves the declaration and that the factories construct; it does not prove the
behaviour of a component kind, which only the owner's suite checks."""

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

from skm.plugin_api import API_VERSION
from skm.plugin_api.manifest import PLUGIN_ID_PATTERN, ComponentKind, PluginContext, PluginManifest

__all__ = [
    "ContractCase",
    "ContractFailure",
    "ContractReport",
    "FixedClock",
    "manifest_contract_suite",
    "plugin_test_context",
    "run_contract_suite",
]

_PLUGIN_ID = re.compile(PLUGIN_ID_PATTERN.removeprefix("^").removesuffix("$"))


@dataclass(frozen=True, slots=True)
class ContractCase:
    name: str
    check: Callable[[], None]  # raises (AssertionError or any exception) when the contract is broken


@dataclass(frozen=True, slots=True)
class ContractFailure:
    case: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class ContractReport:
    suite: str
    passed: tuple[str, ...]
    failures: tuple[ContractFailure, ...]

    @property
    def ok(self) -> bool:
        return not self.failures

    def raise_for_failures(self) -> None:
        if self.failures:
            lines = "; ".join(f"{item.case}: {item.error_type}: {item.message}" for item in self.failures)
            raise AssertionError(f"{self.suite}: {len(self.failures)} case(s) failed: {lines}")


def run_contract_suite(suite: str, cases: Iterable[ContractCase]) -> ContractReport:
    """Run every case in order; a failing case is recorded and the next one still runs."""
    passed: list[str] = []
    failures: list[ContractFailure] = []
    seen: set[str] = set()
    for case in cases:
        if case.name in seen:
            raise ValueError(f"contract case {case.name!r} is declared twice in {suite}")
        seen.add(case.name)
        try:
            case.check()
        except Exception as exc:  # noqa: BLE001 - every failure is a finding of the report
            failures.append(ContractFailure(case.name, type(exc).__name__, str(exc)))
        else:
            passed.append(case.name)
    return ContractReport(suite, tuple(passed), tuple(failures))


@dataclass(frozen=True, slots=True)
class FixedClock:
    at: datetime = datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self.at


class _Log:
    """A logger that keeps records in memory: ``(level, event, fields)``."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, object]]] = []

    def debug(self, event: str, /, **fields: object) -> None:
        self.records.append(("debug", event, fields))

    def info(self, event: str, /, **fields: object) -> None:
        self.records.append(("info", event, fields))

    def warning(self, event: str, /, **fields: object) -> None:
        self.records.append(("warning", event, fields))

    def error(self, event: str, /, *, exc: BaseException | None = None, **fields: object) -> None:  # noqa: ARG002
        self.records.append(("error", event, fields))


def plugin_test_context(
    plugin_id: str,
    *,
    config: Callable[[], object] | None = None,
    settings_view: type | None = None,
    schemas: object = None,
    secrets: object = None,
    clock: FixedClock | None = None,
) -> PluginContext:
    """A ``PluginContext`` for tests: an empty configuration, an in-memory logger and a fixed clock."""
    empty: Mapping[str, object] = MappingProxyType({})
    return PluginContext(
        plugin_id=plugin_id,
        config=config if config is not None else (lambda: empty),
        settings_view=settings_view,
        log=_Log(),
        schemas=schemas,
        secrets=secrets,
        clock=clock or FixedClock(),
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _construct_case(
    manifest: PluginManifest, index: int, context: Callable[[str], PluginContext]
) -> ContractCase:
    spec = manifest.components[index]

    def check() -> None:
        built = spec.factory(context(manifest.id))
        _require(built is not None, "the factory returned None")
        if spec.kind is ComponentKind.RUNTIME:
            _require(
                getattr(built, "runtime_id", None) == spec.key, "runtime_id differs from the component key"
            )

    return ContractCase(f"construct:{index}:{spec.kind.value}:{spec.key}", check)


def manifest_contract_suite(
    manifest: PluginManifest, *, context: Callable[[str], PluginContext] | None = None
) -> ContractReport:
    """Declaration rules of 02-plugins §1-§4 that need no installed distribution, then each factory once."""
    make = context or plugin_test_context
    keys = [(spec.kind, spec.key) for spec in manifest.components]

    def plugin_id() -> None:
        _require(
            _PLUGIN_ID.fullmatch(manifest.id) is not None,
            f"plugin id {manifest.id!r} is not <publisher>.<name>",
        )

    def api_version() -> None:
        _require(manifest.plugin_api == API_VERSION, f"plugin_api {manifest.plugin_api} != {API_VERSION}")

    def unique_keys() -> None:
        _require(len(keys) == len(set(keys)), "a (kind, key) is declared twice")

    def runtime_data_paths() -> None:
        for spec in manifest.components:
            if spec.kind is ComponentKind.RUNTIME:
                expected = f"skm_runtimes/{spec.key}/capabilities.toml"
                _require(
                    spec.capabilities == expected, f"runtime {spec.key}: capabilities must be {expected}"
                )

    cases = [
        ContractCase("plugin_id", plugin_id),
        ContractCase("api_version", api_version),
        ContractCase("unique_keys", unique_keys),
        ContractCase("runtime_data_paths", runtime_data_paths),
        *(_construct_case(manifest, index, make) for index in range(len(manifest.components))),
    ]
    return run_contract_suite(f"manifest:{manifest.id}", cases)
