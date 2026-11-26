"""JSON value types used by payloads, details and documents (kernel-platform §2.1)."""

__all__ = ["JsonObject", "JsonScalar", "JsonValue"]

type JsonScalar = bool | int | float | str | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
