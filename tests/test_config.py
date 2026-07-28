import json
import tempfile
import unittest
from pathlib import Path

from gigaflow.config import AppConfig


class ConfigTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            config = AppConfig(hotkey="alt+space", microphone=3)
            config.save(path)
            loaded = AppConfig.load(path)
            self.assertEqual(loaded.hotkey, "alt+space")
            self.assertEqual(loaded.microphone, 3)
            self.assertEqual(loaded.filler_filter, "soft")

    def test_unknown_fields_are_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({"hotkey": "f8", "future": True}))
            self.assertEqual(AppConfig.load(path).hotkey, "f8")

    def test_performance_settings_are_migrated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "partial_interval_ms": 2800,
                        "auto_finish_silence_seconds": 1.0,
                        "performance_version": 1,
                    }
                )
            )
            loaded = AppConfig.load(path)
            self.assertEqual(loaded.partial_interval_ms, 900)
            self.assertEqual(loaded.auto_finish_silence_seconds, 2.2)
            self.assertEqual(loaded.performance_version, 2)


if __name__ == "__main__":
    unittest.main()
