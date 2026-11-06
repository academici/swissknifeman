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

    def test_no_claude_context_rule_before_a_source_was_seen(self):
        # "prompt is too long" has no primary source in the research pack: no Claude text rule for it.
        self.assertNotIn(ErrorClass.CONTEXT_LIMIT, {rule.error_class for rule in errors.load_error_rules()
                                                    if rule.provider == "claude-code"})

    def test_packaged_rules_are_registered_data(self):
        self.assertTrue(errors.default_rules_path().is_file())
        self.assertTrue(errors.load_error_rules())


NOW = 1_000_000
RESET = NOW + 7200
# Sources: Claude Code headless docs https://code.claude.com/docs/en/headless (system/api_retry `error`,
# `error_status`; rate_limit_event.rate_limit_info) and anthropics/claude-agent-sdk-python#599 (404 with
# result.subtype success + is_error true). Codex: openai/codex codex-rs/protocol/src/error.rs.
CLAUDE_RULES = (
    ("limit_status rejected + is_error (headless rate_limit_event; #599)",
     {"is_error": True, "limit_status": "rejected", "limit_window": "five_hour", "limit_resets_at": RESET},
     "quota", "PROVIDER_QUOTA", "account"),
    ("api_retry authentication_failed", {"retry_category": "authentication_failed"}, "authentication",
     "PROVIDER_AUTH", "account"),
    ("api_retry cloud_credential_error", {"retry_category": "cloud_credential_error"}, "authentication",
     "PROVIDER_AUTH", "account"),
    ("api_error_status 401", {"http_status": 401}, "authentication", "PROVIDER_AUTH", "account"),
    ("api_retry oauth_org_not_allowed", {"retry_category": "oauth_org_not_allowed"}, "authorization",
     "PROVIDER_AUTHZ", "account"),
    ("api_retry account_on_hold", {"retry_category": "account_on_hold"}, "authorization", "PROVIDER_AUTHZ",
     "account"),
    ("api_retry billing_error", {"retry_category": "billing_error"}, "authorization", "PROVIDER_AUTHZ",
     "account"),
    ("api_error_status 403", {"http_status": 403}, "authorization", "PROVIDER_AUTHZ", "account"),
    ("api_retry rate_limit", {"retry_category": "rate_limit"}, "rate_limit", "PROVIDER_RATE_LIMIT", "account"),
    ("api_error_status 429", {"http_status": 429}, "rate_limit", "PROVIDER_RATE_LIMIT", "account"),
    ("api_retry overloaded", {"retry_category": "overloaded"}, "provider_internal", "PROVIDER_OVERLOADED",
     "provider"),
    ("api_retry server_error", {"retry_category": "server_error"}, "provider_internal", "PROVIDER_OVERLOADED",
     "provider"),
    ("api_error_status 529", {"http_status": 529}, "provider_internal", "PROVIDER_OVERLOADED", "provider"),
    ("api_retry model_not_found", {"retry_category": "model_not_found"}, "model_unavailable",
     "MODEL_UNAVAILABLE", "request"),
    ("api_error_status 404 (#599)", {"http_status": 404, "is_error": True}, "model_unavailable",
     "MODEL_UNAVAILABLE", "request"),
    ("api_retry invalid_request", {"retry_category": "invalid_request"}, "invalid_request",
     "PROVIDER_INVALID_REQUEST", "request"),
)
CODEX_RULES = (
    ("UsageLimitReached", "You\u2019ve hit your usage limit. Upgrade to Pro or try again later.", "quota",
     "PROVIDER_QUOTA", "account"),
    ("QuotaExceeded", "Quota exceeded. Check your plan and billing details.", "quota", "PROVIDER_QUOTA",
     "account"),
    ("plan upgrade", "To use Codex with your ChatGPT plan, upgrade to Plus: https://chatgpt.com/explore/plus",
     "authorization", "PROVIDER_AUTHZ", "account"),
    ("ContextWindowExceeded", "Codex ran out of room in the model's context window. Start a new thread.",
     "context_limit", "PROVIDER_CONTEXT", "request"),
    ("ServerOverloaded model", "Selected model is at capacity. Please try a different model.",
     "model_unavailable", "MODEL_UNAVAILABLE", "provider"),
    ("rate limit", "rate limit exceeded: retry after 20s", "rate_limit", "PROVIDER_RATE_LIMIT", "account"),
    ("high demand", "We\u2019re currently experiencing high demand, which may cause temporary errors.",
     "provider_internal", "PROVIDER_OVERLOADED", "provider"),
    ("stream disconnected", "stream disconnected before completion: idle timeout", "transport",
     "PROVIDER_TRANSPORT", "provider"),
)


