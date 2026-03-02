---
name: web-search
description: Search and validate up-to-date information with source links.
always: false
metadata: {"clawlite":{"emoji":"🔎"}}
script: web_search
---

# Web Search

Use this skill when the user asks for latest/current information or needs source attribution.

## Rules

- Prefer primary sources (official docs, project pages, original announcements).
- Include links in the answer.
- Distinguish fact from inference.
- For unstable information (prices, releases, schedules), verify before answering.

Use the `web_search` tool first; use `web_fetch` when full page details are needed.
