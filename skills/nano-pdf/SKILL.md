---
name: nano-pdf
description: Edit PDFs with natural-language instructions using the nano-pdf CLI.
homepage: https://pypi.org/project/nano-pdf/
metadata:
  {
    "clawdbot":
      {
        "emoji": "📄",
        "requires": { "bins": ["nano-pdf"] },
        "install":
          [
            {
              "id": "uv",
              "kind": "uv",
              "package": "nano-pdf",
              "bins": ["nano-pdf"],
              "label": "Install nano-pdf (uv)",
            },
          ],
      },
  }
---

# nano-pdf

Use `nano-pdf` to apply edits to a specific page in a PDF using a natural-language instruction.

## Quick start

```bash
nano-pdf edit deck.pdf 1 "Change the title to 'Q3 Results' and fix the typo in the subtitle"
```

Notes:

- Page numbers are 0-based or 1-based depending on the tool’s version/config; if the result looks off by one, retry with the other.
- Always sanity-check the output PDF before sending it out.

## ClawLite Adaptation
Conteúdo sincronizado da skill equivalente do OpenClaw e adaptado para nomenclatura/fluxo do ClawLite.
Quando algum comando depender de backend não disponível no ambiente atual, use `clawlite skill search` para alternativas.

