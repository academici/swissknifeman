"""A route of a role as the run names it: its label in progress lines and the actor it claims work with."""
from __future__ import annotations


def label(route: dict) -> str:
    return "/".join(part for part in (route.get("provider"), route.get("model"), route.get("effort")) if part)


def actor(role_route: dict) -> dict:
    return {key: role_route[key] for key in ("provider", "model", "effort") if role_route.get(key)}
