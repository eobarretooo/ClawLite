from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawlite.runtime import multiagent
from clawlite.runtime.notifications import create_notification, infer_priority, list_notifications


class NotificationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_dir = multiagent.DB_DIR
        self.old_db_path = multiagent.DB_PATH
        multiagent.DB_DIR = Path(self.tmp.name) / "clawlite"
        multiagent.DB_PATH = multiagent.DB_DIR / "multiagent.db"

    def tearDown(self) -> None:
        multiagent.DB_DIR = self.old_db_dir
        multiagent.DB_PATH = self.old_db_path
        self.tmp.cleanup()

    def test_priority_inference_and_dedup(self) -> None:
        self.assertEqual(infer_priority("cron_failed"), "high")
        self.assertEqual(infer_priority("cron_enqueued"), "low")

        created, first_id = create_notification(
            event="cron_failed",
            message="worker ausente",
            dedupe_key="cron-failed-123",
            dedupe_window_seconds=120,
        )
        self.assertTrue(created)
        self.assertIsNotNone(first_id)

        created_again, second_id = create_notification(
            event="cron_failed",
            message="worker ausente",
            dedupe_key="cron-failed-123",
            dedupe_window_seconds=120,
        )
        self.assertFalse(created_again)
        self.assertIsNone(second_id)

        rows = list_notifications(limit=10, min_priority="normal")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].priority, "high")


if __name__ == "__main__":
    unittest.main()