class TestSignalRules(unittest.TestCase):
    def test_antigravity_individual_quota_is_not_retried_as_unknown(self):
        result = errors.classify_signals("antigravity", {"exit_code": 1, "stderr_tail":
            "error: Individual quota reached. Please upgrade your subscription. Resets in 38h43m57s."}, now=NOW)
        self.assertEqual((result.error_class.value, result.code, result.scope.value),
                         ("quota", "PROVIDER_QUOTA", "request"))
        self.assertFalse(result.retryable)
        self.assertIsNone(errors.classify_failure("antigravity", text="ordinary rate limit"))

    def test_antigravity_authentication_requires_failed_structured_401(self):
        result = errors.classify_signals("antigravity", {"http_status": 401, "is_error": True}, now=NOW)
        self.assertEqual((result.code, result.scope.value), ("PROVIDER_AUTH", "account"))
        self.assertFalse(result.retryable)
        self.assertEqual(result.evidence, "structured")
        for signals in ({"http_status": 401}, {"http_status": 401, "is_error": False},
                        {"http_status": 403, "is_error": True},
                        {"fatal_text": "UNAUTHENTICATED (code 401): quoted text", "is_error": True}):
            with self.subTest(signals=signals):
                self.assertIsNone(errors.classify_signals("antigravity", signals, now=NOW))

    def test_every_claude_structured_rule_on_its_signal(self):
        for name, signals, error_class, code, scope in CLAUDE_RULES:
            with self.subTest(source=name):
                result = errors.classify_signals("claude-code", {"is_error": True, **signals}, now=NOW)
                self.assertEqual((result.error_class.value, result.code, result.scope.value),
                                 (error_class, code, scope))
                self.assertEqual(result.evidence, "structured")
                # the same signals of a run that did not fail (no is_error) are no failure
                healthy = {key: value for key, value in signals.items() if key != "is_error"}
                self.assertIsNone(errors.classify_signals("claude-code", healthy, now=NOW))
                self.assertIsNone(errors.classify_signals("claude-code", {**healthy, "is_error": False}, now=NOW))

    def test_every_codex_rule_on_the_exact_source_string(self):
        for name, text, error_class, code, scope in CODEX_RULES:
            with self.subTest(source=name):
                result = errors.classify_signals("codex", {"fatal_text": text}, now=NOW)
                self.assertEqual((result.error_class.value, result.code, result.scope.value),
                                 (error_class, code, scope))
                self.assertEqual(result.evidence, "text")

    def test_codex_markers_are_found_in_stderr_tail_and_with_either_apostrophe(self):
        for text in ("You\u2019ve hit your usage limit", "You've hit your usage limit", "YOU\u2019VE HIT YOUR USAGE LIMIT"):
            with self.subTest(text=text):
                result = errors.classify_signals("codex", {"stderr_tail": "x\n" + text}, now=NOW)
                self.assertEqual(result.code, "PROVIDER_QUOTA")

    def test_codex_text_rules_do_not_fire_for_claude_and_the_reverse(self):
        self.assertIsNone(errors.classify_signals("claude-code", {"fatal_text": CODEX_RULES[0][1]}, now=NOW))
        self.assertIsNone(errors.classify_signals("codex", {"http_status": 429}, now=NOW))

    def test_allowed_limit_status_is_telemetry_not_a_failure(self):
        for status in ("allowed", "allowed_warning"):
            with self.subTest(status=status):
                signals = {"is_error": True, "limit_status": status, "limit_resets_at": RESET}
                self.assertIsNone(errors.classify_signals("claude-code", signals, now=NOW))

    def test_limit_status_without_failure_or_without_status_is_not_quota(self):
        self.assertIsNone(errors.classify_signals(
            "claude-code", {"is_error": False, "limit_status": "rejected"}, now=NOW))
        self.assertIsNone(errors.classify_signals("claude-code", {"is_error": True}, now=NOW))

    def test_quota_takes_retry_after_from_the_reset_time(self):
        signals = {"is_error": True, "limit_status": "rejected", "limit_resets_at": RESET}
        self.assertEqual(errors.classify_signals("claude-code", signals, now=NOW).retry_after_s, 7200)
        self.assertEqual(errors.classify_signals("claude-code", signals, now=RESET + 50).retry_after_s, 0)
        self.assertEqual(errors.classify_signals("claude-code", signals, now=NOW + 0.5).retry_after_s, 7200)
        del signals["limit_resets_at"]
        self.assertIsNone(errors.classify_signals("claude-code", signals, now=NOW).retry_after_s)

    def test_only_a_rule_with_retry_after_from_dates_the_wait(self):
        signals = {"is_error": True, "retry_category": "authentication_failed", "limit_resets_at": RESET}
        self.assertIsNone(errors.classify_signals("claude-code", signals, now=NOW).retry_after_s)

    def test_structured_rule_wins_over_text(self):
        signals = {"is_error": True, "http_status": 404, "fatal_text": "weekly limit"}
        self.assertEqual(errors.classify_signals("claude-code", signals, now=NOW).code, "MODEL_UNAVAILABLE")
        self.assertEqual(errors.classify_signals(
            "claude-code", {"fatal_text": "weekly limit"}, now=NOW).evidence, "text")

    def test_booleans_are_not_numbers(self):
        self.assertIsNone(errors.classify_signals("claude-code", {"http_status": True}, now=NOW))
        loaded = errors.load_error_rules()
        self.assertIsNone(errors.classify_signals("claude-code", {"is_error": 1, "limit_status": "x"}, now=NOW,
                                                  rules=loaded))

    def test_the_terminal_status_wins_over_an_earlier_retry_category(self):
        # a retry that ended in 429 after an authentication_failed attempt is a rate limit, not an auth failure
        signals = {"is_error": True, "retry_category": "authentication_failed", "http_status": 429}
        self.assertEqual(errors.classify_signals("claude-code", signals, now=NOW).code, "PROVIDER_RATE_LIMIT")

    def test_a_leftover_retry_category_does_not_classify_a_failure_without_is_error(self):
        signals = {"retry_category": "rate_limit", "exit_code": 1, "fatal_text": "tool crashed"}
        self.assertIsNone(errors.classify_signals("claude-code", signals, now=NOW))

    def test_a_wrong_typed_limit_status_is_not_quota(self):
        for status in (1, True, None, ["rejected"]):
            with self.subTest(status=status):
                self.assertIsNone(errors.classify_signals("claude-code", {"is_error": True, "limit_status": status},
                                                          now=NOW))

    def test_a_content_filter_stop_is_a_refusal_not_a_transport_failure(self):
        # codex-rs/protocol/src/error.rs: the content_filter stop reads "stream disconnected before completion: ..."
        text = "stream disconnected before completion: Incomplete response returned, reason: content_filter"
        result = errors.classify_signals("codex", {"fatal_text": text}, now=NOW)
        self.assertEqual((result.error_class, result.code, result.retryable),
                         (ErrorClass.CONTENT_POLICY, "PROVIDER_REFUSED", False))

    def test_a_marker_never_matches_across_two_text_signals(self):
        signals = {"fatal_text": "weekly", "stderr_tail": "limit of open files"}
        self.assertIsNone(errors.classify_signals("claude-code", signals, now=NOW))
        self.assertEqual(errors.classify_signals("claude-code", {"stderr_tail": "x\nweekly limit"}, now=NOW).code,
                         "PROVIDER_QUOTA")

    def test_signals_validate_their_arguments(self):
        for bad in ({"fatal_text": 5}, {"stderr_tail": b"x"}):
            with self.subTest(signals=bad), self.assertRaises(TypeError):
                errors.classify_signals("codex", bad, now=NOW)
        with self.assertRaises(TypeError):
            errors.classify_signals("codex", [], now=NOW)
        with self.assertRaises(TypeError):
            errors.classify_signals("codex", {}, now="1")

    def test_unknown_signals_are_ignored(self):
        self.assertIsNone(errors.classify_signals("claude-code", {"made_up": 1}, now=NOW))

    def test_raw_text_never_reaches_the_record(self):
        record = errors.classify_signals(
            "codex", {"fatal_text": "Quota exceeded. token=secret-xyz"}, now=NOW)
        self.assertNotIn("secret-xyz", json.dumps(record.to_dict()))

    def test_classify_failure_wraps_text_and_exit_code(self):
        record = errors.classify_failure("codex", text="rate limit exceeded", exit_code=1)
        self.assertEqual((record.code, record.evidence), ("PROVIDER_RATE_LIMIT", "text"))

    def test_evidence_is_valid_error_v1(self):
        registry, kind = schema.load_contract(CONTRACT)
        for signals in ({"is_error": True, "http_status": 401}, {"fatal_text": "Quota exceeded"}):
            record = errors.classify_signals("claude-code" if "http_status" in signals else "codex", signals, now=NOW)
            self.assertEqual(schema.validate(record.to_dict(), kind, registry), [])
        with self.assertRaises(ValueError):
            ProviderError(ErrorClass.UNKNOWN, "X", False, "m", evidence="guess")


class TestSignalRuleFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def rules(self, rules):
        return errors.load_error_rules(write_rules(self._tmp.name, rules))

    def rule(self, **fields):
        base = {"provider": "p", "class": "quota", "code": "Q", "match": {"signal_any": {"http_status": [429]}}}
        base.update(fields)
        return base

    def test_signal_any_is_or_inside_and_across_signals(self):
        loaded = self.rules([self.rule(match={"signal_any": {"http_status": [429, 503], "retry_category": ["x"]}})])
        classify = lambda signals: errors.classify_signals("p", signals, now=0, rules=loaded)
        self.assertIsNotNone(classify({"http_status": 503, "retry_category": "x"}))
        self.assertIsNone(classify({"http_status": 503}))
        self.assertIsNone(classify({"http_status": 500, "retry_category": "x"}))

    def test_signal_not_in_needs_the_signal(self):
        loaded = self.rules([self.rule(match={"signal_not_in": {"limit_status": ["allowed"]}})])
        self.assertIsNone(errors.classify_signals("p", {}, now=0, rules=loaded))
        self.assertIsNone(errors.classify_signals("p", {"limit_status": "allowed"}, now=0, rules=loaded))
        self.assertEqual(errors.classify_signals("p", {"limit_status": "rejected"}, now=0, rules=loaded).evidence,
                         "structured")

    def test_text_with_exit_code_is_text_evidence(self):
        loaded = self.rules([self.rule(match={"text_contains_any": ["x"], "exit_code_any": [1]})])
        self.assertEqual(errors.classify_signals("p", {"fatal_text": "x", "exit_code": 1}, now=0,
                                                 rules=loaded).evidence, "text")

    def test_invalid_signal_rules_are_rejected(self):
        for bad in (self.rule(match={"signal_any": {"made_up": [1]}}),
                    self.rule(match={"signal_any": {"fatal_text": ["x"]}}),
                    self.rule(match={"signal_any": {"http_status": []}}),
                    self.rule(match={"signal_any": {"http_status": ["429"]}}),
                    self.rule(match={"signal_any": {"http_status": [True]}}),
                    self.rule(match={"signal_any": {"is_error": [1]}}),
                    self.rule(match={"signal_not_in": []}),
                    self.rule(match={"signal_any": []}),
                    self.rule(match={"signal_any": {}}),
                    self.rule(match={"signal_not_in": {}}),
                    self.rule(match={"text_contains_any": ["x"], "signal_any": {}}),
                    self.rule(retry_after_from="http_status"),
                    self.rule(retry_after_from=5)):
            with self.subTest(rule=bad), self.assertRaises(ValueError):
                self.rules([bad])


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
