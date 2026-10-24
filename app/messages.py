"""The customer message, in Meta's template format.

BODY and FOOTER are submitted to Meta for approval exactly as written here
(see docs/WHATSAPP_TEMPLATE.md). The preview on the CSP's screen and the
WhatsApp sender both fill the same {{1}}..{{8}} placeholders, so what the CSP
sees is what the customer gets.

Only the greeting name and the last 4 digits of each account are filled in
(DPDP: minimal disclosure). The text says who is contacting the customer and
why, and how to opt out (DPDP: notice).
"""
import re

from app import config

BODY = (
    "नमस्ते {{1}} जी,\n"
    "आपका SBI खाता ({{2}}) लंबे समय से उपयोग न होने के कारण निष्क्रिय (Inoperative) हो गया है।\n"
    "इसे फिर से चालू करने के लिए कृपया अपना आधार कार्ड / पैन कार्ड लेकर इस SBI ग्राहक सेवा केंद्र पर आएं:\n"
    "{{3}}, {{4}}\n"
    "धन्यवाद।\n"
    "\n"
    "Dear {{5}},\n"
    "Your SBI account ({{6}}) has become inoperative as it was not used for a long time.\n"
    "To reactivate it, please visit this SBI Customer Service Point with your Aadhaar / PAN:\n"
    "{{7}}, {{8}}\n"
    "Thank you."
)

FOOTER = "SBI CSP (Eko). Reply STOP to stop messages."

# Meta rejects parameters with line breaks, tabs or 4+ spaces in a row.
_BAD_PARAM = re.compile(r"[\r\n\t]+| {4,}")


def _clean(value, limit=200):
    return _BAD_PARAM.sub(" ", str(value)).strip()[:limit] or "-"


def format_accounts(last4_list):
    return ", ".join(f"XXXX{d}" for d in last4_list)


def params(group, csp):
    """Values for {{1}}..{{8}}: name, accounts, CSP name, CSP address - once for
    the Hindi part, once for the English part (Meta wants each placeholder used once)."""
    four = [_clean(group["greeting"], 60), _clean(format_accounts(group["accounts_last4"])),
            _clean(csp["name"], 80), _clean(csp["address"], 150)]
    return four + four


REMINDER_HI = ("नमस्ते {name} जी, याद दिलाना: आपका SBI खाता ({accounts}) अभी भी निष्क्रिय है। "
               "कृपया आधार / पैन लेकर आएं: {csp_name}, {csp_address}। धन्यवाद।")
REMINDER_EN = ("Dear {name}, a reminder: your SBI account ({accounts}) is still inoperative. "
               "Please visit {csp_name}, {csp_address} with your Aadhaar / PAN. Thank you.")


def render_reminder(group, csp):
    name, accounts, csp_name, csp_address = params(group, csp)[:4]
    f = dict(name=name, accounts=accounts, csp_name=csp_name, csp_address=csp_address)
    extra = grievance_line()
    return (REMINDER_HI.format(**f) + "\n\n" + REMINDER_EN.format(**f) + "\n\n" + FOOTER
            + ("\n" + extra if extra else ""))


def grievance_line():
    """DPDP notice: where to ask or complain (added to every message)."""
    if not config.GRIEVANCE_CONTACT:
        return ""
    return f"सवाल / शिकायत - Questions / complaints: {config.GRIEVANCE_CONTACT}"


def render(group, csp):
    text = BODY
    for i, value in enumerate(params(group, csp), start=1):
        text = text.replace("{{%d}}" % i, value)
    extra = grievance_line()
    return text + "\n\n" + FOOTER + ("\n" + extra if extra else "")
