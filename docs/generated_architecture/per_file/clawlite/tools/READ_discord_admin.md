# READ clawlite/tools/discord_admin.py

## Identity

- Path: `clawlite/tools/discord_admin.py`
- Area: `tools`
- Extension: `.py`
- Lines: 493
- Size bytes: 19242
- SHA1: `e4d0ad50e0d511f557ec7f40a567b0925a683b22`

## Summary

`clawlite.tools.discord_admin` is a Python module in the `tools` area. It defines 1 class(es), led by `DiscordAdminTool`. It exposes 15 function(s), including `__init__`, `_build_channel_payload`, `_coerce_bool`, `_apply_layout`, `_ensure_channel`, `_ensure_role`. It depends on 6 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 8
- Async functions: 7
- Constants: 7
- Internal imports: 1
- Imported by: 2
- Matching tests: 3

## Classes

- `DiscordAdminTool`

## Functions

- `__init__`
- `_build_channel_payload`
- `_coerce_bool`
- `_coerce_permissions`
- `_require_guild_id`
- `_simplify_channel`
- `_simplify_role`
- `args_schema`
- `_apply_layout` (async)
- `_ensure_channel` (async)
- `_ensure_role` (async)
- `_list_channels` (async)
- `_list_roles` (async)
- `_request` (async)
- `run` (async)

## Constants

- `DISCORD_CHANNEL_TYPE_CATEGORY`
- `DISCORD_CHANNEL_TYPE_FORUM`
- `DISCORD_CHANNEL_TYPE_STAGE`
- `DISCORD_CHANNEL_TYPE_TEXT`
- `DISCORD_CHANNEL_TYPE_VOICE`
- `_CHANNEL_KIND_BY_TYPE`
- `_CHANNEL_TYPE_BY_KIND`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/tools/discord_admin.py`.
- Cross-reference `CONNECTIONS_discord_admin.md` to see how this file fits into the wider system.
