"""Smoke-тесты пакета core — общий фундамент монорепо (stdlib-only).

Запуск: PYTHONPATH=<корень монорепо> python3 -m unittest discover -s core/tests"""
import inspect
import json
import os
import sys
import tempfile
import threading
import unittest
from dataclasses import FrozenInstanceError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from core import (DEFAULT_DOCS_VISIBILITY, PROJECT_TYPES, BaseEnv,
                  atomic_write_json, atomic_write_text, backup_file,
                  content_hash, detect_project_type, docs_visibility_for,
                  find_monorepo_root, find_run_report, find_repo_root,
                  is_within, is_within_lexical, load_json_db, managed_block,
                  now_iso, parse_args, parse_flags, parse_iso, pid_alive,
                  read_ndjson, read_ndjson_iter, run_cmd,
                  safe_load_json, sanitize, sibling_bin, state_dir, upsert_block)
from core.http import HTTPUnauthorizedError, http_get_json, http_post_json, ping
from core.repo import resolve_plan_dir


class _EchoAuthHandler(BaseHTTPRequestHandler):
    """Сервер-двойник для http.py: отражает полученный заголовок Authorization и
    401'ит protected-путь без корректного bearer'а — как agentmemory 0.9.x."""

    def log_message(self, *a):
        pass

    def _reply(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        auth = self.headers.get("Authorization", "")
        if self.path == "/protected" and auth != "Bearer good-token":
            self._reply(401, {"error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        self._reply(200, {"path": self.path, "authorization": auth,
                          "body": body.decode("utf-8") if body else None})

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()


class _EchoAuthServer:
    def __init__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _EchoAuthHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self):
        _, port = self.httpd.server_address
        return f"http://127.0.0.1:{port}"

    def __enter__(self):
        self.thread.start()
        return self.url

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


class TestHttp(unittest.TestCase):
    def test_get_json_without_headers_unchanged(self):
        with _EchoAuthServer() as url:
            res = http_get_json(f"{url}/open")
            self.assertEqual(res["authorization"], "")

    def test_post_json_without_headers_unchanged(self):
        with _EchoAuthServer() as url:
            res = http_post_json(f"{url}/open", {"k": "v"})
            self.assertEqual(res["authorization"], "")
            self.assertIn('"k": "v"', res["body"])

    def test_ping_without_headers_unchanged(self):
        with _EchoAuthServer() as url:
            self.assertTrue(ping(f"{url}/open"))

    def test_headers_are_sent(self):
        with _EchoAuthServer() as url:
            res = http_get_json(f"{url}/open", headers={"Authorization": "Bearer good-token"})
            self.assertEqual(res["authorization"], "Bearer good-token")

    def test_401_raises_unauthorized_subclass_of_runtimeerror(self):
        with _EchoAuthServer() as url:
            with self.assertRaises(HTTPUnauthorizedError):
                http_get_json(f"{url}/protected")
            with self.assertRaises(RuntimeError):  # HTTPUnauthorizedError — подкласс
                http_get_json(f"{url}/protected")

    def test_401_with_correct_bearer_succeeds(self):
        with _EchoAuthServer() as url:
            res = http_get_json(f"{url}/protected", headers={"Authorization": "Bearer good-token"})
            self.assertEqual(res["authorization"], "Bearer good-token")

    def test_ping_returns_true_on_401_unchanged(self):
        # ping не различает 401 от прочих 4xx — byte-в-byte прежнее поведение (D6/анти-самообман:
        # различие даёт HTTPUnauthorizedError у http_get_json/http_post_json, не ping).
        with _EchoAuthServer() as url:
            self.assertTrue(ping(f"{url}/protected"))


class TestText(unittest.TestCase):
    def test_sanitize_slug(self):
        self.assertEqual(sanitize("Hello World_Foo"), "hello-world-foo")
        self.assertEqual(sanitize("  A--B  "), "a-b")
        self.assertEqual(sanitize("Ωmega!!"), "mega")


