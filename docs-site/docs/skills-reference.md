# Skills Reference

Each skill can be invoked through the ClawLite runtime and extended for your environment.

## Examples

### `github`
```bash
clawlite run "use github skill to summarize open issues"
```

### `web-search`
```bash
clawlite run "search web for arm64 python websocket best practices"
```

### `ollama`
```bash
clawlite run "switch to local ollama model when offline"
```

### `cron`
```bash
clawlite run "schedule daily briefing at 08:00"
```

### `healthcheck`
```bash
clawlite run "perform security healthcheck on this host"
```

## Full skill map

- Core: `coding-agent`, `github`, `web-search`, `web-fetch`, `browser`, `memory-search`
- Productivity: `gmail`, `google-calendar`, `google-drive`, `notion`, `obsidian`, `linear`
- Social: `discord`, `slack`, `twitter`, `threads`
- Infra: `docker`, `ssh`, `firebase`, `supabase`, `aws`, `vercel`, `tailscale`
- AI/Media: `ollama`, `image-gen`, `whisper`, `voice-call`
- Utility: `weather`, `pdf`, `rss`, `youtube`, `maps`, `switchbot`, `cron`, `healthcheck`, `find-skills`, `skill-creator`
