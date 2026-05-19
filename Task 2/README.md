# WhatsApp Session State (Ridhi)

Conversation state management for channel-partner onboarding over WhatsApp, including the **Monday → Tuesday silence → Thursday return** pattern and Meta’s 24-hour messaging window.

## Overview

| Component | Location |
|-----------|----------|
| Architecture (checkpoints, Redis, 24h, templates, failures) | `docs/ARCHITECTURE.md` |
| WhatsApp webhook (Meta format) | `api/webhook.py` |
| Session state manager (Redis + in-memory fallback) | `ridhi/state_manager.py` |
| Onboarding flow (plain Python state machine) | `ridhi/priya_flow.py` |
| Hindi responses + LLM prompt | `ridhi/hindi_prompts.py` |
| Simulation tests | `tests/test_monday_thursday_flow.py` |

## Checkpoints

1. `NAME_COLLECTION` — partner full name  
2. `PROJECT_INTEREST` — project selection (1=Sunrise, 2=Green Valley)  
3. `EOI_CONFIRMATION` — expression of interest  
4. `COMPLETED` — terminal state  

The architecture doc also describes `CONSENT` and `KYC_DOCUMENTS` for a full production rollout.

## Quick start

```bash
cd "Task 2"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

### Run webhook server

```bash
./scripts/run_webhook.sh
# or: uvicorn api.webhook:app --reload --port 8001
```

```bash
curl -s -X POST http://localhost:8001/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "919876543210",
            "id": "wamid.001",
            "type": "text",
            "text": {"body": "राजेश कुमार"}
          }]
        }
      }]
    }]
  }' | jq
```

### Environment

| Variable | Description |
|----------|-------------|
| `REDIS_URL` | Optional Redis (e.g. `redis://localhost:6379/0`) |
| `OPENAI_API_KEY` | Optional — generates Hindi via LLM |
| `WHATSAPP_VERIFY_TOKEN` | Webhook verification (default `ridhi_dev_verify`) |

## State machine

**Plain Python** instead of LangGraph for this scope: deterministic checkpoints, straightforward Monday–Thursday tests, no LLM variance in transitions. Consider LangGraph when adding KYC OCR, CRM integration, and human handoff.

## Hindi prompts

See `PRIYA_REENGAGE_PROMPT` in `ridhi/hindi_prompts.py`. Curated Hindi fallback is used when `OPENAI_API_KEY` is not set.

## Tests

```bash
pytest -v tests/test_monday_thursday_flow.py
```

`test_monday_tuesday_thursday_resume_from_checkpoint` covers:

- **Monday:** name + project selection  
- **Tuesday:** silence (state persisted)  
- **Thursday:** expired session → Hindi re-engagement → resume at EOI  
- **Thursday:** EOI confirm → `COMPLETED`
