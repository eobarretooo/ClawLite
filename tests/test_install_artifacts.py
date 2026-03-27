from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_requirements_include_portalocker_for_local_installer_flow() -> None:
    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "portalocker>=" in requirements


def test_install_script_keeps_local_editable_install_dependency_aware() -> None:
    script = (REPO_ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

    assert 'PIP + ["install", "--upgrade", "-e", ROOT_DIR]' in script
    assert "--no-deps" not in script


def test_termux_install_wrapper_passes_sync_helper_url_into_inner_shell() -> None:
    script = (REPO_ROOT / "scripts" / "install_termux_proot.sh").read_text(encoding="utf-8")

    assert 'SYNC_HELPER_URL="${SYNC_HELPER_URL}" /bin/bash -lc' in script
