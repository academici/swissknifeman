"""Tests of aicore.provider.errors against the error/v1 contract and the packaged rules."""
import json
import tempfile
import unittest
from pathlib import Path

from aicore.provider import errors
from aicore.provider.errors import ErrorClass, ErrorScope, ProviderError
from aicore.util import schema

CONTRACT = Path(__file__).resolve().parents[2] / "schemas" / "error" / "v1"


def schema_enum(name):
    doc = json.loads((CONTRACT / "error.schema.json").read_text(encoding="utf-8"))
    return doc["$defs"][name]["enum"]


def write_rules(directory, rules):
    path = Path(directory) / "rules.json"
    path.write_text(json.dumps({"schema_version": "provider-errors/v1", "rules": rules}), encoding="utf-8")
    return path


class TestContractParity(unittest.TestCase):
    def test_enums_equal_the_schema(self):
        self.assertEqual([item.value for item in ErrorClass], schema_enum("error-class"))
        self.assertEqual([item.value for item in ErrorScope], schema_enum("scope"))
        self.assertEqual(len(ErrorClass), 12)

    def test_defaults_cover_every_class(self):
        self.assertEqual(set(errors.DEFAULT_RETRYABLE), set(ErrorClass))
        self.assertEqual(set(errors.DEFAULT_SAFE_MESSAGE), set(ErrorClass))
        retryable = {item for item, value in errors.DEFAULT_RETRYABLE.items() if value}
        self.assertEqual(retryable, {ErrorClass.RATE_LIMIT, ErrorClass.TRANSPORT, ErrorClass.PROVIDER_INTERNAL,
                                     ErrorClass.TIMEOUT})
        self.assertFalse(errors.DEFAULT_RETRYABLE[ErrorClass.CONTEXT_LIMIT])

    def test_to_dict_is_valid_for_every_class(self):
        registry, kind = schema.load_contract(CONTRACT)
        for item in ErrorClass:
            with self.subTest(error_class=item.value):
                record = ProviderError(item, "SOME_CODE", errors.DEFAULT_RETRYABLE[item],
                                       errors.DEFAULT_SAFE_MESSAGE[item], retry_after_s=5, scope=ErrorScope.SESSION,
                                       provider="codex", request_id="r1", diagnostic_ref="@run/a.txt")
                self.assertEqual(schema.validate(record.to_dict(), kind, registry), [])

    def test_minimal_record_omits_optional_fields(self):
        record = ProviderError(ErrorClass.UNKNOWN, "X", False, "m")
        self.assertEqual(record.to_dict(), {"class": "unknown", "code": "X", "retryable": False, "safe_message": "m"})

    def test_record_validates_its_fields(self):
        for kwargs in ({"error_class": "quota"}, {"code": "lower"}, {"retryable": 1}, {"safe_message": ""},
                       {"retry_after_s": True}, {"scope": "request"}, {"provider": "Codex"}, {"request_id": ""}):
            with self.subTest(kwargs=kwargs):
                base = {"error_class": ErrorClass.QUOTA, "code": "C", "retryable": False, "safe_message": "m"}
                base.update(kwargs)
                with self.assertRaises((TypeError, ValueError)):
                    ProviderError(**base)


class TestPackagedRules(unittest.TestCase):
    def test_quota_markers_of_claude_code(self):
        for text in ("You have hit your session limit", "WEEKLY LIMIT reached", "x Session Limit y"):
            with self.subTest(text=text):
                result = errors.classify_failure("claude-code", text=text)
                self.assertEqual(result.error_class, ErrorClass.QUOTA)
                self.assertEqual(result.code, "PROVIDER_QUOTA")
                self.assertEqual(result.scope, ErrorScope.ACCOUNT)
                self.assertEqual(result.provider, "claude-code")
                self.assertFalse(result.retryable)

    def test_no_match_gives_none(self):
        self.assertIsNone(errors.classify_failure("claude-code", text="syntax error"))
        self.assertIsNone(errors.classify_failure("claude-code"))
        self.assertIsNone(errors.classify_failure("codex", text="session limit"))
        self.assertIsNone(errors.classify_failure("unknown-provider", text="session limit"))

    def test_text_is_never_copied(self):
        text = "session limit: secret-token-123"
        record = errors.classify_failure("claude-code", text=text)
        self.assertNotIn("secret-token-123", json.dumps(record.to_dict()))

    def test_text_must_be_a_string(self):
        with self.assertRaises(TypeError):
            errors.classify_failure("claude-code", text=None)

    def test_no_context_limit_rule_before_a_real_message_was_seen(self):
        self.assertNotIn(ErrorClass.CONTEXT_LIMIT, {rule.error_class for rule in errors.load_error_rules()})

    def test_packaged_rules_are_registered_data(self):
        self.assertTrue(errors.default_rules_path().is_file())
        self.assertTrue(errors.load_error_rules())


class TestRuleFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def rules(self, rules):
        return errors.load_error_rules(write_rules(self._tmp.name, rules))

    def rule(self, **fields):
        base = {"provider": "p", "class": "timeout", "code": "T", "match": {"text_contains_any": ["slow"]}}
        base.update(fields)
        return base

    def test_first_matching_rule_wins_and_rule_overrides(self):
        loaded = self.rules([self.rule(code="FIRST", retryable=False, safe_message="custom"),
                             self.rule(code="SECOND")])
        result = errors.classify_failure("p", text="Very SLOW", rules=loaded)
        self.assertEqual((result.code, result.retryable, result.safe_message), ("FIRST", False, "custom"))

    def test_class_default_when_rule_is_silent(self):
        result = errors.classify_failure("p", text="slow", rules=self.rules([self.rule()]))
        self.assertTrue(result.retryable)
        self.assertEqual(result.safe_message, errors.DEFAULT_SAFE_MESSAGE[ErrorClass.TIMEOUT])

    def test_exit_code_condition_and_combination(self):
        loaded = self.rules([self.rule(match={"exit_code_any": [124]}),
                             self.rule(code="BOTH", match={"text_contains_any": ["a"], "exit_code_any": [1]})])
        self.assertEqual(errors.classify_failure("p", exit_code=124, rules=loaded).code, "T")
        self.assertIsNone(errors.classify_failure("p", exit_code=2, rules=loaded))
        self.assertIsNone(errors.classify_failure("p", text="a", rules=loaded))
        self.assertEqual(errors.classify_failure("p", text="a", exit_code=1, rules=loaded).code, "BOTH")

    def test_invalid_rule_files_are_rejected(self):
        for bad in (self.rule(**{"class": "boom"}), self.rule(code="lower"), self.rule(match={}),
                    self.rule(match={"text_contains_any": [""]}), self.rule(match={"regex": "x"}),
                    self.rule(scope="galaxy"), self.rule(extra=1), self.rule(retryable="yes"),
                    self.rule(provider="P"), self.rule(match={"exit_code_any": [True]})):
            with self.subTest(rule=bad):
                with self.assertRaises(ValueError):
                    self.rules([bad])

    def test_invalid_documents_are_rejected(self):
        path = Path(self._tmp.name) / "bad.json"
        for text in ("not json", "[]", '{"schema_version": "x", "rules": []}',
                     '{"schema_version": "provider-errors/v1"}',
                     '{"schema_version": "provider-errors/v1", "rules": {}}'):
            path.write_text(text, encoding="utf-8")
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    errors.load_error_rules(path)
        with self.assertRaises(ValueError):
            errors.load_error_rules(Path(self._tmp.name) / "missing.json")


if __name__ == "__main__":
    unittest.main()
