# Releasing ClawLite

Last updated: 2026-03-10

This document defines how milestone releases are cut from `main`.

## Delivery Policy

- commit every green, reviewable slice
- push every green commit
- do not create a tag or GitHub release for partial work
- create tags and GitHub releases only when a milestone is validated end to end
- update `CHANGELOG.md`, `README.md`, and affected docs before tagging

## Before You Tag

Confirm that public docs reflect the actual runtime:

- `README.md`
- `CHANGELOG.md`
- `docs/STATUS.md`
- `docs/OPERATIONS.md`
- `docs/API.md`
- any feature-specific docs touched by the milestone

## Validation Checklist

Minimum milestone validation:

```bash
python -m clawlite.cli --help
python -m pytest tests/ -q --tb=short
clawlite validate config
clawlite validate preflight --gateway-url http://127.0.0.1:8787
bash scripts/smoke_test.sh
bash scripts/release_preflight.sh --config ~/.clawlite/config.json --gateway-url http://127.0.0.1:8787
```

If the milestone depends on the Docker path, add:

```bash
clawlite validate preflight --docker
bash scripts/release_preflight.sh --config ~/.clawlite/config.json --gateway-url http://127.0.0.1:8787 --docker
```

Add milestone-specific tests when the work touches gateway, providers, channels, heartbeat, or autonomy.

## Tagging Workflow

1. Ensure `main` is clean and pushed.
2. Confirm `CHANGELOG.md` has a finalized section for the milestone.
3. Create the annotated tag.
4. Push the tag.
5. Create the GitHub release using the same milestone summary.

Example:

```bash
git tag -a v0.x.y -m "ClawLite v0.x.y"
git push origin main
git push origin v0.x.y
gh release create v0.x.y --title "ClawLite v0.x.y" --notes-file CHANGELOG.md
```

Adjust the notes flow if you prepare dedicated release notes instead of using the changelog directly.

## Release Notes Content

Each milestone release should describe:

- what became operationally stronger
- what parity work landed from the reference repos
- what remained intentionally out of scope
- how the milestone was validated
- any upgrade or migration notes for operators

## What Not To Do

- do not tag every commit
- do not ship a release with docs that lag behind behavior
- do not cut a milestone without running the release checklist
- do not hide unverified areas; document them explicitly in the release notes
