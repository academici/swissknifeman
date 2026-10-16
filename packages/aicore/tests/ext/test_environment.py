"""aicore.ext.environment: allowlist, trusted-only extras and secrets, profile, no leaked values."""
import os
import sys
import traceback
import unittest
import uuid
from pathlib import Path

from aicore.config import ConfigError
from aicore.ext import ExtError
from aicore.ext.environment import BASE_ALLOW, clean_environment, effective_profile, ignored_requests
from aicore.ext.errors import CODES
from aicore.ext.process import run_json

SENTINEL = "s3cr3t-" + uuid.uuid4().hex
SHOW_ENV = Path(__file__).resolve().parent / "fixtures" / "procs" / "show_env.py"


def full_trace(error):
    return "".join(traceback.format_exception(type(error), error, error.__traceback__))


class TestAllowlist(unittest.TestCase):
    def test_foreign_variable_does_not_pass(self):
        source = {"PATH": "/bin", "AWS_SECRET_ACCESS_KEY": SENTINEL, "GITHUB_TOKEN": SENTINEL, "HOME": "/h"}
        env, secrets = clean_environment(source)
        self.assertEqual(env["PATH"], "/bin")
        self.assertEqual(env["HOME"], "/h")
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn(SENTINEL, repr(env))
        self.assertEqual(secrets, [])

    def test_every_base_name_and_locale_passes(self):
        source = {name: name.lower() for name in BASE_ALLOW}
        source.update({"LC_ALL": "C", "LC_CTYPE": "C.UTF-8", "LCX": "no", "SKM_OTHER": "no"})
        env, _ = clean_environment(source)
        for name in BASE_ALLOW:
            self.assertEqual(env[name], name.lower())
        self.assertEqual((env["LC_ALL"], env["LC_CTYPE"]), ("C", "C.UTF-8"))
        self.assertNotIn("LCX", env)
        self.assertNotIn("SKM_OTHER", env)

    def test_service_variables(self):
        env, _ = clean_environment({}, trusted=False)
        self.assertEqual((env["SKM_EXT_PROTOCOL"], env["SKM_EXT_TRUSTED"]), ("1", "0"))
        env, _ = clean_environment({}, trusted=True)
        self.assertEqual(env["SKM_EXT_TRUSTED"], "1")

    def test_service_variables_cannot_come_from_the_source_or_extra(self):
        env, _ = clean_environment({"SKM_EXT_TRUSTED": "1", "SKM_EXT_PROTOCOL": "9"})
        self.assertEqual((env["SKM_EXT_PROTOCOL"], env["SKM_EXT_TRUSTED"]), ("1", "0"))
        for bad in ({"SKM_EXT_TRUSTED": "1"}, {"OTHER": "x"}, {"SKM_OK": 1}):
            with self.assertRaises(ValueError):
                clean_environment({}, extra=bad)

    def test_extra_variables_are_added(self):
        env, _ = clean_environment({}, extra={"SKM_EVENT_TYPE": "demo.done"})
        self.assertEqual(env["SKM_EVENT_TYPE"], "demo.done")

    def test_source_is_not_modified(self):
        source = {"PATH": "/bin", "OTHER": "x"}
        clean_environment(source, permissions={"env": ["OTHER"]}, trusted=True)
        self.assertEqual(source, {"PATH": "/bin", "OTHER": "x"})


class TestPermissionsEnv(unittest.TestCase):
    source = {"PATH": "/bin", "MY_SETTING": "on", "OTHER": "x"}

    def test_trusted_receives_listed_names(self):
        env, _ = clean_environment(self.source, permissions={"env": ["MY_SETTING", "ABSENT"]}, trusted=True)
        self.assertEqual(env["MY_SETTING"], "on")
        self.assertNotIn("OTHER", env)
        self.assertNotIn("ABSENT", env)

    def test_untrusted_request_is_ignored_and_reported(self):
        permissions = {"env": ["MY_SETTING"], "secrets": ["env://MY_TOKEN"]}
        env, secrets = clean_environment(self.source, permissions=permissions, trusted=False)
        self.assertNotIn("MY_SETTING", env)
        self.assertEqual(secrets, [])
        notes = ignored_requests(permissions, trusted=False)
        self.assertEqual(len(notes), 2)
        self.assertTrue(any("MY_SETTING" in note for note in notes))
        self.assertEqual(ignored_requests(permissions, trusted=True), [])
        self.assertEqual(ignored_requests(None, trusted=False), [])

    def test_reserved_names_cannot_be_requested(self):
        env, _ = clean_environment({"SKM_EXT_PROTOCOL": "9"}, permissions={"env": ["SKM_EXT_PROTOCOL"]},
                                   trusted=True)
        self.assertEqual(env["SKM_EXT_PROTOCOL"], "1")


