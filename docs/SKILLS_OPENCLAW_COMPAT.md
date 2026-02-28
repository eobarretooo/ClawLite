# OpenClaw Skills Compatibility (ClawLite)

Comparativo entre o catálogo OpenClaw e a adaptação aplicada no ClawLite.

- Skills OpenClaw analisadas: **52**
- Skills no catálogo ClawLite após adaptação: **80**
- Overlap direto por slug: **52**
- Skills OpenClaw adicionadas ao catálogo ClawLite (antes ausentes): **42**

## Aliases executáveis (OpenClaw -> backend ClawLite)

- `apple-reminders` -> `clawlite.skills.cron:run`
- `blogwatcher` -> `clawlite.skills.rss:run`
- `gh-issues` -> `clawlite.skills.github:run`
- `goplaces` -> `clawlite.skills.maps:run`
- `nano-pdf` -> `clawlite.skills.pdf:run`
- `openai-image-gen` -> `clawlite.skills.image_gen:run`
- `openai-whisper` -> `clawlite.skills.whisper:run`
- `openai-whisper-api` -> `clawlite.skills.whisper:run`
- `session-logs` -> `clawlite.skills.memory_search:run`
- `xurl` -> `clawlite.skills.web_fetch:run`

## Skills sem backend nativo (guidance/fallback)

- `1password`
- `apple-notes`
- `bear-notes`
- `blucli`
- `bluebubbles`
- `camsnap`
- `canvas`
- `clawhub`
- `eightctl`
- `gemini`
- `gifgrep`
- `gog`
- `himalaya`
- `imsg`
- `mcporter`
- `model-usage`
- `nano-banana-pro`
- `openhue`
- `oracle`
- `ordercli`
- `peekaboo`
- `sag`
- `sherpa-onnx-tts`
- `songsee`
- `sonoscli`
- `spotify-player`
- `summarize`
- `things-mac`
- `tmux`
- `trello`
- `video-frames`
- `wacli`

## Observações

- Skills importadas ficam em `skills/<slug>/SKILL.md` com seção de adaptação.
- Skills não suportadas no runtime retornam orientação com alternativas quando chamadas via alias de compatibilidade.
- O runtime do ClawLite mantém as skills nativas existentes e agrega aliases OpenClaw no registry.
- Os `SKILL.md` das skills compartilhadas entre OpenClaw e ClawLite foram sincronizados e adaptados (branding/comandos/path/env).
