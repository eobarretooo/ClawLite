from __future__ import annotations
import shutil
import subprocess

SKILL_NAME = "web-search"
SKILL_DESCRIPTION = "This skill should be used when users need to search the web for information, find current content, look up news articles, search for images, or find videos. It uses DuckDuckGo's search API to return results in clean, formatted output (text, markdown, or JSON). Use for research, fact-checking, finding recent information, or gathering web resources."

def run(command: str = "") -> str:
    if not command:
        return f"{SKILL_NAME} pronta. {SKILL_DESCRIPTION}"
    proc = subprocess.run(command, shell=True, text=True, capture_output=True)
    if proc.returncode != 0:
        return proc.stderr.strip() or "erro"
    return proc.stdout.strip()

def info() -> str:
    return '---\nname: web-search\ndescription: This skill should be used when users need to search the web for information, find current content, look up news articles, search for images, or find videos. It uses DuckDuckGo\'s search API to return results in clean, formatted output (text, markdown, or JSON). Use for research, fact-checking, finding recent information, or gathering web resources.\n---\n# Web Search\n## Overview\nSearch the web using DuckDuckGo\'s API to find information across web pages, news articles, images, and videos. Returns results in multiple formats (text, markdown, JSON) with filtering options for time range, region, and safe search.\n## When to Use This Skill\nUse this skill when users request:\n- Web searches for information or resources\n- Finding current or recent information online\n- Looking up news articles about specific topics\n- Searching for images by description or topic\n- Finding videos on specific subjects\n- Research requiring current web data\n- Fact-checking or verification using web sources\n- Gathering URLs and resources on a topic\n## Prerequisites\nInstall the required dependency:\n```bash\npip install duckduckgo-search\n```\nThis library provides a simple Python interface to DuckDuckGo\'s search API without requiring API keys or authentication.\n## Core Capabilities\n### 1. Basic Web Search\nSearch for web pages and information:\n```bash\npython scripts/search.py "<query>"\n```\n**Example:**\n```bash\npython scripts/search.py "python asyncio tutorial"\n```\nReturns the top 10'
