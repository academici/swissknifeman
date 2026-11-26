"""Shared pieces of the API tests: a backend state over a temporary SKM_HOME and the query-demo unit, and a client.

The locked third-party packages must be installed (scripts/test.sh runs `gui deps ensure`); a missing install is a
test error, never a skip.
"""
import os
import shutil
import tempfile
from pathlib import Path

from gui import deps

deps.activate()

from starlette.testclient import TestClient  # noqa: E402

from gui.backend import BackendState, Sessions  # noqa: E402
from gui.catalog import sources  # noqa: E402
from gui.http.app import create_app  # noqa: E402
from gui.settings import load  # noqa: E402
from gui.storage import db  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "units"
PORT = 8765
SECRET_VALUE = "s3cr3t-value-of-the-test-0123456789"


class Backend:
    """A backend state and a factory of clients; ``close`` removes everything."""

    def __init__(self, units: str = "query-demo", env_extra=None):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.env = {"HOME": str(self.tmp / "home"), "SKM_HOME": str(self.tmp / "skm"), "PATH": os.environ["PATH"],
                    "SKM_UNITS_PATH": os.pathsep.join(str(FIXTURES / name) for name in units.split(",")),
                    "SKM_TEST_SECRET": SECRET_VALUE,
                    "AICORE_ROOT": os.environ.get("AICORE_ROOT", "")}
        self.env.update(env_extra or {})
        (self.tmp / "home").mkdir()
        self.frontend = self.tmp / "dist"
        self.conn = db.open_db(self.tmp / "skm" / "state" / "gui" / "gui.db")
        settings = load(self.env)
        self.state = BackendState(settings=settings, conn=self.conn, env=self.env, port=PORT,
                                  sessions=Sessions(), frontend_dir=self.frontend,
                                  state_folder=self.tmp / "skm" / "state" / "gui",
                                  collect=lambda: sources.collect(None, self.env))
        self.app = create_app(self.state)

    def client(self, *, host=f"127.0.0.1:{PORT}", bearer=True, **kwargs) -> TestClient:
        client = TestClient(self.app, base_url=f"http://{host}", raise_server_exceptions=True, **kwargs)
        if bearer:
            client.headers["Authorization"] = f"Bearer {self.state.sessions.secret}"
        return client

    def browser(self) -> TestClient:
        """A client signed in by the token exchange (cookie), sending the Origin of the backend."""
        client = self.client(bearer=False, follow_redirects=False)
        response = client.get(f"/?t={self.state.sessions.new_token()}")
        assert response.status_code == 303, response.status_code
        client.headers["Origin"] = f"http://127.0.0.1:{PORT}"
        return client

    def project(self, name="proj"):
        root = self.tmp / name
        (root / ".git").mkdir(parents=True)
        (root / "src").mkdir()
        return self.state.registry.add(root, source="open")

    def build_frontend(self):
        (self.frontend / "assets").mkdir(parents=True)
        (self.frontend / "index.html").write_text("<!doctype html><title>SKM GUI</title>", encoding="utf-8")
        (self.frontend / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")

    def close(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
