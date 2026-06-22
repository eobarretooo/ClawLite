---
name: web-search
description: "Search the web for up-to-date information, verify claims against primary sources, and return answers with source attribution links. Use when the user asks about current events, latest releases, real-time data, or needs verified facts with citations."
always: false
metadata: {"clawlite":{"emoji":"🔎"}}
script: web_search
---

# Web Search

Use this skill when the user asks for latest/current information, needs source attribution, or wants to verify claims against live data.

## Workflow

1. **Identify intent**: Determine whether the user needs a quick fact, a comparison, or a deep research summary.
2. **Search**: Run `web_search` with targeted queries — prefer specific terms over broad ones.
3. **Verify**: Cross-reference results against primary sources (official docs, project pages, original announcements). For unstable information (prices, releases, schedules), confirm with at least two sources.
4. **Fetch details**: Use `web_fetch` when search snippets are insufficient and full page content is needed.
5. **Synthesize**: Combine findings into a concise answer with inline source links.

## Source Quality Rules

- Prefer primary sources over aggregators or re-posts.
- Distinguish fact from inference — label uncertain information explicitly.
- Include clickable links for every claim so the user can verify independently.
- When sources conflict, present both perspectives with their respective links.

## Example

User: "What is the latest stable release of Python?"

1. Run `web_search` with query `"Python latest stable release"`.
2. Verify against `python.org` official downloads page.
3. Use `web_fetch` on `https://www.python.org/downloads/` if snippet is outdated.
4. Return: "Python 3.x.x is the latest stable release ([source](https://www.python.org/downloads/))."

## Execution

- `script: web_search` dispatches to the `web_search` tool for search queries.
- Use `web_fetch` when full page content is needed beyond search snippets.
