"""Bounded command research protocol and shared synchronous subprocess transport."""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import selectors
import signal
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Any, cast
from urllib.parse import urlsplit

from skm.adapters.research.retry import SourceBusy, SourceFailed
from skm.kernel.cancel import CancelSource, CancelToken
from skm.modules.context.domain.research import RawDocument, RawSourceReply, ResearchSourceConfig, SourceQuery
from skm.modules.context.domain.research_rules import DEFAULT_DENY, HTTPS_RESEARCH_KINDS, url_problem
from skm.platform.config.secrets import SecretRef, SecretValue
from skm.platform.process.identity import group_alive
from skm.platform.process.ownership import launch

__all__ = [
    "CommandResearchSource",
    "PolicyReply",
    "ProcessSession",
    "admit_reply",
    "decode_reply",
    "validate_urls",
]

MAX_CAPTURE = 2_000_000


def validate_urls(
    documents: tuple[RawDocument, ...], *, cancel: CancelToken | None = None, timeout: float = 10
) -> None:
    """Deny private DNS answers as well as private literals; no retrieval/redirects happen here."""
    for doc in documents:
        if not doc.origin.lower().startswith(("http:", "https:")):
            continue
        try:
            url = urlsplit(doc.origin)
            host = url.hostname or ""
            if url.username is not None or url.password is not None or not host:
                raise ValueError("invalid URL")
            try:
                addresses = [ipaddress.ip_address(host)]
            except ValueError:
                # Returned origins are metadata. DNS admission never authorizes another fetch.
                resolver = ProcessSession(
                    (
                        sys.executable,
                        "-c",
                        "import json,socket,sys; "
                        "print(json.dumps([r[4][0] for r in "
                        "socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)]))",
                        host,
                    ),
                    {"PATH": os.defpath},
                    cancel or CancelSource().token,
                    timeout,
                )
                try:
                    addresses = [ipaddress.ip_address(value) for value in json.loads(resolver.exchange(b""))]
                finally:
                    resolver.close()
            if not addresses or any(not address.is_global for address in addresses):
                raise ValueError("private URL")
        except (OSError, ValueError):
            raise SourceFailed() from None


@dataclass(frozen=True, slots=True)
class PolicyReply(RawSourceReply):
    limitations: tuple[str, ...] = ()


def admit_reply(
    reply: RawSourceReply,
    config: ResearchSourceConfig,
    query: SourceQuery,
    *,
    cancel: CancelToken,
    timeout: float,
) -> PolicyReply:
    """Drop prohibited document origins before normalization/capture; keep explicit limitations."""
    documents: list[RawDocument] = []
    limitations: list[str] = list(cast("tuple[str, ...]", getattr(reply, "limitations", ())))
    renamed: dict[str, str] = {}
    deadline = monotonic() + timeout
    seen: set[str] = set()
    for raw_doc in reply.documents:
        doc = replace(raw_doc, locator=locator_value(raw_doc.locator))
        if doc.origin in seen:
            continue
        seen.add(doc.origin)
        if len(documents) >= min(query.max_documents, 50):
            limitations.append("truncated_to_max_documents")
            break
        cancel.raise_if_cancelled()
        if monotonic() >= deadline:
            raise SourceBusy("Research source timed out")
        if doc.origin.lower().startswith(("http:", "https:")):
            problem = url_problem(doc.origin, config.url_allow, DEFAULT_DENY)
            if not problem and config.kind not in HTTPS_RESEARCH_KINDS:
                try:
                    validate_urls((doc,), cancel=cancel, timeout=max(0.001, deadline - monotonic()))
                except SourceFailed:
                    problem = "url_denied:" + (urlsplit(doc.origin).hostname or "invalid")
            if problem:
                limitations.append(problem)
                continue
        elif doc.origin.startswith("file:"):
            limitations.append("source_unavailable:invalid_origin")
            continue
        elif doc.origin.startswith("repo:") and config.kind != "filesystem":
            # An arbitrary process cannot attest to a confined file read using an origin string.
            origin = "mcp:" + config.source_id + "/" + doc.origin
            renamed[doc.origin] = origin
            documents.append(replace(doc, origin=origin))
            continue
        documents.append(doc)
    claims = tuple((text, tuple(renamed.get(ref, ref) for ref in refs)) for text, refs in reply.claims)
    return PolicyReply(
        tuple(documents),
        reply.answer_text,
        claims,
        reply.usage,
        reply.raw_digest,
        tuple(dict.fromkeys(limitations)),
    )


