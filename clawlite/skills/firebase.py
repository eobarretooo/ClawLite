from __future__ import annotations

from clawlite.skills._safe_exec import parse_command, safe_run, require_bin

SKILL_NAME = "firebase"
SKILL_DESCRIPTION = '|'


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
    return '---\nname: firebase\ndescription: |\n  Firebase Management API integration with managed OAuth. Manage Firebase projects, web apps, Android apps, and iOS apps.\n  Use this skill when users want to list Firebase projects, create or manage apps, get app configurations, or link Google Analytics.\n  For other third party apps, use the api-gateway skill (https://clawhub.ai/byungkyu/api-gateway).\ncompatibility: Requires network access and valid Maton API key\nmetadata:\n  author: maton\n  version: "1.0"\n  clawdbot:\n    emoji: 🧠\n    homepage: "https://maton.ai"\n    requires:\n      env:\n        - MATON_API_KEY\n---\n# Firebase\nAccess the Firebase Management API with managed OAuth authentication. Manage Firebase projects and apps (Web, Android, iOS) with full CRUD operations.\n## Quick Start\n```bash\n# List Firebase projects\npython <<\'EOF\'\nimport urllib.request, os, json\nreq = urllib.request.Request(\'https://gateway.maton.ai/firebase/v1beta1/projects\')\nreq.add_header(\'Authorization\', f\'Bearer {os.environ["MATON_API_KEY"]}\')\nprint(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))\nEOF\n```\n## Base URL\n```\nhttps://gateway.maton.ai/firebase/{native-api-path}\n```\nReplace `{native-api-path}` with the actual Firebase Management API endpoint path. The gateway proxies requests to `firebase.googleapis.com` and automatically injects your OAuth token.\n## Authentication\nAll requests require the Maton API key in the Authorization header:\n```\nAuthorization: Bearer $MATON_API_KEY\n```\n**Environment Vari'
