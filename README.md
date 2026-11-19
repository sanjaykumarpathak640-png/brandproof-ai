# BrandProof AI

**Every claim checked. Every flag proven.**

BrandProof AI checks marketing content — posts, ads, emails, PDFs, Word files and **posters** — against an organisation's approved facts, rules, terminology, logo and colour palette *before* it is published. It works in **English, Hindi and Hinglish**. Every issue shows the exact guideline or fact behind it and a fix that keeps the creator's message. A person always approves, and every approval is sealed in a hash-chained **Proof Certificate** that records the verified approvers.

Built by **Team Bug Hunters (IIT Patna)** for the *Inkloom AI* brand-governance problem statement.

- **Live:** https://brandproof-ai-ddlp.onrender.com — click **“Try the demo — no sign-up”**
- **API docs:** `/docs` (OpenAPI) · **Accuracy report:** `/#/accuracy`
- More docs: [User guide](docs/USER_GUIDE.md) · [Architecture](docs/ARCHITECTURE.md) · [Testing](docs/TESTING.md) · [Roadmap](docs/ROADMAP.md) · [Changelog](CHANGELOG.md)

> The demo brand **ABC Electronics** and all sample people are fictional.

---

## Quick start (local, 2 minutes)

Requirements: **Python 3.11+** (3.12 recommended). Nothing else — SQLite is used automatically.

```bash
git clone https://github.com/sanjaykumarpathak640-png/brandproof-ai.git
cd brandproof-ai
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://localhost:8000** and click **Try the demo**. A private sandbox with the ABC Electronics brand and sample history is created for you.

Optional AI (tone review, reading text in images, logo fallback, free-form brand-book import):

```bash
export GEMINI_API_KEY=your_key       # Windows PowerShell: $env:GEMINI_API_KEY="your_key"
uvicorn app.main:app --reload
```

Without a key every rule-based check still works, and the app says clearly which AI features were skipped.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | *(empty)* | Enables the AI layer (Google Gemini). |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Model name. If Google retires it, the app switches to the model Google suggests or the newest available Flash model. |
| `DATABASE_URL` | *(empty)* | `postgres://…` to use PostgreSQL. Empty → SQLite. |
| `DB_PATH` | `data/brandproof.db` | SQLite file location. |
| `ADMIN_TOKEN` | *(empty)* | Protects `POST /api/benchmark/run`. |
| `AI_MAX_CALLS_PER_MIN` | `12` | Rate limit that protects the free AI quota. |

## Deploy on Render (free)

1. Fork or push this repo to GitHub (public).
2. Render → **New → Blueprint** → select the repo. `render.yaml` creates a **free PostgreSQL database** and the **web service**, and wires `DATABASE_URL` automatically.
3. Set `GEMINI_API_KEY` (optional) in the service's Environment tab.
4. Open the service URL. Health check: `/api/health` (shows `"db": "postgres"`).

Notes: Render's free web service sleeps when idle (first request can take ~50 s; the app shows a “waking up” message). Render's free PostgreSQL is for evaluation use.

## What it does

