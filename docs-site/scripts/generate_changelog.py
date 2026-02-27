#!/usr/bin/env python3
from __future__ import annotations
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parents[1] / 'docs' / 'changelog.md'


def main() -> None:
    cmd = ['git', '-C', str(ROOT), 'log', '--pretty=format:%h|%ad|%s', '--date=short', '-n', '120']
    raw = subprocess.check_output(cmd, text=True)
    lines = [l.strip() for l in raw.splitlines() if l.strip()]

    md = [
        '# Changelog',
        '',
        '_Auto-generated from git commits._',
        '',
        '| Commit | Date | Message |',
        '|---|---|---|',
    ]
    for line in lines:
        h, d, s = line.split('|', 2)
        md.append(f'| `{h}` | {d} | {s} |')

    OUT.write_text('\n'.join(md) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
