# scripts/terminal_template.py
"""HTML template da janela terminal macOS-style para o demo GIF. Tema Catppuccin Mocha."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class TermLine:
    text: str
    color: str | None = None
    bold: bool = False
    indent: int = 0


PROMPT_GREEN     = "#a6e3a1"
PROMPT_CMD_COLOR = "#89b4fa"
PROMPT_ARG_COLOR = "#89dceb"
_PROMPT_PREFIX   = "❯"
_FULL_CMD        = "clawlite"
_FULL_RUN        = " run "
_FULL_ARG        = '"o que você pode fazer?"'


def build_html(
    *,
    lines: list[TermLine],
    width: int = 720,
    height: int = 400,
    show_prompt: bool = True,
    partial_prompt: str | None = None,
    show_cursor: bool = False,
    spinner: str | None = None,
) -> str:
    lines_html   = _render_lines(lines)
    spinner_html = f'<div class="spinner">{spinner}</div>' if spinner else ""

    if partial_prompt is not None:
        prompt_html = _render_prompt_partial(partial_prompt, show_cursor)
    elif show_prompt:
        cursor_html = '<span class="cursor">█</span>' if show_cursor else ""
        prompt_html = (
            f'<div class="line prompt-line">'
            f'<span style="color:{PROMPT_GREEN}">{_PROMPT_PREFIX}</span> '
            f'<span style="color:{PROMPT_CMD_COLOR}">{_FULL_CMD}</span>'
            f'{_FULL_RUN}'
            f'<span style="color:{PROMPT_ARG_COLOR}">{_FULL_ARG}</span>'
            f'{cursor_html}</div>'
        )
    else:
        prompt_html = ""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ width: {width}px; height: {height}px; background: #181825; display: flex; align-items: center; justify-content: center; font-family: 'Courier New', Courier, monospace; }}
  .window {{ width: {width - 40}px; background: #1e1e2e; border-radius: 10px; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.6); }}
  .titlebar {{ background: #2a2a3e; padding: 10px 14px; display: flex; align-items: center; gap: 7px; border-bottom: 1px solid #313244; }}
  .dot {{ width: 12px; height: 12px; border-radius: 50%; }}
  .dot-red    {{ background: #ff5f57; }}
  .dot-yellow {{ background: #febc2e; }}
  .dot-green  {{ background: #28c840; }}
  .title {{ margin-left: auto; font-size: 12px; color: #585b70; letter-spacing: 0.3px; }}
  .content {{ padding: 18px 20px; font-size: 13px; line-height: 1.8; color: #cdd6f4; min-height: 200px; }}
  .line {{ white-space: pre-wrap; }}
  .prompt-line {{ margin-bottom: 8px; }}
  .spinner {{ color: #6c7086; margin: 4px 0 8px; }}
  .cursor {{ display: inline-block; background: #cdd6f4; color: #1e1e2e; margin-left: 2px; width: 8px; }}
</style>
</head>
<body>
  <div class="window">
    <div class="titlebar">
      <div class="dot dot-red"></div>
      <div class="dot dot-yellow"></div>
      <div class="dot dot-green"></div>
      <span class="title">clawlite — terminal</span>
    </div>
    <div class="content">
      {prompt_html}
      {spinner_html}
      {lines_html}
    </div>
  </div>
</body>
</html>"""


def _render_prompt_partial(partial: str, show_cursor: bool) -> str:
    cursor_html = '<span class="cursor">█</span>' if show_cursor else ""
    cmd_len = len(_FULL_CMD)
    run_len = len(_FULL_CMD) + len(_FULL_RUN)

    if len(partial) <= cmd_len:
        body = f'<span style="color:{PROMPT_CMD_COLOR}">{partial}</span>'
    elif len(partial) <= run_len:
        rest = partial[cmd_len:]
        body = f'<span style="color:{PROMPT_CMD_COLOR}">{_FULL_CMD}</span>{rest}'
    else:
        arg_part = partial[run_len:]
        body = (
            f'<span style="color:{PROMPT_CMD_COLOR}">{_FULL_CMD}</span>'
            f'{_FULL_RUN}'
            f'<span style="color:{PROMPT_ARG_COLOR}">{arg_part}</span>'
        )

    return (
        f'<div class="line prompt-line">'
        f'<span style="color:{PROMPT_GREEN}">{_PROMPT_PREFIX}</span> '
        f'{body}{cursor_html}</div>'
    )


def _render_lines(lines: list[TermLine]) -> str:
    parts = []
    for line in lines:
        indent = "&nbsp;" * (line.indent * 2)
        text = line.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        weight = "font-weight:bold;" if line.bold else ""
        if line.color:
            parts.append(f'<div class="line">{indent}<span style="color:{line.color};{weight}">{text}</span></div>')
        else:
            style = f' style="{weight}"' if weight else ""
            parts.append(f'<div class="line"{style}>{indent}{text}</div>')
    return "\n".join(parts)