| Area | Features |
|---|---|
| **Accounts & teams** | Email + password sign-up (scrypt-hashed), team workspaces, invite links with roles (Creator, Compliance, Reviewer, Brand Admin), role management, HTTP-only session cookies. **Demo sandboxes:** one private workspace per visitor with a guided tour; deleted after 48 h idle. |
| **Brand Memory** | Versioned facts with source and validity dates (expired facts kept to catch outdated info), rules with severity and source, terminology, confidential terms, colour palette, approved logo, brand voice. Brand-book import (PDF/DOCX/TXT): patterns for “Label: value” lines, AI for free-form books — every value must appear in the document — all as *pending* candidates for the admin. |
| **Impact preview** | Before changing a fact, term, rule or confidential list, see which *already-approved* content would now be flagged. |
| **Text checks** | 15+ deterministic rules: price (digits or words; **outdated** prices), discount limit (incl. “half price”, “aadhe daam”), T&C disclaimer, warranty (incl. lifetime/paraphrased), battery (incl. “never runs out”), IP rating, superlatives, guarantees, terminology, product name, hype, urgency, confidential leaks, long sentences — **English, Hindi (Devanagari) and Hinglish**. PDF findings show page and paragraph. |
| **Creative (image) checks** | Text inside the image read by the vision model and run through the **same rules**, with boxes drawn on the image; **contrast measured per text block**; **logo presence** by pixel template matching (no AI) with a vision-model fallback; palette ΔE; alt text (with an AI draft). |
| **AI layer** | Gemini judges tone, messaging and implied claims. **Evidence verifier**: an AI finding is kept only if it quotes real text and cites a real rule; drops are counted on screen. Redaction of emails/phones/confidential terms; **Confidential mode** sends nothing; results cached by content hash; rate-limited; graceful fallback to rules. |
| **Fixes** | Accept fixes one by one; only flagged words change; **Purpose Guard** checks the product, offer, call-to-action and goal words survive; automatic re-check; word-level diff. |
| **Workflow** | Creator → Compliance (if high-risk) → Reviewer, enforced on the server. High-severity findings can be dismissed only by Compliance with a reason. **Four-eyes rule:** nobody approves their own submission in a team. Request changes, reject, resubmit as a new version, comments, audit trail, “next step” banner. Double submits/approvals are refused (idempotent). |
| **Proof Certificates** | SHA-256 content hash, Brand Memory version, every decision, verified approver identities, AI model; hash-chained per workspace; chain re-verification and “is this the approved text?”. |
| **Insights** | Repeated mistakes, issues by creator and channel, **guideline health** (rules reviewers keep overriding → “unclear”) with a drafted clearer rule. |
| **Accuracy** | 266-sample labelled benchmark (EN/HI/Hinglish; digits, words, paraphrase, meaning-based) with an in-app report: rules-only vs rules + AI. |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q                                   # 31 tests, SQLite, no network (AI is mocked)
DATABASE_URL=postgres://… pytest -q         # same suite on PostgreSQL
python -m benchmark.run_benchmark           # accuracy report → benchmark/results.json
python -m benchmark.run_benchmark --ai      # + rules vs rules+AI on the hard subset (needs GEMINI_API_KEY)
```

See [docs/TESTING.md](docs/TESTING.md) for the end-to-end browser test and the manual test checklist.

## Project structure

```
app/
  main.py              FastAPI app: REST API, auth context, error handling, static frontend
  auth.py              accounts, workspaces, invites, sessions, demo sandboxes, roles
  db.py                SQLite / PostgreSQL storage layer (every table scoped by org_id)
  engine.py            deterministic rule engine, risk score, fixes, Purpose Guard
  lang.py              numbers & claims in words: English, Hinglish, Hindi (Devanagari)
  vision.py            text in images + per-box contrast, logo template matching
  ai.py                Gemini: review, OCR, logo, alt text, brand-book extraction; verifier, cache, rate limit
  service.py           checks, workflow, insights, brand-book import, impact preview
  certs.py             hash-chained Proof Certificates
  extract.py           PDF/DOCX/TXT extraction, palette ΔE, contrast maths
  seed.py              demo brand (ABC Electronics) + sample history
  benchmark_runner.py  accuracy scoring used by CLI and the Accuracy page
static/                index.html, app.js (core), pages.js (pages), styles.css, samples/
benchmark/             build_samples.py, samples.json (266), run_benchmark.py, results.json
tests/                 test_brandproof.py (pytest), run_e2e.py (Playwright) + fake_ai_server.py
docs/                  USER_GUIDE, ARCHITECTURE, TESTING, ROADMAP
```

## Team Bug Hunters — IIT Patna

| Member | Role |
|---|---|
| Ayush Kumar (Team Leader) | AI & architecture: governance engine, AI verifier, vision pipeline |
| Akanksha Mishra | Backend: APIs, database, accounts & approval workflow |
| Shiksha Rawat | Frontend: checker, review pages, guided demo |
| Mahima Kumari | UI/UX & accessibility |
| Md Akil Akhtar | Document & image processing, deployment |
| Antra Priyadarshini | Research, benchmark dataset, testing & documentation |
