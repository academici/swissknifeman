"""Stubs: additional instructions a person writes for a role, by machine and by project (instruction overlays).

A stub never replaces the canonical text of a role and never changes what the role may do (tools, write authority,
scope, checks, result contract): it is one more block of the prompt, after the role text and before the task. A module
names its customization points as targets (``orch.role.reviewer``); a target ``<package>.<kind>.<name>`` is fed by four
slots, from the general to the specific::

    _all.md   <package>/_all.md   <package>/<kind>s/_all.md   <package>/<kind>s/<name>.md

each looked up in two layers: the machine (``<config dir>/stubs``, ``~/.local/share/swissknifeman/config/stubs``) and the project
(``projects/<code>/local/stubs`` of the project's workspace when the project marker names one, else
``<project>/.swissknifeman/stubs``). Within a slot the project file decides by its mode; an empty file (or one with
comments only) inherits the machine one, so publishing every empty file masks nothing:

- ``replace`` (default): a non-empty project body replaces the machine body of the slot;
- ``append``: the project body follows the machine body;
- ``disable``: the slot gives nothing (its body must be empty).

The slots that give text are joined from the general to the specific. A file is read once, as bytes, without following
a symlink; the first line may be ``<!-- skm-stub:v1 target=<id> mode=<mode> -->``. Text is literal (no includes, no
variables). ``resolve`` gives the text of each target and the provenance of every part, ``snapshot`` the document a run
keeps so that a resume uses the same text whatever the files say later. stdlib only.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Iterable, Mapping, Optional

from aicore.state.locations import config_dir, project_stubs_dir
from aicore.util.digest import digest_json
from aicore.util.redact import redact_text

SCHEMA = "urn:swissknifeman:aicore:instruction-set:v1"
LAYERS = ("machine", "project")
MODES = ("replace", "append", "disable")
MAX_BYTES = 32 * 1024  # one file
MAX_TARGET_BYTES = 64 * 1024  # the joined text of one target
_HEADER = re.compile(r"\A<!--\s*skm-stub:(?P<version>\S+)(?P<fields>(?:\s+[a-z_]+=\S+)*)\s*-->[ \t]*\n?")
_FIELD = re.compile(r"([a-z_]+)=(\S+)")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TARGET = re.compile(r"^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*\.[a-z0-9][a-z0-9-]*$")
_VARIANT_NAME = re.compile(r"[a-z0-9][a-z0-9.-]*")


class StubError(ValueError):
    """A stub that cannot be used: ``STUB_SYMLINK_FORBIDDEN``, ``STUB_NOT_REGULAR``, ``STUB_PERMISSIONS`` (writable by
    every user), ``STUB_TOO_LARGE``, ``STUB_INVALID_UTF8``, ``STUB_METADATA_INVALID``, ``STUB_TARGET_MISMATCH``,
    ``STUB_MODE_INVALID``, ``STUB_SECRET``, ``STUB_TARGET_UNKNOWN``. The message names the file."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def roots(project: Optional[os.PathLike] = None, *, env: Optional[Mapping[str, str]] = None,
          layers: Iterable[str] = LAYERS) -> dict:
    """``{layer: folder}`` of the stubs, for the layers asked (the project only with a project)."""
    found = {}
    if "machine" in layers:
        found["machine"] = config_dir(env=env) / "stubs"
    if "project" in layers and project is not None:
        found["project"] = project_stubs_dir(project, env=env)
    return found


def slots(target: str) -> list:
    """The slot paths of ``target`` (``package.kind.name``), from the general to the specific."""
    if not _TARGET.match(target):
        raise StubError("STUB_TARGET_UNKNOWN", f"{target!r} is not <package>.<kind>.<name>")
    package, kind, name = target.split(".")
    return ["_all.md", f"{package}/_all.md", f"{package}/{kind}s/_all.md", f"{package}/{kind}s/{name}.md"]


