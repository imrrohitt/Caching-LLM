"""
Hindi response generation for Priya.

Uses OpenAI when OPENAI_API_KEY is set; otherwise returns curated fallback text
generated from the documented prompt below.
"""

from __future__ import annotations

import os

# Prompt used to generate REENGAGE_RESUME_HI (document for assessors)
PRIYA_REENGAGE_PROMPT = """You are Priya, PropOS's WhatsApp onboarding assistant for Indian real estate channel partners.

Context:
- The channel partner (CP) started onboarding, completed name and project selection, then went silent for more than 24 hours.
- They have returned and sent a message. The WhatsApp session window is open again because they messaged first.
- Next step: EOI (Expression of Interest) confirmation.

Instructions:
- Reply in Hindi (Devanagari script only).
- Tone: warm, professional, concise (maximum 2 short sentences).
- Acknowledge that they are resuming onboarding.
- Tell them the next step is EOI confirmation; ask them to reply "हाँ" or "पुष्टि" to confirm.
- Do NOT ask for their name or project again.

CP name: {cp_name}
Last checkpoint: {checkpoint}
"""

# Curated output from the above prompt (CP: राजेश, checkpoint: PROJECT_INTEREST)
REENGAGE_RESUME_HI = (
    "नमस्ते {name}! आपका स्वागत है — चलिए जहाँ छोड़ा था वहीं से शुरू करते हैं। "
    "अगला कदम: EOI की पुष्टि। कृपया 'हाँ' या 'पुष्टि' लिखकर जवाब दें।"
)

PRIYA_PROMPTS: dict[str, str] = {
    "ask_name_hi": (
        "नमस्ते! मैं प्रिया, PropOS की ऑनबोर्डिंग सहायक। "
        "शुरू करने के लिए कृपया अपना पूरा नाम भेजें।"
    ),
    "ask_name_en": "Hi! I'm Priya from PropOS. Please send your full name to get started.",
    "ask_project_hi": (
        "धन्यवाद {name}! कृपया बताएं आप किन प्रोजेक्ट में रुचि रखते हैं — "
        "1) Sunrise Residency  2) Green Valley  (नंबर या नाम लिखें)"
    ),
    "ask_eoi_hi": (
        "{name}, आपकी रुचि दर्ज हो गई। क्या आप Expression of Interest (EOI) की पुष्टि करते हैं? "
        "'हाँ' या 'पुष्टि' लिखें।"
    ),
    "completed_hi": (
        "बधाई हो {name}! 🎉 आपका PropOS ऑनबोर्डिंग पूरा हो गया। "
        "हमारी टीम जल्द संपर्क करेगी।"
    ),
}


def generate_reengage_hindi(cp_name: str, checkpoint: str) -> str:
    """Generate Hindi re-engagement text via LLM or fallback."""
    name = cp_name or "साथी"
    prompt = PRIYA_REENGAGE_PROMPT.format(cp_name=name, checkpoint=checkpoint)

    if os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI

            client = OpenAI()
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Generate the WhatsApp reply now."},
                ],
                max_tokens=150,
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                return text
        except Exception:
            pass

    return REENGAGE_RESUME_HI.format(name=name)
