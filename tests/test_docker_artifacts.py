from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_docker_compose_gateway_healthcheck_targets_health_endpoint() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "clawlite-gateway:" in compose
    assert "healthcheck:" in compose
    assert "http://127.0.0.1:8787/health" in compose


def test_docker_setup_waits_for_gateway_health_and_prints_logs_on_timeout() -> None:
    script = (REPO_ROOT / "scripts" / "docker_setup.sh").read_text(encoding="utf-8")

    assert 'docker_wait_timeout="${CLAWLITE_DOCKER_WAIT_TIMEOUT:-120}"' in script
    assert "wait_for_gateway_health" in script
    assert "docker inspect --format" in script
    assert "docker compose \"${profile_args[@]}\" logs --tail 50 clawlite-gateway" in script


def test_release_preflight_supports_optional_docker_probe_flag() -> None:
    script = (REPO_ROOT / "scripts" / "release_preflight.sh").read_text(encoding="utf-8")

    assert "DOCKER_PREFLIGHT=0" in script
    assert "--docker" in script
    assert 'set -- "$@" --docker' in script
