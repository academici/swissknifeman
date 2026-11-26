"""Serve the generated OpenAPI document from package resources."""

from functools import cache
from importlib.resources import files

from starlette.requests import Request
from starlette.responses import Response

__all__ = ["endpoint"]


@cache
def _document() -> bytes:
    return files("skm.entrypoints.api").joinpath("openapi.json").read_bytes()


async def endpoint(request: Request) -> Response:
    del request
    return Response(_document(), media_type="application/json")
