"""Read Composer package declarations from a checkout."""

from pathlib import Path

from skm.kernel.json_types import JsonObject

from .package_json import json_dependencies

__all__ = ["ComposerJsonReader"]


class ComposerJsonReader:
    def dependencies(self, root: Path) -> tuple[JsonObject, ...]:
        return json_dependencies(root, "composer.json", "composer", ("require", "require-dev"))
