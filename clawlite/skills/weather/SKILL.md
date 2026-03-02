---
name: weather
description: Get current weather and forecast with the weather script binding.
always: false
metadata: {"clawlite":{"emoji":"🌤️"}}
script: weather
---

# Weather

Use this skill for weather requests.

Input:
- `location` (preferred) or `input` as fallback.

Behavior:
- Calls weather source and returns a concise line.
- If location is missing, default location is used.
