from __future__ import annotations
import subprocess
SKILL_NAME='rss'
SKILL_DESCRIPTION="Agentic RSS digest using the feed CLI. Fetch, triage, and summarize RSS feeds to surface high-signal posts. Use when: (1) reading RSS feeds or catching up on news, (2) user asks for a digest, roundup, or summary of recent posts, (3) user asks what's new or interesting today, (4) user mentions feed, RSS, or blogs."
def run(command:str='')->str:
    if not command:
        return f"{SKILL_NAME} pronta. {SKILL_DESCRIPTION}"
    p=subprocess.run(command,shell=True,text=True,capture_output=True)
    return p.stdout.strip() if p.returncode==0 else (p.stderr.strip() or 'erro')
