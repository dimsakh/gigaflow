import unittest

from gigaflow.ui.overlay import OVERLAY_HEIGHT, OVERLAY_WIDTH


class OverlayLayoutTests(unittest.TestCase):
    def test_overlay_is_compact(self):
        self.assertLessEqual(OVERLAY_WIDTH, 220)
        self.assertLessEqual(OVERLAY_HEIGHT, 52)


if __name__ == "__main__":
    unittest.main()
