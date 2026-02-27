from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawlite.config import settings
from clawlite.runtime.battery import effective_poll_seconds, get_battery_mode, set_battery_mode


class BatteryModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_dir = settings.CONFIG_DIR
        self.old_path = settings.CONFIG_PATH
        settings.CONFIG_DIR = Path(self.tmp.name) / "cfg"
        settings.CONFIG_PATH = settings.CONFIG_DIR / "config.json"

    def tearDown(self) -> None:
        settings.CONFIG_DIR = self.old_dir
        settings.CONFIG_PATH = self.old_path
        self.tmp.cleanup()

    def test_set_and_apply_battery_throttling(self) -> None:
        mode = set_battery_mode(enabled=True, throttle_seconds=8.0)
        self.assertTrue(mode["enabled"])
        self.assertEqual(mode["throttle_seconds"], 8.0)

        loaded = get_battery_mode()
        self.assertTrue(loaded["enabled"])
        self.assertEqual(effective_poll_seconds(2.0), 8.0)

    def test_disabled_mode_keeps_base_poll(self) -> None:
        set_battery_mode(enabled=False, throttle_seconds=9.0)
        self.assertEqual(effective_poll_seconds(2.5), 2.5)


if __name__ == "__main__":
    unittest.main()
