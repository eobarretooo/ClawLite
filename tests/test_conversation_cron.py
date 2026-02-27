from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from clawlite.runtime import multiagent
from clawlite.runtime.conversation_cron import add_cron_job, list_cron_jobs, remove_cron_job, run_cron_jobs


class ConversationCronTests(unittest.TestCase):
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

    def test_add_list_remove_job(self) -> None:
        job_id = add_cron_job(
            channel="telegram",
            chat_id="123",
            thread_id="",
            label="general",
            name="heartbeat",
            text="ping",
            interval_seconds=60,
        )
        rows = list_cron_jobs(chat_id="123")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, job_id)
        self.assertEqual(rows[0].name, "heartbeat")

        self.assertTrue(remove_cron_job(job_id))
        self.assertEqual(list_cron_jobs(chat_id="123"), [])

    def test_run_job_enqueues_task_for_conversation(self) -> None:
        multiagent.upsert_worker("telegram", "123", "", "general", 'clawlite run "{text}"')
        add_cron_job(
            channel="telegram",
            chat_id="123",
            thread_id="",
            label="general",
            name="daily",
            text="status diário",
            interval_seconds=30,
        )

        results = run_cron_jobs(run_all=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "enqueued")
        self.assertIsNotNone(results[0].task_id)

        with sqlite3.connect(multiagent.DB_PATH) as conn:
            count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
