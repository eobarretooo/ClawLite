from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from clawlite.runtime import multiagent
from clawlite.runtime.conversation_cron import add_cron_job, list_cron_jobs, remove_cron_job, run_cron_jobs
from clawlite.skills.marketplace import install_skill


class ConversationCronTests(unittest.TestCase):
    def _make_skill_zip(self, root: Path, slug: str, version: str, body: str) -> tuple[Path, str]:
        zip_path = root / f"{slug}-{version}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("SKILL.md", body)
        digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        return zip_path, digest

    def _write_index(self, root: Path, entry: dict) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        index_path = root / "manifest.local.json"
        payload = {"schema_version": "1.0", "generated_at": "2026-01-01T00:00:00Z", "skills": [entry]}
        index_path.write_text(json.dumps(payload), encoding="utf-8")
        return index_path

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

    def test_run_system_auto_update_job_executes_runtime_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_dir = root / "installed"
            manifest_path = root / "installed.json"
            archive, checksum = self._make_skill_zip(root, "demo", "1.0.0", "# demo")
            index = self._write_index(
                root / "idx",
                {
                    "slug": "demo",
                    "version": "1.0.0",
                    "download_url": archive.as_uri(),
                    "checksum_sha256": checksum,
                },
            )
            install_skill(
                "demo",
                index_url=index.as_uri(),
                install_dir=install_dir,
                manifest_path=manifest_path,
                allow_file_urls=True,
            )

            payload = json.dumps(
                {
                    "action": "skill-auto-update",
                    "index_url": index.as_uri(),
                    "strict": False,
                    "allow_hosts": [],
                    "manifest_path": str(manifest_path),
                    "install_dir": str(install_dir),
                    "allow_file_urls": True,
                }
            )
            add_cron_job(
                channel="system",
                chat_id="local",
                thread_id="",
                label="skills",
                name="auto-update",
                text=payload,
                interval_seconds=30,
            )

            results = run_cron_jobs(run_all=True)
            self.assertEqual(results[0].status, "executed")

    def test_run_job_without_worker_uses_inline_fallback(self) -> None:
        add_cron_job(
            channel="telegram",
            chat_id="123",
            thread_id="",
            label="general",
            name="inline-fallback",
            text="status agora",
            interval_seconds=30,
        )

        with patch(
            "clawlite.runtime.conversation_cron._run_inline_telegram_fallback",
            return_value=(True, "inline telegram delivery ok"),
        ):
            results = run_cron_jobs(run_all=True)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "executed")
        self.assertIn("inline", results[0].message)


if __name__ == "__main__":
    unittest.main()
