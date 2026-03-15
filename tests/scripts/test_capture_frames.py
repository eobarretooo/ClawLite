from __future__ import annotations
import shutil
import pytest
from scripts.terminal_template import TermLine

# Skip entire module if playwright chromium binary is not installed
def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            path = pw.chromium.executable_path
            return shutil.which(path) is not None or __import__("pathlib").Path(path).exists()
    except Exception:
        return False

pytestmark = pytest.mark.skipif(not _chromium_available(), reason="playwright chromium binary not installed")


def test_capture_returns_bytes_list():
    from scripts.capture_frames import capture_frames
    frames_spec = [
        {"lines": [], "show_cursor": True, "delay_ms": 500},
        {"lines": [TermLine("hello", color=None)], "delay_ms": 800},
    ]
    frames = capture_frames(frames_spec)
    assert len(frames) == 2
    for png_bytes, delay_ms in frames:
        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 1000
        assert png_bytes[:4] == b'\x89PNG'
        assert delay_ms > 0


def test_capture_correct_delays():
    from scripts.capture_frames import capture_frames
    frames_spec = [{"lines": [], "delay_ms": 300}, {"lines": [], "delay_ms": 1500}]
    frames = capture_frames(frames_spec)
    assert frames[0][1] == 300
    assert frames[1][1] == 1500


def test_capture_partial_prompt_frame():
    from scripts.capture_frames import capture_frames
    frames_spec = [{"lines": [], "partial_prompt": "clawlite", "show_cursor": True, "delay_ms": 80}]
    frames = capture_frames(frames_spec)
    assert frames[0][0][:4] == b'\x89PNG'
