"""Settings sections of the integrations module: typed views and section validators (settings spec §B.8.3).

``VALIDATORS`` holds the validators that need nothing from outside. ``integrations.hook_subscriptions`` must
know the hookable event types and event sink ids of the running installation, so it is built per registry with
``validators_for``; no permissive default exists.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import cast

from skm.kernel.json_types import JsonValue
from skm.platform.config.registry import SectionValidatorFn

from .application.subscribers import HookSubscriptionsValidator
from .generated.settings import HooksSettings, IntegrationsSettings

__all__ = [
    "SECTION_URN",
    "SECTION_URNS",
    "VALIDATORS",
    "VIEWS",
    "HooksSettings",
    "IntegrationsSettings",
    "hook_subscriptions_validator",
    "validators_for",
]

SECTION_URN = "urn:skm:settings:integrations:v1"
SECTION_URNS = ("urn:skm:settings:integrations:v1", "urn:skm:settings:hooks:v1")


def _budget_order(values: Mapping[str, JsonValue]) -> str | None:
    """target <= warn."""
    target = values["integrations.budget.first_turn.target"]
    warn = values["integrations.budget.first_turn.warn"]
    if target is None or warn is None:
        return None
    if cast("int", target) > cast("int", warn):
        return "integrations.budget.first_turn.target must not exceed integrations.budget.first_turn.warn"
    return None


def hook_subscriptions_validator(
    *, hookable_types: Iterable[str], sink_ids: Iterable[str]
) -> SectionValidatorFn:
    """The ``integrations.hook_subscriptions`` callback bound to immutable copies of the known sets."""
    return HookSubscriptionsValidator(frozenset(hookable_types), frozenset(sink_ids))


def validators_for(
    *, hookable_types: Iterable[str], sink_ids: Iterable[str]
) -> Mapping[str, SectionValidatorFn]:
    """All validators of the module for one registry build."""
    return {
        **VALIDATORS,
        "integrations.hook_subscriptions": hook_subscriptions_validator(
            hookable_types=hookable_types, sink_ids=sink_ids
        ),
    }


VIEWS: Mapping[str, type] = {"integrations": IntegrationsSettings, "hooks": HooksSettings}
VALIDATORS: Mapping[str, SectionValidatorFn] = {"integrations.budget_order": _budget_order}
