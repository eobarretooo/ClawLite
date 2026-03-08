from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx

from clawlite.tools.base import Tool, ToolContext


DISCORD_CHANNEL_TYPE_TEXT = 0
DISCORD_CHANNEL_TYPE_VOICE = 2
DISCORD_CHANNEL_TYPE_CATEGORY = 4
DISCORD_CHANNEL_TYPE_STAGE = 13
DISCORD_CHANNEL_TYPE_FORUM = 15

_CHANNEL_TYPE_BY_KIND: dict[str, int] = {
    "text": DISCORD_CHANNEL_TYPE_TEXT,
    "voice": DISCORD_CHANNEL_TYPE_VOICE,
    "category": DISCORD_CHANNEL_TYPE_CATEGORY,
    "stage": DISCORD_CHANNEL_TYPE_STAGE,
    "forum": DISCORD_CHANNEL_TYPE_FORUM,
}

_CHANNEL_KIND_BY_TYPE: dict[int, str] = {
    value: key for key, value in _CHANNEL_TYPE_BY_KIND.items()
}


class DiscordAdminTool(Tool):
    name = "discord_admin"
    description = (
        "Inspect and administer Discord guilds with the configured bot: list guilds/channels/roles, "
        "create roles/channels, or apply a server layout."
    )

    def __init__(
        self,
        *,
        token: str,
        api_base: str = "https://discord.com/api/v10",
        timeout_s: float = 10.0,
    ) -> None:
        self.token = str(token or "").strip()
        self.api_base = str(api_base or "https://discord.com/api/v10").strip().rstrip("/")
        self.timeout_s = max(0.1, float(timeout_s or 10.0))

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list_guilds",
                        "list_channels",
                        "list_roles",
                        "create_role",
                        "create_channel",
                        "apply_layout",
                    ],
                },
                "guild_id": {"type": "string"},
                "name": {"type": "string"},
                "kind": {"type": "string", "enum": sorted(_CHANNEL_TYPE_BY_KIND.keys())},
                "parent_id": {"type": "string"},
                "topic": {"type": "string"},
                "nsfw": {"type": "boolean"},
                "position": {"type": "integer"},
                "bitrate": {"type": "integer"},
                "user_limit": {"type": "integer"},
                "permissions": {"type": ["string", "integer"]},
                "color": {"type": "integer"},
                "hoist": {"type": "boolean"},
                "mentionable": {"type": "boolean"},
                "reason": {"type": "string"},
                "ensure": {"type": "boolean"},
                "template": {
                    "type": "object",
                    "properties": {
                        "roles": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "channels": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "categories": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "position": {"type": "integer"},
                                    "channels": {
                                        "type": "array",
                                        "items": {"type": "object"},
                                    },
                                },
                                "required": ["name"],
                            },
                        },
                    },
                },
            },
            "required": ["action"],
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        del ctx
        if not self.token:
            return json.dumps(
                {
                    "ok": False,
                    "error": "discord_not_configured",
                    "detail": "channels.discord.token is required",
                }
            )

        action = str(arguments.get("action", "") or "").strip().lower()
        guild_id = str(arguments.get("guild_id", "") or "").strip()
        reason = str(arguments.get("reason", "") or "").strip()
        try:
            if action == "list_guilds":
                guilds = await self._request("GET", "/users/@me/guilds")
                rows = []
                for item in guilds if isinstance(guilds, list) else []:
                    if not isinstance(item, dict):
                        continue
                    rows.append(
                        {
                            "id": str(item.get("id", "") or "").strip(),
                            "name": str(item.get("name", "") or "").strip(),
                            "owner": bool(item.get("owner", False)),
                            "permissions": str(item.get("permissions", "") or "").strip(),
                        }
                    )
                return json.dumps({"ok": True, "action": action, "count": len(rows), "guilds": rows})

            if action == "list_channels":
                self._require_guild_id(guild_id)
                rows = await self._list_channels(guild_id)
                return json.dumps({"ok": True, "action": action, "guild_id": guild_id, "count": len(rows), "channels": rows})

            if action == "list_roles":
                self._require_guild_id(guild_id)
                rows = await self._list_roles(guild_id)
                return json.dumps({"ok": True, "action": action, "guild_id": guild_id, "count": len(rows), "roles": rows})

            if action == "create_role":
                self._require_guild_id(guild_id)
                ensure = self._coerce_bool(arguments.get("ensure"), default=False)
                roles = await self._list_roles(guild_id)
                row, created = await self._ensure_role(
                    guild_id=guild_id,
                    spec=arguments,
                    existing_roles=roles,
                    reason=reason,
                    ensure=ensure,
                )
                return json.dumps(
                    {
                        "ok": True,
                        "action": action,
                        "guild_id": guild_id,
                        "created": created,
                        "role": row,
                    }
                )

            if action == "create_channel":
                self._require_guild_id(guild_id)
                ensure = self._coerce_bool(arguments.get("ensure"), default=False)
                channels = await self._list_channels(guild_id)
                row, created = await self._ensure_channel(
                    guild_id=guild_id,
                    spec=arguments,
                    existing_channels=channels,
                    reason=reason,
                    ensure=ensure,
                )
                return json.dumps(
                    {
                        "ok": True,
                        "action": action,
                        "guild_id": guild_id,
                        "created": created,
                        "channel": row,
                    }
                )

            if action == "apply_layout":
                self._require_guild_id(guild_id)
                template = arguments.get("template")
                if not isinstance(template, dict):
                    raise ValueError("template is required for action=apply_layout")
                payload = await self._apply_layout(guild_id=guild_id, template=template, reason=reason)
                return json.dumps(payload)
        except ValueError as exc:
            return json.dumps({"ok": False, "action": action, "error": "invalid_arguments", "detail": str(exc)})
        except RuntimeError as exc:
            return json.dumps({"ok": False, "action": action, "error": str(exc)})

        return json.dumps({"ok": False, "action": action, "error": "invalid_action"})

    @staticmethod
    def _coerce_bool(value: Any, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, str):
            clean = value.strip().lower()
            if clean in {"1", "true", "yes", "on"}:
                return True
            if clean in {"0", "false", "no", "off"}:
                return False
        return bool(value)

    @staticmethod
    def _require_guild_id(guild_id: str) -> None:
        if not str(guild_id or "").strip():
            raise ValueError("guild_id is required")

    @staticmethod
    def _coerce_permissions(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return str(value)
        text = str(value or "").strip()
        return text or None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        reason: str = "",
    ) -> Any:
        headers = {"Authorization": f"Bot {self.token}"}
        if reason:
            headers["X-Audit-Log-Reason"] = quote(reason, safe=" ")
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=headers) as client:
            response = await client.request(method.upper(), f"{self.api_base}{path}", json=payload)
        if response.status_code < 200 or response.status_code >= 300:
            detail = ""
            try:
                body = response.json() if response.content else {}
            except Exception:
                body = {}
            if isinstance(body, dict):
                detail = str(body.get("message", "") or "").strip()
            if not detail:
                detail = str(response.text or "").strip()
            suffix = f":{detail}" if detail else ""
            raise RuntimeError(f"discord_admin_http_{response.status_code}{suffix}")
        if not response.content:
            return {}
        try:
            return response.json()
        except Exception:
            return {}

    @staticmethod
    def _simplify_channel(row: dict[str, Any]) -> dict[str, Any]:
        channel_type = int(row.get("type", -1) or -1)
        return {
            "id": str(row.get("id", "") or "").strip(),
            "name": str(row.get("name", "") or "").strip(),
            "kind": _CHANNEL_KIND_BY_TYPE.get(channel_type, str(channel_type)),
            "type": channel_type,
            "parent_id": str(row.get("parent_id", "") or "").strip(),
            "position": int(row.get("position", 0) or 0),
            "topic": str(row.get("topic", "") or "").strip(),
            "nsfw": bool(row.get("nsfw", False)),
        }

    @staticmethod
    def _simplify_role(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row.get("id", "") or "").strip(),
            "name": str(row.get("name", "") or "").strip(),
            "color": int(row.get("color", 0) or 0),
            "hoist": bool(row.get("hoist", False)),
            "mentionable": bool(row.get("mentionable", False)),
            "permissions": str(row.get("permissions", "") or "").strip(),
            "position": int(row.get("position", 0) or 0),
        }

    async def _list_channels(self, guild_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/guilds/{guild_id}/channels")
        rows = [
            self._simplify_channel(item)
            for item in data if isinstance(item, dict)
        ] if isinstance(data, list) else []
        rows.sort(key=lambda item: (item.get("position", 0), item.get("name", "")))
        return rows

    async def _list_roles(self, guild_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/guilds/{guild_id}/roles")
        rows = [
            self._simplify_role(item)
            for item in data if isinstance(item, dict)
        ] if isinstance(data, list) else []
        rows.sort(key=lambda item: (item.get("position", 0), item.get("name", "")))
        return rows

    async def _ensure_role(
        self,
        *,
        guild_id: str,
        spec: dict[str, Any],
        existing_roles: list[dict[str, Any]],
        reason: str,
        ensure: bool,
    ) -> tuple[dict[str, Any], bool]:
        name = str(spec.get("name", "") or "").strip()
        if not name:
            raise ValueError("name is required")
        if ensure:
            for row in existing_roles:
                if str(row.get("name", "") or "").strip().lower() == name.lower():
                    return row, False
        payload: dict[str, Any] = {"name": name}
        permissions = self._coerce_permissions(spec.get("permissions"))
        if permissions is not None:
            payload["permissions"] = permissions
        if spec.get("color") is not None:
            payload["color"] = int(spec.get("color") or 0)
        if spec.get("hoist") is not None:
            payload["hoist"] = self._coerce_bool(spec.get("hoist"), default=False)
        if spec.get("mentionable") is not None:
            payload["mentionable"] = self._coerce_bool(spec.get("mentionable"), default=False)
        data = await self._request(
            "POST",
            f"/guilds/{guild_id}/roles",
            payload=payload,
            reason=reason,
        )
        row = self._simplify_role(data if isinstance(data, dict) else {})
        existing_roles.append(row)
        return row, True

    def _build_channel_payload(
        self,
        *,
        spec: dict[str, Any],
        parent_id: str = "",
    ) -> dict[str, Any]:
        name = str(spec.get("name", "") or "").strip()
        if not name:
            raise ValueError("name is required")
        kind = str(spec.get("kind", "") or "").strip().lower() or "text"
        if kind not in _CHANNEL_TYPE_BY_KIND:
            raise ValueError("kind must be one of text, voice, category, stage, forum")
        payload: dict[str, Any] = {
            "name": name,
            "type": _CHANNEL_TYPE_BY_KIND[kind],
        }
        effective_parent_id = str(spec.get("parent_id", "") or "").strip() or parent_id
        if effective_parent_id and kind != "category":
            payload["parent_id"] = effective_parent_id
        if spec.get("position") is not None:
            payload["position"] = int(spec.get("position") or 0)
        if kind == "text" or kind == "forum":
            topic = str(spec.get("topic", "") or "").strip()
            if topic:
                payload["topic"] = topic
            if spec.get("nsfw") is not None:
                payload["nsfw"] = self._coerce_bool(spec.get("nsfw"), default=False)
        if kind in {"voice", "stage"}:
            if spec.get("bitrate") is not None:
                payload["bitrate"] = int(spec.get("bitrate") or 0)
            if spec.get("user_limit") is not None:
                payload["user_limit"] = int(spec.get("user_limit") or 0)
        return payload

    async def _ensure_channel(
        self,
        *,
        guild_id: str,
        spec: dict[str, Any],
        existing_channels: list[dict[str, Any]],
        reason: str,
        ensure: bool,
        parent_id: str = "",
    ) -> tuple[dict[str, Any], bool]:
        payload = self._build_channel_payload(spec=spec, parent_id=parent_id)
        name = str(payload.get("name", "") or "").strip()
        channel_type = int(payload.get("type", -1) or -1)
        effective_parent = str(payload.get("parent_id", "") or "").strip()
        if ensure:
            for row in existing_channels:
                if (
                    str(row.get("name", "") or "").strip().lower() == name.lower()
                    and int(row.get("type", -1) or -1) == channel_type
                    and str(row.get("parent_id", "") or "").strip() == effective_parent
                ):
                    return row, False
        data = await self._request(
            "POST",
            f"/guilds/{guild_id}/channels",
            payload=payload,
            reason=reason,
        )
        row = self._simplify_channel(data if isinstance(data, dict) else {})
        existing_channels.append(row)
        return row, True

    async def _apply_layout(
        self,
        *,
        guild_id: str,
        template: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        roles = await self._list_roles(guild_id)
        channels = await self._list_channels(guild_id)
        ensured_roles: list[dict[str, Any]] = []
        top_channels: list[dict[str, Any]] = []
        categories: list[dict[str, Any]] = []

        for raw_role in template.get("roles", []):
            if not isinstance(raw_role, dict):
                continue
            row, created = await self._ensure_role(
                guild_id=guild_id,
                spec=raw_role,
                existing_roles=roles,
                reason=reason,
                ensure=True,
            )
            ensured_roles.append(row | {"created": created})

        for raw_channel in template.get("channels", []):
            if not isinstance(raw_channel, dict):
                continue
            row, created = await self._ensure_channel(
                guild_id=guild_id,
                spec=raw_channel,
                existing_channels=channels,
                reason=reason,
                ensure=True,
            )
            top_channels.append(row | {"created": created})

        for raw_category in template.get("categories", []):
            if not isinstance(raw_category, dict):
                continue
            category_spec = dict(raw_category)
            category_spec["kind"] = "category"
            category_row, category_created = await self._ensure_channel(
                guild_id=guild_id,
                spec=category_spec,
                existing_channels=channels,
                reason=reason,
                ensure=True,
            )
            child_rows: list[dict[str, Any]] = []
            for raw_child in raw_category.get("channels", []):
                if not isinstance(raw_child, dict):
                    continue
                child_row, child_created = await self._ensure_channel(
                    guild_id=guild_id,
                    spec=raw_child,
                    existing_channels=channels,
                    reason=reason,
                    ensure=True,
                    parent_id=str(category_row.get("id", "") or "").strip(),
                )
                child_rows.append(child_row | {"created": child_created})
            categories.append(
                {
                    **category_row,
                    "created": category_created,
                    "channels": child_rows,
                }
            )

        return {
            "ok": True,
            "action": "apply_layout",
            "guild_id": guild_id,
            "roles": ensured_roles,
            "channels": top_channels,
            "categories": categories,
        }
