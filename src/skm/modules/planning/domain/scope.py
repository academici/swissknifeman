"""Path scope of a phase or an item and its document form (planning §4.2).

Phases and items both carry a ``Scope``; it lives apart from either record so that ``item`` can use the
phase ``Strategy`` while ``phase`` reuses the scope codec, without an import cycle between the two.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from skm.modules.planning.domain.reads import strs_of

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.json_types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class Scope:
    include: tuple[str, ...]
    exclude: tuple[str, ...]


def scope_from_doc(doc: Mapping[str, JsonValue]) -> Scope:
    return Scope(strs_of(doc, "include"), strs_of(doc, "exclude"))


def scope_to_doc(scope: Scope) -> JsonObject:
    return {"include": list(scope.include), "exclude": list(scope.exclude)}
