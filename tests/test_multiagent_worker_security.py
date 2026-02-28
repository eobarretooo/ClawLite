from __future__ import annotations

import subprocess
import sys
import unittest

from clawlite.runtime.multiagent import _render_command_args


class MultiagentWorkerSecurityTests(unittest.TestCase):
    def test_render_command_args_keeps_text_as_single_argument(self) -> None:
        args = _render_command_args(
            f"{sys.executable} -c \"import sys; print(sys.argv[1])\" {{text}}",
            {"text": "olá mundo", "channel": "telegram"},
        )
        proc = subprocess.run(args, capture_output=True, text=True, check=True)
        self.assertEqual(proc.stdout.strip(), "olá mundo")

    def test_render_command_args_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValueError):
            _render_command_args("echo {unknown}", {"text": "ok"})

    def test_shell_metacharacters_are_not_executed(self) -> None:
        text = 'safe; echo INJECTED'
        args = _render_command_args(
            f"{sys.executable} -c \"import sys; print(sys.argv[1])\" {{text}}",
            {"text": text, "channel": "telegram"},
        )
        proc = subprocess.run(args, capture_output=True, text=True, check=True)
        self.assertEqual(proc.stdout.strip(), text)


if __name__ == "__main__":
    unittest.main()
