"""Research sources (P10.1): config layers, the command, filesystem and mcp-stdio adapters, repeats, the CLI.

The mcp-stdio server is a fake (tests/fixtures/research/fake_mcp.py); no real source is asked. Its messages follow
packages/orch/docs/research/tools/pplx_stdio.py (initialize, notifications/initialized, tools/call).
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from aicore.config import ConfigError

from orch import research, settings
from orch.cli import main
from orch.research import sources

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "research"
PY = sys.executable


def _toml_list(items) -> str:
    return "[" + ", ".join(json.dumps(item) for item in items) + "]"


class ResearchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.project = self.root / "project"
        (self.home / "skm" / "config").mkdir(parents=True)
        (self.project / ".swissknifeman").mkdir(parents=True)
        self.env = {"SKM_HOME": str(self.home / "skm"), "HOME": str(self.home)}

    def machine(self, text: str) -> None:
        (self.home / "skm" / "config" / "config.toml").write_text("schema_version = 1\n" + text, encoding="utf-8")

    def project_file(self, text: str) -> None:
        (self.project / ".swissknifeman" / "config.toml").write_text("schema_version = 1\n" + text, encoding="utf-8")

    def load(self, **kwargs) -> settings.Settings:
        return settings.load(env=self.env, home=self.home, **kwargs)

    def mcp(self, *extra, **fields) -> sources.Source:
        return sources.Source(id="fake", kind="mcp-stdio", argv=(PY, str(FIXTURES / "fake_mcp.py"), *extra),
                              **fields)


class ConfigTests(ResearchCase):
    def test_defaults(self):
        found = self.load()
        self.assertEqual({"policy": "conditional", "sources": {}}, found.research)
        self.assertEqual([], research.sources_from(found))

    def test_machine_source_with_defaults_filled_in(self):
        self.machine('[orch.research.sources.perplexity]\nkind = "mcp-stdio"\nargv = ["~/perplexity-web-mcp/start.sh"]\n'
                     'order = 1\ncapabilities = ["search", "citations"]\n')
        (source,) = research.sources_from(self.load(project=self.project))
        self.assertEqual(("perplexity", "mcp-stdio", ("~/perplexity-web-mcp/start.sh",), "search", 600, 1, 1),
                         (source.id, source.kind, source.argv, source.tool, source.timeout_s, source.concurrency,
                          source.order))

    def test_the_project_cannot_set_an_argv(self):
        self.project_file('[orch.research.sources.evil]\nkind = "command"\nargv = ["/bin/sh", "-c", "id"]\n')
        with self.assertRaises(ConfigError) as caught:
            self.load(project=self.project)
        self.assertEqual("CONFIG_LAYER_FORBIDDEN", caught.exception.code)

    def test_the_project_can_set_roots_and_policy(self):
        self.project_file('[orch.research]\npolicy = "required"\n[orch.research.sources.notes]\nkind = "filesystem"\n'
                          'roots = ["docs"]\n')
        found = self.load(project=self.project)
        self.assertEqual("required", found.research["policy"])
        self.assertEqual(("docs",), research.sources_from(found)[0].roots)

    def test_unknown_kind_and_policy_are_refused(self):
        self.machine('[orch.research.sources.x]\nkind = "http"\n')
        with self.assertRaises(ConfigError):
            self.load()
        self.machine('[orch.research]\npolicy = "sometimes"\n')
        with self.assertRaises(ConfigError):
            self.load()

    def test_the_ladder_is_sorted_by_order_then_id(self):
        self.machine('[orch.research.sources.b]\nkind = "filesystem"\norder = 2\n'
                     '[orch.research.sources.a]\nkind = "filesystem"\norder = 2\n'
                     '[orch.research.sources.z]\nkind = "filesystem"\norder = 1\n')
        self.assertEqual(["z", "a", "b"], [s.id for s in research.sources_from(self.load())])


class McpStdioTests(ResearchCase):
    def test_the_reply_is_normalised(self):
        log = self.root / "log.jsonl"
        answer = research.query(self.mcp("--log", str(log)), "what is x?")
        self.assertEqual("fake", answer["source"])
        self.assertIn("Answer to: what is x?", answer["text"])
        self.assertEqual(["https://example.org/a", "https://example.org/b"], answer["sources"])
        self.assertRegex(answer["raw_ref"], r"^sha256:[0-9a-f]{64}$")
        methods = [json.loads(line).get("method") for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(["initialize", "notifications/initialized", "tools/call"], methods)

    def test_the_tool_is_configurable(self):
        answer = research.query(self.mcp("--tool", "search_deep", tool="search_deep"), "q")
        self.assertIn("Answer to: q", answer["text"])
        with self.assertRaises(research.SourceError) as caught:
            research.query(self.mcp("--tool", "search_deep"), "q")  # the default tool is `search`
        self.assertEqual("SOURCE_UNAVAILABLE", caught.exception.code)

    def test_busy_is_asked_again(self):
        counter = self.root / "busy"
        waits: list = []
        answer = research.query(self.mcp("--busy", "2", "--busy-file", str(counter)), "q", sleep=waits.append,
                                retry_wait_s=7)
        self.assertIn("Answer to: q", answer["text"])
        self.assertEqual("3", counter.read_text(encoding="utf-8"))
        self.assertEqual([7, 14], waits)

    def test_busy_for_good_is_source_unavailable(self):
        counter = self.root / "busy"
        waits: list = []
        with self.assertRaises(research.SourceError) as caught:
            research.query(self.mcp("--busy", "99", "--busy-file", str(counter)), "q", sleep=waits.append)
        self.assertEqual("SOURCE_UNAVAILABLE", caught.exception.code)
        self.assertEqual(research.RETRIES_MAX, len(waits))
        self.assertEqual(str(research.RETRIES_MAX + 1), counter.read_text(encoding="utf-8"))

    def test_a_slow_server_times_out_and_is_asked_again(self):
        waits: list = []
        with self.assertRaises(research.SourceError) as caught:
            research.query(self.mcp("--sleep", "5", timeout_s=1), "q", sleep=waits.append)
        self.assertEqual("SOURCE_UNAVAILABLE", caught.exception.code)
        self.assertEqual(research.RETRIES_MAX, len(waits))

    def test_a_missing_server_is_source_unavailable(self):
        source = sources.Source(id="gone", kind="mcp-stdio", argv=(str(self.root / "no-such-server"),))
        with self.assertRaises(research.SourceError) as caught:
            research.query(source, "q")
        self.assertEqual("SOURCE_UNAVAILABLE", caught.exception.code)

    def test_an_empty_query_and_a_missing_argv(self):
        with self.assertRaises(research.SourceError) as caught:
            research.query(self.mcp(), "  \n")
        self.assertEqual("QUERY_EMPTY", caught.exception.code)
        with self.assertRaises(research.SourceError) as caught:
            research.query(sources.Source(id="x", kind="mcp-stdio"), "q")
        self.assertEqual("SOURCE_INVALID", caught.exception.code)


class CommandAndFilesystemTests(ResearchCase):
    def test_command_source(self):
        source = sources.Source(id="cmd", kind="command", argv=(PY, str(FIXTURES / "fake_command.py")))
        answer = research.query(source, "hello")
        self.assertEqual(("command answer: hello", ["https://example.org/c"]), (answer["text"], answer["sources"]))

    def test_command_failures(self):
        for code in ("import sys; sys.exit(3)", "print('not json')", "print('[1]')"):
            source = sources.Source(id="cmd", kind="command", argv=(PY, "-c", code))
            with self.assertRaises(research.SourceError) as caught:
                research.query(source, "q")
            self.assertEqual("SOURCE_UNAVAILABLE", caught.exception.code)

    def test_filesystem_source_reads_only_and_cites_paths(self):
        source = sources.Source(id="fs", kind="filesystem", roots=("tree",))
        answer = research.query(source, "gateway timeout", cwd=FIXTURES)
        self.assertEqual(["tree/docs/a.md"], answer["sources"])
        self.assertEqual("tree/docs/a.md:2: The Gateway timeout is 30s", answer["text"])

    def test_a_project_folder_that_links_out_of_the_project_is_not_read(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            outside, project = Path(tmp) / "outside", Path(tmp) / "project"
            outside.mkdir()
            project.mkdir()
            (outside / "secret.txt").write_text("gateway timeout is a secret\n", encoding="utf-8")
            (project / "notes").symlink_to(outside, target_is_directory=True)
            source = sources.Source(id="fs", kind="filesystem", roots=("notes",))
            self.assertEqual("", research.query(source, "gateway timeout", cwd=project)["text"])
            absolute = sources.Source(id="fs", kind="filesystem", roots=(str(outside),))  # a machine-configured root
            self.assertIn("secret.txt", research.query(absolute, "gateway timeout", cwd=project)["text"])

    def test_a_fifo_under_a_root_is_skipped_instead_of_blocking_the_read(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.mkfifo(root / "pipe")
            (root / "note.txt").write_text("gateway timeout is 30s\n", encoding="utf-8")
            source = sources.Source(id="fs", kind="filesystem", roots=(str(root),))
            answer = research.query(source, "gateway timeout", cwd=root)
            self.assertIn("note.txt", answer["text"])

    def test_filesystem_without_a_match_or_roots(self):
        source = sources.Source(id="fs", kind="filesystem", roots=(str(FIXTURES / "tree"),))
        self.assertEqual(([], ""), (lambda a: (a["sources"], a["text"]))(research.query(source, "zzz-none")))
        with self.assertRaises(research.SourceError) as caught:
            research.query(sources.Source(id="fs", kind="filesystem"), "q")
        self.assertEqual("SOURCE_INVALID", caught.exception.code)


class CliTests(ResearchCase):
    def setUp(self):
        super().setUp()
        self.machine(f'[orch.research.sources.fake]\nkind = "mcp-stdio"\nargv = {_toml_list([PY, str(FIXTURES / "fake_mcp.py")])}\n'
                     'order = 1\ncapabilities = ["search"]\n'
                     f'[orch.research.sources.cmd]\nkind = "command"\nargv = {_toml_list([PY, str(FIXTURES / "fake_command.py")])}\n'
                     'order = 2\n')
        self.query_file = self.root / "q.txt"
        self.query_file.write_text("the question\n", encoding="utf-8")

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        import os
        saved = {key: os.environ.get(key) for key in self.env}
        os.environ.update(self.env)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["--project", str(self.project), *argv])
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        return code, out.getvalue(), err.getvalue()

    def test_sources_json(self):
        code, out, _ = self.run_cli("research", "sources", "--json")
        doc = json.loads(out)
        self.assertEqual(0, code)
        self.assertEqual("conditional", doc["policy"])
        self.assertEqual(["fake", "cmd"], [row["id"] for row in doc["sources"]])
        self.assertEqual(["search"], doc["sources"][0]["capabilities"])

    def test_sources_text(self):
        code, out, _ = self.run_cli("research", "sources")
        self.assertEqual(0, code)
        self.assertIn("1\tfake\tmcp-stdio\tsearch", out)

    def test_query_json(self):
        code, out, _ = self.run_cli("research", "query", "--source", "fake", "--query-file", str(self.query_file),
                                    "--json")
        doc = json.loads(out)
        self.assertEqual(0, code)
        self.assertEqual(("fake", ["https://example.org/a", "https://example.org/b"]), (doc["source"], doc["sources"]))
        self.assertIn("Answer to: the question", doc["text"])

    def test_query_text(self):
        code, out, _ = self.run_cli("research", "query", "--source", "cmd", "--query-file", str(self.query_file))
        self.assertEqual(0, code)
        self.assertIn("command answer: the question", out)
        self.assertIn("source: https://example.org/c", out)

    def test_unknown_source(self):
        code, _, err = self.run_cli("research", "query", "--source", "nope", "--query-file", str(self.query_file))
        self.assertEqual(1, code)
        self.assertIn("SOURCE_UNKNOWN", err)

    def test_missing_query_file(self):
        code, _, err = self.run_cli("research", "query", "--source", "fake", "--query-file", str(self.root / "none"))
        self.assertEqual((1, True), (code, "INPUT_INVALID" in err))

    def test_a_project_argv_is_a_config_error(self):
        self.project_file('[orch.research.sources.evil]\nkind = "command"\nargv = ["/bin/true"]\n')
        code, _, err = self.run_cli("research", "sources")
        self.assertEqual(1, code)
        self.assertIn("CONFIG_INVALID", err)
        self.assertIn("CONFIG_LAYER_FORBIDDEN", err)


if __name__ == "__main__":
    unittest.main()