class TestEnv(unittest.TestCase):
    def test_base_env_normalizes_paths(self):
        env = BaseEnv("/tmp/x", "cmd", home="/tmp/h")
        self.assertEqual(str(env.root), "/tmp/x")
        self.assertEqual(str(env.home), "/tmp/h")
        self.assertEqual(env.cmd, "cmd")

    def test_base_env_home_reads_current_env(self):
        # default_factory зовёт Path.home() при создании (не модульный снимок) —
        # подменённый $HOME подхватывается (нужно для тестируемости).
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"HOME": tmp}):
                self.assertEqual(BaseEnv("/r").home, Path(tmp))

    def test_base_env_is_frozen(self):
        env = BaseEnv("/tmp/x")
        with self.assertRaises(FrozenInstanceError):
            env.root = "/other"  # frozen dataclass

    def test_subclass_keeps_frozen_and_core(self):
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class Sub(BaseEnv):
            @property
            def state(self):
                return self.home / ".thing"

        s = Sub("/tmp/x", home="/tmp/h")
        self.assertEqual(str(s.state), "/tmp/h/.thing")


class TestTerm(unittest.TestCase):
    def test_now_iso_format(self):
        # YYYY-MM-DDTHH:MM:SSZ
        self.assertRegex(now_iso(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TestAtomicIO(unittest.TestCase):
    def test_write_text_creates_parents(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a" / "b" / "f.txt"
            atomic_write_text(p, "привет")
            self.assertEqual(p.read_text(encoding="utf-8"), "привет")
            # tmp-файл не остаётся после успешной записи
            self.assertEqual(list(Path(tmp).rglob("*.tmp")), [])

    def test_write_text_cleans_tmp_on_failure(self):
        # Если replace падает (кросс-устройство/нет места), осиротевший .tmp не
        # должен оставаться на диске — иначе мусор копится в долгоживущих процессах.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            with mock.patch("core.io.os.replace", side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    atomic_write_text(p, "data")
            self.assertEqual(list(Path(tmp).rglob("*.tmp")), [])
            self.assertFalse(p.exists())

    def test_write_json_version_first_and_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "db.json"
            atomic_write_json(p, {"a": 1, "version": 9}, version=2)
            text = p.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            data = json.loads(text)
            self.assertEqual(data["version"], 2)            # version переписан
            self.assertEqual(list(data.keys())[0], "version")  # первым ключом
            self.assertEqual(data["a"], 1)

    def test_write_json_indent_param(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.json"
            atomic_write_json(p, {"k": "v"}, indent=4)
            self.assertIn('\n    "k"', p.read_text(encoding="utf-8"))

    def test_write_mode_0600(self):
        # mode= ставит права атомарно (на .tmp до replace) — для конфигов с секретами.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "secret.json"
            atomic_write_json(p, {"token": "x"}, mode=0o600)
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)


class TestLoadJsonDb(unittest.TestCase):
    DEFAULT = {"version": 1, "items": []}

    def test_missing_returns_deepcopy_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = load_json_db(Path(tmp) / "nope.json", self.DEFAULT)
            self.assertEqual(out, self.DEFAULT)
            out["items"].append("x")                      # не мутирует исходный default
            self.assertEqual(self.DEFAULT["items"], [])

    def test_corrupt_backs_up_and_returns_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "db.json"
            p.write_text("{ broken", encoding="utf-8")
            out = load_json_db(p, self.DEFAULT)
            self.assertEqual(out, self.DEFAULT)
            self.assertFalse(p.exists())                   # переименован в .corrupt.<date>
            self.assertTrue(list(Path(tmp).glob("db.json.corrupt.*")))

    def test_version_too_new_dies(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "db.json"
            p.write_text(json.dumps({"version": 99}), encoding="utf-8")
            with self.assertRaises(SystemExit):
                load_json_db(p, self.DEFAULT, max_version=1)

    def test_valid_passthrough(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "db.json"
            p.write_text(json.dumps({"version": 1, "items": [1]}), encoding="utf-8")
            self.assertEqual(load_json_db(p, self.DEFAULT, max_version=1)["items"], [1])


class TestPaths(unittest.TestCase):
    def test_is_within_true_for_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = root / "a" / "b"
            child.mkdir(parents=True)
            self.assertTrue(is_within(child, root))
            self.assertTrue(is_within(root, root))         # совпадение

    def test_is_within_false_for_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            self.assertFalse(is_within(root.parent / "other", root))

    def test_is_within_lexical_blocks_dotdot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dest"
            root.mkdir()
            # имя с '../' лексически вырывается за dest → False
            self.assertFalse(is_within_lexical(root / ".." / "evil", root))
            self.assertTrue(is_within_lexical(root / "skill", root))

    def test_state_dir_umbrella_root(self):
        home = Path("/home/u")
        self.assertEqual(state_dir(home), home / ".swissknifeman")

    def test_state_dir_app_subdir(self):
        home = Path("/home/u")
        self.assertEqual(state_dir(home, "analyst"), home / ".swissknifeman" / "analyst")

    def test_state_dir_accepts_str_home(self):
        self.assertEqual(state_dir("/home/u", "analyst"),
                         Path("/home/u") / ".swissknifeman" / "analyst")


class TestRepoRoot(unittest.TestCase):
    def test_find_repo_root_walks_up_to_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            deep = root / "packages" / "x" / "lib"
            deep.mkdir(parents=True)
            self.assertEqual(find_repo_root(deep), root)

    def test_find_repo_root_none_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(find_repo_root(Path(tmp)))

    def test_find_monorepo_root_by_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "core").mkdir()
            (root / "packages").mkdir()
            deep = root / "packages" / "maind"
            deep.mkdir()
            self.assertEqual(find_monorepo_root(deep), root)

    def test_find_monorepo_root_none_standalone(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(find_monorepo_root(Path(tmp) / "lonely"))


class TestResolvePlanDir(unittest.TestCase):
    def test_live_plan_wins_over_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plans" / "2026.01.01-X").mkdir(parents=True)
            self.assertEqual(resolve_plan_dir(root, "2026.01.01-X"),
                             root / "plans" / "2026.01.01-X")

    def test_archived_plan_resolves_when_live_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plans" / "archive" / "2026.01.01-X").mkdir(parents=True)
            self.assertEqual(resolve_plan_dir(root, "2026.01.01-X"),
                             root / "plans" / "archive" / "2026.01.01-X")

    def test_missing_from_both_raises_with_both_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FileNotFoundError) as ctx:
                resolve_plan_dir(root, "2026.01.01-X")
            message = str(ctx.exception)
            self.assertIn(str(root / "plans" / "2026.01.01-X"), message)
            self.assertIn(str(root / "plans" / "archive" / "2026.01.01-X"), message)


class TestSiblingBin(unittest.TestCase):
    def test_env_override_wins_when_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "custom-maind"
            f.write_text("#!/bin/sh\n")
            with mock.patch.dict(os.environ, {"MAIND_BIN": str(f)}):
                self.assertEqual(sibling_bin("maind", env_var="MAIND_BIN"), f)

    def test_env_override_missing_returns_none(self):
        with mock.patch.dict(os.environ, {"MAIND_BIN": "/nope/maind"}):
            self.assertIsNone(sibling_bin("maind", env_var="MAIND_BIN",
                                          use_path=False))

    def test_monorepo_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binp = root / "packages" / "harness" / "bin" / "harness"
            binp.parent.mkdir(parents=True)
            binp.write_text("#!/bin/sh\n")
            with mock.patch.dict(os.environ, {}, clear=True):
                got = sibling_bin("harness", env_var="SKM_HARNESS_BIN",
                                  use_path=False, monorepo_root=root)
            self.assertEqual(got, binp)

    def test_none_when_nothing_found(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(sibling_bin("nonexistent-pkg", use_path=False,
                                          monorepo_root=None))


class TestBackupFile(unittest.TestCase):
    def test_backup_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "settings.json"
            f.write_text('{"a":1}')
            bak = backup_file(f)
            self.assertEqual(bak, f.with_name("settings.json.bak"))
            self.assertEqual(bak.read_text(), '{"a":1}')

    def test_absent_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(backup_file(Path(tmp) / "missing.json"))

    def test_custom_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "x.conf"
            f.write_text("z")
            self.assertEqual(backup_file(f, suffix=".orig").name, "x.conf.orig")


class TestManagedBlock(unittest.TestCase):
    def test_insert_when_absent(self):
        text, changed, state = upsert_block("hello\n", "body", "MARK")
        self.assertTrue(changed)
        self.assertEqual(state, "absent")
        self.assertIn("<!-- MARK", text)
        self.assertIn("<!-- /MARK -->", text)
        self.assertIn("body", text)

    def test_idempotent_fresh(self):
        t1, _, _ = upsert_block("", "body", "MARK")
        t2, changed, state = upsert_block(t1, "body", "MARK")
        self.assertFalse(changed)
        self.assertEqual(state, "fresh")
        self.assertEqual(t1, t2)

    def test_update_stale(self):
        t1, _, _ = upsert_block("", "old", "MARK")
        t2, changed, state = upsert_block(t1, "new", "MARK")
        self.assertTrue(changed)
        self.assertEqual(state, "stale")
        self.assertIn("new", t2)
        self.assertNotIn("old", t2)

    def test_hash_stable(self):
        self.assertEqual(content_hash("abc"), content_hash("abc"))
        self.assertNotEqual(content_hash("abc"), content_hash("abd"))

    def test_owner_in_header(self):
        self.assertIn("managed by skiller", managed_block("x", "M", owner="skiller"))
        self.assertIn("managed by maind", managed_block("x", "M"))


class TestParseFlags(unittest.TestCase):
    def test_bool_and_str_flags(self):
        out = parse_flags(["--name", "x", "--force"],
                          {"--name": "str", "--force": "bool"})
        self.assertEqual(out["name"], "x")
        self.assertIs(out["force"], True)
        self.assertIs(out["help"], False)

    def test_defaults_when_absent(self):
        out = parse_flags([], {"--name": "str", "--force": "bool"})
        self.assertEqual(out["name"], "")
        self.assertIs(out["force"], False)

    def test_dash_to_underscore_key(self):
        out = parse_flags(["--dry-run"], {"--dry-run": "bool"})
        self.assertIs(out["dry_run"], True)

    def test_help_flag(self):
        self.assertIs(parse_flags(["-h"], {})["help"], True)

    def test_unknown_flag_dies(self):
        with self.assertRaises(SystemExit):
            parse_flags(["--nope"], {})

    def test_missing_value_dies(self):
        with self.assertRaises(SystemExit):
            parse_flags(["--name"], {"--name": "str"})


class TestParseArgs(unittest.TestCase):
    def test_positionals_collected(self):
        opts, pos = parse_args(["a", "--force", "b"],
                               {"--force": "bool"}, max_pos=2)
        self.assertEqual(pos, ["a", "b"])
        self.assertIs(opts["force"], True)

    def test_too_many_positionals_dies(self):
        with self.assertRaises(SystemExit):
            parse_args(["a", "b"], {}, max_pos=1)

    def test_unknown_flag_dies(self):
        with self.assertRaises(SystemExit):
            parse_args(["--x"], {}, max_pos=0)


class TestRunCmd(unittest.TestCase):
    def test_success_capture(self):
        r = run_cmd([sys.executable, "-c", "print('hi')"], capture=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "hi")

    def test_nonzero_with_check_dies(self):
        with self.assertRaises(SystemExit):
            run_cmd([sys.executable, "-c", "import sys; sys.exit(3)"])

    def test_nonzero_without_check_returns(self):
        r = run_cmd([sys.executable, "-c", "import sys; sys.exit(3)"],
                    check=False)
        self.assertEqual(r.returncode, 3)

    def test_missing_binary_dies(self):
        with self.assertRaises(SystemExit):
            run_cmd(["definitely-no-such-binary-xyz"])


class TestSafeLoadJson(unittest.TestCase):
    def test_loads_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.json"
            p.write_text('{"k": 1}', encoding="utf-8")
            self.assertEqual(safe_load_json(p), {"k": 1})

    def test_missing_returns_default(self):
        self.assertEqual(safe_load_json("/no/such/file.json", default={}), {})

    def test_corrupt_returns_default_and_calls_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text("{not json", encoding="utf-8")
            seen = []
            out = safe_load_json(p, default=[], on_error=seen.append)
            self.assertEqual(out, [])
            self.assertEqual(len(seen), 1)


class TestProjectDetect(unittest.TestCase):
    def _mk(self, tmp, files=(), dirs=()):
        root = Path(tmp)
        for d in dirs:
            (root / d).mkdir(parents=True, exist_ok=True)
        for name, content in files:
            (root / name).write_text(content, encoding="utf-8")
        return root

    def test_taxonomy_ids_unique_and_complete(self):
        self.assertEqual(len(PROJECT_TYPES), len(set(PROJECT_TYPES)))
        self.assertIn("standalone", PROJECT_TYPES)

    def test_obsidian_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, files=[("composer.json", "{}")], dirs=[".obsidian"])
            self.assertEqual(detect_project_type(root), "obsidian-vault")

    def test_laravel_vs_php_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, files=[("composer.json", "{}"), ("artisan", "")])
            self.assertEqual(detect_project_type(root), "laravel-project")
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, files=[("composer.json", "{}")])
            self.assertEqual(detect_project_type(root), "php-package")

    def test_dart_flutter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, files=[("pubspec.yaml", "name: x")])
            self.assertEqual(detect_project_type(root), "dart-flutter")

    def test_python_before_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, files=[("pyproject.toml", ""), ("package.json", "{}")])
            self.assertEqual(detect_project_type(root), "python-backend")

    def test_node_frontend_vs_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, files=[
                ("package.json", '{"dependencies": {"vue": "^3"}}')])
            self.assertEqual(detect_project_type(root), "node-frontend")
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, files=[("package.json", '{"name": "lib"}')])
            self.assertEqual(detect_project_type(root), "node-package")
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, files=[("package.json", "{}"), ("vite.config.ts", "")])
            self.assertEqual(detect_project_type(root), "node-frontend")

    def test_blender_by_blend_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, files=[("scene.blend", "")])
            self.assertEqual(detect_project_type(root), "blender")

    def test_blender_by_bpy_import_beats_python(self):
        # addon с requirements.txt: import bpy → blender, не python-backend
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, files=[("addon.py", "import bpy\n"),
                                        ("requirements.txt", "")])
            self.assertEqual(detect_project_type(root), "blender")

    def test_blender_by_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, files=[("blender_manifest.toml", "")])
            self.assertEqual(detect_project_type(root), "blender")

    def test_standalone_default_never_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(detect_project_type(tmp), "standalone")

    def test_corrupt_package_json_degrades(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._mk(tmp, files=[("package.json", "{not json")])
            self.assertEqual(detect_project_type(root), "node-package")


class TestDocsVisibility(unittest.TestCase):
    def test_packages_public(self):
        for t in ("php-package", "node-package", "dart-flutter"):
            self.assertEqual(docs_visibility_for(t), "public", t)

    def test_products_private(self):
        for t in ("laravel-project", "node-frontend", "python-backend",
                  "blender", "obsidian-vault", "standalone"):
            self.assertEqual(docs_visibility_for(t), "private", t)

    def test_unknown_falls_back_to_default_private(self):
        self.assertEqual(docs_visibility_for("nope"), DEFAULT_DOCS_VISIBILITY)
        self.assertEqual(DEFAULT_DOCS_VISIBILITY, "private")

    def test_every_project_type_has_default(self):
        # каждый известный тип имеет явную видимость (не упадёт на дефолт молча)
        from core import DOCS_VISIBILITY_BY_TYPE
        for t in PROJECT_TYPES:
            self.assertIn(t, DOCS_VISIBILITY_BY_TYPE, t)


class TestParseIso(unittest.TestCase):
    def test_z_suffix(self):
        dt = parse_iso("2026-07-01T12:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.utcoffset().total_seconds(), 0)

    def test_offset(self):
        self.assertIsNotNone(parse_iso("2026-07-01T12:00:00+03:00"))

    def test_fractional_various_digit_counts(self):
        # py39 fromisoformat не принимал 2/4/7 знаков дробной части — нормализуем
        for s in ("2026-07-01T12:00:00.1Z", "2026-07-01T12:00:00.12Z",
                  "2026-07-01T12:00:00.1234Z", "2026-07-01T12:00:00.1234567Z",
                  "2026-07-01T12:00:00.123456Z"):
            self.assertIsNotNone(parse_iso(s), s)

    def test_naive_treated_as_utc(self):
        dt = parse_iso("2026-07-01T12:00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.utcoffset().total_seconds(), 0)

    def test_now_iso_roundtrip(self):
        self.assertIsNotNone(parse_iso(now_iso()))

    def test_bad_input(self):
        for s in (None, "", "not-a-date", 123, "2026-13-99"):
            self.assertIsNone(parse_iso(s), repr(s))

    def test_chronological_order_with_fractions(self):
        a = parse_iso("2026-07-01T12:00:00.1Z")
        b = parse_iso("2026-07-01T12:00:00.9Z")
        self.assertLess(a, b)


class TestPidAlive(unittest.TestCase):
    def test_current_process_alive(self):
        self.assertTrue(pid_alive(os.getpid()))

    def test_none_unknown(self):
        self.assertIsNone(pid_alive(None))
        self.assertIsNone(pid_alive(0))

    def test_huge_pid_no_crash(self):
        # OverflowError на огромном pid не должен ронять вызывающего
        self.assertTrue(pid_alive(10 ** 12))

    def test_dead_pid(self):
        # почти наверняка несуществующий pid
        self.assertFalse(pid_alive(2 ** 22 - 1))


class TestReadNdjson(unittest.TestCase):
    def test_skips_blank_and_broken_and_nondict(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.ndjson"
            p.write_text('{"a":1}\n\n  \nне-json\n[1,2]\n{"b":2}\n',
                         encoding="utf-8")
            self.assertEqual(read_ndjson(p), [{"a": 1}, {"b": 2}])

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(read_ndjson(Path(d) / "nope.ndjson"), [])

    def test_iter_skips_blank_and_broken_and_nondict(self):
        # проверка ФИЛЬТРАЦИИ независимо от read_ndjson — против hardcoded-ожидания,
        # не против read_ndjson(p) (тот сам определён как list(read_ndjson_iter(p)),
        # сравнение с самим собой ничего бы не поймало при сломанном фильтре)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.ndjson"
            p.write_text('{"a":1}\n\n  \nне-json\n[1,2]\n{"b":2}\n',
                         encoding="utf-8")
            self.assertEqual(list(read_ndjson_iter(p)), [{"a": 1}, {"b": 2}])

    def test_iter_missing_file_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(list(read_ndjson_iter(Path(d) / "nope.ndjson")), [])

    def test_iter_is_lazy_generator(self):
        # генератор-специфичное поведение: объект и потребление по одной записи,
        # не список — ради этого read_ndjson_iter и был выделен (streaming-потребители)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.ndjson"
            p.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
            gen = read_ndjson_iter(p)
            self.assertTrue(inspect.isgenerator(gen))
            self.assertEqual(next(gen), {"a": 1})
            self.assertEqual(next(gen), {"b": 2})
            self.assertRaises(StopIteration, next, gen)

    def test_read_ndjson_is_list_of_iter(self):
        # read_ndjson — тонкая обёртка над read_ndjson_iter, не отдельная копия логики
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.ndjson"
            p.write_text('{"a":1}\n\n  \nне-json\n[1,2]\n{"b":2}\n',
                         encoding="utf-8")
            self.assertEqual(read_ndjson(p), list(read_ndjson_iter(p)))


class TestFindRunReport(unittest.TestCase):
    def _make(self, root, sid, payload):
        runs = Path(root) / ".claude" / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        (runs / f"{sid}.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_by_session(self):
        with tempfile.TemporaryDirectory() as d:
            self._make(d, "s1", {"session_id": "s1"})
            self.assertEqual(find_run_report(d, "s1")["session_id"], "s1")

    def test_latest(self):
        with tempfile.TemporaryDirectory() as d:
            self._make(d, "s1", {"session_id": "s1"})
            self.assertIsNotNone(find_run_report(d))

    def test_no_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(find_run_report(d))

    def test_foreign_absolute_changed_file_rejects_report_even_when_cwd_claims_project(self):
        from core.runs import find_run_report_result
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / ".claude" / "runs"
            runs.mkdir(parents=True)
            (runs / "s1.json").write_text(json.dumps({
                "session_id": "s1", "cwd": str(root),
                "files_changed": ["/tmp/another-project/app.py"],
            }), encoding="utf-8")
            result = find_run_report_result(root, "s1")
            self.assertIsNone(result.report)
            self.assertEqual(result.diagnostic["code"], "RUN_REPORT_PROJECT_MISMATCH")

    def test_session_provider_and_project_identity_are_checked_when_present(self):
        from core.runs import find_run_report_result
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make(root, "s1", {
                "session_id": "other", "provider_id": "codex",
                "project_id": "other-project", "cwd": str(root),
            })
            result = find_run_report_result(root, "s1", project_id="expected-project")
            self.assertIsNone(result.report)
            self.assertEqual(
                {row["field"] for row in result.diagnostic["conflicts"]},
                {"provider", "session_id", "project_id"},
            )

    def test_expanduser(self):
        # ~-путь должен раскрываться (расхождение, которое чинит вынос в core)
        with tempfile.TemporaryDirectory() as home:
            with mock.patch.dict(os.environ, {"HOME": home}):
                self._make(home, "s1", {"session_id": "s1"})
                self.assertIsNotNone(find_run_report("~", "s1"))


if __name__ == "__main__":
    unittest.main()
