from __future__ import annotations
import pytest


def test_build_frames_spec_structure():
    from scripts.make_demo_gif import build_frames_spec
    spec = build_frames_spec()
    assert isinstance(spec, list)
    assert len(spec) == 16
    for item in spec:
        assert "lines" in item
        assert "delay_ms" in item
        assert item["delay_ms"] > 0


def test_build_frames_spec_has_typing_frames():
    from scripts.make_demo_gif import build_frames_spec
    spec = build_frames_spec()
    typing_frames = [f for f in spec if f.get("partial_prompt")]
    assert len(typing_frames) >= 5


def test_build_frames_spec_has_final_pause():
    from scripts.make_demo_gif import build_frames_spec
    spec = build_frames_spec()
    assert spec[-1]["delay_ms"] >= 2000


@pytest.mark.slow
def test_make_demo_gif_generates_file(tmp_path):
    from scripts.make_demo_gif import make_demo_gif
    output = tmp_path / "demo.gif"
    make_demo_gif(output_path=str(output))
    assert output.exists()
    assert output.stat().st_size > 50_000
