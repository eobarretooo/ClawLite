# Contributing to ClawLite

Thank you for your interest in contributing! Here's how to get started.

## Setup

```bash
git clone https://github.com/eobarretooo/ClawLite.git
cd ClawLite
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Before You Code

- **Check open issues** — someone may already be working on it
- **Open an issue first** for large features — alignment before implementation
- **Write tests first** — ClawLite uses TDD throughout

## Code Style

- Python 3.10+, typed annotations
- `ruff check --select=E,F,W .` must pass
- New features need tests in `tests/`
- Keep functions focused; prefer small, testable units

## Running Tests

```bash
python -m pytest tests/ -q --tb=short        # full suite
python -m pytest tests/channels/ -v          # channel tests
python -m pytest tests/core/test_engine.py   # engine tests
```

## Pull Request Guidelines

1. Branch from `main`: `git checkout -b feat/your-feature`
2. Commit with clear messages (`feat:`, `fix:`, `docs:`, `refactor:`)
3. All tests must pass; CI runs Python 3.10 + 3.12
4. Reference the issue number in your PR description
5. Keep PRs focused — one feature or fix per PR

## Questions?

Open a [GitHub Issue](https://github.com/eobarretooo/ClawLite/issues) — we're happy to help.
