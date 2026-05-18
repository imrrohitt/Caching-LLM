# Ridhi — WhatsApp Session State Architecture (Priya / CP Onboarding)

**Author:** PropOS Task 2  
**Scope:** Channel partner (CP) onboarding over WhatsApp (Hindi + English)  
**Constraint:** Meta WhatsApp Business API **24-hour customer service window**

---

## 1. Checkpoint design

Onboarding is split into **atomic, idempotent checkpoints**. Each checkpoint completes only when required data is validated and persisted; Priya never assumes partial in-memory state across restarts.

| # | Checkpoint ID | Purpose | Entry criteria | Completion criteria |
|---|---------------|---------|----------------|-------------------|
| 1 | `CONSENT` | GDPR/Meta opt-in, language pick | New CP (`wa_id` unknown) | `consent_given=true`, `language` set |
| 2 | `NAME_COLLECTION` | Legal / display name for CRM | `CONSENT` done | `cp_name` non-empty, validated |
| 3 | `PROJECT_INTEREST` | Which PropOS projects CP sells | `NAME_COLLECTION` done | `project_ids[]` has ≥1 selection |
| 4 | `KYC_DOCUMENTS` | PAN / RERA / ID upload links | `PROJECT_INTEREST` done | Required doc flags all `received` |
| 5 | `EOI_CONFIRMATION` | Expression of interest + terms | `KYC_DOCUMENTS` done | `eoi_accepted=true`, timestamp recorded |
| 6 | `COMPLETED` | Handoff to ops / CRM | `EOI_CONFIRMATION` done | Welcome pack sent, CRM sync queued |

**Monday → Tuesday → Thursday behaviour:**  
Checkpoints are **durable in Redis**, not tied to the WhatsApp session window. Silence on Tuesday does not roll back `NAME_COLLECTION` or `PROJECT_INTEREST`. On Thursday, Priya loads `last_checkpoint` and resumes the **next incomplete** step.

**Working code (Part B)** implements checkpoints 2–4 as a minimal 3-step flow: `NAME_COLLECTION` → `PROJECT_INTEREST` → `EOI_CONFIRMATION` (consent implied on first message).

---

## 2. Redis state schema

### Key structure

| Key pattern | Type | TTL | Purpose |
|-------------|------|-----|---------|
| `ridhi:cp:{wa_id}:onboarding` | `STRING` (JSON) | **90 days** | Canonical onboarding state |
| `ridhi:cp:{wa_id}:session` | `HASH` | **48 hours** | Fast session-window metadata |
| `ridhi:cp:{wa_id}:msg:{wamid}` | `STRING` | 7 days | Idempotency for webhook `wamid` |
| `ridhi:phone:{e164}:wa_id` | `STRING` | 90 days | Resolve number changes → `wa_id` |

`wa_id` = WhatsApp user phone in E.164 without `+` (e.g. `919876543210`).

### Value schema — `ridhi:cp:{wa_id}:onboarding`

```json
{
  "cp_id": "cp_8f3a2b",
  "wa_id": "919876543210",
  "language": "hi",
  "last_checkpoint": "PROJECT_INTEREST",
  "completed_checkpoints": ["CONSENT", "NAME_COLLECTION"],
  "data": {
    "cp_name": "राजेश कुमार",
    "project_ids": ["proj_sunrise", "proj_greens"],
    "eoi_accepted": false
  },
  "last_user_message_at": "2026-05-12T09:15:00+05:30",
  "last_bot_message_at": "2026-05-12T09:15:45+05:30",
  "session_window_expires_at": "2026-05-13T09:15:00+05:30",
  "re_engagement_count": 1,
  "version": 3
}
```

### Value schema — `ridhi:cp:{wa_id}:session` (HASH)

| Field | Type | Description |
|-------|------|-------------|
| `expires_at` | ISO-8601 string | `last_user_message_at + 24h` |
| `is_expired` | `"0"` / `"1"` | Cached flag, recomputed on read |
| `last_template_sent` | ISO-8601 | When business-initiated template last used |
| `template_name` | string | e.g. `reengage_mid_hi` |

### Expiry handling

- **Onboarding JSON (90d):** Refreshed on every checkpoint save. If key missing on return → treat as new CP or offer “resume by phone verification”.
- **Session hash (48h):** TTL = 2× window so metadata survives one missed day; `is_expired` computed: `now > session_window_expires_at`.
- **Webhook idempotency:** `SET ridhi:cp:{wa_id}:msg:{wamid} 1 NX EX 604800` — duplicate deliveries ignored.

---

## 3. The 24-hour boundary (Monday → Tuesday → Thursday)

### Timeline

