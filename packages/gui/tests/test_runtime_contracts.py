"""Runtime contracts against their sources in code and docs: run states, error codes, kinds, references, secrets."""
import json
import re
import unittest
from pathlib import Path

from gui import contracts, errors
from gui.core import run_states

MODULE_ROOT = Path(__file__).resolve().parents[1]
API_DOC = (MODULE_ROOT / "docs" / "api.md").read_text(encoding="utf-8")
UNIT = json.loads((MODULE_ROOT / "unit.json").read_text(encoding="utf-8"))
LISTED = [entry["id"].rpartition(":")[2] for entry in UNIT["provides"]["contracts"]]
RUNTIME = ("api-error", "bootstrap", "run", "stream", "trust", "config-mutation")


def root_schema(contract):
    registry, kind = contracts.load(contract)
    return registry.for_kind(kind)[0]


def table(heading):
    """Rows of the first markdown table after ``heading`` as lists of cell texts without backquotes."""
    text = API_DOC.split(heading, 1)[1]
    rows = []
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
            if not set(cells[0]) <= set("- "):
                rows.append(cells)
        elif rows:
            break
    return rows[1:]  # without the header


class TestRunStates(unittest.TestCase):
    def test_schema_enum_equals_the_states_in_code(self):
        self.assertEqual(list(run_states.STATES), root_schema("run")["$defs"]["state"]["enum"])
        self.assertEqual(set(run_states.STATES), set(run_states.TRANSITIONS))
        for targets in run_states.TRANSITIONS.values():
            self.assertLessEqual(targets, set(run_states.STATES))

    def test_terminal_states(self):
        self.assertEqual({"denied", "failed_to_start", "succeeded", "failed", "cancelled", "timed_out", "lost"},
                         set(run_states.TERMINAL))
        for state in run_states.TERMINAL:
            self.assertTrue(run_states.is_terminal(state))
            self.assertFalse(any(run_states.can_transition(state, other) for other in run_states.STATES))

    def test_every_unfinished_state_can_be_lost_and_reaches_an_end(self):
        for state in set(run_states.STATES) - run_states.TERMINAL:
            with self.subTest(state=state):
                self.assertTrue(run_states.can_transition(state, "lost"))
                seen, todo = set(), [state]
                while todo:
                    current = todo.pop()
                    seen.add(current)
                    todo.extend(run_states.TRANSITIONS[current] - seen)
                self.assertTrue(seen & {"succeeded", "failed", "denied", "cancelled"})

    def test_states_with_a_process(self):
        self.assertEqual({"starting", "running", "cancelling"}, set(run_states.WITH_PROCESS))
        self.assertFalse(run_states.WITH_PROCESS & run_states.TERMINAL)

    def test_doc_table_matches_the_transitions(self):
        rows = {cells[0]: cells[1] for cells in table("### States and transitions")}
        self.assertEqual(set(run_states.STATES), set(rows))
        for state, targets in run_states.TRANSITIONS.items():
            documented = set() if rows[state] == "terminal" else {t.strip().strip("`") for t in rows[state].split(",")}
            self.assertEqual(set(targets), documented, state)

    def test_unknown_states_do_not_transition(self):
        self.assertFalse(run_states.can_transition("adopted", "running"))
        self.assertFalse(run_states.can_transition("queued", "running"))


class TestErrorCodes(unittest.TestCase):
    def test_classes_match_the_schema(self):
        enum = root_schema("api-error")["$defs"]["class"]["enum"]
        self.assertEqual(list(errors.CLASSES), enum)
        self.assertLessEqual({cls for cls, _ in errors.CODES.values()}, set(enum))

    def test_codes_follow_the_pattern_and_statuses_are_http_errors(self):
        pattern = re.compile(root_schema("api-error")["$defs"]["code"]["pattern"])
        for code, (_, status) in errors.CODES.items():
            with self.subTest(code=code):
                self.assertRegex(code, pattern)
                self.assertTrue(400 <= status <= 599)

    def test_registry_in_docs_matches_the_code(self):
        rows = {cells[0]: cells[1:] for cells in table("### Code registry")}
        self.assertEqual(set(errors.CODES), set(rows))
        for code, (cls, status) in errors.CODES.items():
            with self.subTest(code=code):
                self.assertEqual([cls, str(status), "yes" if errors.retryable(code) else "no"], rows[code])

    def test_design_codes_are_registered(self):
        self.assertLessEqual({
            "AUTH_REQUIRED", "AUTH_INVALID", "HOST_REJECTED", "ORIGIN_REJECTED", "PROTOCOL_INCOMPATIBLE", "NOT_FOUND",
            "INPUT_INVALID", "OUTPUT_INVALID", "PATH_ESCAPE", "PERMISSION_DENIED", "CONFIRMATION_REQUIRED",
            "CONCURRENCY_LIMIT", "RUN_NOT_CANCELLABLE", "HANDLER_FAILED", "HANDLER_TIMEOUT", "PLUGIN_UNAVAILABLE",
            "PLUGIN_QUARANTINED", "CONFIG_REVISION_CONFLICT", "CONFIG_LOCKED", "CONFIG_LAYER_FORBIDDEN", "PREVIEW_STALE",
            "PAYLOAD_TOO_LARGE", "INTERNAL"}, set(errors.CODES))
        self.assertLessEqual(errors.RETRYABLE, set(errors.CODES))

    def test_error_envelope_is_valid(self):
        for code in errors.CODES:
            with self.subTest(code=code):
                error = errors.GuiError(code, "Safe text.", details={"module": "planner", "count": 2},
                                        issues=[{"pointer": "/input/item", "code": "pattern", "message": "bad"}])
                document = error.envelope("req-00000001")
                self.assertEqual([], contracts.validate(document, "api-error"))
                self.assertEqual(errors.retryable(code), document["error"]["retryable"])
                self.assertEqual(f"{code}: Safe text.", str(error))

    def test_unregistered_code_is_refused(self):
        with self.assertRaises(ValueError):
            errors.GuiError("NOPE", "x")
        with self.assertRaises(KeyError):
            errors.retryable("NOPE")


