# WhatsApp template for Meta approval

Submit this in **Meta Business Manager -> WhatsApp Manager -> Message templates
-> Create template**. The text must match `app/messages.py` exactly, because the
app fills the same placeholders.

| Field | Value |
|---|---|
| Category | **Utility** (account status update the customer needs to act on) |
| Name | `inoperative_account_reactivation` (put the same name in `.env` as `WHATSAPP_TEMPLATE_NAME`) |
| Language | **Hindi** (`hi`) - the body is Hindi followed by English; set `WHATSAPP_TEMPLATE_LANG=hi` |
| Header | none |
| Buttons | none |

## Body (438 of 1024 characters)

```
नमस्ते {{1}} जी,
आपका SBI खाता ({{2}}) लंबे समय से उपयोग न होने के कारण निष्क्रिय (Inoperative) हो गया है।
इसे फिर से चालू करने के लिए कृपया अपना आधार कार्ड / पैन कार्ड लेकर इस SBI ग्राहक सेवा केंद्र पर आएं:
{{3}}, {{4}}
धन्यवाद।

Dear {{5}},
Your SBI account ({{6}}) has become inoperative as it was not used for a long time.
To reactivate it, please visit this SBI Customer Service Point with your Aadhaar / PAN:
{{7}}, {{8}}
Thank you.
```

## Footer (43 of 60 characters)

```
SBI CSP (Eko). Reply STOP to stop messages.
```

## Sample values (Meta asks for one example per placeholder)

| Placeholder | Meaning | Example to give Meta |
|---|---|---|
| `{{1}}` and `{{5}}` | customer's first name | `Ramesh` |
| `{{2}}` and `{{6}}` | last 4 digits of the account(s) | `XXXX5970` |
| `{{3}}` and `{{7}}` | CSP shop name | `Sharma Grahak Seva Kendra` |
| `{{4}}` and `{{8}}` | CSP address | `Main Road, Village Rampur` |

The Hindi and English halves use separate placeholders because Meta expects each
placeholder once, and each half ends with text ("धन्यवाद।" / "Thank you.") because
Meta rejects templates that end with a placeholder.

## Notes

- Meta may move a template to **Marketing** if it reads like promotion; this text
  is a factual account-status notice, which fits Utility. If Meta re-categorises
  it, sending still works but costs more per message.
- Only the last 4 digits of the account are ever sent (DPDP minimal disclosure).
- The footer tells customers how to opt out. Replies of STOP / बंद / रोकें are
  caught by the webhook and that number is never messaged again.
- Have Eko compliance approve this wording before submitting.

## Webhook setup (delivery status + STOP replies)

In the Meta app -> WhatsApp -> Configuration -> Webhook:

- Callback URL: `https://<your-domain>/webhook/whatsapp`
- Verify token: any long random word; put the same in `.env` as `WHATSAPP_VERIFY_TOKEN`
- Subscribe to the **messages** field
- Put the Meta app's **App secret** in `.env` as `WHATSAPP_APP_SECRET`
  (every webhook call is checked against it; calls without a valid signature are refused)
