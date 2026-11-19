# Architecture

```
Browser (vanilla JS SPA: app.js + pages.js)
   │  REST/JSON · HTTP-only session cookie · X-Acting-Role header (validated server-side)
   ▼
FastAPI (app/main.py) ── error handlers (401/403/409/422/500 → friendly JSON), body-size limit
   │
   ├── auth.py      sessions → Ctx{org_id, user, role, roles, demo}; signup/login/invites; demo sandboxes
   ├── service.py   run_check · fix · workflow state machine · insights · import · impact preview
   │      ├── engine.py   deterministic rules + risk score + fix application + Purpose Guard
   │      │      └── lang.py   numbers/claims in words (EN · Hinglish · Hindi), Devanagari-safe boundaries
   │      ├── vision.py   image text (via ai.py) + per-box WCAG contrast + NumPy logo template matching
   │      ├── extract.py  PDF/DOCX/TXT text with page/paragraph offsets · palette ΔE (CIE76)
   │      ├── ai.py       Gemini calls: review · OCR · logo · alt text · brand-book · rule drafts
   │      │               redaction → call → evidence verifier; cache by content hash; rate limiter
   │      └── certs.py    SHA-256 content hash · per-workspace hash chain · verification
   └── db.py        SQLite (local) or PostgreSQL (production) — every business table has org_id
```

## Key decisions

| Decision | Why | Trade-off |
|---|---|---|
| **Rules first, AI second** | Prices, percentages, durations, ratings, terms, colours and contrast are measurable, so they are checked in code: exact, repeatable, free, and still working when AI is down or not allowed. | Rules can't judge meaning (competitor attacks, implied claims) — that is the AI's job. |
| **Evidence verifier** | An AI finding survives only if its quote exists verbatim in the draft and it cites a rule ID that exists in this workspace's Brand Memory. Drops are counted in the UI. | A true finding with a slightly wrong quote is dropped (we prefer missing to inventing). |
| **Same rule engine for image text** | Text read from a poster is joined line by line and checked by `engine.run_rules`; each finding is mapped back to the bounding box of its line. One source of truth for text and images. | Depends on OCR quality of the vision model; the boxes let a human verify. |
| **Logo: pixel match first** | Normalised cross-correlation (FFT + integral images, 14 scales) finds an unchanged logo without AI in ~50 ms; the vision model is asked only if that fails (resized/recoloured logos). | Heavily stylised logo variants need the AI path. |
| **Numbers in words** | `lang.py` parses English, Hinglish and Devanagari number words and multipliers (thousand / hazaar / हज़ार / lakh, “7k”, “dedh lakh”), currency before or after, percent words (percent / pratishat / प्रतिशत) and paraphrases (half price, aadhe daam, lifetime / aajeevan / आजीवन, battery never runs out). Every match keeps its original character offsets so it can be highlighted and fixed in place. | Pattern coverage is explicit; anything outside it falls to the AI layer. |
| **Versioned facts with validity dates** | Changing a fact ends the old one instead of deleting it, so content using an expired price is reported as *outdated* with both versions shown. | Admins should give a source when changing facts. |
| **Impact preview** | `impact_preview` builds a hypothetical Brand Memory snapshot and re-runs the rules over every approved item, before anything is saved. | Rule-based only (fast, no AI cost). |
| **Workspaces by `org_id`** | Every query is filtered by the session's org; demo visitors each get their own org, so judges never see each other's actions. | Cross-workspace sharing is not supported (by design). |
| **Server-enforced workflow** | Who may dismiss, clear, approve, reject or resubmit is decided in `service.act`, never in the browser. Four-eyes rule in teams. Repeated actions return 409. | — |
| **Hash-chained certificates** | Each certificate's hash covers its payload plus the previous certificate hash; editing any past record breaks re-verification. Approver identities are the signed-in accounts. | Integrity proof, not a legal e-signature. |
| **Vanilla JS, one service** | One deploy and one URL, with no build step. Fast cold start on free hosting. | Less component reuse than a framework. |
| **SQLite ↔ PostgreSQL** | Zero-setup local runs; persistent production data on Render PostgreSQL. A tiny adapter translates placeholders and `RETURNING id`. | Kept to portable SQL. |

## Data model (main tables)

`orgs`, `users`, `memberships(org_id,user_id,roles)`, `invites`, `sessions(token_hash, org_id, user_id, demo)`,
`meta`, `facts(valid_from, valid_to, source)`, `rules`, `terms`, `palette`, `assets(logo)`, `brand_versions`, `candidates`,
`submissions`, `versions(findings JSON, image, image_info, ai_info)`, `decisions`, `events` (audit), `comments`,
`certificates(number, payload, content_hash, prev_hash, cert_hash)`, `feedback`, `ai_cache`, `benchmark_runs`.

## The hardest parts

1. **No hallucinated flags.** Measurable checks in code; AI only for meaning; evidence verifier; per-finding evidence (rule + fact + source + validity).
2. **Multilingual numbers with exact positions.** Tokenised number-phrase grammar with Devanagari-aware word boundaries (the danda “।” is treated as punctuation), so “सात हज़ार रुपये।” is highlighted and replaced precisely.
3. **Posters.** OCR lines → same rules → boxes on the image; contrast measured inside each text box by 2-colour quantisation; logo template matching with FFT-based NCC.
4. **Safe multi-fix application.** Overlapping fixes resolved by severity; fixes applied from the end of the text backwards; Purpose Guard and automatic re-check afterwards.
