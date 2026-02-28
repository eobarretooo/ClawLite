from typing import Any
from fastapi import APIRouter, Request, HTTPException, Query
import logging

from clawlite.channels.manager import manager
from clawlite.channels.whatsapp import WhatsAppChannel

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

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
    
    # Busca a instância ativa do WhatsAppChannel no manager
    wa_channel = manager.active_channels.get("whatsapp")
    
    if not wa_channel or not isinstance(wa_channel, WhatsAppChannel):
        logger.warning("Webhook WhatsApp recebido mas o canal offline/não configurado.")
        return {"status": "ignored"}

    # Dispara background processing
    import asyncio
    asyncio.create_task(wa_channel.process_webhook_payload(payload))
    
    # Retorna 200 OK imediato como exigido pela Meta
    return {"status": "ok"}
