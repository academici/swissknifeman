"""Endpoints of the local API: bootstrap, catalog, schemas, projects with confirmation, queries, static files."""
import json
import os
import unittest

from tests.http_support import PORT, Backend

from gui import contracts
from gui.http import confirm


def code(response):
    body = response.json()
    assert contracts.validate(body, "api-error") == [], body
    return body["error"]["code"]


class ApiCase(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.addCleanup(self.backend.close)
        self.client = self.backend.client()


class TestCore(ApiCase):
    def test_bootstrap_is_valid_and_names_the_units(self):
        response = self.client.get("/v1/bootstrap")
        body = response.json()
        self.assertEqual([], contracts.validate(body, "bootstrap"))
        self.assertEqual(("browser", self.backend.state.epoch), (body["mode"], body["epoch"]))
        self.assertEqual([{"id": "qdemo", "version": "0.2.0"}], body["units"])
        self.assertIn({"id": "urn:swissknifeman:gui:project", "version": "v1"}, body["contracts"])
        self.assertEqual(["queries", "projects", "runs", "events", "config"], body["features"])

    def test_contributions_and_refresh(self):
        catalog = self.client.get("/v1/ui/contributions").json()
        self.assertEqual([], contracts.validate(catalog, "catalog"))
        self.assertEqual(["qdemo"], [entry["owner"] for entry in catalog["contributions"]])
        self.backend.env["SKM_UNITS_PATH"] = str(self.backend.tmp / "none")
        (self.backend.tmp / "none").mkdir()
        self.assertEqual(catalog, self.client.get("/v1/ui/contributions").json())
        refreshed = self.client.get("/v1/ui/contributions?refresh=1").json()
        self.assertEqual([], refreshed["contributions"])

    def test_schemas_only_from_the_allowlist(self):
        response = self.client.get("/v1/schemas/project/v1")
        self.assertEqual("urn:swissknifeman:gui:project:v1", response.json()["$id"])
        for path in ("/v1/schemas/project/v2", "/v1/schemas/nope/v1", "/v1/schemas/..%2F..%2Funit/v1",
                     "/v1/schemas/project/..%2Fv1"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual((404, "NOT_FOUND"), (response.status_code, code(response)))

    def test_unknown_endpoint_and_method(self):
        self.assertEqual("NOT_FOUND", code(self.client.get("/v1/nothing")))
        self.assertEqual("NOT_FOUND", code(self.client.get("/v1/queries/qdemo.items")))
        self.assertEqual("NOT_FOUND", code(self.client.post("/elsewhere", json={})))


class TestProjects(ApiCase):
    def folder(self, name="proj"):
        root = self.backend.tmp / name
        (root / ".git").mkdir(parents=True)
        return root

    def test_bearer_adds_at_once_and_lists(self):
        root = self.folder()
        response = self.client.post("/v1/projects", json={"path": str(root)})
        self.assertEqual(201, response.status_code)
        project = response.json()
        self.assertEqual([], contracts.validate(project, "project"))
        self.assertEqual(("open", str(root)), (project["source"], project["root"]))
        listing = self.client.get("/v1/projects").json()
        self.assertEqual([], contracts.validate(listing, "project"))
        self.assertEqual([project["id"]], [entry["id"] for entry in listing["projects"]])
        self.assertEqual(project, self.client.get(f"/v1/projects/{project['id']}").json())
        self.assertEqual("NOT_FOUND", code(self.client.get("/v1/projects/nope-00000000")))

    def test_cookie_add_needs_a_confirmation_bound_to_the_path(self):
        root, other = self.folder(), self.folder("other")
        browser = self.backend.browser()
        first = browser.post("/v1/projects", json={"path": str(root)})
        self.assertEqual((428, "CONFIRMATION_REQUIRED"), (first.status_code, code(first)))
        details = first.json()["error"]["details"]
        self.assertIn(str(root), details["summary"])
        self.assertEqual([], self.backend.state.registry.list())
        wrong = browser.post("/v1/projects", json={"path": str(other), "confirm": details["confirm"]})
        self.assertEqual("CONFIRMATION_REQUIRED", code(wrong))
        done = browser.post("/v1/projects", json={"path": str(root), "confirm": details["confirm"]})
        self.assertEqual(201, done.status_code)
        self.assertEqual("user", done.json()["source"])

    def test_confirm_is_bound_to_the_epoch(self):
        state = self.backend.state
        token = confirm.token(state.sessions.secret, state.epoch, "project.add", {"path": "/x"})
        self.assertNotEqual(token, confirm.token(state.sessions.secret, "other-epoch", "project.add", {"path": "/x"}))

    def test_invalid_bodies(self):
        for body in ({"path": "relative"}, {}, {"path": str(self.folder()), "extra": 1}, {"path": 3}):
            with self.subTest(body=body):
                self.assertEqual("INPUT_INVALID", code(self.client.post("/v1/projects", json=body)))
        response = self.client.post("/v1/projects", content=b"{not json", headers={"Content-Type": "application/json"})
        self.assertEqual("INPUT_INVALID", code(response))
        missing = self.client.post("/v1/projects", json={"path": str(self.backend.tmp / "absent")})
        self.assertEqual("NOT_FOUND", code(missing))


class TestQueries(ApiCase):
    def setUp(self):
        super().setUp()
        self.marks = self.backend.tmp / "marks.jsonl"
        self.backend.env["QDEMO_MARKS"] = str(self.marks)
        self.project = self.backend.project()

    def query(self, query_id, **body):
        return self.client.post(f"/v1/queries/{query_id}", json=body)

    def test_ok_with_params_defaults_and_project_root(self):
        (self.backend.tmp / "proj" / "src" / "sub").mkdir()
        response = self.query("qdemo.items", context={"project_id": self.project.id},
                              params={"filter": "abc", "folder": "src/sub/../sub"})
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual([], contracts.validate(response.json(), "view-data"))
        mark = json.loads(self.marks.read_text().splitlines()[-1])
        self.assertEqual({"filter": "abc", "folder": os.path.join("src", "sub"), "limit": 10}, mark["input"]["params"])
        self.assertEqual({"project_id": self.project.id}, mark["input"]["context"])
        self.assertEqual(self.project.root, mark["project_root"])

    def test_invalid_input(self):
        cases = [({"context": {"project_id": self.project.id}, "params": {"filter": "ABC"}}, "/params/filter"),
                 ({"context": {"project_id": self.project.id}, "params": {"limit": 0}}, "/params/limit"),
                 ({"context": {"project_id": self.project.id}, "params": {"nope": 1}}, "/params/nope"),
                 ({"context": {"project_id": self.project.id}, "params": {"folder": "../.."}}, "/params/folder"),
                 ({"context": {}}, "/context/project_id"),
                 ({"context": {"project_id": self.project.id, "plan_id": "bad"}}, "/context/plan_id"),
                 ({"context": {"project_id": self.project.id, "other": 1}}, "/context/other")]
        for body, pointer in cases:
            with self.subTest(body=body):
                response = self.query("qdemo.items", **body)
                self.assertEqual("INPUT_INVALID", code(response))
                self.assertIn(pointer, [issue["pointer"] for issue in response.json()["error"]["issues"]])
        self.assertEqual("INPUT_INVALID", code(self.client.post("/v1/queries/qdemo.items", json={"argv": ["sh"]})))

    def test_unknown_query_and_project(self):
        self.assertEqual("NOT_FOUND", code(self.query("qdemo.nope")))
        self.assertEqual("NOT_FOUND", code(self.query("qdemo.items", context={"project_id": "gone-00000000"})))

    def test_handler_results(self):
        for query_id, status, expected in (("qdemo.wrong-view", 502, "OUTPUT_INVALID"),
                                           ("qdemo.broken", 502, "OUTPUT_INVALID"),
                                           ("qdemo.fails", 502, "HANDLER_FAILED"),
                                           ("qdemo.slow", 504, "HANDLER_TIMEOUT")):
            with self.subTest(query=query_id):
                response = self.query(query_id)
                self.assertEqual((status, expected), (response.status_code, code(response)))
        failed = self.query("qdemo.fails").json()["error"]
        self.assertEqual({"plugin_code": "QDEMO_BROKEN"}, failed["details"])
        self.assertTrue(failed["retryable"])

    def test_output_size_limit(self):
        import dataclasses

        state = self.backend.state
        state.settings = dataclasses.replace(state.settings, query=dataclasses.replace(state.settings.query,
                                                                                         max_output_bytes=50))
        self.assertEqual("OUTPUT_INVALID", code(self.query("qdemo.metrics")))

    def test_cache_reuses_an_answer(self):
        first = self.query("qdemo.metrics")
        second = self.query("qdemo.metrics")
        self.assertEqual(first.json(), second.json())
        self.assertEqual(1, len(self.marks.read_text().splitlines()))
        self.query("qdemo.items", context={"project_id": self.project.id})
        self.query("qdemo.items", context={"project_id": self.project.id})
        self.assertEqual(3, len(self.marks.read_text().splitlines()))

    def test_moved_project_root_is_not_found(self):
        os.rename(self.project.root, self.project.root + "-moved")
        self.assertEqual("NOT_FOUND", code(self.query("qdemo.items", context={"project_id": self.project.id})))


class TestStatic(ApiCase):
    def test_not_built(self):
        response = self.client.get("/")
        self.assertEqual((503, "FRONTEND_NOT_BUILT"), (response.status_code, code(response)))
        page = self.client.get("/", headers={"Accept": "text/html"})
        self.assertEqual(503, page.status_code)
        self.assertIn("npm --prefix packages/gui/frontend", page.text)

    def test_files_and_spa_fallback(self):
        self.backend.build_frontend()
        (self.backend.tmp / "outside.txt").write_text("secret file")
        os.symlink(self.backend.tmp / "outside.txt", self.backend.frontend / "assets" / "link.txt")
        self.assertEqual("console.log(1)", self.client.get("/assets/app.js").text)
        for path in ("/", "/x/qdemo/items", "/assets/missing.js", "/assets/link.txt", "/../outside.txt",
                     "/assets/..%2F..%2Foutside.txt"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(200, response.status_code)
                self.assertIn("<title>SKM GUI</title>", response.text)
        self.assertIn("default-src 'self'", self.client.get("/").headers["content-security-policy"])

    def test_static_needs_authentication(self):
        self.backend.build_frontend()
        response = self.backend.client(bearer=False).get("/assets/app.js")
        self.assertEqual(401, response.status_code)


if __name__ == "__main__":
    unittest.main()
