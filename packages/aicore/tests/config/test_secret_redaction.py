"""The value of a secret never reaches output, repr, error text or a traceback of aicore.config."""
import json
import pickle
import traceback
import unittest
import uuid

from aicore import config
from aicore.config import ConfigError, Secret, secrets

from tests.config.support import Workspace

SENTINEL = "s3cr3t-" + uuid.uuid4().hex


def full_trace(error: BaseException) -> str:
    return "".join(traceback.format_exception(type(error), error, error.__traceback__))


def chain(error: BaseException):
    """The error and everything reachable through __cause__ / __context__."""
    seen = []
    while error is not None and error not in seen:
        seen.append(error)
        error = error.__cause__ or error.__context__
    return seen


class RedactionCase(Workspace):
    def assertClean(self, *texts):
        for text in texts:
            self.assertNotIn(SENTINEL, text)

    def assertErrorClean(self, error):
        self.assertClean(str(error), repr(error), full_trace(error))
        for link in chain(error):
            self.assertClean(str(link), repr(link), repr(link.args))
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)


class TestReferenceHidesTheValue(RedactionCase):
    """Case 1: ``env://NAME`` — nothing printed contains the secret, ``reveal()`` returns it."""

    def setUp(self):
        super().setUp()
        self.env["SKM_TEST_TOKEN"] = SENTINEL
        self.proj("[demo]\ntoken = \"env://SKM_TEST_TOKEN\"\n")

    def test_every_output_form_is_free_of_the_value(self):
        resolved = self.resolve()
        secret = resolved.secret("token")
        outputs = [
            resolved.explain_text(), resolved.explain_text("token"), json.dumps(resolved.explain_json()),
            json.dumps(resolved.as_dict()), repr(resolved), repr(secret), str(secret), f"{secret}", "%s" % secret,
            repr(resolved.explain()), repr(resolved.explain("token")[0]), str(resolved.explain("token")[0]),
            repr(resolved.layers), repr(resolved.warnings), repr(resolved.get("token")), str(resolved.as_dict()),
        ]
        self.assertClean(*outputs)

    def test_the_reference_is_shown_and_the_entry_is_marked(self):
        resolved = self.resolve()
        entry = resolved.explain("token")[0]
        self.assertEqual((entry.value, entry.secret), ("env://SKM_TEST_TOKEN", True))
        self.assertEqual(resolved.get("token"), "env://SKM_TEST_TOKEN")
        self.assertEqual(repr(resolved.secret("token")), "Secret('env://SKM_TEST_TOKEN')")
        self.assertEqual(str(resolved.secret("token")), "***")

    def test_reveal_returns_the_value_and_caches_nothing(self):
        env = dict(self.env)
        secret = self.resolve(env=env).secret("token")
        self.assertEqual(secret.reveal(), SENTINEL)
        env["SKM_TEST_TOKEN"] = SENTINEL + "-rotated"  # the handle reads the mapping given to resolve()
        self.assertEqual(secret.reveal(), SENTINEL + "-rotated")

    def test_resolve_does_not_read_the_secret(self):
        env = {k: v for k, v in self.env.items() if k != "SKM_TEST_TOKEN"}
        resolved = self.resolve(env=env)  # the variable is absent: resolving the config must still work
        with self.assertRaises(ConfigError) as caught:
            resolved.secret("token").reveal()
        self.assertEqual(caught.exception.code, "SECRET_UNRESOLVED")

    def test_secret_handle_state_has_no_value(self):
        secret = self.resolve().secret("token")
        self.assertEqual(secret.ref, "env://SKM_TEST_TOKEN")
        for slot in Secret.__slots__:
            self.assertClean(repr(getattr(secret, slot)))
        self.assertFalse(hasattr(secret, "__dict__"))


