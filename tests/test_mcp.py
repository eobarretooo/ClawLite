from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(tmp_home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_home)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    return subprocess.run(
        [sys.executable, "-m", "clawlite.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )


def _boot(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = importlib.import_module("clawlite.config.settings")
    importlib.reload(settings)
    mcp = importlib.import_module("clawlite.mcp")
    importlib.reload(mcp)
    server = importlib.import_module("clawlite.gateway.server")
    importlib.reload(server)
    return mcp, server, TestClient(server.app)


def test_mcp_config_add_list_remove(monkeypatch, tmp_path):
    mcp, _, _ = _boot(monkeypatch, tmp_path)

    assert mcp.list_servers() == []
    row = mcp.add_server("local.fs", "https://example.com/mcp")
    assert row["name"] == "local.fs"

    listed = mcp.list_servers()
    assert len(listed) == 1
    assert listed[0]["name"] == "local.fs"

    cfg_path = tmp_path / ".clawlite" / "mcp.json"
    assert cfg_path.exists()
    payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert payload["servers"]["local.fs"] == "https://example.com/mcp"

    assert mcp.remove_server("local.fs") is True
    assert mcp.remove_server("local.fs") is False


def test_mcp_cli_and_gateway_endpoints(monkeypatch, tmp_path):
    add = _run_cli(tmp_path, "mcp", "add", "srv1", "https://x.test/mcp")
    assert add.returncode == 0
    assert "MCP server adicionado" in add.stdout

    listing = _run_cli(tmp_path, "mcp", "list")
    assert listing.returncode == 0
    assert "srv1" in listing.stdout

    bad = _run_cli(tmp_path, "mcp", "add", "@@", "invalid")
    assert bad.returncode == 1
    assert "Falha no comando 'mcp'" in bad.stdout

    _, server, client = _boot(monkeypatch, tmp_path)
    token = server._token()
    headers = {"Authorization": f"Bearer {token}"}

    search = client.get("/api/mcp/search?q=filesystem", headers=headers)
    assert search.status_code == 200
    assert any(item["name"] == "filesystem" for item in search.json()["items"])

    install = client.post("/api/mcp/install", headers=headers, json={"name": "filesystem"})
    assert install.status_code == 200

    add_api = client.post("/api/mcp/add", headers=headers, json={"name": "srv2", "url": "https://z.test/mcp"})
    assert add_api.status_code == 200

    status = client.get("/api/mcp/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["count"] >= 2

    rem_api = client.post("/api/mcp/remove", headers=headers, json={"name": "srv2"})
    assert rem_api.status_code == 200

    rpc_init = client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert rpc_init.status_code == 200
    assert rpc_init.json()["result"]["capabilities"]["tools"]["listChanged"] is False

    rpc_list = client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    tools = rpc_list.json()["result"]["tools"]
    assert any(t["name"].startswith("skill.") for t in tools)

    rpc_call = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "skill.web-search", "arguments": {"command": "echo mcp-ok"}},
        },
    )
    assert rpc_call.status_code == 200
    assert "mcp-ok" in rpc_call.json()["result"]["content"][0]["text"]
