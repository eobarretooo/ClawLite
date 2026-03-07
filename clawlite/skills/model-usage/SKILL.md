---
name: model-usage
description: Summarize per-model cost usage from CodexBar JSON for ClawLite workflows.
metadata: {"clawlite":{"emoji":"📊"}}
script: model_usage
---

# Model usage

Use this skill when the user asks for model-level usage or cost split from CodexBar exports.

## What it does

- Reads CodexBar `cost --format json` payloads
- Summarizes by model for one provider (`codex` or `claude`)
- Supports current-model mode (latest day heuristic) and all-model mode

## Run manually

From the ClawLite repo root:

```bash
python clawlite/skills/model-usage/scripts/model_usage.py --provider codex --mode current
python clawlite/skills/model-usage/scripts/model_usage.py --provider codex --mode all
python clawlite/skills/model-usage/scripts/model_usage.py --provider claude --mode all --format json --pretty
```

With an input file or stdin:

```bash
codexbar cost --provider codex --format json > /tmp/cost.json
python clawlite/skills/model-usage/scripts/model_usage.py --input /tmp/cost.json --mode all
cat /tmp/cost.json | python clawlite/skills/model-usage/scripts/model_usage.py --input - --mode current
```

## Notes

- Script is stdlib-only and can run without ClawLite runtime services.
- CodexBar output usually exposes cost per model; token split by model may be unavailable.