def _read(path: Path) -> Optional[bytes]:
    """The bytes of ``path``; None when there is no file. A symlink anywhere below the layer root is refused by the
    caller; here the file itself is opened without following one and checked through its descriptor."""
    try:
        handle = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return None
    except OSError as error:
        if os.path.islink(path):
            raise StubError("STUB_SYMLINK_FORBIDDEN", f"{path} is a symlink") from None
        raise StubError("STUB_NOT_REGULAR", f"{path}: {error}") from None
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode):
            raise StubError("STUB_NOT_REGULAR", f"{path} is not a regular file")
        if info.st_mode & stat.S_IWOTH:  # any user of the machine could put words into every prompt of the role
            raise StubError("STUB_PERMISSIONS", f"{path} is writable by every user (chmod o-w)")
        if info.st_size > MAX_BYTES:
            raise StubError("STUB_TOO_LARGE", f"{path} has {info.st_size} bytes, more than {MAX_BYTES}")
        with os.fdopen(handle, "rb") as stream:
            handle = -1
            return stream.read(MAX_BYTES + 1)
    finally:
        if handle >= 0:
            os.close(handle)


def _no_link_on_the_way(root: Path, relative: str) -> None:
    """A folder of the slot path that is a symlink would lead the read outside the layer: refused."""
    current = root
    for part in [""] + relative.split("/")[:-1]:
        current = current / part if part else current
        if os.path.islink(current):
            raise StubError("STUB_SYMLINK_FORBIDDEN", f"{current} is a symlink")


def parse(data: bytes, *, path: str, target: str, slot: str) -> dict:
    """``{mode, body}`` of one stub file. The body is the text without the header and the comments, with LF line ends
    and one final newline; "" means the file inherits."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise StubError("STUB_INVALID_UTF8", f"{path}: {error}") from None
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    mode = "replace"
    header = _HEADER.match(text)
    if header:
        if header.group("version") != "v1":
            raise StubError("STUB_METADATA_INVALID", f"{path}: unknown stub version {header.group('version')!r}")
        fields = dict(_FIELD.findall(header.group("fields")))
        unknown = sorted(set(fields) - {"target", "mode"})
        if unknown:
            raise StubError("STUB_METADATA_INVALID", f"{path}: unknown field(s) {', '.join(unknown)}")
        mode = fields.get("mode", mode)
        if mode not in MODES:
            raise StubError("STUB_MODE_INVALID", f"{path}: mode {mode!r} is not one of {', '.join(MODES)}")
        expected = slot_target(target, slot)
        if "target" in fields and fields["target"] != expected:
            raise StubError("STUB_TARGET_MISMATCH", f"{path}: header names {fields['target']!r}, the file is {expected!r}")
        text = text[header.end():]
    elif "skm-stub:" in text.split("\n", 1)[0]:
        raise StubError("STUB_METADATA_INVALID", f"{path}: the first line is not a valid skm-stub header")
    body = _COMMENT.sub("", text).strip()
    if body and redact_text(body) != body:  # the text goes to a model provider: a token never does
        raise StubError("STUB_SECRET", f"{path}: the text holds what looks like a secret (a token or name=value of a "
                        "secret name); name where the role finds it instead")
    if mode == "disable" and body:
        raise StubError("STUB_MODE_INVALID", f"{path}: a disable stub holds no text")
    return {"mode": mode, "body": body + "\n" if body else ""}


def slot_target(target: str, slot: str) -> str:
    """The id a slot file names in its header: the target for the exact slot, ``<package>.<kind>s._all`` and so on
    for the shared ones (``_all`` for the root)."""
    exact = slots(target)[-1]
    if slot.startswith(exact[:-3] + "@") and slot.endswith(".md"):
        variant = slot[len(exact[:-3]) + 1:-3]
        variant_slot(target, variant)  # validate before accepting a header with @
        return f"{target}@{variant}"
    parts = slot[:-len(".md")].split("/")
    return target if slot == slots(target)[-1] else ".".join(parts)


def variant_slot(target: str, variant: str) -> str:
    """The extra slot of the same target; provider and optional family cannot escape its directory."""
    exact = slots(target)[-1]
    provider, separator, family = variant.partition("--")
    if (not _VARIANT_NAME.fullmatch(provider) or
            (separator and (not _VARIANT_NAME.fullmatch(family) or "--" in family))):
        raise StubError("STUB_TARGET_UNKNOWN", f"{exact[:-3]}@{variant}.md: invalid stub variant")
    return f"{exact[:-3]}@{variant}.md"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def effective_bytes(parts: list) -> int:
    """Bytes of the largest text one route can be given: the common parts, then, for the provider whose choice is
    largest, its ``provider`` variant and its largest ``provider--family`` variant. A route takes at most one variant of
    each kind, so the variants of other providers never add up; which variant a route takes is the caller's business."""
    def size(rows: list) -> int:
        return len("\n".join(row["body"] for row in rows).encode("utf-8"))

    common = [part for part in parts if "variant" not in part]
    chosen: dict = {}
    for part in parts:
        if "variant" in part:
            chosen.setdefault(part["variant"], []).append(part)
    worst = size(common)
    for provider in {variant.partition("--")[0] for variant in chosen}:
        families = [rows for variant, rows in chosen.items() if variant.startswith(provider + "--")]
        worst = max(worst, size(common + chosen.get(provider, []) + max(families, key=size, default=[])))
    return worst


