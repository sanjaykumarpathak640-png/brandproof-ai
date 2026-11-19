# Product roadmap

## Delivered (event)
- Round 1: plan. Round 2: MVP (rules, fixes, workflow, certificates, insights).
- Round 3: text inside images + logo check · real accounts, team workspaces, PostgreSQL, verified approvers, smoother review · Hindi/Hinglish & paraphrase-aware claims, 266-sample benchmark with rules vs rules + AI, guideline-change impact preview.

## Next 3 months
1. **Where content is written** — Chrome extension and Google Docs / Canva add-ons that check as you type; Slack/Teams approval notifications.
2. **SSO & enterprise controls** — Google/Microsoft sign-in, SCIM, per-workspace data retention, audit export (CSV/PDF), customer-managed AI keys.
3. **More languages** — Tamil, Telugu, Bengali, Marathi number words and claims; transliteration-aware matching.
4. **Video & audio** — speech-to-text and frame text for reels/ads, checked by the same rules.

## 6–12 months
5. **Regulation packs** — ASCI advertising code, financial-promotion and health-claim rule sets that teams can switch on.
6. **Agency mode** — one agency, many client brands, with separate Brand Memory and approvals.
7. **Learning loop** — accepted/dismissed findings tune rule severity per workspace; benchmark grows from real (anonymised, opt-in) decisions.
8. **Public API & webhooks** — let generative-AI tools call BrandProof before showing output (“governance-as-a-service”).

## Business model
Free tier (1 workspace, 3 members, 200 checks/month) → Team (per seat) → Business (SSO, regulation packs, audit export) → Enterprise (private deployment, own AI keys).

## Known limitations today
- Free hosting sleeps when idle (first load ~50 s).
- Scanned (image-only) PDFs are not OCR'd — upload pages as images instead.
- Video/audio not supported.
- Contrast check works per text line from OCR, not per glyph.
