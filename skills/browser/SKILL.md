# Skill: browser-history — Search Chrome History

Search Das's Chrome browsing history to find URLs, videos, sites he's visited before.

## Chrome History Location

```
~/Library/Application Support/Google/Chrome/Default/History
```

SQLite database. Can be queried directly if Chrome isn't locking it.

---

## Search Commands

### Basic search (URL or title contains term)
```bash
sqlite3 ~/Library/Application\ Support/Google/Chrome/Default/History \
  "SELECT url, title FROM urls WHERE url LIKE '%TERM%' OR title LIKE '%TERM%' ORDER BY last_visit_time DESC LIMIT 10;"
```

### YouTube videos only
```bash
sqlite3 ~/Library/Application\ Support/Google/Chrome/Default/History \
  "SELECT url, title FROM urls WHERE url LIKE '%youtube.com/watch%' AND (url LIKE '%TERM%' OR title LIKE '%TERM%') ORDER BY last_visit_time DESC LIMIT 10;"
```

### Most visited (all time)
```bash
sqlite3 ~/Library/Application\ Support/Google/Chrome/Default/History \
  "SELECT url, title, visit_count FROM urls ORDER BY visit_count DESC LIMIT 20;"
```

### Recent visits
```bash
sqlite3 ~/Library/Application\ Support/Google/Chrome/Default/History \
  "SELECT url, title FROM urls ORDER BY last_visit_time DESC LIMIT 20;"
```

---

## If Database is Locked

Chrome locks the History file while running. Options:

1. **Copy first:**
   ```bash
   cp ~/Library/Application\ Support/Google/Chrome/Default/History /tmp/chrome_history
   sqlite3 /tmp/chrome_history "SELECT ..."
   ```

2. **Use WAL mode** (usually works even when Chrome is open):
   The sqlite3 command often works anyway due to WAL mode.

---

## Open URL in Chrome

```bash
open -a "Google Chrome" "URL_HERE"
```

## Hide/Minimize Chrome

```bash
osascript -e 'tell application "System Events" to set visible of process "Google Chrome" to false'
```

---

## Common Searches for Das

| What | Search Term |
|------|-------------|
| Brain.fm focus music | `brain.fm` |
| YouTube videos | `youtube.com/watch` |
| GitHub repos | `github.com` |
| Transcript API | `transcriptapi` or `youtubetotranscript` |
