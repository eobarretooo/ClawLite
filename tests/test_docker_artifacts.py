from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_docker_compose_gateway_healthcheck_targets_health_endpoint() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "clawlite-gateway:" in compose
    assert "healthcheck:" in compose
    assert "http://127.0.0.1:8787/health" in compose


def test_dockerfile_declares_image_healthcheck_for_gateway_runtime() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "HEALTHCHECK" in dockerfile
    assert "/proc/1/cmdline" in dockerfile
    assert "clawlite gateway" in dockerfile
    assert "http://127.0.0.1:8787/health" in dockerfile


def test_docker_compose_cli_service_disables_image_healthcheck() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    cli_block = compose.split("  clawlite-cli:\n", 1)[1].split("\n\n  redis:\n", 1)[0]

    assert "healthcheck:" in cli_block
    assert "disable: true" in cli_block


def test_docker_setup_waits_for_gateway_health_and_prints_logs_on_timeout() -> None:
    script = (REPO_ROOT / "scripts" / "docker_setup.sh").read_text(encoding="utf-8")

    assert 'docker_wait_timeout="${CLAWLITE_DOCKER_WAIT_TIMEOUT:-120}"' in script
    assert "wait_for_gateway_health" in script
    assert "docker inspect --format" in script
    assert 'docker compose "${compose_args[@]}" "${profile_args[@]}" logs --tail 50 clawlite-gateway' in script


def test_release_preflight_supports_optional_docker_probe_flag() -> None:
    script = (REPO_ROOT / "scripts" / "release_preflight.sh").read_text(encoding="utf-8")

    assert "DOCKER_PREFLIGHT=0" in script
    assert "--docker" in script
    assert 'set -- "$@" --docker' in script


def test_docker_setup_supports_optional_compose_env_file() -> None:
    script = (REPO_ROOT / "scripts" / "docker_setup.sh").read_text(encoding="utf-8")

    assert "CLAWLITE_DOCKER_ENV_FILE" in script
    assert "--env-file" in script
    assert "Docker env file not found" in script
    assert "docker_cli_status_cmd" in script
    assert "printf '%q' \"$docker_env_file\"" in script


def test_docker_compose_env_example_documents_common_overrides() -> None:
    env_example = (REPO_ROOT / "docker-compose.env.example").read_text(encoding="utf-8")

    assert "CLAWLITE_UID=1000" in env_example
    assert "CLAWLITE_MODEL=" in env_example
    assert "CLAWLITE_GATEWAY_AUTH_TOKEN=" in env_example
    assert "OPENAI_API_KEY=" in env_example
    assert "CLAWLITE_CODEX_ACCESS_TOKEN=" in env_example
    assert "CLAWLITE_BUS_BACKEND=inprocess" in env_example
    assert "Do not commit real tokens" in env_example


def test_docker_compose_passes_runtime_and_provider_envs_through_to_services() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert 'CLAWLITE_MODEL: "${CLAWLITE_MODEL:-}"' in compose
    assert 'CLAWLITE_LITELLM_API_KEY: "${CLAWLITE_LITELLM_API_KEY:-}"' in compose
    assert 'CLAWLITE_GATEWAY_AUTH_TOKEN: "${CLAWLITE_GATEWAY_AUTH_TOKEN:-}"' in compose
    assert 'OPENAI_API_KEY: "${OPENAI_API_KEY:-}"' in compose
    assert 'ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY:-}"' in compose
    assert 'GEMINI_API_KEY: "${GEMINI_API_KEY:-}"' in compose
    assert 'CLAWLITE_CODEX_ACCESS_TOKEN: "${CLAWLITE_CODEX_ACCESS_TOKEN:-}"' in compose
    assert 'CLAWLITE_GEMINI_AUTH_PATH: "${CLAWLITE_GEMINI_AUTH_PATH:-}"' in compose
