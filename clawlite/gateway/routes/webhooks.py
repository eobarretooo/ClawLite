import asyncio
import hmac
import ipaddress
import json
import logging
import re
import secrets
import time
from threading import Lock
from typing import Any, TypeVar

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from clawlite.channels.googlechat import GoogleChatChannel
from clawlite.channels.imessage import IMessageChannel
from clawlite.channels.irc import IrcChannel
from clawlite.channels.manager import manager
from clawlite.channels.signal import SignalChannel
from clawlite.channels.whatsapp import WhatsAppChannel
from clawlite.config.settings import load_config

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)
TChannel = TypeVar("TChannel")
_CTRL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RATE_STATE: dict[tuple[str, str], list[float]] = {}
_RATE_LOCK = Lock()
_MAX_DEPTH = 8
_MAX_ITEMS = 200
_MAX_STRING = 4000


def _resolve_channel_instances(channel_name: str, expected_type: type[TChannel]) -> list[TChannel]:
    prefix = f"{channel_name}:"
    rows: list[TChannel] = []
    for key, channel in manager.active_channels.items():
        if key == channel_name or key.startswith(prefix):
            if isinstance(channel, expected_type):
                rows.append(channel)
    return rows


def _channel_cfg(channel_name: str) -> dict[str, Any]:
    cfg = load_config()
    channels = cfg.get("channels", {})
    if not isinstance(channels, dict):
        return {}
    row = channels.get(channel_name, {})
    return row if isinstance(row, dict) else {}


