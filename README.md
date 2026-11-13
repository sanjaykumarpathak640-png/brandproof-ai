# BrandProof AI

**Every claim checked. Every flag proven.**
BrandProof AI checks marketing content against an organisation's approved facts, rules, terminology and palette *before* it is published. Every issue shows the exact guideline or fact behind it, plus a fix that keeps the creator's message. A human always approves, and every approval is sealed in a hash-chained **Proof Certificate**.

Built by **Team Bug Hunters (IIT Patna)** for the *Inkloom AI* brand-governance problem statement. This is the Round 2 MVP.

> Demo brand: **ABC Electronics** (fictional). All people in the sample data are fictional.

---

## What works end-to-end

| Step | What happens |
|---|---|
| **1. Brand Memory** | Versioned facts (price, max discount, warranty, battery, IP rating, tagline, product name), each with a source and validity dates. Also rules (with severity and source), terminology, palette and confidential terms. The admin can import a brand-book PDF/DOCX/TXT. Extracted facts and terms become *pending candidates* until the admin approves them, and each approval creates a new Brand Memory version. |
| **2. Check** | Paste text, or upload PDF / DOCX / TXT / PNG / JPG. Deterministic checks run in code: prices (incl. **outdated** prices from expired facts), discount limits, T&C disclaimer, warranty, specs, superlatives, absolute guarantees, terminology, product name, hype / caps / `!!`, urgency, confidential terms and sentence length. For images: colour palette (**ΔE** distance), estimated contrast and missing alt text. PDF findings show **page · paragraph**. |
| **3. AI review (optional)** | When `GEMINI_API_KEY` is set, Gemini reviews tone, messaging and implied claims. An **evidence verifier** keeps an AI finding only if it quotes text that really exists in the draft and cites a real rule ID. Everything else is dropped, and the drop count is shown on screen. Emails, phone numbers and confidential terms are masked before sending. **Confidential mode** sends nothing to any AI service. |
| **4. Explainable report** | 0–100 risk score with a per-category breakdown. Each finding has a highlight in the text, severity, rule ID, message, measured value vs. approved value, the evidence (rule + fact + source) and a suggested fix. |
| **5. Fix + Purpose Guard** | Creators accept fixes one by one. Each fix replaces only the flagged words. **Purpose Guard** confirms the brand/product, call-to-action, offer and goal words are still present, and the revised text is re-checked automatically. |
| **6. BrandFlow approval** | Creator → **Compliance** (when high-severity issues exist) → **Reviewer** → approved. Rules are enforced on the server: a creator cannot dismiss a high-severity finding, only Compliance can, and only with a reason. Only a Reviewer can approve. Reviewers can request changes or reject, and the creator can resubmit a new version, which is re-checked. Includes comments, version history with diff, and a full audit trail. |
| **7. Proof Certificate** | Approval issues a certificate with the SHA-256 hash of the content, the Brand Memory version, every decision with its reason, the approvers and the AI model used. Each certificate includes the previous certificate's hash, so the chain can be re-verified at any time. *Verify* tells you whether a piece of text is exactly the approved version. |
| **8. Insights** | Most repeated mistakes, issues by creator/agency and channel, and **Guideline health**: rules that reviewers often dismiss or creators contest are marked *unclear*. The app drafts a clearer version of the rule (AI or template), which the admin can apply. |
| **9. Trust & feedback** | Explains how AI and data are used and lists the libraries, plus a built-in user-testing feedback form. |

Use the **“Acting as”** menu (top-right) to switch between Creator, Compliance, Reviewer and Brand Admin. No sign-up is needed for the demo.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# optional: export GEMINI_API_KEY=your_key
uvicorn app.main:app --reload
# open http://localhost:8000   ·   API docs at http://localhost:8000/docs
```

The SQLite database is created and seeded automatically on first start (`data/brandproof.db`). Delete that file to reset the demo.

## Deploy on Render (free)

1. Push this folder to a public GitHub repo.
2. In Render, choose **New → Blueprint** and select the repo. `render.yaml` is detected automatically.
   (Or **New → Web Service**: build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.)
3. Optional: add the environment variable `GEMINI_API_KEY`.
4. Open the URL. Health check: `/api/health`.

Note: on Render's free plan the disk is temporary, so the demo database re-seeds after each restart or redeploy.

## Tests & benchmark

```bash
pip install -r requirements-dev.txt
pytest -q                          # 12 tests: rules, fixes, workflow permissions, certificate chain, import, image, AI verifier, redaction
python -m benchmark.run_benchmark  # rule-engine accuracy on 42 labelled samples → benchmark/results.json
```

## Project structure

```
app/
  main.py      FastAPI routes (REST API + static frontend)
  engine.py    deterministic rule engine, risk score, fix application, Purpose Guard
  ai.py        optional Gemini layer: redaction, evidence verifier, rule & alt-text drafts
  service.py   checks, BrandFlow workflow, insights, brand-book import
  certs.py     hash-chained Proof Certificates
  extract.py   PDF/DOCX/TXT extraction, image colour (ΔE) and contrast analysis
  db.py        SQLite schema & helpers
  seed.py      demo Brand Memory + sample review history
static/        index.html, app.js, styles.css, samples/ (PDF, DOCX, images to try)
benchmark/     labelled samples + accuracy script
tests/         pytest suite
```

## Main API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | status, AI model, Brand Memory version |
| GET | `/api/brand` | full Brand Memory, versions and pending candidates |
| POST | `/api/check` | check text and/or image → findings, risk, AI verifier stats |
| POST | `/api/extract` | upload PDF/DOCX/TXT/image → text or image data |
| POST | `/api/fix` | apply accepted fixes → revised text, Purpose Guard, re-check |
| GET/POST | `/api/submissions` | list / submit for review |
| POST | `/api/submissions/{id}/action` | dismiss, clear_claims, approve, reject, request_changes, resubmit, comment |
| POST | `/api/brand/import` | extract candidates from a brand book (admin) |
| POST | `/api/brand/candidates/{id}/approve\|reject` | admin decision |
| POST | `/api/brand/facts`, `/api/brand/terms`, `/api/brand/rules/{id}/update` | edit Brand Memory (admin) |
| GET | `/api/insights`, POST `/api/insights/suggest/{rule}` | analytics and clearer-rule drafts |
| GET | `/api/certificates`, POST `/api/certificates/verify` | certificate chain and text verification |
| GET/POST | `/api/feedback` | user-testing feedback |

## Tech stack

Python 3.12 · FastAPI · Uvicorn · Pydantic · SQLite · pypdf · python-docx · Pillow · httpx → Google Gemini API (optional) · vanilla HTML/CSS/JS · Render.

## Team Bug Hunters — IIT Patna

| Member | Role |
|---|---|
| Ayush Kumar (Team Leader) | AI & architecture: governance engine, verification pipeline, risk score |
| Akanksha Mishra | Backend: APIs, database, roles & approval workflow |
| Shiksha Rawat | Frontend: checker, highlighted report, review queue |
| Mahima Kumari | UI/UX & accessibility module |
| Md Akil Akhtar | Document & image processing, deployment |
| Antra Priyadarshini | Research, benchmark dataset, testing & documentation |
