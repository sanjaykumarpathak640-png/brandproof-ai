# Changelog

## v3.0 — Round 3 (19–21 Nov 2026)
**Improvement 1 — text inside images + logo check**
- Vision model reads every text line in a poster with its bounding box; lines run through the same rule engine; findings drawn as boxes on the image.
- Contrast measured inside each text box (WCAG ratio); ALL-CAPS poster headlines no longer flagged.
- Approved logo stored in Brand Memory; logo presence by NumPy template matching (no AI), vision-model fallback for resized/recoloured logos; new rules R-LOGO-01, R-IMG-01.
- AI results cached by image hash; rate limiter; alt-text drafts.

**Improvement 2 — real accounts, team workspaces, persistent storage, smoother review**
- Email/password accounts (scrypt), HTTP-only sessions, team workspaces, invite links with roles, member role management.
- Every table scoped by workspace; per-visitor private demo sandboxes with auto-cleanup.
- PostgreSQL support (Render free Postgres) — data survives redeploys.
- Proof Certificates record verified approver identities; per-workspace certificate chains; four-eyes rule.
- Review page: Next-step banner, one-click role switch, reason chips, queue filters.

**Improvement 3 — paraphrase-aware & Hindi/Hinglish checks, benchmark, impact preview**
- `lang.py`: numbers and claims in words — English, Hinglish, Hindi (Devanagari digits and words), half price / aadhe daam, lifetime / aajeevan / आजीवन, battery never runs out, Hindi superlatives/urgency/guarantees, Hindi disclaimer.
- AI review prompt handles Hindi/Hinglish and paraphrased claims.
- Benchmark grown to 266 labelled samples; Accuracy page with rules-only vs rules + AI.
- Guideline-change impact preview for facts, terms, confidential terms and rules.

**Reliability & usability**
- Idempotent submit/approve/clear/dismiss (409 on repeats); input limits; friendly errors for every failure; request timeouts; “waking up the server” message; state kept across refresh; empty states; keyboard focus styles; guided demo.
- Polish (v3.2): page icons, count-up stats, animated risk ring, hovering a highlight lights its finding (and back), clickable queue rows, certificate-style cards linked by hash, team avatars, loading skeletons, and a Ctrl/Cmd+K command palette to jump to any page, run a sample or switch role. No workflow changed.
- New look (v3.1): dark sidebar app layout with icons, judge path inside the sidebar, new landing page (live proof-marked example, "Try a caption" with no sign-up, How it works, what gets checked, live benchmark numbers) and a "How it works" page for new users and judges. No workflow changed.
- Faster, sturdier AI: one combined vision call per poster; text and image AI run in parallel; a backup Flash model answers when the main model is overloaded or times out (and is used directly for 3 minutes after an overload); rule results are never held back more than ~25 s by a slow AI service (the AI finishes in the background and is cached for the next run).
- AI-assisted free-form brand-book import (values verified against the document).
- 35 automated tests (SQLite + PostgreSQL), Playwright end-to-end test, docs.

## v2.0 — Round 2
Rule engine, explainable report, fixes with Purpose Guard, approval workflow, Proof Certificates, insights, brand-book import, image palette checks.
