---
name: summarize
description: Summarize URLs, local files, and transcripts with the summarize CLI when available.
always: false
homepage: https://summarize.sh
metadata: {"clawlite":{"emoji":"🧾","requires":{"bins":["summarize"]}}}
command: summarize
---

# Summarize

Use this skill when the user asks to summarize an article/file/video or extract transcript-like output quickly.

## Examples

Summarize URL:
```bash
summarize "https://example.com"
```

Summarize local file:
```bash
summarize "/path/to/file.pdf"
```

Summarize YouTube URL:
```bash
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto
```

## Rules

- Preserve hard facts (numbers, deadlines, owners).
- Avoid generic filler.
- If content is too large, return an executive summary first and expand by section on demand.
