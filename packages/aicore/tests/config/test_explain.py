"""explain: origin of every value (layer, file, line, source), overridden values, text and JSON forms."""
import json
import unittest
from pathlib import Path

from aicore.config import ConfigError, ExtraLayer
from aicore.util import schema

from tests.config.support import Workspace

CONTRACT = Path(__file__).resolve().parents[2] / "schemas" / "config-explain" / "v1"


class TestExplain(Workspace):
    def layered(self):
        self.machine("[demo.recompute]\n# a comment\ncandidate_min_n = 18\n")
        self.proj("[demo]\nmode = \"fast\"\n\n[demo.recompute]\ncandidate_min_n = 20\n")

    def test_entry_names_layer_file_line_and_overridden_values(self):
        self.layered()
        entry = self.resolve().explain("recompute.candidate_min_n")[0]
        self.assertEqual((entry.key, entry.value, entry.layer), ("recompute.candidate_min_n", 20, "project"))
        self.assertEqual((entry.file, entry.line, entry.source), (str(self.project_file), 6, None))
        self.assertEqual([(o.layer, o.file, o.line, o.value) for o in entry.overridden],
                         [("machine", str(self.machine_file), 4, 18), ("defaults", None, None, 15)])
        self.assertTrue(entry.has_default)
        self.assertEqual(entry.default, 15)
        self.assertFalse(entry.secret)

    def test_value_from_the_schema_default(self):
        entry = self.resolve().explain("verbose")[0]
        self.assertEqual((entry.value, entry.layer, entry.file, entry.line, entry.source), (False, "defaults", None, None, None))
        self.assertEqual(entry.overridden, ())

    def test_key_without_default_or_value_has_no_entry(self):
        resolved = self.resolve()
        self.assertEqual(resolved.explain("limits.retries"), [])
        self.assertNotIn("limits.retries", [entry.key for entry in resolved.explain()])

    def test_listing_follows_the_schema_order(self):
        keys = [entry.key for entry in self.resolve().explain()]
        self.assertEqual(keys, ["recompute.candidate_min_n", "recompute.ratio", "recompute.window.days",
                                "verbose", "mode", "sources", "cache_dir"])

    def test_explain_of_a_table(self):
        keys = [entry.key for entry in self.resolve().explain("recompute.window")]
        self.assertEqual(keys, ["recompute.window.days"])

    def test_unknown_key(self):
        with self.assertRaises(ConfigError) as caught:
            self.resolve().explain("nope")
        self.assertEqual(caught.exception.code, "CONFIG_UNKNOWN_KEY")

    def test_environment_flag_and_invocation_sources(self):
        invocation = self.write(self.root / "run.toml", "schema_version = 1\n[demo]\nmode = \"fast\"\n")
        resolved = self.resolve(env={**self.env, "SKM_DEMO_VERBOSE": "true"}, config_file=invocation,
                                flags={"recompute.candidate_min_n": "9"})
        verbose, mode, minimum = (resolved.explain(key)[0] for key in ("verbose", "mode", "recompute.candidate_min_n"))
        self.assertEqual((verbose.layer, verbose.source, verbose.file), ("env", "SKM_DEMO_VERBOSE", None))
        self.assertEqual((mode.layer, mode.source, mode.file, mode.line), ("invocation", "--config", str(invocation), 3))
        self.assertEqual((minimum.layer, minimum.source), ("flags", "flag"))
        self.assertEqual(mode.overridden[0].layer, "defaults")

    def test_extra_layer_source_is_its_name(self):
        resolved = self.resolve(extra_layers=[ExtraLayer("legacy", {"verbose": True})])
        entry = resolved.explain("verbose")[0]
        self.assertEqual((entry.layer, entry.source), ("legacy", "legacy"))

    def test_append_is_listed_with_its_resulting_array(self):
        self.proj("[demo._append]\nsources = [\"x\"]\n")
        entry = self.resolve().explain("sources")[0]
        self.assertEqual((entry.value, entry.layer, entry.source, entry.line), (["local", "x"], "project", "_append", 3))
        self.assertEqual([(o.layer, o.value) for o in entry.overridden], [("defaults", ["local"])])

    def test_unset_shows_the_resetting_layer_among_the_overridden(self):
        self.machine("[demo.recompute]\ncandidate_min_n = 18\n")
        self.proj("[demo]\n_unset = [\"recompute.candidate_min_n\"]\n")
        entry = self.resolve().explain("recompute.candidate_min_n")[0]
        self.assertEqual((entry.value, entry.layer, entry.file), (15, "defaults", None))
        first = entry.overridden[0]
        self.assertEqual((first.layer, first.source, first.value, first.line), ("project", "_unset", None, 3))
        self.assertEqual([(o.layer, o.value) for o in entry.overridden[1:]], [("machine", 18)])

    def test_a_value_set_after_an_unset_wins_again(self):
        self.machine("[demo]\nmode = \"fast\"\n")
        self.proj("[demo]\n_unset = [\"mode\"]\n")
        resolved = self.resolve(flags={"mode": "fast"})
        entry = resolved.explain("mode")[0]
        self.assertEqual(entry.layer, "flags")
        self.assertEqual([(o.layer, o.source) for o in entry.overridden],
                         [("project", "_unset"), ("machine", None), ("defaults", None)])

    def test_text_form(self):
        self.layered()
        text = self.resolve().explain_text("recompute.candidate_min_n")
        self.assertEqual(text, "\n".join([
            "recompute.candidate_min_n = 20",
            f"  from project {self.project_file}:6",
            f"  overrides machine {self.machine_file}:4 = 18; defaults = 15",
        ]))

    def test_text_form_for_default_env_and_unset(self):
        self.assertEqual(self.resolve().explain_text("mode"), 'mode = "safe"\n  from defaults')
        env_text = self.resolve(env={**self.env, "SKM_DEMO_MODE": "fast"}).explain_text("mode")
        self.assertEqual(env_text, 'mode = "fast"\n  from env SKM_DEMO_MODE\n  overrides defaults = "safe"')
        self.machine("[demo]\nmode = \"fast\"\n")
        self.proj("[demo]\n_unset = [\"mode\"]\n")
        text = self.resolve().explain_text("mode")
        self.assertIn(f"overrides project {self.project_file}:3 unset; machine {self.machine_file}:3 = \"fast\"", text)

    def test_explain_text_lists_all_keys(self):
        text = self.resolve().explain_text()
        self.assertEqual(text.count("\n  from "), 7)


