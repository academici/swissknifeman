"""Bounded retries and per-source concurrency for host research gateways."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from threading import Lock
from time import monotonic
from typing import TYPE_CHECKING, cast

from skm.kernel.clock import Clock
from skm.kernel.id_generator import IdGenerator
from skm.platform.logging.redaction import Redactor
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

if TYPE_CHECKING:
    from skm.kernel.cancel import CancelToken
    from skm.modules.context.domain.research import (
        RawSourceReply,
        ResearchSourceConfig,
        SourceQuery,
    )
    from skm.modules.context.ports import ResearchSource

__all__ = ["ResearchSources", "SourceBusy", "SourceFailed", "with_retry"]


class SourceBusy(TimeoutError):
    """Transient source timeout or concurrency saturation."""


class SourceFailed(ValueError):
    """Permanent failure; never include subprocess output or credentials."""

    def __init__(self, code: str = "RESEARCH_SOURCE_UNAVAILABLE") -> None:
        self.code = code
        super().__init__("Research source failed")


def with_retry[T](call: Callable[[], T], *, cancel: CancelToken, attempts: int = 3) -> T:
    if not 1 <= attempts <= 3:
        raise ValueError("research attempts must be between one and three")
    for attempt in range(1, attempts + 1):
        cancel.raise_if_cancelled()
        try:
            return call()
        except SourceBusy:
            if attempt == attempts:
                raise
            cancel.wait(5 * attempt)
            cancel.raise_if_cancelled()
    raise AssertionError("unreachable")


class ResearchSources:
    """Registry wraps all adapters, including plugins, in the same retry/concurrency gate."""

    def __init__(
        self,
        sources: Mapping[str, ResearchSource],
        *,
        redactor: Redactor | None = None,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self._sources = dict(sources)
        self.redactor = redactor or Redactor()
        self.clock = clock or SystemClock()
        self.ids = ids or Uuid7Generator(self.clock)
        self._gates: dict[str, _Gate] = {}
        self._lock = Lock()

    def kinds(self) -> frozenset[str]:
        return frozenset(self._sources)

    def get(self, kind: str) -> ResearchSource:
        return _Source(self, self._sources[kind])

    def checkout_state(
        self, mounts: Mapping[str, str], cancel: CancelToken, *, source: ResearchSourceConfig | None = None
    ) -> str | None:
        # The same checkout bytes can yield different results before and after a native reindex.
        if source is not None and source.kind == "codegraph":
            return None
        reader = getattr(self._sources.get("filesystem"), "checkout_state", None)
        return (
            cast(
                "str | None",
                reader(mounts, cancel, roots=source.roots if source and source.kind == "filesystem" else ()),
            )
            if callable(reader)
            else None
        )

    def gate(self, config: ResearchSourceConfig) -> _Gate:
        if not 1 <= config.concurrency <= 16:
            raise SourceFailed("RESEARCH_SOURCE_INVALID")
        with self._lock:
            gate = self._gates.setdefault(config.source_id, _Gate(config.concurrency))
            gate.narrow(config.concurrency)
            return gate


class _Gate:
    """A nonblocking semaphore; live narrowing never creates another allowance."""

    def __init__(self, limit: int) -> None:
        self.limit, self.active = limit, 0
        self.lock = Lock()

    def narrow(self, limit: int) -> None:
        with self.lock:
            self.limit = min(self.limit, limit)

    def acquire(self, *, blocking: bool = False) -> bool:
        if blocking:
            raise ValueError("research gates are nonblocking")
        with self.lock:
            if self.active >= self.limit:
                return False
            self.active += 1
            return True

    def release(self) -> None:
        with self.lock:
            if self.active <= 0:
                raise ValueError("unbalanced research gate release")
            self.active -= 1


class _Source:
    def __init__(self, registry: ResearchSources, adapter: ResearchSource) -> None:
        self.registry, self.adapter = registry, adapter
        self.kind = adapter.kind

    def validate_config(self, config: ResearchSourceConfig) -> tuple[str, ...]:
        return self.adapter.validate_config(config)

    def search(
        self, config: ResearchSourceConfig, query: SourceQuery, *, cancel: CancelToken
    ) -> RawSourceReply:
        def attempt() -> RawSourceReply:
            cancel.raise_if_cancelled()
            gate = self.registry.gate(config)
            if not gate.acquire(blocking=False):
                raise SourceBusy("Research source busy")
            try:
                from skm.adapters.research.command import admit_reply

                started = monotonic()
                reply = self.adapter.search(config, query, cancel=cancel)
                reply = replace(
                    reply,
                    documents=tuple(
                        replace(
                            doc,
                            locator={
                                self.registry.redactor.text(key): value for key, value in doc.locator.items()
                            },
                        )
                        for doc in reply.documents
                    ),
                )
                return admit_reply(
                    reply,
                    config,
                    query,
                    cancel=cancel,
                    timeout=max(0.001, config.timeout_seconds - (monotonic() - started)),
                )
            finally:
                gate.release()

        return with_retry(attempt, cancel=cancel)
