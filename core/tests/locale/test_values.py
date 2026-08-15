import unittest
from core.locale.values import SURFACES


class ValueTests(unittest.TestCase):
    def test_surface_order_is_frozen(self):
        self.assertEqual(SURFACES, ("response", "plan", "diagnostics"))
