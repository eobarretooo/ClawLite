from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from clawlite.gateway.request_handlers import GatewayRequestHandlers


def _build_handlers() -> GatewayRequestHandlers:
    auth_guard = SimpleNamespace(check_http=lambda **_: None)
    runtime = SimpleNamespace(
        engine=SimpleNamespace(
            tools=SimpleNamespace(schema=lambda: [{"name": "exec"}]),
        ),
        cron=SimpleNamespace(
            add_job=AsyncMock(return_value="job-1"),
            list_jobs=lambda session_id: [{"id": "job-1", "session_id": session_id}],
            remove_job=lambda job_id: job_id == "job-1",
        ),
    )
    return GatewayRequestHandlers(
        auth_guard=auth_guard,
        diagnostics_require_auth=False,
        runtime=runtime,
        dashboard_asset_root="/_clawlite",
        dashboard_bootstrap_token="bootstrap-token",
        run_engine_with_timeout_fn=AsyncMock(return_value=SimpleNamespace(text="pong", model="fake/test")),
        provider_error_payload_fn=lambda exc: (500, str(exc)),
        finalize_bootstrap_for_user_turn_fn=lambda session_id: None,
        build_tools_catalog_payload_fn=lambda schema, include_schema=False: {
            "groups": ["default"],
            "count": len(schema),
            "include_schema": include_schema,
        },
        parse_include_schema_flag_fn=lambda params: bool(params.get("include_schema")),
        control_plane_payload_fn=lambda: {"contract_version": "2026-03-04"},
        dashboard_asset_text_fn=lambda asset_name: f"asset:{asset_name}",
        render_root_dashboard_html_fn=lambda **kwargs: (
            f"<html data-root=\"{kwargs['dashboard_asset_root']}\" data-token=\"{kwargs['dashboard_bootstrap_token']}\"></html>"
        ),
    )


def test_request_handlers_chat_and_cron_paths() -> None:
    handlers = _build_handlers()
    req = SimpleNamespace(session_id="cli:test", text="ping")
    request = SimpleNamespace(query_params={})

    chat_payload = asyncio.run(handlers.chat(req, request))
    cron_add_payload = asyncio.run(
        handlers.cron_add(
            SimpleNamespace(session_id="cli:test", expression="* * * * *", prompt="x", name="job"),
            request,
        )
    )
    cron_list_payload = asyncio.run(handlers.cron_list(session_id="cli:test", request=request))
    cron_remove_payload = asyncio.run(handlers.cron_remove(job_id="job-1", request=request))

    assert chat_payload == {"text": "pong", "model": "fake/test"}
    assert cron_add_payload == {"ok": True, "status": "created", "id": "job-1"}
    assert cron_list_payload == {"jobs": [{"id": "job-1", "session_id": "cli:test"}]}
    assert cron_remove_payload == {"ok": True, "status": "removed"}


def test_request_handlers_tools_and_dashboard_assets() -> None:
    handlers = _build_handlers()
    request = SimpleNamespace(query_params={"include_schema": "true"})

    tools_payload = asyncio.run(handlers.tools_catalog(request))
    css_response = asyncio.run(handlers.dashboard_css())
    js_response = asyncio.run(handlers.dashboard_js())
    root_response = asyncio.run(handlers.root())

    assert tools_payload["include_schema"] is True
    assert css_response.body == b"asset:dashboard.css"
    assert js_response.body == b"asset:dashboard.js"
    assert b'data-root="/_clawlite"' in root_response.body
