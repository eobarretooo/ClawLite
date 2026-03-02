---
name: weather
description: Get current weather for a location using the built-in weather script binding.
always: false
metadata: {"clawlite":{"emoji":"🌤️"}}
script: weather
---

# Weather

Use this skill for weather requests.

## Input

- `location` (preferred)
- `input` (fallback)

## Behavior

- Dispatches to `script: weather` handled by ClawLite.
- Returns a concise weather line.
- Defaults to Sao Paulo when no location is provided.
