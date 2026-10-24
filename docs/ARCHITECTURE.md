# Grahak Sampark - Kaise kaam karta hai

**Kaam:** CSP inoperative account list ki photo daalta hai → app padh leta hai →
CSP check karta hai → har customer ko WhatsApp message (Hindi + English).

## Kaun kya karta hai

| Hissa | Kaam |
|---|---|
| Web page | Login, photo upload, check, send |
| OCR | Photo se account, naam, mobile padhta hai |
| ├ Voxomos (optional) | Bahar ki OCR service - DPDP clearance ke baad hi |
| └ RapidOCR (backup) | Laptop/server par hi, bina internet - Voxomos fail ho to yahi |
| Check | Naam, 11 digit account, 10 digit mobile, duplicate jaanchta hai |
| Database (server) | Sirf logins, har list ki ginti, STOP wale numbers (hash) - koi customer list nahi |
| WhatsApp | CSP ke apne WhatsApp se, ek tap = ek customer |
| CSP ka phone | **List sirf yahin rehti hai** - check, WhatsApp, "aaya", 7 din baad reminder, 30 din baad delete |

## Ek list ka safar

1. CSP apni ID se **login** karta hai.
2. List ki **photo** (ya Excel) daalta hai.
3. App **padhta hai** - sirf account, naam, mobile rakhta hai, baaki sab phenk deta hai.
4. Har row par label: ✅ OK · ⚠️ galti · 📞 mobile nahi (call/visit).
5. CSP **paper se milata hai**, tick lagata hai, **Save** karta hai.
6. Har customer ke aage **WhatsApp button** - tap karo, Send dabao.
7. Phone: 7 din baad reminder, "aaya" mark, STOP wale ko kabhi message nahi.

## DPDP

- Sirf 3 cheezein: account, naam, mobile.
- **List server par kabhi save nahi hoti** - photo padh ke bhool jaata hai, list sirf CSP ke phone mein (30 din baad delete).
- Har CSP ko sirf apni list dikhti hai.
- Log mein customer data nahi.
- Voxomos asli list ke liye tabhi: saving band + India server + agreement + naya key.
- Claude ya koi AI app ke andar nahi hai.

## Kahan chalta hai

- **Abhi:** laptop par (`127.0.0.1:8000`).
- **Aage:** India server par HTTPS link - CSP phone se kholega.

*Problem aaye to: [TROUBLESHOOTING.md](TROUBLESHOOTING.md) · Detail chahiye to: [HOW_IT_WORKS.md](HOW_IT_WORKS.md) · [DATA_PROTECTION.md](DATA_PROTECTION.md) · [DEPLOYMENT.md](DEPLOYMENT.md)*
