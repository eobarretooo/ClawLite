from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from clawlite.runtime import multiagent


class MultiagentRecoveryTests(unittest.TestCase):
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

    def test_is_pid_running_nonexistent(self) -> None:
        with patch("clawlite.runtime.multiagent.os.kill", side_effect=OSError):
            self.assertFalse(multiagent._is_pid_running(999999))

    def test_is_pid_running_zombie_defunct(self) -> None:
        with (
            patch("clawlite.runtime.multiagent.os.kill", return_value=None),
            patch("clawlite.runtime.multiagent._pid_state", return_value="Z"),
        ):
            self.assertFalse(multiagent._is_pid_running(1234))

    def test_is_pid_running_healthy(self) -> None:
        with (
            patch("clawlite.runtime.multiagent.os.kill", return_value=None),
            patch("clawlite.runtime.multiagent._pid_state", return_value="S"),
        ):
            self.assertTrue(multiagent._is_pid_running(1234))

    def test_recover_workers_restarts_when_defunct(self) -> None:
        worker_id = multiagent.upsert_worker(
            channel="telegram",
            chat_id="123",
            thread_id="",
            label="general",
            command_template="echo ok",
            enabled=True,
        )
        multiagent._set_worker_runtime(worker_id, 4321, "running", enabled=1)

        proc = Mock()
        proc.pid = 5678

        with (
            patch("clawlite.runtime.multiagent.os.kill", return_value=None),
            patch("clawlite.runtime.multiagent._pid_state", side_effect=lambda pid: "Z" if pid == 4321 else "S"),
            patch("clawlite.runtime.multiagent.subprocess.Popen", return_value=proc),
        ):
            restarted = multiagent.recover_workers()

        self.assertEqual(restarted, [worker_id])
        worker = multiagent._get_worker(worker_id)
        self.assertEqual(worker.pid, 5678)
        self.assertEqual(worker.status, "running")


if __name__ == "__main__":
    unittest.main()
