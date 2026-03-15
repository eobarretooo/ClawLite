from __future__ import annotations
import io
from PIL import Image


def _make_fake_png(color: tuple, width: int = 720, height: int = 400) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_assemble_creates_gif(tmp_path):
    from scripts.assemble_gif import assemble_gif
    frames = [(_make_fake_png((30, 30, 46)), 500), (_make_fake_png((137, 180, 250)), 800)]
    output = tmp_path / "test.gif"
    assemble_gif(frames, output_path=str(output))
    assert output.exists()
    assert output.stat().st_size > 1000


def test_assemble_gif_loops_forever(tmp_path):
    from scripts.assemble_gif import assemble_gif
    frames = [(_make_fake_png((30, 30, 46)), 500), (_make_fake_png((50, 50, 70)), 500)]
    output = tmp_path / "loop.gif"
    assemble_gif(frames, output_path=str(output))
    img = Image.open(str(output))
    assert img.info.get("loop") == 0, f"esperado loop=0, got: {img.info.get('loop')!r}"


def test_assemble_gif_frame_count(tmp_path):
    from scripts.assemble_gif import assemble_gif
    frames = [(_make_fake_png((i * 20, i * 20, i * 20)), 200) for i in range(5)]
    output = tmp_path / "frames.gif"
    assemble_gif(frames, output_path=str(output))
    img = Image.open(str(output))
    count = 0
    try:
        while True:
            count += 1
            img.seek(img.tell() + 1)
    except EOFError:
        pass
    assert count == 5
