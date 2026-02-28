from typing import Any
from fastapi import APIRouter, Request, HTTPException, Query
import logging

from clawlite.channels.manager import manager
from clawlite.channels.whatsapp import WhatsAppChannel

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


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
    active = [
        channel
        for key, channel in manager.active_channels.items()
        if (key == "whatsapp" or key.startswith("whatsapp:")) and isinstance(channel, WhatsAppChannel)
    ]
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

# O Meta Cloud API pede verificação de webhook
@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """Valida o webhook originado do Meta."""
    # Neste modo Lite aceitamos o challenge se os dados baterem
    if hub_mode == "subscribe" and hub_challenge:
        return int(hub_challenge)
    raise HTTPException(status_code=400, detail="Invalid verify token")


@router.post("/whatsapp")
async def handle_whatsapp_webhook(request: Request):
    """
    Recebe mensagens do WhatsApp e encaminha 
    para a instância ativa do WhatsAppChannel.
    """
    payload = await request.json()
    
    wa_channel = _resolve_whatsapp_channel(payload)
    
    if not wa_channel or not isinstance(wa_channel, WhatsAppChannel):
        logger.warning("Webhook WhatsApp recebido mas o canal offline/não configurado.")
        return {"status": "ignored"}

    # Dispara background processing
    import asyncio
    asyncio.create_task(wa_channel.process_webhook_payload(payload))
    
    # Retorna 200 OK imediato como exigido pela Meta
    return {"status": "ok"}