| Day | Event |
|-----|--------|
| **Monday 10:00** | CP completes name + project interest. `last_checkpoint=PROJECT_INTEREST`, window expires **Tuesday 10:00**. |
| **Tuesday** | Silence — no messages. Window **closes** Tuesday 10:00. State remains in Redis. |
| **Thursday 11:00** | CP sends: `हाँ, आगे बढ़ते हैं` |

### Exact sequence on Thursday (CP messages first)

1. **Meta webhook** → Ridhi `POST /webhook/whatsapp`.
2. **Idempotency** check on `wamid`.
3. **Load** `ridhi:cp:{wa_id}:onboarding` → checkpoint `PROJECT_INTEREST`, data intact.
4. **Session check:** `now > session_window_expires_at` → `session_expired=true`.
5. **Window reset:** CP’s inbound message **opens a new 24-hour service window**. Update `last_user_message_at`, `session_window_expires_at = now + 24h`.
6. **Priya’s first reply (free-form, not template):** Because the **customer messaged first**, Meta allows session messages. Priya sends a **Hindi re-engagement + resume** message (see code: `REENGAGE_RESUME_HI`), then immediately asks the **EOI confirmation** prompt for checkpoint 3.
7. **No template required** for step 6. Templates are only needed if **PropOS messages first** after window lapse (e.g. outbound nudge Tuesday evening).

### If PropOS must message first (business-initiated)

- After window close, only **approved templates** may be sent.
- Ridhi sets `re_engagement_count++`, logs `template_name`, sends Hindi template (§4).
- When CP replies to template, window opens → free-form resume.

---

## 4. Template message strategy (Hindi)

Meta approval typically takes **3–10 business days** (first submission often longer). **Launch implication:** submit all re-engagement templates **≥3 weeks before** Priya pilot; run English-only fallback if Hindi pending; never block checkpoint persistence on template approval.

### Template A — Mid-onboarding (`reengage_mid_hi`)

**Category:** Utility | **Language:** Hindi  

```
नमस्ते {{1}}! 👋
आपका PropOS पार्टनर ऑनबोर्डिंग अधूरा है।
आपने प्रोजेक्ट चुन लिया है — बस एक छोटा सा कदम बाकी है।
जारी रखने के लिए "हाँ" लिखकर जवाब दें।
```

`{{1}}` = CP first name. **Use when:** `last_checkpoint=PROJECT_INTEREST`, silence >24h, business-initiated nudge.

### Template B — Near-complete (`reengage_near_complete_hi`)

```
नमस्ते {{1}}!
बधाई हो — आपका PropOS ऑनबोर्डिंग लगभग पूरा है।
EOI की पुष्टि बाकी है। 2 मिनट में पूरा करें।
"पुष्टि" लिखकर जवाब दें।
```

**Use when:** `last_checkpoint=EOI_CONFIRMATION`, `eoi_accepted=false`.

---

## 5. Failure handling

### Redis unavailable

| Layer | Behaviour |
|-------|-----------|
| **Read path** | Try Redis → fallback to in-memory LRU (per pod, non-durable) → if miss, reply: *"सिस्टम व्यस्त है, कृपया कुछ मिनट बाद पुनः संदेश भेजें।"* + alert PagerDuty |
| **Write path** | Queue checkpoint to local WAL file / SQS retry buffer; ack webhook 200 to Meta (avoid retries storm); reconcile when Redis returns |
| **Never** | Silently restart onboarding from `CONSENT` — always prefer stale checkpoint over data loss |

### CP changes WhatsApp number mid-onboarding

1. New `wa_id` has no Redis key → appears as new user.
2. Priya asks: *"क्या आप पहले से पंजीकृत हैं? पुराना नंबर भेजें।"*
3. Ops links `ridhi:phone:{old_e164}:wa_id` → copy onboarding JSON to `ridhi:cp:{new_wa_id}:onboarding`, mark old key `migrated_to={new_wa_id}`.
4. Resume from `last_checkpoint` on new number; audit log for compliance.

---

## 6. State machine choice (Part B)

**Plain Python state machine** (not LangGraph) for the deliverable:

- Only **3 checkpoints** + session metadata — graph overhead not justified.
- Deterministic transitions ease **24h simulation tests** without LLM non-determinism in the loop.
- LangGraph adds value at 10+ tool-using steps; Ridhi can migrate later when Priya gains KYC OCR, CRM writes, and human handoff nodes.

---

## 7. Hindi LLM prompt (Priya)

Documented in `ridhi/hindi_prompts.py`. Example system intent:

> You are Priya, PropOS's WhatsApp onboarding assistant for Indian real estate channel partners. Reply in Hindi (Devanagari), warm and professional, ≤2 sentences. The CP paused onboarding and returned after several days. Acknowledge resume, state the next step (EOI confirmation), do not ask for information already collected.

See `PRIYA_REENGAGE_PROMPT` in code for the exact prompt used to generate `REENGAGE_RESUME_HI`.
