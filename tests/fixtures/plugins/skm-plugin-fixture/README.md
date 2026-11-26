# skm-plugin-fixture

Fixture distribution of the plugin loader tests (`tests/unit/bootstrap/test_plugins.py`,
`tests/security/test_plugin_allowlist.py`). It declares one entry point `acme.fixture` with a `runtime`
(`fixture_rt`) and an `isolation` (`acme.fixture:jail`) component, the step 2a data files under
`skm_runtimes/fixture_rt/` and a settings section `plugins.acme.fixture`.

`sentinel.py` records side effects: `import:acme.fixture` when `plugin.py` is imported and
`factory:<kind>` when a factory runs. `unstable.py` imports `skm.modules.*` on purpose (the negative example of
`skm plugins lint`) and is never imported by the plugin.