def resolve(targets: Iterable[str], project: Optional[os.PathLike] = None, *, env: Optional[Mapping[str, str]] = None,
            layers: Iterable[str] = LAYERS, variants: Optional[Mapping[str, Iterable[str]]] = None) -> dict:
    """``{target: {"text", "parts": [...], "skipped": [...]}}``: the additional instructions of each target. A part:
    ``{slot, layer, path, mode, sha256, bytes, reason}``; variant parts additionally keep ``variant`` and ``body``.
    Variants are extra slots of the same target, excluded from its common ``text``. ``skipped`` names inherited
    (empty) and disabled files."""
    found_roots = roots(project, env=env, layers=layers)
    cache: dict = {}

    def load(layer: str, slot: str, target: str) -> Optional[dict]:
        key = (layer, slot)
        if key not in cache:
            root = found_roots.get(layer)
            if root is None:
                cache[key] = None
            else:
                _no_link_on_the_way(root, slot)
                data = _read(root / slot)
                cache[key] = None if data is None else dict(
                    parse(data, path=str(root / slot), target=target, slot=slot), path=str(root / slot))
        return cache[key]

    out = {}
    for target in targets:
        parts, skipped = [], []
        target_slots = [(slot, None) for slot in slots(target)]
        target_slots += [(variant_slot(target, variant), variant)
                         for variant in dict.fromkeys((variants or {}).get(target, []))]
        for slot, variant in target_slots:
            skipped_start = len(skipped)
            machine, project_file = load("machine", slot, target), load("project", slot, target)
            chosen = []
            if project_file is not None and project_file["mode"] == "disable":
                skipped.append({"slot": slot, "layer": "project", "path": project_file["path"], "reason": "disabled"})
            else:
                if machine is not None and machine["body"]:
                    if project_file is not None and project_file["body"] and project_file["mode"] == "replace":
                        skipped.append({"slot": slot, "layer": "machine", "path": machine["path"], "reason": "replaced"})
                    else:
                        chosen.append(("machine", machine, "inherited" if project_file else "machine"))
                if project_file is not None and project_file["body"]:
                    chosen.append(("project", project_file, project_file["mode"]))
                for layer, doc in ((name, doc) for name, doc in (("machine", machine), ("project", project_file))
                                   if doc is not None and not doc["body"]):
                    skipped.append({"slot": slot, "layer": layer, "path": doc["path"], "reason": "empty"})
            for layer, doc, reason in chosen:
                parts.append({"slot": slot, "layer": layer, "path": doc["path"], "mode": doc["mode"],
                              "sha256": _sha(doc["body"]), "bytes": len(doc["body"].encode("utf-8")), "reason": reason,
                              "body": doc["body"], **({"variant": variant} if variant is not None else {})})
            if variant is not None:
                for row in skipped[skipped_start:]:
                    row["variant"] = variant
        text = "\n".join(part["body"] for part in parts if "variant" not in part)
        if effective_bytes(parts) > MAX_TARGET_BYTES:
            raise StubError("STUB_TOO_LARGE", f"{target}: the common stubs and the largest variant hold more than "
                                              f"{MAX_TARGET_BYTES} bytes")
        out[target] = {"text": text, "parts": [{key: value for key, value in part.items()
                                               if key != "body" or "variant" in part}
                                               for part in parts], "skipped": skipped}
    return out


