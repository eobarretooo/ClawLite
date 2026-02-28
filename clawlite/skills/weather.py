from __future__ import annotations

from clawlite.skills._safe_exec import parse_command, safe_run, require_bin

SKILL_NAME = "weather"
SKILL_DESCRIPTION = 'Get current weather and forecasts (no API key required).'


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
    return '---\nname: weather\ndescription: Get current weather and forecasts (no API key required).\nhomepage: https://wttr.in/:help\nmetadata: {"clawdbot":{"emoji":"🌤️","requires":{"bins":["curl"]}}}\n---\n# Weather\nTwo free services, no API keys needed.\n## wttr.in (primary)\nQuick one-liner:\n```bash\ncurl -s "wttr.in/London?format=3"\n# Output: London: ⛅️ +8°C\n```\nCompact format:\n```bash\ncurl -s "wttr.in/London?format=%l:+%c+%t+%h+%w"\n# Output: London: ⛅️ +8°C 71% ↙5km/h\n```\nFull forecast:\n```bash\ncurl -s "wttr.in/London?T"\n```\nFormat codes: `%c` condition · `%t` temp · `%h` humidity · `%w` wind · `%l` location · `%m` moon\nTips:\n- URL-encode spaces: `wttr.in/New+York`\n- Airport codes: `wttr.in/JFK`\n- Units: `?m` (metric) `?u` (USCS)\n- Today only: `?1` · Current only: `?0`\n- PNG: `curl -s "wttr.in/Berlin.png" -o /tmp/weather.png`\n## Open-Meteo (fallback, JSON)\nFree, no key, good for programmatic use:\n```bash\ncurl -s "https://api.open-meteo.com/v1/forecast?latitude=51.5&longitude=-0.12&current_weather=true"\n```\nFind coordinates for a city, then query. Returns JSON with temp, windspeed, weathercode.\nDocs: https://open-meteo.com/en/docs'
