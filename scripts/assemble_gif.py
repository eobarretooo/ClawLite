# scripts/assemble_gif.py
"""Monta frames PNG em GIF animado usando Pillow."""
from __future__ import annotations
import io
from pathlib import Path
from PIL import Image


def assemble_gif(
    frames: list[tuple[bytes, int]],
    *,
    output_path: str,
    optimize: bool = True,
) -> None:
    if not frames:
        raise ValueError("frames list is empty")
    pil_frames: list[Image.Image] = []
    durations: list[int] = []
    for png_bytes, delay_ms in frames:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        pil_frames.append(img.convert("P", palette=Image.ADAPTIVE, colors=256))
        durations.append(max(20, delay_ms))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    pil_frames[0].save(
        str(output),
        format="GIF",
        save_all=True,
        append_images=pil_frames[1:],
        optimize=optimize,
        loop=0,
        duration=durations,
    )
