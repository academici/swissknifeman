import unittest
from core.provider.control_plane import CONTROL_PLANE_VERSION


class ControlPlaneTests(unittest.TestCase):
    def test_locale_boundary_keeps_control_plane_version(self):
        self.assertEqual(CONTROL_PLANE_VERSION, "1.0.0")
