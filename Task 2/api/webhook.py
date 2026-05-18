"""
WhatsApp webhook mock — Meta Cloud API format.

POST /webhook/whatsapp — inbound messages
GET  /webhook/whatsapp — hub verification
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ridhi.priya_flow import PriyaFlow
from ridhi.state_manager import SessionStateManager

app = FastAPI(title="Ridhi WhatsApp Webhook Mock")

_state_manager = SessionStateManager()
_priya = PriyaFlow(_state_manager)


class OutboundMessage(BaseModel):
    to: str
    type: str = "text"
    text: dict[str, str]


class WebhookResponse(BaseModel):
    status: str
    wa_id: str
    replies: list[str]
    checkpoint: str
    session_was_expired: bool
    used_template: bool = False


@app.get("/webhook/whatsapp")
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
) -> int | str:
    token = os.getenv("WHATSAPP_VERIFY_TOKEN", "propos_ridhi_dev")
    if hub_mode == "subscribe" and hub_verify_token == token:
        return int(hub_challenge) if hub_challenge.isdigit() else hub_challenge
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/whatsapp", response_model=WebhookResponse)
async def receive_whatsapp(request: Request) -> WebhookResponse:
    """
    Accept standard Meta WhatsApp Business webhook payload.
    https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks
    """
    payload: dict[str, Any] = await request.json()
    message = _extract_message(payload)
    if not message:
        return WebhookResponse(
            status="ignored",
            wa_id="",
            replies=[],
            checkpoint="",
            session_was_expired=False,
        )

    wa_id = message["from"]
    text = message.get("text", "")
    wamid = message.get("id", "")

    result = _priya.handle_message(wa_id, text, wamid=wamid or None)

    return WebhookResponse(
        status="ok",
        wa_id=wa_id,
        replies=result.replies,
        checkpoint=result.state.last_checkpoint.value,
        session_was_expired=result.session_was_expired,
        used_template=result.used_template,
    )


@app.post("/admin/reengage/{wa_id}", response_model=WebhookResponse)
def business_reengage(wa_id: str) -> WebhookResponse:
    """Simulate business-initiated template after 24h window."""
    result = _priya.trigger_business_reengagement(wa_id)
    return WebhookResponse(
        status="ok",
        wa_id=wa_id,
        replies=result.replies,
        checkpoint=result.state.last_checkpoint.value,
        session_was_expired=True,
        used_template=result.used_template,
    )


@app.get("/admin/state/{wa_id}")
def get_state(wa_id: str) -> dict[str, Any]:
    state = _state_manager.load_state(wa_id)
    if not state:
        raise HTTPException(status_code=404, detail="CP not found")
    return state.to_dict()


def _extract_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]["value"]
        messages = change.get("messages")
        if not messages:
            return None
        msg = messages[0]
        return {
            "from": msg["from"],
            "id": msg.get("id", ""),
            "text": msg.get("text", {}).get("body", ""),
            "timestamp": msg.get("timestamp"),
        }
    except (KeyError, IndexError, TypeError):
        return None


def build_meta_payload(wa_id: str, text: str, wamid: str = "wamid.test") -> dict[str, Any]:
    """Helper for tests — standard Meta inbound message envelope."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550000000",
                                "phone_number_id": "PHONE_NUMBER_ID",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test CP"},
                                    "wa_id": wa_id,
                                }
                            ],
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": wamid,
                                    "timestamp": "1715000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
