# Testing

## 1. Automated tests — `pytest -q` (31 tests, all passing)
Runs on SQLite by default and on PostgreSQL with `DATABASE_URL=postgres://…` (both verified). AI calls are mocked, so no network is needed.

| Area | What is proven |
|---|---|
| Access | API refuses requests without a session; demo workspaces cannot read each other's submissions (404) |
| Rules | risky ad flags all core issues; clean copy passes; valid offer price and “100% guaranteed” not mis-flagged; outdated price cites the expired fact; every finding has evidence |
| Multilingual | 11 cases: words, Hinglish, Hindi for price, discount, warranty, battery, superlative, urgency |
| Fixes | risk 100 → 0 with Purpose Guard OK; confidential leaks have no auto-fix |
| Workflow | role permissions, reason required, Compliance gate, approve/clear/dismiss twice → 409, double submit returns the same submission, certificate chain valid, edited text fails verification, resubmit needs changed text |
| Teams | sign-up validation, duplicate email, invites (single use), role enforcement, four-eyes rule, verified approver identity on certificate, logout/login (email case-insensitive) |
| Brand Memory | import is admin-only, re-import doesn't duplicate, approve twice → 409; impact preview lists affected approved content; validation of numbers |
| Images | palette ΔE + logo pixel match without AI; text in image checked with boxes; poster ALL-CAPS not flagged; per-box contrast; second check served from cache |
| AI safety | verifier drops 2 of 3 fake findings; redaction of email/phone/confidential |
| Bad input | empty text, >20k chars, broken image, .exe, fake PDF, unknown submission, unknown action |
| Accuracy | benchmark ≥ 200 samples, precision ≥ 0.95, rule-detectable recall ≥ 0.95 |

## 2. Accuracy benchmark — `python -m benchmark.run_benchmark`
266 labelled samples (148 English, 71 Hinglish, 47 Hindi; digits, words, paraphrases, meaning-based). Results are also shown in the app (**Accuracy** page). The rules + AI comparison runs on the server on the hard subset.

## 3. End-to-end browser test — `tests/run_e2e.py` (Playwright)
Starts from the landing page and drives a real browser through: demo → check → fix → submit → reviewer approve → certificate → reload → approve twice (409) → Hinglish → Compliance dismiss + clear → request changes → auto-fix → resubmit → poster check → impact preview → brand-book import → insights → accuracy → certificates → empty input → sign-up (short password rejected) → invite → join in a second browser → four-eyes refusal → approval with verified identity → cross-workspace access (404) → wrong password → login → mobile viewport. Run it against a server with fake AI: `python tests/fake_ai_server.py` then `python tests/run_e2e.py`.

Issues found by this test and fixed: the demo guide panel covered the *Apply fixes* button (now the page leaves room for it); the header wrapped badly at 1360 px (nav moved to its own row); ALL-CAPS poster headlines produced noisy tone findings (now skipped for image text); the Hindi full stop “।” broke word boundaries (fixed in `lang.py`); “100%” in “100% guaranteed” wrongly triggered the T&C rule (fixed).

## 4. User testing
Round 2 testers (4) rated ease, trust and usefulness 5/5; their two improvement comments (smoother review step) led to the **Next step** banner, one-click role switch and reason chips in Round 3. Feedback is collected in-app on the **Trust** page.

## 5. Manual checklist before release
Refresh on every page · same action twice · empty states (new team workspace) · 6 MB+ upload · scanned PDF · wrong file type · AI key removed (rules-only) · Confidential mode · mobile width 390 px · keyboard navigation (Tab/Enter on highlights and rows).
