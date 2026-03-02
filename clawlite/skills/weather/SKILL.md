---
name: weather
description: Get current weather and forecast without API key.
always: false
metadata: {"clawlite":{"emoji":"🌤️","requires":{"bins":["curl"]}}}
script: weather
---

# Weather

Use this skill for weather requests.

## Primary source: wttr.in

Current condition:
```bash
curl -s "wttr.in/Sao+Paulo?format=3"
```

Detailed line:
```bash
curl -s "wttr.in/Sao+Paulo?format=%l:+%c+%t+%h+%w"
```

## Fallback source: Open-Meteo

```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=-23.55&longitude=-46.63&current_weather=true"
```

When ambiguity exists, confirm location and timezone before responding.