class TestPlainValueIsRefused(RedactionCase):
    """Case 2: a plain value in a file is an error that does not repeat it."""

    def test_plain_value_in_the_project_file(self):
        self.proj(f"[demo]\ntoken = \"{SENTINEL}\"\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        error = caught.exception
        self.assertEqual((error.code, error.layer, error.key), ("SECRET_REF_INVALID", "project", "token"))
        self.assertIn("redacted", str(error))
        self.assertErrorClean(error)
        self.assertTrue(str(error).startswith(f"{self.project_file}:3:"))

    def test_plain_value_in_the_machine_file_and_in_an_extra_layer(self):
        self.machine(f"[demo]\ntoken = \"{SENTINEL}\"\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertErrorClean(caught.exception)
        self.machine_file.unlink()
        with self.assertRaises(ConfigError) as caught:
            self.resolve(extra_layers=[config.ExtraLayer("legacy", {"token": SENTINEL})])
        self.assertEqual(caught.exception.code, "SECRET_REF_INVALID")
        self.assertErrorClean(caught.exception)

    def test_wrong_type_on_a_secret_key(self):
        self.proj("[demo]\ntoken = 12345\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "CONFIG_TYPE")
        self.assertNotIn("12345", str(caught.exception))

    def test_plain_value_through_flags_and_parse_value(self):
        with self.assertRaises(ConfigError) as caught:
            self.resolve(flags={"token": SENTINEL})
        self.assertEqual(caught.exception.code, "SECRET_REF_INVALID")
        self.assertErrorClean(caught.exception)
        with self.assertRaises(ConfigError) as caught:
            self.resolve(flags={"token": [SENTINEL]})
        self.assertErrorClean(caught.exception)


class TestEnvironmentCarriesOnlyReferences(RedactionCase):
    """Case 3: the same plain value through ``SKM_<MODULE>_TOKEN``."""

    def test_plain_value_in_the_variable(self):
        with self.assertRaises(ConfigError) as caught:
            self.resolve(env={**self.env, "SKM_DEMO_TOKEN": SENTINEL})
        error = caught.exception
        self.assertEqual((error.code, error.layer), ("SECRET_REF_INVALID", "env"))
        self.assertIn("SKM_DEMO_TOKEN", str(error))
        self.assertErrorClean(error)

    def test_reference_in_the_variable_is_accepted(self):
        env = {**self.env, "SKM_DEMO_TOKEN": "env://SKM_TEST_TOKEN", "SKM_TEST_TOKEN": SENTINEL}
        resolved = self.resolve(env=env)
        self.assertEqual(resolved.secret("token").reveal(), SENTINEL)
        entry = resolved.explain("token")[0]
        self.assertEqual((entry.layer, entry.source), ("env", "SKM_DEMO_TOKEN"))
        self.assertClean(resolved.explain_text(), json.dumps(resolved.explain_json()))


class TestResolverFailure(RedactionCase):
    """Case 4: a resolver that raises with the value in its message leaves no trace."""

    def setUp(self):
        super().setUp()
        self.addCleanup(secrets.unregister_secret_resolver, "vault")

    def test_failing_resolver_gives_secret_unresolved_without_the_cause(self):
        def broken(path):
            raise ValueError(f"bad {SENTINEL}")

        config.register_secret_resolver("vault", broken)
        self.proj("[demo]\ntoken = \"vault://team/api\"\n")
        secret = self.resolve().secret("token")
        with self.assertRaises(ConfigError) as caught:
            secret.reveal()
        error = caught.exception
        self.assertEqual(error.code, "SECRET_UNRESOLVED")
        self.assertIn("vault://team/api", str(error))
        self.assertErrorClean(error)

    def test_resolver_returning_nothing_is_unresolved(self):
        for returned in (None, "", 5):
            with self.subTest(returned=returned):
                secrets.unregister_secret_resolver("vault")
                config.register_secret_resolver("vault", lambda path, value=returned: value)
                self.proj("[demo]\ntoken = \"vault://x\"\n")
                with self.assertRaises(ConfigError) as caught:
                    self.resolve().secret("token").reveal()
                self.assertEqual(caught.exception.code, "SECRET_UNRESOLVED")

    def test_resolver_gets_the_path_and_its_value_is_returned(self):
        seen = []
        config.register_secret_resolver("vault", lambda path: seen.append(path) or SENTINEL)
        self.proj("[demo]\ntoken = \"vault://team/api\"\n")
        self.assertEqual(self.resolve().secret("token").reveal(), SENTINEL)
        self.assertEqual(seen, ["team/api"])

    def test_missing_variable_is_unresolved(self):
        self.proj("[demo]\ntoken = \"env://SKM_TEST_ABSENT\"\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve().secret("token").reveal()
        self.assertEqual(caught.exception.code, "SECRET_UNRESOLVED")
        self.assertIsNone(caught.exception.__context__)

    def test_invalid_variable_name_is_unresolved(self):
        self.proj("[demo]\ntoken = \"env://lower-case\"\n")
        with self.assertRaises(ConfigError) as caught:
            self.resolve().secret("token").reveal()
        self.assertEqual(caught.exception.code, "SECRET_UNRESOLVED")


class TestUnknownScheme(RedactionCase):
    """Case 5: ``keyring://`` is known but has no resolver here."""

    def test_keyring_is_an_unknown_scheme_at_reveal(self):
        self.proj("[demo]\ntoken = \"keyring://demo/token\"\n")
        resolved = self.resolve()  # the file loads; only the use of the secret fails
        with self.assertRaises(ConfigError) as caught:
            resolved.secret("token").reveal()
        error = caught.exception
        self.assertEqual(error.code, "SECRET_SCHEME_UNKNOWN")
        self.assertIn("register a resolver", str(error))
        self.assertIn("resolver plugins arrive with aicore extensions", str(error))
        self.assertNotIn("demo/token", str(error))

    def test_a_url_in_a_secret_key_does_not_leak_through_the_scheme_error(self):
        self.proj(f"[demo]\ntoken = \"https://user:{SENTINEL}@example.org/\"\n")
        resolved = self.resolve()
        with self.assertRaises(ConfigError) as caught:
            resolved.secret("token").reveal()
        self.assertEqual(caught.exception.code, "SECRET_SCHEME_UNKNOWN")
        self.assertErrorClean(caught.exception)

    def test_registering_makes_the_scheme_known(self):
        self.addCleanup(secrets.unregister_secret_resolver, "keyring")
        config.register_secret_resolver("keyring", lambda path: SENTINEL)
        self.proj("[demo]\ntoken = \"keyring://demo/token\"\n")
        self.assertEqual(self.resolve().secret("token").reveal(), SENTINEL)


class TestHandleSemantics(RedactionCase):
    """Case 6: the handle cannot be serialized or compared by value."""

    def test_pickle_is_refused(self):
        secret = Secret("env://SKM_TEST_TOKEN")
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(protocol=protocol):
                with self.assertRaises(TypeError):
                    pickle.dumps(secret, protocol)

    def test_no_comparison_by_value(self):
        self.assertNotEqual(Secret("env://A"), Secret("env://A"))
        secret = Secret("env://A")
        self.assertEqual(secret, secret)

    def test_construction_needs_a_reference(self):
        with self.assertRaises(ConfigError) as caught:
            Secret(SENTINEL)
        self.assertEqual(caught.exception.code, "SECRET_REF_INVALID")
        self.assertErrorClean(caught.exception)

    def test_secret_accessor_checks_the_key(self):
        resolved = self.resolve()
        with self.assertRaises(ConfigError) as caught:
            resolved.secret("mode")
        self.assertEqual(caught.exception.code, "CONFIG_TYPE")
        with self.assertRaises(ConfigError) as caught:
            resolved.secret("token")  # secret key without a reference
        self.assertEqual(caught.exception.code, "SECRET_UNRESOLVED")
        with self.assertRaises(ConfigError):
            resolved.secret("nope")


class TestResolverRegistry(unittest.TestCase):
    def tearDown(self):
        secrets.unregister_secret_resolver("probe")

    def test_a_scheme_registers_once(self):
        config.register_secret_resolver("probe", lambda path: "x")
        with self.assertRaises(ValueError):
            config.register_secret_resolver("probe", lambda path: "y")

    def test_builtin_env_cannot_be_replaced_or_removed(self):
        with self.assertRaises(ValueError):
            config.register_secret_resolver("env", lambda path: "x")
        with self.assertRaises(ValueError):
            secrets.unregister_secret_resolver("env")

    def test_invalid_registration(self):
        for scheme, fn in (("Bad", print), ("1x", print), ("", print), ("probe", "not callable")):
            with self.subTest(scheme=scheme):
                with self.assertRaises(ValueError):
                    config.register_secret_resolver(scheme, fn)

    def test_reference_syntax(self):
        for ref in ("env://A", "keyring://svc/user", "a+b.c-d://x"):
            self.assertTrue(secrets.is_secret_ref(ref), ref)
        for ref in ("env:/A", "://x", "env://", "Env://A", "env://a b", "plain", 5, None):
            self.assertFalse(secrets.is_secret_ref(ref), repr(ref))


if __name__ == "__main__":
    unittest.main()
