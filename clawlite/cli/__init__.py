from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Callable

_LEGACY_CLI_MODULE: ModuleType | None = None


def _load_legacy_cli() -> ModuleType:
    """
    Load the historical CLI implementation from clawlite/cli.py.

    The project currently contains both:
    - package: clawlite/cli/
    - module:  clawlite/cli.py

    Python resolves `clawlite.cli` to the package, so we bridge to the legacy
    module here to keep `python -m clawlite.cli` and console scripts working.
    """
    global _LEGACY_CLI_MODULE
    if _LEGACY_CLI_MODULE is not None:
        return _LEGACY_CLI_MODULE

    legacy_path = Path(__file__).resolve().parents[1] / "cli.py"
    spec = importlib.util.spec_from_file_location("clawlite._legacy_cli", legacy_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Não foi possível carregar CLI legado em: {legacy_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _LEGACY_CLI_MODULE = module
    return module


def main() -> None:
    module = _load_legacy_cli()
    runner = getattr(module, "main", None)
    if not callable(runner):
        raise RuntimeError("CLI legado não expõe função main().")
    cast_runner: Callable[[], None] = runner
    cast_runner()