def object_value(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SourceFailed()
    return cast("dict[str, Any]", value)


def array_value(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise SourceFailed()
    return cast("list[Any]", value)


def locator_value(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        value = {"fragment": value}
    locator = object_value(value)
    if set(locator) - {"page", "line_from", "line_to", "fragment"}:
        raise SourceFailed()
    for key, item in locator.items():
        if key == "fragment":
            if not isinstance(item, str) or len(item) > 500:
                raise SourceFailed()
        elif type(item) is not int or item < 1:
            raise SourceFailed()
    return locator


def decode_reply(data: bytes, protocol: str) -> RawSourceReply:  # noqa: PLR0912 -- independent untrusted protocol fields
    try:
        raw = object_value(json.loads(data))
        docs: list[RawDocument] = []
        answer: str | None = None
        claims: list[tuple[str, tuple[str, ...]]] = []
        if protocol == "text-v0":
            answer = raw["text"]
            if not isinstance(answer, str):
                raise SourceFailed()
            for origin in array_value(raw["sources"]):
                if not isinstance(origin, str):
                    raise SourceFailed()
                if not 1 <= len(origin) <= 2000:
                    raise SourceFailed()
                docs.append(RawDocument(origin, origin, None, {}))
        elif protocol == "json-v1":
            for entry in array_value(raw["documents"]):
                doc = object_value(entry)
                origin, title, body = doc["origin"], doc["title"], doc.get("text")
                locator = locator_value(doc.get("locator", {}))
                if (
                    not isinstance(origin, str)
                    or not isinstance(title, str)
                    or (body is not None and not isinstance(body, str))
                ):
                    raise SourceFailed()
                if any(
                    type(v) not in (str, int, float, bool, type(None))
                    or (type(v) is float and not math.isfinite(v))
                    for v in locator.values()
                ):
                    raise SourceFailed()
                if not 1 <= len(origin) <= 1900 or any(
                    len(key) > 500 or (isinstance(value, str) and len(value) > 500)
                    for key, value in locator.items()
                ):
                    raise SourceFailed()
                docs.append(RawDocument(origin, title, body, locator))
            for entry in array_value(raw.get("claims", [])):
                claim = object_value(entry)
                refs = array_value(claim["origins"])
                if (
                    not isinstance(claim["text"], str)
                    or not 1 <= len(claim["text"]) <= 4000
                    or not all(isinstance(ref, str) for ref in refs)
                ):
                    raise SourceFailed()
                claims.append((claim["text"], tuple(refs)))
        else:
            raise SourceFailed("RESEARCH_SOURCE_INVALID")
        if len(docs) > 5000 or len(claims) > 1000:
            raise SourceFailed()
        usage = object_value(raw["usage"]) if raw.get("usage") is not None else None
        if usage is not None and any(type(v) not in (str, int) for v in usage.values()):
            raise SourceFailed()
        return RawSourceReply(tuple(docs), answer, tuple(claims), usage, "sha256:" + sha256(data).hexdigest())
    except (ValueError, TypeError, KeyError, RecursionError, AttributeError):
        raise SourceFailed() from None


class ProcessSession:
    """Nonblocking pipes, one deadline and bounded combined stdout/stderr for one process group."""

    def __init__(
        self, argv: tuple[str, ...], env: Mapping[str, str], cancel: CancelToken, timeout: float
    ) -> None:
        cancel.raise_if_cancelled()
        self.cancel, self.deadline = cancel, monotonic() + timeout
        self.captured = 0
        self.pending = bytearray()
        self.stdout = bytearray()
        self.selector = selectors.DefaultSelector()
        try:
            self.process, self.owned = launch(argv, cwd=Path("/"), env=env)
        except OSError:
            self.selector.close()
            raise SourceFailed() from None
        for stream, kind in (
            (self.process.stdin, "in"),
            (self.process.stdout, "out"),
            (self.process.stderr, "err"),
        ):
            os.set_blocking(stream.fileno(), False)
            if kind != "in":
                self.selector.register(stream, selectors.EVENT_READ, kind)

    def send(self, data: bytes) -> None:
        if not data:
            return
        if len(data) + len(self.pending) > MAX_CAPTURE:
            raise SourceFailed()
        self.pending.extend(data)
        stream = self.process.stdin
        if stream not in [key.fileobj for key in self.selector.get_map().values()]:
            self.selector.register(stream, selectors.EVENT_WRITE, "in")

    def pump(self) -> None:
        self.cancel.raise_if_cancelled()
        if monotonic() >= self.deadline:
            raise SourceBusy("Research source timed out")
        for key, _ in self.selector.select(min(0.05, max(0, self.deadline - monotonic()))):
            fd = key.fd
            if key.data == "in":
                try:
                    size = os.write(fd, self.pending[:65536])
                except BrokenPipeError:
                    raise SourceFailed() from None
                del self.pending[:size]
                if not self.pending:
                    self.selector.unregister(key.fileobj)
            else:
                chunk = os.read(fd, 65536)
                if not chunk:
                    self.selector.unregister(key.fileobj)
                    continue
                self.captured += len(chunk)
                if self.captured > MAX_CAPTURE:
                    raise SourceFailed()
                if key.data == "out":
                    self.stdout.extend(chunk)

    def exchange(self, data: bytes, *, allowed_exit_codes: tuple[int, ...] = (0,)) -> bytes:
        self.send(data)
        while self.pending:
            self.pump()
        self.process.stdin.close()
        while self.selector.get_map() or self.owned.exit_code() is None:
            self.pump()
        if self.owned.exit_code() not in allowed_exit_codes:
            raise SourceFailed()
        return bytes(self.stdout)

    def close(self) -> None:
        # pidfd ownership keeps signals bound to this group even after its leader exits.
        try:
            self.owned.signal_group(signal.SIGTERM)
            deadline = monotonic() + 5
            pause = Event()
            while self.owned.group_alive() and monotonic() < deadline:
                pause.wait(min(0.05, max(0, deadline - monotonic())))
            self.owned.signal_group(signal.SIGKILL)
            if self.owned.reap(5) is None:
                raise SourceFailed()
            # reap() waits for the leader only. A member that ignored SIGTERM can
            # still be running after the leader has already exited and been reaped.
            deadline = monotonic() + 5
            while group_alive(self.owned.pid) and monotonic() < deadline:
                pause.wait(min(0.05, max(0, deadline - monotonic())))
            if group_alive(self.owned.pid):
                raise SourceFailed()
        finally:
            self.owned.close()
            self.selector.close()
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                stream.close()


class CommandResearchSource:
    kind = "command"

    def __init__(
        self,
        *,
        env_refs: Mapping[str, SecretRef] | None = None,
        resolve: Callable[[SecretRef], SecretValue] | None = None,
    ) -> None:
        self.env_refs, self.resolve = dict(env_refs or {}), resolve

    def validate_config(self, config: ResearchSourceConfig) -> tuple[str, ...]:
        problems: list[str] = []
        if not config.argv or not all(arg and "\0" not in arg for arg in config.argv):
            problems.append("argv")
        if config.protocol not in ("text-v0", "json-v1") or not 0 < config.timeout_seconds <= 3600:
            problems.append("protocol_or_timeout")
        if any(
            not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", key)
            or key.upper().startswith("SKM_")
            or key not in self.env_refs
            for key in config.env_allow
        ):
            problems.append("env_refs")
        return tuple(problems)

    def environment(self, config: ResearchSourceConfig) -> dict[str, str]:
        if self.validate_config(config):
            raise SourceFailed("RESEARCH_SOURCE_INVALID")
        env = {"PATH": os.defpath, "LANG": "C.UTF-8"}
        for key in config.env_allow:
            ref = self.env_refs[key]
            if (
                type(ref) is not SecretRef
                or (ref.scheme == "env" and ref.path.upper().startswith("SKM_"))
                or self.resolve is None
            ):
                raise SourceFailed("RESEARCH_SOURCE_INVALID")
            env[key] = self.resolve(ref).reveal()
        return env

    def search(
        self, config: ResearchSourceConfig, query: SourceQuery, *, cancel: CancelToken
    ) -> RawSourceReply:
        data = (
            query.text.encode()
            if config.protocol == "text-v0"
            else json.dumps(
                {"query": query.text, "max_documents": query.max_documents, "depth": query.depth}
            ).encode()
        )
        session = ProcessSession(config.argv, self.environment(config), cancel, config.timeout_seconds)
        try:
            reply = decode_reply(session.exchange(data), config.protocol)
            return admit_reply(
                reply, config, query, cancel=cancel, timeout=max(0.001, session.deadline - monotonic())
            )
        finally:
            session.close()
