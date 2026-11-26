"""Exercise URL validation and descriptor-relative traversal through the real HTTP boundary."""

from pathlib import Path

import pytest
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from security.api.harness import make_world
from skm.entrypoints.api import static


def test_editable_bundle_wheel_precedence_and_symlinks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    package = tmp_path / "src/skm"
    package.mkdir(parents=True)
    monkeypatch.setattr(static, "files", lambda _: package)
    editable = tmp_path / "web/dist"
    editable.mkdir(parents=True)
    (editable / "index.html").write_text("editable")
    bundled = package / "_web"

    def private(request: Request) -> Response:
        return Response("private")

    with make_world(tmp_path).client(routes=[Route("/custom", private)]) as client:
        assert client.get("/login").text == "editable"
        assert client.get("/custom").status_code == 401
        assert client.get("/login", headers={"Host": "example.invalid"}).status_code == 403
        assert client.post("/login").status_code != 200
        bundled.mkdir()
        (bundled / "index.html").write_text("wheel")
        assets = bundled / "assets"
        assets.mkdir()
        (assets / "style.css").write_text("body{}")
        assert client.get("/").text == "wheel"
        css = client.get("/assets/style.css")
        assert css.text == "body{}"
        assert css.headers["content-type"].startswith("text/css")
        (bundled / "outside").symlink_to(editable, target_is_directory=True)
        assert client.get("/outside/index.html").status_code == 404
        (assets / "link.js").symlink_to(editable / "index.html")
        (assets / "dir").symlink_to(editable, target_is_directory=True)
        for path in ("link.js", "dir/index.html", "%2e%2e/index.html", "style.css%00"):
            assert client.get("/assets/" + path).status_code == 404
        (bundled / "index.html").unlink()
        (bundled / "index.html").symlink_to(editable / "index.html")
        assert client.get("/").status_code == 404