def snapshot(targets: Iterable[str], project: Optional[os.PathLike] = None, *, env: Optional[Mapping[str, str]] = None,
             layers: Iterable[str] = LAYERS, variants: Optional[Mapping[str, Iterable[str]]] = None) -> dict:
    """The instruction set a run keeps (``instruction-set/v1``): the resolved text of every target with a part, the
    layers read and one digest of it all (the same files give the same digest)."""
    layers = tuple(layer for layer in LAYERS if layer in tuple(layers))
    resolved = resolve(targets, project, env=env, layers=layers, variants=variants)
    body = {target: {"text": found["text"], "parts": found["parts"]}
            for target, found in sorted(resolved.items()) if found["parts"]}
    digest = digest_json({"layers": list(layers), "targets": body})
    document = {"$schema": SCHEMA, "layers": list(layers), "digest": digest, "targets": body}
    _validate_snapshot(document)
    return document


def _validate_snapshot(document: dict) -> None:
    """Refuse a snapshot the instruction-set schema does not accept (``INSTRUCTION_SET_INVALID``)."""
    from aicore.util.schema import load_contract, validate
    directory = Path(__file__).resolve().parents[2] / "schemas" / "instruction-set" / "v1"
    registry, kind = load_contract(directory)
    issues = validate(document, kind, registry)
    if issues:
        raise StubError("INSTRUCTION_SET_INVALID", "; ".join(issue.message for issue in issues[:5]))


def template(target: str, slot: str) -> str:
    """The text of an empty stub file of ``slot``: the header and one comment; it inherits until somebody writes in it."""
    return (f"<!-- skm-stub:v1 target={slot_target(target, slot)} mode=replace -->\n"
            "<!-- Additional instructions for this target. An empty file inherits the machine layer; mode=append adds to "
            "it, mode=disable drops it. They refine how the role works; they cannot change its tools, write authority, "
            "scope, checks or result. -->\n")


def publish(targets: Iterable[str], root: os.PathLike, *, dry_run: bool = False) -> list:
    """Create the missing stub files of ``targets`` under ``root``: ``[{path, status}]`` with status ``created``,
    ``unchanged`` (a file is there: it is never overwritten) or ``refused`` (a symlink or not a regular file). A file is
    created with ``O_CREAT|O_EXCL``, so two publishers never write one file twice."""
    root = Path(root)
    rows, seen = [], set()
    for target in targets:
        for slot in slots(target):
            if slot in seen:
                continue
            seen.add(slot)
            path = root / slot
            row = {"path": str(path), "slot": slot}
            try:
                _no_link_on_the_way(root, slot)
            except StubError as error:
                rows.append(dict(row, status="refused", reason=error.message))
                continue
            if os.path.lexists(path):
                regular = stat.S_ISREG(os.lstat(path).st_mode)
                rows.append(dict(row, status="unchanged" if regular else "refused",
                                 **({} if regular else {"reason": "not a regular file (a symlink?)"})))
                continue
            if not dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    handle = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
                except FileExistsError:
                    rows.append(dict(row, status="unchanged"))
                    continue
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    stream.write(template(target, slot))
            rows.append(dict(row, status="created"))
    return rows
