# scripts/make_demo_gif.py
"""Gera docs/demo.gif — demo animada do ClawLite para o README.

Uso:
    python3 scripts/make_demo_gif.py
    python3 scripts/make_demo_gif.py --output /caminho/custom.gif

16 frames: digitação → cursor piscando → spinner → resposta em streaming.
Sem API key — tudo scripted.
"""
from __future__ import annotations
import argparse
from pathlib import Path

from scripts.terminal_template import TermLine, _FULL_CMD, _FULL_RUN, _FULL_ARG
from scripts.capture_frames import capture_frames
from scripts.assemble_gif import assemble_gif

_BLUE = "#89b4fa"
_GRAY = "#6c7086"

_DEFAULT_OUTPUT = Path(__file__).parent.parent / "docs" / "demo.gif"

_TYPING_STATES = [
    "c",
    _FULL_CMD,
    _FULL_CMD + _FULL_RUN.rstrip(),
    _FULL_CMD + _FULL_RUN + '"o que você',
    _FULL_CMD + _FULL_RUN + _FULL_ARG,
]


def build_frames_spec() -> list[dict]:
    intro = TermLine("Posso ajudar com muita coisa! Aqui o resumo:")
    bullets = [
        TermLine("🧠 Memória  — lembro do que conversamos entre sessões", color=_BLUE),
        TermLine("🔍 Busca    — pesquiso na web em tempo real",           color=_BLUE),
        TermLine("💻 Código   — escrevo, reviso e executo scripts",       color=_BLUE),
        TermLine("📂 Arquivos — leio, crio e edito arquivos locais",      color=_BLUE),
        TermLine("📡 Canais   — respondo no Telegram e Discord",          color=_BLUE),
    ]
    footer = TermLine("Use clawlite skills list para ver tudo.", color=_GRAY)

    frames: list[dict] = []

    # Frames 1-5: typing (80ms each)
    for state in _TYPING_STATES:
        frames.append({"lines": [], "partial_prompt": state, "show_cursor": True, "delay_ms": 80})

    # Frames 6-7: cursor blink (400ms each) — frame 6 cursor off (distinct from frame 5)
    frames.append({"lines": [], "show_cursor": False, "delay_ms": 400})
    frames.append({"lines": [], "show_cursor": True,  "delay_ms": 400})

    # Frames 8-9: spinner (800ms each)
    frames.append({"lines": [], "show_cursor": False, "spinner": "⠸ pensando...", "delay_ms": 800})
    frames.append({"lines": [], "show_cursor": False, "spinner": "⠴ pensando...", "delay_ms": 800})

    # Frame 10: intro
    frames.append({"lines": [intro], "delay_ms": 600})

    # Frames 11-15: bullets progressive
    for i in range(len(bullets)):
        frames.append({"lines": [intro] + bullets[: i + 1], "delay_ms": 520})

    # Frame 16: footer + final pause
    frames.append({"lines": [intro] + bullets + [TermLine(""), footer], "delay_ms": 3200})

    return frames


def make_demo_gif(*, output_path: str | None = None) -> None:
    out = str(output_path or _DEFAULT_OUTPUT)
    spec = build_frames_spec()
    print(f"⠸ Capturando {len(spec)} frames via Playwright...")
    frames = capture_frames(spec)
    print(f"⠸ Montando GIF em {out} ...")
    assemble_gif(frames, output_path=out)
    size_kb = Path(out).stat().st_size // 1024
    print(f"✓ {out} gerado ({size_kb} KB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gera docs/demo.gif para o README")
    parser.add_argument("--output", default=None, help="Caminho de saída do GIF")
    args = parser.parse_args()
    make_demo_gif(output_path=args.output)
