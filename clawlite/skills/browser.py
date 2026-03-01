from __future__ import annotations

from clawlite.skills._safe_exec import parse_command, safe_run, require_bin

SKILL_NAME = "browser"
SKILL_DESCRIPTION = 'Skill imported from OpenClaw archive.'


def run(command: str = "") -> str:
    """Executa a skill de forma segura (sem shell=True)."""
    if not command:
        return f"{SKILL_NAME} pronta. {SKILL_DESCRIPTION}"
    try:
        args = parse_command(command)
    except ValueError as exc:
        return str(exc)
    return safe_run(args)


def info() -> str:
    return '# Skill: browser-history — Search Chrome History\nSearch Das\'s Chrome browsing history to find URLs, videos, sites he\'s visited before.\n## Chrome History Location\n```\n~/Library/Application Support/Google/Chrome/Default/History\n```\nSQLite database. Can be queried directly if Chrome isn\'t locking it.\n---\n## Search Commands\n### Basic search (URL or title contains term)\n```bash\nsqlite3 ~/Library/Application\\ Support/Google/Chrome/Default/History \\\n  "SELECT url, title FROM urls WHERE url LIKE \'%TERM%\' OR title LIKE \'%TERM%\' ORDER BY last_visit_time DESC LIMIT 10;"\n```\n### YouTube videos only\n```bash\nsqlite3 ~/Library/Application\\ Support/Google/Chrome/Default/History \\\n  "SELECT url, title FROM urls WHERE url LIKE \'%youtube.com/watch%\' AND (url LIKE \'%TERM%\' OR title LIKE \'%TERM%\') ORDER BY last_visit_time DESC LIMIT 10;"\n```\n### Most visited (all time)\n```bash\nsqlite3 ~/Library/Application\\ Support/Google/Chrome/Default/History \\\n  "SELECT url, title, visit_count FROM urls ORDER BY visit_count DESC LIMIT 20;"\n```\n### Recent visits\n```bash\nsqlite3 ~/Library/Application\\ Support/Google/Chrome/Default/History \\\n  "SELECT url, title FROM urls ORDER BY last_visit_time DESC LIMIT 20;"\n```\n---\n## If Database is Locked\nChrome locks the History file while running. Options:\n1. **Copy first:**\n   ```bash\n   cp ~/Library/Application\\ Support/Google/Chrome/Default/History /tmp/chrome_history\n   sqlite3 /tmp/chrome_history "SELECT ..."\n   ```\n2. **Use WAL mode** (usually works even when Chrome'
