"""
24-hour simulation: Monday interaction → Tuesday silence → Thursday return.

Verifies Priya resumes from last checkpoint after session window expiry.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.webhook import app, build_meta_payload
from ridhi.checkpoints import Checkpoint
from ridhi.priya_flow import PriyaFlow
from ridhi.state_manager import InMemoryBackend, SessionStateManager

IST = timezone(timedelta(hours=5, minutes=30))

# Monday 10:00 IST
MONDAY = datetime(2026, 5, 11, 10, 0, 0, tzinfo=IST)
# Thursday 11:00 IST (>48h later, window long expired)
THURSDAY = datetime(2026, 5, 14, 11, 0, 0, tzinfo=IST)

WA_ID = "919999888877"


@pytest.fixture
def flow() -> PriyaFlow:
    backend = InMemoryBackend()
    sm = SessionStateManager(backend=backend)
    return PriyaFlow(sm)


def test_monday_tuesday_thursday_resume_from_checkpoint(flow: PriyaFlow) -> None:
    """Full scenario: name + project on Monday, silence, EOI resume on Thursday."""
    # --- Monday: provide name ---
    r1 = flow.handle_message(WA_ID, "राजेश कुमार", message_time=MONDAY, wamid="wamid.mon.1")
    assert r1.advanced_checkpoint
    assert r1.state.last_checkpoint == Checkpoint.PROJECT_INTEREST
    assert r1.state.data.cp_name == "राजेश कुमार"
    assert any("प्रोजेक्ट" in reply or "Sunrise" in reply for reply in r1.replies)

    # --- Monday: select project ---
    monday_2 = MONDAY + timedelta(minutes=5)
    r2 = flow.handle_message(WA_ID, "1 Sunrise", message_time=monday_2, wamid="wamid.mon.2")
    assert r2.state.last_checkpoint == Checkpoint.EOI_CONFIRMATION
    assert "proj_sunrise" in r2.state.data.project_ids
    assert any("EOI" in reply for reply in r2.replies)

    # Tuesday: silence — no messages (state persists in backend)

    # --- Thursday: CP returns after >24h ---
    r3 = flow.handle_message(
        WA_ID,
        "नमस्ते, मैं वापस आ गया हूँ",
        message_time=THURSDAY,
        wamid="wamid.thu.1",
    )

    assert r3.session_was_expired, "Should detect expired WhatsApp session window"
    assert r3.state.re_engagement_count >= 1

    # Hindi re-engagement message (Priya response in Hindi)
    hindi_replies = [reply for reply in r3.replies if _has_devanagari(reply)]
    assert hindi_replies, f"Expected Hindi reply on re-engagement, got: {r3.replies}"

    # Still at EOI checkpoint — not restarted to NAME_COLLECTION
    assert r3.state.last_checkpoint == Checkpoint.EOI_CONFIRMATION
    assert r3.state.data.cp_name == "राजेश कुमार"
    assert "proj_sunrise" in r3.state.data.project_ids

    # --- Thursday: confirm EOI ---
    thu_2 = THURSDAY + timedelta(minutes=2)
    r4 = flow.handle_message(WA_ID, "पुष्टि", message_time=thu_2, wamid="wamid.thu.2")
    assert r4.state.last_checkpoint == Checkpoint.COMPLETED
    assert r4.state.data.eoi_accepted
    assert any("बधाई" in reply for reply in r4.replies)


def test_webhook_meta_payload_monday_thursday() -> None:
    """Webhook integration: same scenario via FastAPI + Meta payload format."""
    client = TestClient(app)
    wa_id = "919888777666"

    # Monday — name
    p1 = build_meta_payload(wa_id, "अमित शर्मा", wamid="wamid.wh.1")
    res1 = client.post("/webhook/whatsapp", json=p1)
    assert res1.status_code == 200
    assert res1.json()["checkpoint"] == "PROJECT_INTEREST"

    # Monday — project (simulate via direct state not time-travel in webhook)
    p2 = build_meta_payload(wa_id, "2 Green Valley", wamid="wamid.wh.2")
    res2 = client.post("/webhook/whatsapp", json=p2)
    assert res2.json()["checkpoint"] == "EOI_CONFIRMATION"

    # Manually backdate session expiry to simulate Tuesday silence
    from api.webhook import _state_manager

    state = _state_manager.load_state(wa_id)
    assert state is not None
    expired_at = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    state.session_window_expires_at = expired_at
    state.last_user_message_at = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
    _state_manager.save_state(state)

    # Thursday return
    p3 = build_meta_payload(wa_id, "नमस्ते, फिर से शुरू करें", wamid="wamid.wh.3")
    res3 = client.post("/webhook/whatsapp", json=p3)
    body3 = res3.json()
    assert body3["session_was_expired"] is True
    assert body3["checkpoint"] == "EOI_CONFIRMATION"
    assert any(_has_devanagari(r) for r in body3["replies"])


def test_business_initiated_template_after_expiry(flow: PriyaFlow) -> None:
    """When PropOS messages first after 24h, template is required."""
    flow.handle_message(WA_ID, "सुनील वर्मा", message_time=MONDAY, wamid="wamid.biz.1")

    result = flow.trigger_business_reengagement(WA_ID)
    assert result.used_template
    assert result.template_name == "reengage_mid_hi"
    assert "PropOS" in result.replies[0] or "ऑनबोर्डिंग" in result.replies[0]

    flow.handle_message(WA_ID, "1", message_time=MONDAY + timedelta(minutes=3), wamid="wamid.biz.2")
    near = flow.trigger_business_reengagement(WA_ID)
    assert near.template_name == "reengage_near_complete_hi"


def test_redis_fallback_in_memory() -> None:
    sm = SessionStateManager(backend=InMemoryBackend())
    state = sm.get_or_create("919111222333")
    assert state.wa_id == "919111222333"
    loaded = sm.load_state("919111222333")
    assert loaded is not None
    assert loaded.cp_id == state.cp_id


def _has_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in text)