class TestExplainJson(Workspace):
    def validate(self, document):
        registry, kind = schema.load_contract(CONTRACT)
        return schema.validate(document, kind, registry)

    def test_explain_json_is_valid_by_the_contract(self):
        self.machine("[demo.recompute]\ncandidate_min_n = 18\n")
        self.proj("[demo]\nmode = \"fast\"\ntoken = \"env://DEMO_TOKEN\"\n_unset = [\"recompute.candidate_min_n\"]\n"
                  "[demo._append]\nsources = [\"x\"]\n")
        resolved = self.resolve(env={**self.env, "SKM_DEMO_VERBOSE": "1"}, flags={"recompute.ratio": "0.1"})
        document = resolved.explain_json()
        self.assertEqual(self.validate(document), [])
        self.assertEqual(json.loads(json.dumps(document)), document)

    def test_document_header(self):
        document = self.resolve().explain_json()
        self.assertEqual(document["$schema"], "urn:swissknifeman:aicore:config-explain:v1")
        self.assertEqual((document["module"], document["project"], document["config_file_version"]),
                         ("demo", str(self.project), 1))
        self.assertEqual([layer["name"] for layer in document["layers"]],
                         ["defaults", "machine", "project", "env", "invocation", "flags"])
        self.assertIsNone(self.resolve(project=None).explain_json()["project"])

    def test_default_is_omitted_when_the_schema_has_none(self):
        self.proj("[demo.limits]\nretries = 2\n")
        entries = {entry["key"]: entry for entry in self.resolve().explain_json()["entries"]}
        self.assertNotIn("default", entries["limits.retries"])
        self.assertEqual(entries["verbose"]["default"], False)
        self.assertEqual(self.validate(self.resolve().explain_json()), [])

    def test_json_of_one_key(self):
        document = self.resolve().explain_json("mode")
        self.assertEqual([entry["key"] for entry in document["entries"]], ["mode"])

    def test_returned_document_is_a_copy(self):
        resolved = self.resolve()
        document = resolved.explain_json()
        document["entries"][-2]["value"].append("hacked")
        self.assertEqual(resolved.get("sources"), ["local"])

    def test_contract_rejects_a_broken_document(self):
        document = self.resolve().explain_json()
        document["entries"][0].pop("layer")
        self.assertTrue(self.validate(document))


if __name__ == "__main__":
    unittest.main()
