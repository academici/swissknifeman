"""aicore.util.redact: known values and explicit token formats, never ordinary prose."""
import unittest

from aicore.config.secrets import Secret
from aicore.util.redact import MASK, env_secrets, redact_document, redact_text

# Formats from the provider documentation of each issuer (prefix and length class only; the values are made up).
SK = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2"
GHP = "ghp_" + "A" * 36
PAT = "github_pat_" + "B1" * 20
SLACK = "xoxb-" + "1234567890-abcdefghij"
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
BEARER = "Bearer " + "abcdefghijklmnopqrstuvwxyz012345"


class TestText(unittest.TestCase):
    def test_every_token_format_is_masked(self):
        for token in (SK, GHP, PAT, SLACK, AWS, BEARER):
            with self.subTest(token=token[:8]):
                out = redact_text(f"failed with {token} at the end")
                self.assertEqual(out, f"failed with {MASK} at the end")

    def test_a_named_value_keeps_its_name(self):
        self.assertEqual(redact_text("api_key=abcdefgh12345 and x"), f"api_key={MASK} and x")
        self.assertEqual(redact_text('"password": "hunter2hunter2"'), f'"password": "{MASK}"')
        self.assertEqual(redact_text("TOKEN: s3cr3t-value-1"), f"TOKEN: {MASK}")

    def test_ordinary_text_is_untouched(self):
        for text in ("tokens 120/30 used", "the token budget is spent", "sk-short", "password: none",
                     "risk score 40 reached 30", "AKIA is a prefix", "Bearer of bad news"):
            self.assertEqual(redact_text(text), text)

    def test_known_values_are_masked_longest_first_and_without_patterns(self):
        self.assertEqual(redact_text("a pw-1 and pw-12", secrets=("pw-1", "pw-12"), patterns=False),
                         f"a {MASK} and {MASK}")
        self.assertEqual(redact_text(f"{SK}", secrets=(), patterns=False), SK)

    def test_a_secret_object_is_known_by_its_value(self):
        self.assertEqual(redact_text("is value-xyz-123 here", secrets=(Secret("env://SOME_NAME", lambda: "value-xyz-123"),)),
                         f"is {MASK} here")

    def test_mask_is_chosen_by_the_caller(self):
        self.assertEqual(redact_text(f"x {GHP}", mask="***"), "x ***")

    def test_empty_and_short_secrets_are_ignored(self):
        self.assertEqual(redact_text("abc", secrets=("", None)), "abc")


class TestDocument(unittest.TestCase):
    def test_strings_keys_and_nested_values(self):
        doc = {"a": [f"x {GHP}", 3, None, True], f"k-{SK}": {"b": "known-secret-1"}}
        out = redact_document(doc, secrets=["known-secret-1"])
        self.assertEqual(out, {"a": [f"x {MASK}", 3, None, True], f"k-{MASK}": {"b": MASK}})
        self.assertIn(GHP, str(doc))  # the input is not changed

    def test_a_scalar_whose_text_holds_a_secret_is_masked(self):
        self.assertEqual(redact_document({"n": 1234567890}, secrets=["34567"], patterns=False), {"n": MASK})


class TestEnv(unittest.TestCase):
    def test_values_of_secret_named_variables(self):
        env = {"MY_API_KEY": "value-one-123", "GITHUB_TOKEN": "value-two-456", "PATH": "/usr/bin",
               "SHORT_TOKEN": "abc", "DB_PASSWORD": "pw-long-789", "EMPTY_SECRET": ""}
        self.assertEqual(sorted(env_secrets(env)), ["pw-long-789", "value-one-123", "value-two-456"])

    def test_the_process_environment_by_default(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"X_TOKEN": "from-process-env"}):
            self.assertIn("from-process-env", env_secrets())


if __name__ == "__main__":
    unittest.main()