class TestSecrets(unittest.TestCase):
    source = {"PATH": "/bin", "MY_TOKEN": SENTINEL}

    def test_trusted_receives_env_secret(self):
        env, secrets = clean_environment(self.source, permissions={"secrets": ["env://MY_TOKEN"]}, trusted=True)
        self.assertEqual(env["MY_TOKEN"], SENTINEL)
        self.assertEqual(secrets, [SENTINEL])

    def test_untrusted_does_not_receive_the_secret(self):
        env, secrets = clean_environment(self.source, permissions={"secrets": ["env://MY_TOKEN"]})
        self.assertNotIn("MY_TOKEN", env)
        self.assertEqual(secrets, [])

    def test_secret_comes_from_the_given_source_not_from_os_environ(self):
        os.environ["SKM_TEST_ONLY_IN_OS"] = SENTINEL
        self.addCleanup(os.environ.pop, "SKM_TEST_ONLY_IN_OS", None)
        with self.assertRaises(ConfigError) as caught:
            clean_environment({}, permissions={"secrets": ["env://SKM_TEST_ONLY_IN_OS"]}, trusted=True)
        self.assertEqual(caught.exception.code, "SECRET_UNRESOLVED")

    def test_other_schemes_are_refused_without_the_value(self):
        for ref in ("keyring://service/user", "vault://kv/token"):
            with self.assertRaises(ExtError) as caught:
                clean_environment(self.source, permissions={"secrets": ["env://MY_TOKEN", ref]}, trusted=True)
            self.assertEqual(caught.exception.code, "PLUGIN_SECRET_UNSUPPORTED")
            self.assertNotIn(SENTINEL, str(caught.exception) + repr(caught.exception) + full_trace(caught.exception))

    def test_untrusted_with_unsupported_scheme_is_not_an_error(self):
        env, _ = clean_environment(self.source, permissions={"secrets": ["keyring://a/b"]}, trusted=False)
        self.assertEqual(env["SKM_EXT_TRUSTED"], "0")

    def test_unresolved_and_invalid_refs_do_not_leak(self):
        for ref, code in (("env://MISSING", "SECRET_UNRESOLVED"), ("not a ref", "SECRET_REF_INVALID")):
            with self.assertRaises(ConfigError) as caught:
                clean_environment(self.source, permissions={"secrets": [ref]}, trusted=True)
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn(SENTINEL, str(caught.exception) + full_trace(caught.exception))

    def test_sentinel_is_only_in_the_two_intended_places(self):
        env, secrets = clean_environment(self.source, permissions={"secrets": ["env://MY_TOKEN"],
                                                                   "env": ["PATH"]}, trusted=True)
        self.assertEqual([name for name, value in env.items() if value == SENTINEL], ["MY_TOKEN"])
        self.assertEqual(secrets, [SENTINEL])


class TestProfile(unittest.TestCase):
    def test_trusted_local_is_default_and_not_enforced(self):
        self.assertEqual(effective_profile(None), {"profile": "trusted-local", "enforced": False})
        self.assertEqual(effective_profile({}), {"profile": "trusted-local", "enforced": False})
        self.assertEqual(effective_profile({"profile": "trusted-local"})["enforced"], False)

    def test_read_only_is_unavailable(self):
        with self.assertRaises(ExtError) as caught:
            effective_profile({"profile": "read-only"})
        self.assertEqual(caught.exception.code, "PLUGIN_PROFILE_UNAVAILABLE")
        self.assertIn("PLUGIN_PROFILE_UNAVAILABLE", CODES)

    def test_unknown_profile_is_refused(self):
        with self.assertRaises(ExtError):
            effective_profile({"profile": "paranoid"})


class TestChildSeesTheCleanedEnvironment(unittest.TestCase):
    def test_child_gets_only_the_allowed_names_and_stderr_is_redacted(self):
        source = dict(os.environ, AWS_SECRET_ACCESS_KEY=SENTINEL, MY_TOKEN=SENTINEL)
        env, secrets = clean_environment(source, permissions={"secrets": ["env://MY_TOKEN"]}, trusted=True)
        code = "import json, os, sys; sys.stderr.write(os.environ['MY_TOKEN']); " \
               "json.dump({'names': sorted(os.environ)}, sys.stdout)"
        result = run_json([sys.executable, "-c", code], {}, deadline_s=10, env=env, cwd=None,
                          secrets_to_redact=secrets)
        self.assertTrue(result.ok, result)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", result.document["names"])
        self.assertIn("MY_TOKEN", result.document["names"])
        self.assertEqual(result.stderr_tail, "***")
        self.assertNotIn(SENTINEL, repr(result))

    def test_untrusted_child_does_not_see_the_secret(self):
        source = {"PATH": os.environ.get("PATH", ""), "MY_TOKEN": SENTINEL}
        env, _ = clean_environment(source, permissions={"secrets": ["env://MY_TOKEN"]}, trusted=False)
        result = run_json([sys.executable, str(SHOW_ENV)], {}, deadline_s=10, env=env, cwd=None)
        self.assertTrue(result.ok, result)
        self.assertNotIn("MY_TOKEN", result.document["names"])
        self.assertIn("SKM_EXT_TRUSTED", result.document["names"])


if __name__ == "__main__":
    unittest.main()
