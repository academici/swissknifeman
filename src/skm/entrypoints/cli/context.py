"""CLI context (cli §1.1): the contract commands program against and the one process-level implementation.

``CliContext`` is what a command function receives. ``CliSession`` is its implementation for one invocation:
global flags, output streams, the redactor, the idempotency-key source and, for groups that need a backend,
the client built by ``main``. References are parsed here (``refs.py``); turning a slug, alias or prefix into
an id is a bus query of the owning group, so those lookups raise ``CAPABILITY_UNAVAILABLE`` until the group
that needs them supplies a resolver. Workspace/project context belongs to the selected instance (CLI §5.2).
"""

import json
import sys
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import accumulate
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Final, Protocol, TextIO, cast, override
from uuid import UUID

from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext
from skm.bootstrap.machine_access import SELECTION_KEY, validate_user_setting
from skm.entrypoints.cli.refs import (
    CliRef,
    RefForm,
    RefKind,
    ScopeSelector,
    as_uuid,
    default_scope_kind,
    parse_ref,
    parse_scope,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, NotFound, ValidationFailed
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import HostId, PlanId, ProjectId, RevisionId, RunId, ScopeId, TaskId, WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.public import DraftId
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.logging.redaction import ISSUED_TOKEN_VISIBLE_PATTERNS, MASK, Redactor
from skm.platform.machine import MachinePrincipal, MachineStore

if TYPE_CHECKING:
    from skm.bootstrap.checkout_operations import CheckoutRunner
    from skm.platform.config.sources.bootstrap import ProfileCatalog


__all__ = [
    "CONTEXT_SCHEMA",
    "Cell",
    "CliContext",
    "CliOptions",
    "CliRedactor",
    "CliSession",
    "frame",
    "seal",
    "untrusted",
]

CONTEXT_SCHEMA: Final = "urn:skm:cli:context:v1"
_CONTEXT_KEYS: Final = ("workspace_id", "workspace_slug", "project_id", "project_slug")


@dataclass(frozen=True, slots=True)
class Cell:
    """One unit of rendered output, for the last credential check (``seal``).

    ``own`` text is the CLI's fixed framing (labels, separators, JSON syntax, an applied mask) and is never
    masked. Any other cell is untrusted: a run of characters of a value in its shown form (``raw`` encoded by
    ``encode``, for example ``\\x1b`` for ESC) or a whole JSON scalar. An untrusted cell a credential touches
    becomes ``masked``; a run is first split into its characters, so only the touched ones are masked.
    """

    shown: str
    own: bool = False
    masked: str = MASK
    raw: str = ""
    encode: Callable[[str], str] | None = None


_MASK_CELL: Final = Cell(MASK, own=True)


def frame(text: str) -> Cell:
    """The CLI's own text: shown as it is and never masked."""
    return Cell(text, own=True)


def untrusted(redacted: str, encode: Callable[[str], str] = str) -> list[Cell]:
    """Cells of an already redacted value: its masks as they are and the runs between them, encoded.

    ``encode`` must work character by character (``encode(ab) == encode(a) + encode(b)``).
    """
    cells: list[Cell] = []
    for index, run in enumerate(redacted.split(MASK)):
        if index:
            cells.append(_MASK_CELL)
        if run:
            cells.append(Cell(encode(run), raw=run, encode=encode))
    return cells


def seal(redactor: Redactor, cells: Iterable[Cell]) -> str:
    """The joined cells after every untrusted cell that a registered credential overlaps has been masked.

    The search runs on the joined text, so a credential is found across characters of different values, an
    encoding (``\\x1b``, ``\\u0000``), a mask or the CLI's framing; only the untrusted characters of such an
    occurrence are masked, the framing stays. A ``Redactor`` other than ``CliRedactor`` has nothing to add.
    """
    secrets = redactor.secrets() if isinstance(redactor, CliRedactor) else ()
    return _seal(list(cells), secrets)


def _seal(cells: list[Cell], secrets: Sequence[str]) -> str:
    # Each round masks or splits at least one untrusted cell and never adds one, so the loop ends.
    while True:
        shown = "".join(cell.shown for cell in cells)
        present = [secret for secret in secrets if secret in shown]
        if not present:
            return shown
        starts = list(accumulate((len(cell.shown) for cell in cells[:-1]), initial=0))
        touched: set[int] = set()
        for secret in present:
            at = shown.find(secret)
            while at >= 0:
                first, last = bisect_right(starts, at) - 1, bisect_right(starts, at + len(secret) - 1) - 1
                touched.update(index for index in range(first, last + 1) if not cells[index].own)
                at = shown.find(secret, at + 1)
        if not touched:
            return shown
        cells = _masked(cells, touched)


def _masked(cells: list[Cell], touched: set[int]) -> list[Cell]:
    result: list[Cell] = []
    for index, cell in enumerate(cells):
        if index in touched and cell.encode is not None and len(cell.raw) > 1:
            result.extend(Cell(cell.encode(char), raw=char, encode=cell.encode) for char in cell.raw)
            continue
        current = (_MASK_CELL if cell.masked == MASK else frame(cell.masked)) if index in touched else cell
        if not (current == _MASK_CELL and result and result[-1] == _MASK_CELL):  # one mask per masked run
            result.append(current)
    return result


class CliRedactor(Redactor):
    """The shared ``Redactor`` plus credentials of any length, such as a short ``--as-token`` value.

    Every registered value (and its Python repr/ascii and JSON string spellings) is masked wherever it occurs
    as a substring, whatever its length and whatever stands next to it: ``Q7`` is masked in ``xQ7y`` too. All
    occurrences of all values (overlapping ones included) and all shared pattern matches are found in the
    original text and each covered run becomes one mask, so one value cannot hide part of another or a
    pattern match. Credentials assembled across masks or escaping are checked by ``seal``.
    Whitespace-separated fragments are registered too, so separate writes cannot reassemble a credential
    across lines or a prompt.
    Masking ordinary text that contains a short value or fragment is the accepted price; no length is refused.
    """

    def __init__(self) -> None:
        super().__init__(ISSUED_TOKEN_VISIBLE_PATTERNS)
        self._spellings: frozenset[str] = frozenset()  # replaced whole, so a reader takes one snapshot
        self._spellings_lock = Lock()

    @override
    def register_secret(self, value: str) -> None:
        if type(value) is not str:
            raise TypeError("a revealed secret must be a string")
        spellings = {
            spelling
            for part in (value, *value.split())
            for spelling in (
                part,
                repr(part)[1:-1],
                ascii(part)[1:-1],
                json.dumps(part, ensure_ascii=False)[1:-1],
                json.dumps(part, ensure_ascii=True)[1:-1],
            )
            if spelling
        }
        for spelling in spellings:
            super().register_secret(spelling)
        with self._spellings_lock:
            self._spellings = self._spellings | set(spellings)

    def secrets(self) -> tuple[str, ...]:
        """Registered spellings and fragments, including canonical shared values, longest first."""
        return tuple(sorted({*self._known(), *self._spellings}, key=lambda text: (-len(text), text)))

    def _cover(self, value: str, secrets: Sequence[str]) -> str:
        """Mask each run covered by a secret, an existing mask or a shared pattern match.

        Every span is found in the original input: masking a registered value first could hide a
        named assignment (``pass`` in ``password=``), a ``Bearer`` value or turn an invalid
        reference into a valid one, so the patterns never see an already masked text.
        """
        covered = bytearray(len(value))
        for start, end in self._spans(value, (*secrets, MASK)):
            covered[start:end] = b"\x01" * (end - start)
        shown = [
            char if not covered[index] else MASK
            for index, char in enumerate(value)
            if not covered[index] or index == 0 or not covered[index - 1]
        ]
        return "".join(shown)

    def _redact(self, value: str, secrets: Sequence[str]) -> str:
        return _seal(untrusted(self._cover(value, secrets)), secrets)

    @override
    def text(self, value: str) -> str:
        if type(value) is not str:
            raise TypeError("redaction text must be a string")
        return self._redact(value, self.secrets())

    @override
    def document(self, value: JsonValue) -> JsonValue:
        """Keys, strings and the JSON spelling of every other scalar, as ``text``, with one snapshot."""
        secrets = self.secrets()

        def walk(item: JsonValue) -> JsonValue:
            if type(item) is str:
                return self._redact(item, secrets)
            if type(item) is list:
                return [walk(entry) for entry in item]
            if type(item) is dict:
                result: dict[str, JsonValue] = {}
                for key, entry in item.items():
                    if type(key) is not str:
                        raise TypeError("redaction document keys must be strings")
                    result[self._redact(key, secrets)] = walk(entry)
                return result
            if item is None or type(item) in (bool, int, float):
                encoded = json.dumps(item, allow_nan=False)
                return MASK if any(secret in encoded for secret in secrets) else item
            raise TypeError("redaction accepts only JSON values")

        return walk(value)


class CliContext(Protocol):
    @property
    def client(self) -> SkmClient: ...
    @property
    def json(self) -> bool: ...
    @property
    def quiet(self) -> bool: ...
    @property
    def verbose(self) -> bool: ...
    @property
    def verbosity(self) -> int: ...
    @property
    def assume_yes(self) -> bool: ...
    @property
    def actor_hint(self) -> str | None: ...
    @property
    def color(self) -> bool: ...
    @property
    def request_id(self) -> str: ...
    @property
    def stdout(self) -> TextIO: ...
    @property
    def stderr(self) -> TextIO: ...
    @property
    def redactor(self) -> Redactor: ...

    def resolve_workspace(self, text: str | None) -> WorkspaceId: ...
    def resolve_project(self, text: str | None) -> ProjectId: ...
    def resolve_plan(self, text: str, *, project: ProjectId | None = None) -> PlanId: ...
    def resolve_revision(self, plan_id: PlanId, text: str | None) -> RevisionId: ...
    def resolve_draft(self, plan_id: PlanId, text: str | None) -> DraftId: ...
    def resolve_run(self, text: str) -> RunId: ...
    def resolve_task(self, run_id: RunId | None, text: str) -> TaskId: ...
    def resolve_scope(self, text: str | None) -> ScopeRef: ...
    def resolve_host(self, text: str | None) -> HostId: ...
    def new_idempotency_key(self) -> str: ...
    def confirm(self, prompt: str) -> bool: ...
    def save_context(self, **changes: str | None) -> None: ...
    def host_context(self) -> HostContext: ...


@dataclass(frozen=True, slots=True)
class CliOptions:
    """The global flags (cli §2) after parsing."""

    json: bool = False
    quiet: bool = False
    verbosity: int = 0
    assume_yes: bool = False
    no_color: bool = False
    actor_hint: str | None = None
    scope: str | None = None
    instance: str | None = None
    bootstrap: str | None = None
    sets: tuple[str, ...] = ()
    config: str | None = None


@dataclass(slots=True)
class CliSession:
    """``CliContext`` of one invocation. ``client`` is ``None`` for groups that do not need a backend."""

    options: CliOptions
    stdout: TextIO
    stderr: TextIO
    redactor: Redactor
    ids: IdGenerator
    request_id: str
    stdin: TextIO = field(default_factory=lambda: sys.stdin)
    client_: SkmClient | None = None
    host_factory: Callable[[], HostContext] | None = None
    state_dir: Path | None = None
    instance_id: UUID | None = None
    environ: Mapping[str, str] = field(default_factory=dict[str, str])
    remote_identity: Callable[[], UUID] | None = None
    machine_store: MachineStore | None = None
    machine_scope: Callable[[], MachinePrincipal] | None = None
    checkout_operation: "CheckoutRunner | None" = None
    host_name: str | None = None
    _context: dict[str, str] | None = field(default=None, repr=False)

    # ------------------------------------------------------------------ flags
    @property
    def json(self) -> bool:
        return self.options.json

    @property
    def quiet(self) -> bool:
        return self.options.quiet

    @property
    def verbosity(self) -> int:
        return self.options.verbosity

    @property
    def verbose(self) -> bool:
        return self.options.verbosity >= 1

    @property
    def assume_yes(self) -> bool:
        return self.options.assume_yes

    @property
    def actor_hint(self) -> str | None:
        return self.options.actor_hint

    @property
    def color(self) -> bool:
        return not self.options.no_color and "NO_COLOR" not in self.environ

    @property
    def client(self) -> SkmClient:
        if self.client_ is None:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "this command group runs without a backend client",
                details={"reason": "no_backend"},
            )
        return self.client_

    @property
    def home(self) -> Path:
        return Path(self.environ["HOME"]) if self.environ.get("HOME") else Path.home()

    def profile_catalog(self) -> "ProfileCatalog":
        from skm.platform.config.sources.bootstrap import ProfileCatalog

        return ProfileCatalog.read(self.options.bootstrap, self.environ, self.home)

    # ------------------------------------------------------------------ cli-context.json
    def _context_path(self) -> Path | None:
        return None if self.state_dir is None else self.state_dir / "cli-context.json"

    def load_context(self) -> dict[str, str]:
        if self._context is not None:
            return self._context
        if self.machine_store is not None:
            if self.machine_scope is None:
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Missing verified machine user scope")
            stored = self.machine_store.get_user_setting(self.machine_scope(), SELECTION_KEY)
            self._context = (
                {
                    key: value
                    for key, value in stored.items()
                    if key in _CONTEXT_KEYS and isinstance(value, str)
                }
                if isinstance(stored, dict)
                else {}
            )
            return self._context
        if self.remote_identity is not None:
            return {}
        loaded: dict[str, str] = {}
        path = self._context_path()
        if path is not None and path.is_file():
            try:
                parsed: object = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                parsed = None
            document: dict[str, object] = {}
            if isinstance(parsed, dict):
                document = cast("dict[str, object]", parsed)
            else:
                # The selection is lost either way; say so instead of acting as if none was ever made.
                self.stderr.write("warning: cli-context.json is unreadable; ignored (run `skm use` again)\n")
            same_instance = self.instance_id is None or document.get("instance_id") == str(self.instance_id)
            if document.get("schema") == CONTEXT_SCHEMA and same_instance:
                loaded = {key: str(document[key]) for key in _CONTEXT_KEYS if document.get(key)}
            elif document.get("schema") == CONTEXT_SCHEMA:
                self.stderr.write("warning: cli-context.json belongs to another instance; ignored\n")
        self._context = loaded
        return loaded

    def save_context(self, **changes: str | None) -> None:
        """Write ``cli-context.json`` (0600, atomic); ``None`` clears a key."""
        if self.machine_store is None and self.remote_identity is not None:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "HTTP context requires a verified machine profile"
            )
        unknown = sorted(set(changes) - set(_CONTEXT_KEYS))
        path = self._context_path()
        if unknown or (path is None and self.machine_store is None):
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                "cannot save the CLI context" if path is None else f"unknown context keys: {unknown}",
                details={"reason": "no_state_dir" if path is None else "unknown_keys"},
            )
        current = dict(self.load_context())
        for key, value in changes.items():
            if value is None:
                current.pop(key, None)
            else:
                current[key] = value
        if self.machine_store is not None and self.machine_scope is not None:
            value = validate_user_setting(
                SELECTION_KEY, {key: current.get(key) for key in ("workspace_id", "project_id")}, self.client
            )
            self.machine_store.set_user_setting(self.machine_scope(), SELECTION_KEY, value)
            self._context = current
            return
        assert path is not None  # noqa: S101 -- file-backed context was validated above
        document: dict[str, object] = {"schema": CONTEXT_SCHEMA, **current}
        if self.instance_id is not None:
            document["instance_id"] = str(self.instance_id)
        atomic_write(path, (json.dumps(document, indent=2, sort_keys=True) + "\n").encode(), mode=0o600)
        self._context = current

    def _from_context(self, key: str, kind: RefKind) -> UUID:
        value = self.load_context().get(key)
        if value is None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                f"no {kind.value} selected; pass one or run `skm use`",
                details={"kind": kind.value, "hint": "skm use"},
            )
        try:
            return UUID(value)
        except ValueError:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                f"the saved {kind.value} id is not valid; run `skm use` again",
                details={"kind": kind.value, "hint": "skm use"},
            ) from None

    # ------------------------------------------------------------------ references
    def _lookup(self, ref: CliRef) -> UUID:
        """``<kind>:<uuid>`` is its own answer; every other form is a lookup of the owner group."""
        if ref.form is RefForm.UUID and ref.uuid is not None:
            return ref.uuid
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            f'resolving the {ref.kind.value} reference "{ref.text}" needs the query of its command group',
            details={
                "kind": ref.kind.value,
                "form": ref.form.value,
                "hint": f"pass {ref.kind.value}:<uuid> or the bare uuid",
            },
        )

    def resolve_workspace(self, text: str | None) -> WorkspaceId:
        ref = parse_ref(RefKind.WORKSPACE, text)
        if ref.form is RefForm.CURRENT:
            return WorkspaceId(self._from_context("workspace_id", RefKind.WORKSPACE))
        return WorkspaceId(self._lookup(ref))

    def resolve_project(self, text: str | None) -> ProjectId:
        ref = parse_ref(RefKind.PROJECT, text)
        if ref.form is RefForm.CURRENT:
            return ProjectId(self._from_context("project_id", RefKind.PROJECT))
        return ProjectId(self._lookup(ref))

    def resolve_plan(self, text: str, *, project: ProjectId | None = None) -> PlanId:  # noqa: ARG002
        return PlanId(self._lookup(parse_ref(RefKind.PLAN, text)))

    def resolve_revision(self, plan_id: PlanId, text: str | None) -> RevisionId:  # noqa: ARG002
        return RevisionId(self._lookup(parse_ref(RefKind.REVISION, text)))

    def resolve_draft(self, plan_id: PlanId, text: str | None) -> DraftId:  # noqa: ARG002
        return DraftId(self._lookup(parse_ref(RefKind.DRAFT, text)))

    def resolve_run(self, text: str) -> RunId:
        return RunId(self._lookup(parse_ref(RefKind.RUN, text)))

    def resolve_task(self, run_id: RunId | None, text: str) -> TaskId:
        ref = parse_ref(RefKind.TASK, text)
        if ref.form is RefForm.DISPLAY_KEY and run_id is None:
            raise ValidationFailed(
                ErrorCode.INVALID_REFERENCE,
                f'task display key "{ref.text}" needs a run',
                details={"kind": "task", "ref": ref.text, "reason": "run_required"},
            )
        return TaskId(self._lookup(ref))

    def resolve_host(self, text: str | None) -> HostId:
        ref = parse_ref(RefKind.HOST, text)
        if ref.form is RefForm.CURRENT:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "the current host is not known to this process",
                details={"kind": "host", "hint": "skm host register"},
            )
        return HostId(self._lookup(ref))

    def scope_selector(self, text: str | None) -> ScopeSelector:
        """``--scope`` text or the default level of the saved context (cli §5.3), still unresolved."""
        if text is not None:
            return parse_scope(text)
        saved = self.load_context()
        kind = default_scope_kind(project="project_id" in saved, workspace="workspace_id" in saved)
        return ScopeSelector(kind)

    def resolve_scope(self, text: str | None) -> ScopeRef:
        """Scope of an explicit id or the saved context; other forms need a lookup."""
        selector = self.scope_selector(text if text is not None else self.options.scope)
        if selector.kind is ScopeKind.INSTANCE:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "the instance scope id is read from the backend by the command group",
                details={"kind": "instance"},
            )
        if selector.ref is None:
            key = {ScopeKind.WORKSPACE: "workspace_id", ScopeKind.PROJECT: "project_id"}.get(selector.kind)
            if key is None:
                raise ValidationFailed(
                    ErrorCode.INVALID_REFERENCE,
                    f"scope {selector.kind.value} needs a reference",
                    details={"kind": "scope", "ref": selector.kind.value},
                )
            kind = RefKind(selector.kind.value)
            return ScopeRef(selector.kind, ScopeId(self._from_context(key, kind)))
        by_id = as_uuid(selector.ref)
        if by_id is not None:
            return ScopeRef(selector.kind, ScopeId(by_id))
        ref_kind = RefKind(selector.kind.value)
        return ScopeRef(selector.kind, ScopeId(self._lookup(parse_ref(ref_kind, selector.ref))))

    # ------------------------------------------------------------------ interaction
    def new_idempotency_key(self) -> str:
        return "cli-" + str(self.ids.new_id())

    def confirm(self, prompt: str) -> bool:
        """``--yes`` -> True; without a terminal -> False; otherwise ask on stderr.

        The prompt is untrusted text like any other (SURFACE-03): redacted, then escaped, and only then
        does the CLI append its own ``[y/N]`` suffix.
        """
        from skm.entrypoints.cli.output import safe_join  # output imports this module for CliContext

        if self.assume_yes:
            return True
        if not self.stdin.isatty():
            return False
        self.stderr.write(safe_join(self, prompt, frame(" [y/N] ")))
        self.stderr.flush()
        return self.stdin.readline().strip().lower() in {"y", "yes"}

    def host_context(self) -> HostContext:
        if self.host_factory is None:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "host operations are not available in this composition",
                details={"reason": "no_host_services"},
            )
        return self.host_factory()
