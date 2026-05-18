# Task 2: Ridhi — WhatsApp Session State Design

Priya (PropOS CP onboarding agent) conversation state management for the **Monday → Tuesday silence → Thursday return** scenario on WhatsApp.

## Deliverables

| Part | Item | Location |
|------|------|----------|
| **A** | Architecture (checkpoints, Redis, 24h, templates, failures) | `docs/ARCHITECTURE.md` |
| **B** | WhatsApp webhook mock (Meta format) | `api/webhook.py` |
| **B** | Session state manager (Redis + in-memory fallback) | `ridhi/state_manager.py` |
| **B** | Priya 3-checkpoint flow (plain Python FSM) | `ridhi/priya_flow.py` |
| **B** | Hindi responses + LLM prompt | `ridhi/hindi_prompts.py` |
| **B** | 24-hour simulation test | `tests/test_monday_thursday_flow.py` |

## Checkpoints (code)

1. `NAME_COLLECTION` — CP full name  
2. `PROJECT_INTEREST` — project selection (1=Sunrise, 2=Green Valley)  
3. `EOI_CONFIRMATION` — expression of interest  
4. `COMPLETED` — terminal state  

Architecture doc defines **6 checkpoints** including `CONSENT` and `KYC_DOCUMENTS` for full production.

## Quick start

```bash
cd "Task 2"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

### Run webhook server

```bash
uvicorn api.webhook:app --reload --port 8001
```

```bash
# Simulate Meta inbound message
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
| `WHATSAPP_VERIFY_TOKEN` | Webhook verification (default `propos_ridhi_dev`) |

## State machine choice

**Plain Python** over LangGraph: 3 deterministic checkpoints, easy Monday–Thursday simulation, no LLM variance in transitions. LangGraph recommended when Priya adds KYC OCR, CRM writes, and human handoff.

## Hindi prompt

See `PRIYA_REENGAGE_PROMPT` in `ridhi/hindi_prompts.py`. Fallback Hindi text is pre-generated when `OPENAI_API_KEY` is unset.

## Tests

```bash
pytest -v tests/test_monday_thursday_flow.py
```

`test_monday_tuesday_thursday_resume_from_checkpoint` simulates:

- **Monday:** name + project selection  
- **Tuesday:** silence (state in Redis/memory)  
- **Thursday:** session expired → Hindi re-engagement → resume at EOI (not restart)  
- **Thursday:** EOI confirm → `COMPLETED`
