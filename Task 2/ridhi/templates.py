"""Meta-approved template definitions for business-initiated re-engagement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WhatsAppTemplate:
    name: str
    language: str
    category: str
    body: str
    use_when: str


# Architecture doc §4 — mid-onboarding
REENGAGE_MID_HI = WhatsAppTemplate(
    name="reengage_mid_hi",
    language="hi",
    category="UTILITY",
    body=(
        "नमस्ते {{1}}! 👋\n"
        "आपका PropOS पार्टनर ऑनबोर्डिंग अधूरा है।\n"
        "आपने प्रोजेक्ट चुन लिया है — बस एक छोटा सा कदम बाकी है।\n"
        'जारी रखने के लिए "हाँ" लिखकर जवाब दें।'
    ),
    use_when="last_checkpoint=PROJECT_INTEREST, >24h silence, business-initiated",
)

# Architecture doc §4 — near-complete
REENGAGE_NEAR_COMPLETE_HI = WhatsAppTemplate(
    name="reengage_near_complete_hi",
    language="hi",
    category="UTILITY",
    body=(
        "नमस्ते {{1}}!\n"
        "बधाई हो — आपका PropOS ऑनबोर्डिंग लगभग पूरा है।\n"
        "EOI की पुष्टि बाकी है। 2 मिनट में पूरा करें।\n"
        '"पुष्टि" लिखकर जवाब दें।'
    ),
    use_when="last_checkpoint=EOI_CONFIRMATION, eoi_accepted=false",
)


def render_template(template: WhatsAppTemplate, cp_name: str) -> str:
    return template.body.replace("{{1}}", cp_name or "साथी")