def _error_response(
    *,
    channel: str,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "ok": False,
        "channel": channel,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        body["error"]["details"] = details
    return JSONResponse(body, status_code=status_code)


def _request_ip(request: Request) -> str:
    forwarded = str(request.headers.get("x-forwarded-for", "")).strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    client = request.client
    if client and client.host:
        return str(client.host)
    return "unknown"


def _extract_webhook_token(request: Request) -> str:
    direct = str(request.headers.get("x-clawlite-webhook-token", "")).strip()
    if direct:
        return direct
    legacy = str(request.headers.get("x-webhook-token", "")).strip()
    if legacy:
        return legacy
    auth = str(request.headers.get("authorization", "")).strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _ip_allowed(request_ip: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    if request_ip == "unknown":
        return False
    for raw in allowed:
        item = str(raw).strip()
        if not item:
            continue
        try:
            if "/" in item:
                if ipaddress.ip_address(request_ip) in ipaddress.ip_network(item, strict=False):
                    return True
            elif request_ip == item:
                return True
        except ValueError:
            continue
    return False


def _verify_signature(raw_body: bytes, provided_header: str, secret_key: str) -> bool:
    provided = str(provided_header or "").strip()
    if not provided:
        return False
    if provided.lower().startswith("sha256="):
        provided = provided.split("=", 1)[1].strip()
    expected = hmac.new(secret_key.encode("utf-8"), raw_body, digestmod="sha256").hexdigest()
    return secrets.compare_digest(provided, expected)


def _sanitize_payload(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return None
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for idx, (k, v) in enumerate(value.items()):
            if idx >= _MAX_ITEMS:
                break
            key = str(k)[:128]
            clean[key] = _sanitize_payload(v, depth=depth + 1)
        return clean
    if isinstance(value, list):
        return [_sanitize_payload(v, depth=depth + 1) for v in value[:_MAX_ITEMS]]
    if isinstance(value, str):
        trimmed = value.strip()
        trimmed = _CTRL_CHARS_RE.sub("", trimmed)
        return trimmed[:_MAX_STRING]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:_MAX_STRING]


def _rate_limit_check(channel: str, request: Request, cfg: dict[str, Any]) -> tuple[bool, int]:
    raw_limit = cfg.get("rate_limit_per_min", 120)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = 120
    if limit <= 0:
        return True, 0
    now = time.monotonic()
    ip = _request_ip(request)
    key = (channel, ip)
    cutoff = now - 60.0
    with _RATE_LOCK:
        current = [ts for ts in _RATE_STATE.get(key, []) if ts >= cutoff]
        if len(current) >= limit:
            oldest = min(current)
            retry_after = max(1, int(60 - (now - oldest)))
            _RATE_STATE[key] = current
            return False, retry_after
        current.append(now)
        _RATE_STATE[key] = current
    return True, 0


async def _read_json_body(request: Request, channel: str, cfg: dict[str, Any]) -> tuple[dict[str, Any] | None, JSONResponse | None, bytes]:
    raw_body = await request.body()
    raw_max_kb = cfg.get("max_payload_kb", 256)
    try:
        max_kb = int(raw_max_kb)
    except (TypeError, ValueError):
        max_kb = 256
    if max_kb <= 0:
        max_kb = 256
    max_bytes = max_kb * 1024
    if len(raw_body) > max_bytes:
        return None, _error_response(
            channel=channel,
            code="payload_too_large",
            message=f"Payload excede limite de {max_kb}KB",
            status_code=413,
        ), raw_body
    try:
        parsed = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return None, _error_response(
            channel=channel,
            code="invalid_json",
            message="Corpo JSON inválido",
            status_code=400,
        ), raw_body
    if not isinstance(parsed, dict):
        return None, _error_response(
            channel=channel,
            code="invalid_payload",
            message="Payload deve ser objeto JSON",
            status_code=400,
        ), raw_body
    return parsed, None, raw_body


def _authenticate_request(
    *,
    request: Request,
    channel: str,
    cfg: dict[str, Any],
    raw_body: bytes,
) -> JSONResponse | None:
    token_cfg = str(cfg.get("webhook_token") or cfg.get("webhookToken") or "").strip()
    if token_cfg:
        provided_token = _extract_webhook_token(request)
        if not provided_token or not secrets.compare_digest(provided_token, token_cfg):
            return _error_response(
                channel=channel,
                code="unauthorized_webhook",
                message="Token de webhook inválido",
                status_code=401,
            )

    sign_secret = str(cfg.get("webhook_signing_secret") or cfg.get("webhookSigningSecret") or "").strip()
    if sign_secret:
        header_sig = str(request.headers.get("x-clawlite-signature") or request.headers.get("x-webhook-signature") or "")
        if not _verify_signature(raw_body, header_sig, sign_secret):
            return _error_response(
                channel=channel,
                code="invalid_signature",
                message="Assinatura do webhook inválida",
                status_code=401,
            )

    allow_raw = cfg.get("allowed_ips", cfg.get("allowedIps", []))
    allowed_ips = allow_raw if isinstance(allow_raw, list) else []
    ip = _request_ip(request)
    if not _ip_allowed(ip, [str(v).strip() for v in allowed_ips]):
        return _error_response(
            channel=channel,
            code="forbidden_origin",
            message="Origem do webhook não permitida",
            status_code=403,
            details={"ip": ip},
        )
    return None


def _validate_googlechat_payload(payload: dict[str, Any]) -> str | None:
    event_type = str(payload.get("type", "")).strip().upper()
    if event_type and event_type not in {"MESSAGE", "ADDED_TO_SPACE"}:
        return "type inválido para Google Chat"
    if event_type == "ADDED_TO_SPACE":
        return None

    message = payload.get("message", payload)
    if not isinstance(message, dict):
        return "message ausente/inválido"
    text = str(message.get("text", "") or message.get("argumentText", "")).strip()
    if not text:
        return "mensagem sem texto"

    sender = message.get("sender", {})
    if not isinstance(sender, dict) or not str(sender.get("name", "")).strip():
        return "sender.name ausente"
    space = message.get("space", {})
    if not isinstance(space, dict) or not str(space.get("name", "")).strip():
        return "space.name ausente"
    return None


def _validate_irc_payload(payload: dict[str, Any]) -> str | None:
    text = str(payload.get("text") or payload.get("message") or "").strip()
    if not text:
        return "mensagem IRC sem texto"
    sender = str(payload.get("sender") or payload.get("nick") or "").strip()
    if not sender:
        return "sender/nick ausente"
    channel_name = str(payload.get("channel", "")).strip()
    if channel_name and not channel_name.startswith("#"):
        return "channel IRC inválido (esperado '#canal')"
    return None


def _validate_signal_payload(payload: dict[str, Any]) -> str | None:
    envelope = payload.get("envelope")
    if isinstance(envelope, dict):
        data_message = envelope.get("dataMessage")
    else:
        data_message = None
    if not isinstance(data_message, dict):
        data_message = {}

    text = str(payload.get("text") or payload.get("message") or data_message.get("message") or "").strip()
    if not text:
        return "mensagem Signal sem texto"
    sender = str(
        payload.get("from")
        or payload.get("source")
        or (envelope.get("source") if isinstance(envelope, dict) else "")
        or (envelope.get("sourceNumber") if isinstance(envelope, dict) else "")
        or (envelope.get("sourceUuid") if isinstance(envelope, dict) else "")
        or ""
    ).strip()
    if not sender:
        return "remetente Signal ausente"
    return None


def _validate_imessage_payload(payload: dict[str, Any]) -> str | None:
    text = str(payload.get("text") or payload.get("message") or "").strip()
    if not text:
        return "mensagem iMessage sem texto"
    sender = str(payload.get("from") or payload.get("handle") or "").strip()
    chat_id = str(payload.get("chat_id") or payload.get("chatId") or "").strip()
    if not sender and not chat_id:
        return "from/handle ou chat_id ausente"
    return None


def _extract_phone_number_id(payload: dict[str, Any]) -> str:
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                value_id = str(metadata.get("phone_number_id", "")).strip()
                if value_id:
                    return value_id
    except Exception:
        return ""
    return ""


def _resolve_whatsapp_channel(payload: dict[str, Any]) -> WhatsAppChannel | None:
    active = _resolve_channel_instances("whatsapp", WhatsAppChannel)
    if not active:
        return None

    expected_phone_number_id = _extract_phone_number_id(payload)
    if expected_phone_number_id:
        for channel in active:
            configured = str(getattr(channel, "phone_number_id", "")).strip()
            if configured and configured == expected_phone_number_id:
                return channel

    preferred = manager.active_channels.get("whatsapp")
    if isinstance(preferred, WhatsAppChannel):
        return preferred
    return active[0]


def _resolve_googlechat_channel() -> GoogleChatChannel | None:
    active = _resolve_channel_instances("googlechat", GoogleChatChannel)
    if not active:
        return None
    preferred = manager.active_channels.get("googlechat")
    if isinstance(preferred, GoogleChatChannel):
        return preferred
    return active[0]


def _resolve_irc_channel() -> IrcChannel | None:
    active = _resolve_channel_instances("irc", IrcChannel)
    if not active:
        return None
    preferred = manager.active_channels.get("irc")
    if isinstance(preferred, IrcChannel):
        return preferred
    return active[0]


def _resolve_signal_channel() -> SignalChannel | None:
    active = _resolve_channel_instances("signal", SignalChannel)
    if not active:
        return None
    preferred = manager.active_channels.get("signal")
    if isinstance(preferred, SignalChannel):
        return preferred
    return active[0]


def _resolve_imessage_channel() -> IMessageChannel | None:
    active = _resolve_channel_instances("imessage", IMessageChannel)
    if not active:
        return None
    preferred = manager.active_channels.get("imessage")
    if isinstance(preferred, IMessageChannel):
        return preferred
    return active[0]


@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """Valida o webhook originado do Meta."""
    if hub_mode == "subscribe" and hub_challenge:
        return int(hub_challenge)
    raise HTTPException(status_code=400, detail="Invalid verify token")


@router.post("/whatsapp")
async def handle_whatsapp_webhook(request: Request) -> dict[str, str]:
    payload = await request.json()

    wa_channel = _resolve_whatsapp_channel(payload)
    if not wa_channel:
        logger.warning("Webhook WhatsApp recebido mas o canal offline/não configurado.")
        return {"status": "ignored"}

    asyncio.create_task(wa_channel.process_webhook_payload(payload))
    return {"status": "ok"}


@router.post("/googlechat")
async def handle_googlechat_webhook(request: Request) -> JSONResponse:
    channel = "googlechat"
    cfg = _channel_cfg(channel)
    allowed, retry_after = _rate_limit_check(channel, request, cfg)
    if not allowed:
        return _error_response(
            channel=channel,
            code="rate_limited",
            message="Limite de requisições excedido para o webhook",
            status_code=429,
            details={"retry_after_seconds": retry_after},
        )

    payload, parse_error, raw_body = await _read_json_body(request, channel, cfg)
    if parse_error:
        return parse_error
    if payload is None:
        return _error_response(
            channel=channel,
            code="invalid_payload",
            message="Payload ausente",
            status_code=400,
        )

    auth_error = _authenticate_request(request=request, channel=channel, cfg=cfg, raw_body=raw_body)
    if auth_error:
        return auth_error

    sanitized_payload = _sanitize_payload(payload)
    if not isinstance(sanitized_payload, dict):
        return _error_response(
            channel=channel,
            code="invalid_payload",
            message="Payload inválido após sanitização",
            status_code=400,
        )

    validation_error = _validate_googlechat_payload(sanitized_payload)
    if validation_error:
        return _error_response(
            channel=channel,
            code="invalid_payload",
            message=validation_error,
            status_code=400,
        )

    gc_channel = _resolve_googlechat_channel()
    if not gc_channel:
        logger.warning("Webhook Google Chat recebido mas o canal offline/não configurado.")
        return _error_response(
            channel=channel,
            code="channel_unavailable",
            message="Canal Google Chat não está ativo",
            status_code=503,
        )

    try:
        response = await gc_channel.process_webhook_payload(sanitized_payload)
    except Exception as exc:
        logger.error(f"Falha no processamento do webhook Google Chat: {exc}")
        return _error_response(
            channel=channel,
            code="processing_error",
            message="Falha ao processar webhook",
            status_code=500,
        )
    if not isinstance(response, dict):
        return _error_response(
            channel=channel,
            code="invalid_channel_response",
            message="Resposta inválida do canal",
            status_code=502,
        )
    return JSONResponse(response or {"text": ""})


@router.post("/irc")
async def handle_irc_webhook(request: Request) -> JSONResponse:
    channel = "irc"
    cfg = _channel_cfg(channel)
    allowed, retry_after = _rate_limit_check(channel, request, cfg)
    if not allowed:
        return _error_response(
            channel=channel,
            code="rate_limited",
            message="Limite de requisições excedido para o webhook",
            status_code=429,
            details={"retry_after_seconds": retry_after},
        )

    payload, parse_error, raw_body = await _read_json_body(request, channel, cfg)
    if parse_error:
        return parse_error
    if payload is None:
        return _error_response(
            channel=channel,
            code="invalid_payload",
            message="Payload ausente",
            status_code=400,
        )

    auth_error = _authenticate_request(request=request, channel=channel, cfg=cfg, raw_body=raw_body)
    if auth_error:
        return auth_error

    sanitized_payload = _sanitize_payload(payload)
    if not isinstance(sanitized_payload, dict):
        return _error_response(
            channel=channel,
            code="invalid_payload",
            message="Payload inválido após sanitização",
            status_code=400,
        )

    validation_error = _validate_irc_payload(sanitized_payload)
    if validation_error:
        return _error_response(
            channel=channel,
            code="invalid_payload",
            message=validation_error,
            status_code=400,
        )

    irc_channel = _resolve_irc_channel()
    if not irc_channel:
        logger.warning("Webhook IRC recebido mas o canal offline/não configurado.")
        return _error_response(
            channel=channel,
            code="channel_unavailable",
            message="Canal IRC não está ativo",
            status_code=503,
        )
    try:
        await irc_channel.process_webhook_payload(sanitized_payload)
    except Exception as exc:
        logger.error(f"Falha no processamento do webhook IRC: {exc}")
        return _error_response(
            channel=channel,
            code="processing_error",
            message="Falha ao processar webhook",
            status_code=500,
        )
    return JSONResponse({"ok": True, "channel": channel, "status": "ok"})


@router.post("/signal")
async def handle_signal_webhook(request: Request) -> JSONResponse:
    channel = "signal"
    cfg = _channel_cfg(channel)
    allowed, retry_after = _rate_limit_check(channel, request, cfg)
    if not allowed:
        return _error_response(
            channel=channel,
            code="rate_limited",
            message="Limite de requisições excedido para o webhook",
            status_code=429,
            details={"retry_after_seconds": retry_after},
        )

    payload, parse_error, raw_body = await _read_json_body(request, channel, cfg)
    if parse_error:
        return parse_error
    if payload is None:
        return _error_response(
            channel=channel,
            code="invalid_payload",
            message="Payload ausente",
            status_code=400,
        )

    auth_error = _authenticate_request(request=request, channel=channel, cfg=cfg, raw_body=raw_body)
    if auth_error:
        return auth_error

    sanitized_payload = _sanitize_payload(payload)
    if not isinstance(sanitized_payload, dict):
        return _error_response(
            channel=channel,
            code="invalid_payload",
            message="Payload inválido após sanitização",
            status_code=400,
        )

    validation_error = _validate_signal_payload(sanitized_payload)
    if validation_error:
        return _error_response(
            channel=channel,
            code="invalid_payload",
            message=validation_error,
            status_code=400,
        )

    sig_channel = _resolve_signal_channel()
    if not sig_channel:
        logger.warning("Webhook Signal recebido mas o canal offline/não configurado.")
        return _error_response(
            channel=channel,
            code="channel_unavailable",
            message="Canal Signal não está ativo",
            status_code=503,
        )
    try:
        await sig_channel.process_webhook_payload(sanitized_payload)
    except Exception as exc:
        logger.error(f"Falha no processamento do webhook Signal: {exc}")
        return _error_response(
            channel=channel,
            code="processing_error",
            message="Falha ao processar webhook",
            status_code=500,
        )
    return JSONResponse({"ok": True, "channel": channel, "status": "ok"})


@router.post("/imessage")
async def handle_imessage_webhook(request: Request) -> JSONResponse:
    channel = "imessage"
    cfg = _channel_cfg(channel)
    allowed, retry_after = _rate_limit_check(channel, request, cfg)
    if not allowed:
        return _error_response(
            channel=channel,
            code="rate_limited",
            message="Limite de requisições excedido para o webhook",
            status_code=429,
            details={"retry_after_seconds": retry_after},
        )

    payload, parse_error, raw_body = await _read_json_body(request, channel, cfg)
    if parse_error:
        return parse_error
    if payload is None:
        return _error_response(
            channel=channel,
            code="invalid_payload",
            message="Payload ausente",
            status_code=400,
        )

    auth_error = _authenticate_request(request=request, channel=channel, cfg=cfg, raw_body=raw_body)
    if auth_error:
        return auth_error

    sanitized_payload = _sanitize_payload(payload)
    if not isinstance(sanitized_payload, dict):
        return _error_response(
            channel=channel,
            code="invalid_payload",
            message="Payload inválido após sanitização",
            status_code=400,
        )

    validation_error = _validate_imessage_payload(sanitized_payload)
    if validation_error:
        return _error_response(
            channel=channel,
            code="invalid_payload",
            message=validation_error,
            status_code=400,
        )

    imsg_channel = _resolve_imessage_channel()
    if not imsg_channel:
        logger.warning("Webhook iMessage recebido mas o canal offline/não configurado.")
        return _error_response(
            channel=channel,
            code="channel_unavailable",
            message="Canal iMessage não está ativo",
            status_code=503,
        )
    try:
        await imsg_channel.process_webhook_payload(sanitized_payload)
    except Exception as exc:
        logger.error(f"Falha no processamento do webhook iMessage: {exc}")
        return _error_response(
            channel=channel,
            code="processing_error",
            message="Falha ao processar webhook",
            status_code=500,
        )
    return JSONResponse({"ok": True, "channel": channel, "status": "ok"})