class TestKinds(unittest.TestCase):
    def kinds(self, contract):
        name, branches = contracts.discriminator(contract)
        return name, set(branches)

    def test_stream_kinds(self):
        self.assertEqual(("kind", {"subscribe", "unsubscribe", "event", "log", "run", "snapshot_required", "heartbeat",
                                   "error"}), self.kinds("stream"))

    def test_config_mutation_kinds(self):
        self.assertEqual(("kind", {"preview_request", "preview", "commit_request", "commit_result"}),
                         self.kinds("config-mutation"))

    def test_bootstrap_modes(self):
        self.assertEqual(("mode", {"desktop", "browser"}), self.kinds("bootstrap"))

    def test_every_kind_has_a_valid_example(self):
        for contract in ("stream", "config-mutation", "bootstrap"):
            name, kinds = self.kinds(contract)
            seen = {json.loads(path.read_text(encoding="utf-8"))[name]
                    for path in (contracts.contract_dir(contract) / "examples" / "valid").glob("*.json")}
            self.assertEqual(kinds, seen, contract)

    def test_documented_stream_kinds(self):
        self.assertEqual(self.kinds("stream")[1], {cells[0] for cells in table("## Event stream (`stream/v1`)")})


class TestSafety(unittest.TestCase):
    def walk(self, node, where, found):
        if isinstance(node, dict):
            for keyword in ("properties", "patternProperties"):
                for name, child in node.get(keyword, {}).items():
                    found.append((f"{where}/{name}", name))
                    self.walk(child, f"{where}/{name}", found)
            for keyword in ("$defs",):
                for name, child in node.get(keyword, {}).items():
                    self.walk(child, f"{where}/$defs/{name}", found)
            self.walk(node.get("items"), f"{where}/items", found)
            for index, child in enumerate(node.get("oneOf", ())):
                self.walk(child, f"{where}/oneOf/{index}", found)

    def test_no_field_holds_a_secret_value(self):
        for contract in LISTED:
            found = []
            self.walk(root_schema(contract), contract, found)
            for where, name in found:
                self.assertNotRegex(name.lower(), r"secret|token|password|passwd|api_?key|credential", where)

    def test_every_reference_resolves(self):
        def refs(node):
            if isinstance(node, dict):
                if isinstance(node.get("$ref"), str):
                    yield node["$ref"]
                for value in node.values():
                    yield from refs(value)
            elif isinstance(node, list):
                for value in node:
                    yield from refs(value)

        for contract in LISTED:
            registry, kind = contracts.load(contract)
            root, root_id = registry.for_kind(kind)
            for ref in refs(root):
                with self.subTest(contract=contract, ref=ref):
                    registry.resolve(ref, root_id)

    def test_contracts_reference_each_other_by_urn_only(self):
        for contract in RUNTIME:
            text = (contracts.contract_dir(contract) / f"{contract}.schema.json").read_text(encoding="utf-8")
            for ref in re.findall(r'"\$ref": "([^"#][^"]*)"', text):
                self.assertTrue(ref.startswith(("urn:swissknifeman:gui:", "urn:swissknifeman:aicore:")), ref)

    def test_config_write_needs_the_revision(self):
        schema = root_schema("config-mutation")["$defs"]
        self.assertIn("expected_revision", schema["preview_request"]["required"])
        self.assertIn("expected_revision", schema["commit_request"]["required"])

    def test_resume_needs_cursor_and_epoch(self):
        self.assertLessEqual({"cursor", "epoch"}, set(root_schema("stream")["$defs"]["subscribe"]["required"]))
        for mode in ("desktop", "browser"):
            self.assertIn("epoch", root_schema("bootstrap")["$defs"][mode]["required"])


if __name__ == "__main__":
    unittest.main()
