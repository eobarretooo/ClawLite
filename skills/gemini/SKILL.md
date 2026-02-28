---
name: gemini
description: Gemini CLI for one-shot Q&A, summaries, and generation.
homepage: https://ai.google.dev/
metadata:
  {
    "clawdbot":
      {
        "emoji": "♊️",
        "requires": { "bins": ["gemini"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "gemini-cli",
              "bins": ["gemini"],
              "label": "Install Gemini CLI (brew)",
            },
          ],
      },
  }
---

# Gemini CLI

Use Gemini in one-shot mode with a positional prompt (avoid interactive mode).

Quick start

- `gemini "Answer this question..."`
- `gemini --model <name> "Prompt..."`
- `gemini --output-format json "Return JSON"`

Extensions

- List: `gemini --list-extensions`
- Manage: `gemini extensions <command>`

Notes

- If auth is required, run `gemini` once interactively and follow the login flow.
- Avoid `--yolo` for safety.

## ClawLite Adaptation
Conteúdo sincronizado da skill equivalente do OpenClaw e adaptado para nomenclatura/fluxo do ClawLite.
Quando algum comando depender de backend não disponível no ambiente atual, use `clawlite skill search` para alternativas.

