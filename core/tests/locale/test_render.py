import unittest
from core.locale import Catalog, render_message


class RenderTests(unittest.TestCase):
    def test_result_is_typed_and_falls_back(self):
        result = render_message(Catalog("en", {"diagnostic.safe": "Safe"}), None, "diagnostic.safe")
        self.assertEqual(result["resolved_locale"], "en")
