"""Project preset definitions shared by projection planning and hook policy."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal, cast, get_args

from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.yaml_scalars import parse_quoted_yaml_string

from .hook_events import HookClass, HookEventKind
from .hook_subscriptions import parse_subscriptions, subscription_json
from .target import TargetId

__all__ = [
    "PACKAGE_NAME",
    "PRESETS",
    "PRESET_BUNDLES",
    "PRESET_SUBSCRIPTIONS",
    "PRESET_SUBSCRIPTION_DIGESTS",
    "Preset",
    "dart_package_fallback",
    "dart_package_name",
    "php_package_slug",
    "preset_instruction_block",
    "preset_of_renderer",
    "preset_renderer",
    "preset_subscription_config",
    "preset_subscriptions",
    "read_preset",
]

type Preset = Literal["php-project", "php-package", "dart-project", "dart-package"]
PRESETS: tuple[Preset, ...] = get_args(Preset.__value__)
PACKAGE_NAME = re.compile(r"[a-z][a-z0-9_]*")
PRESET_BUNDLES: dict[Preset, tuple[str, str, frozenset[str] | None]] = {
    "php-project": (
        "agent-packs-backend-laravel",
        "agent-pack-backend-laravel",
        frozenset({".claude/rules/eloquent.md"}),
    ),
    "php-package": ("agent-packs-laravel-package", "skm-preset-php-package", None),
    "dart-project": (
        "agent-packs-dart-flutter",
        "agent-pack-dart-flutter",
        frozenset({".claude/rules/flutter-ui.md"}),
    ),
    "dart-package": ("agent-packs-dart-package", "skm-preset-dart-package", None),
}
_PRESET_GUIDANCE: dict[Preset, str] = {
    "php-project": "Follow the repository's Laravel conventions and run the PHP checks before handing off.",
    "php-package": "Preserve the public API and keep the consumer guidance in resources/boost current.",
    "dart-project": "Follow the repository's Dart and Flutter conventions. Run Dart checks before handoff.",
    "dart-package": "Preserve the public API and keep the package usage skill and examples current.",
}
_RENDERER_SEPARATOR = "_preset_"
CLAUDE_SETTINGS = ".claude/settings.json"


@dataclass(frozen=True, slots=True)
class _Check:
    id: str
    argv: tuple[str, ...]
    extension: str | None = None

    @property
    def event(self) -> HookEventKind:
        return HookEventKind.POST_TOOL if self.extension else HookEventKind.STOP

    @property
    def hook_class(self) -> HookClass:
        return HookClass.WORKFLOW if self.extension else HookClass.ENFORCEMENT

    def config(self) -> JsonObject:
        return {
            "class": self.hook_class.value,
            "kind": "command",
            "execution_location": "host",
            "event_types": [f"client:{self.event.value}"],
            "target": {"argv": list(self.argv), "cwd": "checkout", "env_allow": ["PATH"]},
            "timeout_ms": 1500 if self.extension else 9000,
            "failure_policy": "warn" if self.extension else "deny",
        }


_DART_FORMAT = _Check("preset.dart.format", ("dart", "format", "."))
_CHECKS: dict[Preset, tuple[_Check, ...]] = {
    "php-project": (
        _Check("preset.php.lint", ("php", "-l"), ".php"),
        _Check("preset.php.pint", ("pint", "--dirty")),
        _Check("preset.php.phpstan", ("phpstan", "analyse")),
    ),
    "php-package": (),
    "dart-project": (_Check("preset.dart.analyze", ("dart", "analyze"), ".dart"), _DART_FORMAT),
    "dart-package": (_DART_FORMAT, _Check("preset.dart.skills-lint", ("dart", "run", "skills_lint"))),
}
PRESET_SUBSCRIPTIONS = {check.id: check for checks in _CHECKS.values() for check in checks}


def read_preset(value: object) -> Preset | None:
    return next((preset for preset in PRESETS if preset == value), None)


def preset_renderer(renderer: str, preset: Preset | None) -> str:
    if preset is None:
        return renderer
    name, separator, suffix = renderer.partition("@")
    target, dot, surface = name.partition(".")
    return target + _RENDERER_SEPARATOR + preset.replace("-", "_") + dot + surface + separator + suffix


def preset_of_renderer(renderer: str | None) -> Preset | None:
    name = (renderer or "").partition("@")[0].partition(".")[0]
    return read_preset(name.partition(_RENDERER_SEPARATOR)[2].replace("_", "-"))


def _preset_instructions(preset: Preset) -> str:
    return "\n".join(
        (
            f"# {preset.replace('-', ' ').title()}",
            "",
            _PRESET_GUIDANCE[preset],
            "",
            "Run manual workflows with /grill-me, /to-spec, /to-tickets, /implement, and /handoff.",
        )
    )


def preset_instruction_block(preset: Preset, project_slug: str) -> JsonObject:
    return {
        "enabled": True,
        "preset": preset,
        "content": _preset_instructions(preset),
        "zero_shadowing": True,
        "package_name": dart_package_fallback(project_slug)
        if preset == "dart-package"
        else project_slug.replace("-", "_"),
        "package_slug": project_slug,
    }


def preset_subscription_config(preset: Preset | None, target: TargetId) -> dict[str, JsonValue]:
    if preset is None or target is not TargetId.CLAUDE_CODE:
        return {}
    return {check.id: check.config() for check in _CHECKS[preset]}


def preset_subscriptions(preset: Preset | None, target: TargetId) -> tuple[JsonObject, ...]:
    subscriptions, violations = parse_subscriptions(preset_subscription_config(preset, target), {})
    if violations:
        raise ValueError("invalid built-in preset subscription")
    results: list[JsonObject] = []
    for sub in subscriptions:
        doc = subscription_json(sub)
        target_doc = doc["target"]
        if not isinstance(target_doc, dict):
            raise ValueError("invalid built-in preset command")
        results.append(
            {
                "id": sub.id,
                "digest": sub.digest,
                **target_doc,
                **{
                    key: doc[key] for key in ("class", "event_types", "timeout_ms", "retry", "failure_policy")
                },
            }
        )
    return tuple(results)


PRESET_SUBSCRIPTION_DIGESTS = {
    cast("str", sub["id"]): cast("str", sub["digest"])
    for preset in PRESETS
    for sub in preset_subscriptions(preset, TargetId.CLAUDE_CODE)
}


def dart_package_name(pubspec: str | None) -> str | None:
    for line in (pubspec or "").splitlines():
        key, separator, raw = line.partition(":")
        if separator and key.rstrip() in ("name", "'name'", '"name"'):
            raw = raw.strip()
            value = (
                parse_quoted_yaml_string(raw) if raw.startswith(("'", '"')) else raw.split("#", 1)[0].strip()
            )
            return value if value is not None and PACKAGE_NAME.fullmatch(value) else None
    return None


def dart_package_fallback(project_slug: str) -> str:
    name = project_slug.replace("-", "_")
    return name if PACKAGE_NAME.fullmatch(name) else f"package_{name}"


def php_package_slug(composer: str | None) -> str | None:
    try:
        document = json.loads(composer or "{}")
    except ValueError:
        return None
    name = cast("dict[str, object]", document).get("name") if isinstance(document, dict) else None
    if isinstance(name, str):
        slug = re.sub(r"[^a-z0-9]+", "-", name.rsplit("/", 1)[-1].lower()).strip("-")
        return slug or None
    return None
