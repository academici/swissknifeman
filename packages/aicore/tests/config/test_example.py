"""Generation of config.example.toml from a schema."""
import unittest
from pathlib import Path

from aicore import config
from aicore.config import example, units

from .support import SCHEMA_FILE, demo_schema

EXPECTED = '''\
# demo configuration, generated from configs/config.schema.json; do not edit by hand.
# Copy into ~/.local/share/swissknifeman/config/config.toml or <project>/.swissknifeman/config.toml
# (swissknifeman config init does it) and uncomment the keys you change.
schema_version = 1

[demo]
# Print details. Boolean.
# verbose = false

# Run mode. One of: "fast", "safe".
# mode = "safe"

# Where to read from. Array of strings.
# sources = ["local"]

# Reference to the API token. Secret reference of the form <scheme>://<name>.
# token = "env://NAME"

# Machine-local cache directory; never set per project. String.
# Allowed in layers: defaults, machine.
# cache_dir = ""

[demo.recompute]
# Smallest sample that makes a candidate. Integer >= 1 and <= 1000.
# candidate_min_n = 15

# Share of agreeing samples. Number >= 0 and <= 1.
# ratio = 0.5

[demo.recompute.window]
# Length of the window in days. Integer >= 1.
# days = 7

[demo.limits]
# Retry count; unset by default. Integer >= 0.
# retries = <integer>
'''


class TestExample(unittest.TestCase):
    def test_exact_text(self):
        self.assertEqual(EXPECTED, example.render(demo_schema()))

    def test_deterministic(self):
        self.assertEqual(example.render(demo_schema()), example.render(demo_schema()))

    def test_example_is_a_valid_empty_layer(self):
        parsed = config.toml.loads(example.render(demo_schema()))
        self.assertEqual({"schema_version": 1, "demo": {"recompute": {"window": {}}, "limits": {}}}, parsed)

    def test_sections_have_no_version_line_or_header(self):
        text = example.render_sections(demo_schema())
        self.assertTrue(text.startswith("[demo]\n"))
        self.assertNotIn("schema_version", text)

    def test_render_unit_uses_declared_schema_path(self):
        info = units.load_unit(Path(SCHEMA_FILE).parent / "units" / "demo")
        self.assertEqual(EXPECTED, example.render_unit(info))
