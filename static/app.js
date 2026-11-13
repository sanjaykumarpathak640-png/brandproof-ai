/* BrandProof AI — frontend (vanilla JS, no build step) */
"use strict";

const PEOPLE = { creator: "Riya Sharma", compliance: "Neha Verma", reviewer: "Kabir Singh", admin: "Ayush (Brand Admin)" };
const ROLE_LABEL = { creator: "Creator", compliance: "Compliance", reviewer: "Reviewer", admin: "Brand Admin" };
const STATUS_LABEL = { draft: "Draft", compliance_review: "Waiting for Compliance", in_review: "Waiting for Reviewer", approved: "Approved", rejected: "Rejected", changes_requested: "Changes requested" };
const SAMPLES = {
  risky: { title: "Diwali Instagram post", channel: "Instagram", goal: "Promote the Diwali offer and drive purchases", ai: true,
    text: "ABC Electronics – India's No. 1 Brand! Buy SoundPods Pro for just ₹7,000. Get 50% OFF. 100% guaranteed performance with lifetime warranty!!" },
  outdated: { title: "Product page update", channel: "Website", goal: "Explain features and price", ai: false,
    text: "Meet Sound Pods Pro: 40 hours of battery, fully waterproof and now only ₹12,000. Get yours today." },
  confidential: { title: "Launch teaser", channel: "Twitter/X", goal: "Build excitement for upcoming launch", ai: true,
    text: "OMG something big is coming! Project Falcon is almost here and the new SoundPods Max will be the best earbuds in India. Hurry, pre-order now!!" },
  clean: { title: "Retail standee", channel: "Print", goal: "In-store awareness", ai: false,
    text: "SoundPods Pro – Smart Technology for Everyday Life. Enjoy 30 hours of playback and an approved 2-year warranty. Now up to 20% off this Diwali. T&C apply." },
};

const S = { role: "creator", health: null, brand: null };
try { S.role = localStorage.getItem("bp_role") || "creator"; } catch (e) {}

/* ---------------------------------------------------------------- helpers */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (s) => { try { return new Date(s).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); } catch (e) { return s; } };
const short = (h) => h ? h.slice(0, 10) + "…" + h.slice(-6) : "";

async function api(path, opts = {}) {
  const o = { headers: {}, ...opts };
  if (o.body && !(o.body instanceof FormData)) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(o.body); }
  const r = await fetch(path, o);
  let data = null;
  try { data = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error((data && (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))) || `Request failed (${r.status})`);
  return data;
}
function toast(msg, err = false) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), err ? 5200 : 3200);
}
function ask(title, placeholder = "", ok = "Confirm") {
  return new Promise((res) => {
    const bg = document.createElement("div");
    bg.className = "modal-bg";
    bg.innerHTML = `<div class="modal"><h3 style="margin-bottom:10px">${esc(title)}</h3>
      <textarea class="inp" style="min-height:90px" placeholder="${esc(placeholder)}"></textarea>
      <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-x>Cancel</button><button class="btn pri" data-ok>${esc(ok)}</button></div></div>`;
    document.body.appendChild(bg);
    const ta = $("textarea", bg); ta.focus();
    const done = (v) => { bg.remove(); res(v); };
    $("[data-x]", bg).onclick = () => done(null);
    $("[data-ok]", bg).onclick = () => { const v = ta.value.trim(); if (!v) { ta.style.borderColor = "var(--high)"; return; } done(v); };
    bg.onclick = (e) => { if (e.target === bg) done(null); };
  });
}
function busy(btn, on, label) {
  if (!btn) return;
  if (on) { btn.dataset.l = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spin"></span> ${label || "Working…"}`; }
  else { btn.disabled = false; btn.innerHTML = btn.dataset.l || btn.innerHTML; }
}

/* ---------------------------------------------------------------- shared renderers */
function highlight(text, findings) {
  const spans = findings.filter((f) => f.target !== "image" && f.end > f.start).sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start));
  const inserts = findings.filter((f) => f.target !== "image" && f.end === f.start);
  let out = "", pos = 0;
  const used = [];
  for (const f of spans) {
    if (f.start < pos) continue;
    out += esc(text.slice(pos, f.start));
    out += `<span class="hl ${f.severity}" data-n="${f.n}" title="${esc(f.rule_id + ": " + f.title)}">${esc(text.slice(f.start, f.end))}<sup>${f.n}</sup></span>`;
    pos = f.end; used.push(f);
  }
  out += esc(text.slice(pos));
  for (const f of inserts) out += ` <span class="ins" data-n="${f.n}">+ ${esc(f.fix ? f.fix.replacement.trim() : f.title)} <sup>${f.n}</sup></span>`;
  return out || '<span class="muted">(no text)</span>';
}

function findingCard(f, o = {}) {
  const ev = (f.evidence || []).map((e) => `<div><span class="ref">${esc(e.ref)}</span><span>${esc(e.text)}${e.valid ? ` <span class="muted">(${esc(e.valid)})</span>` : ""}${e.source ? ` <span class="muted">— ${esc(e.source)}</span>` : ""}</span></div>`).join("");
  const metric = f.metric && (f.metric.found || f.metric.swatch)
    ? `<div class="metric"><span class="a">${f.metric.swatch ? `<i class="swatch" style="background:${esc(f.metric.swatch)}"></i> ` : ""}Found: ${esc(f.metric.found)}</span><span class="b">${f.metric.approved ? "Approved: " + esc(f.metric.approved) : f.metric.limit ? "Limit: " + esc(f.metric.limit) : esc(f.metric.status || "")}${f.metric.nearest ? ` <i class="swatch" style="background:${esc(f.metric.nearest)}"></i>` : ""}</span></div>` : "";
  let fix = "";
  if (f.fix) {
    const before = f.end > f.start ? `<del>${esc(f.quote)}</del> → ` : (f.fix.target === "alt" ? "Alt text: " : "Add: ");
    const after = f.fix.replacement.trim() ? `<ins>${esc(f.fix.replacement.trim())}</ins>` : `<span class="muted">(remove)</span>`;
    const box = o.selectable && !f.fix.overlaps && f.fix.target !== "alt"
      ? `<input type="checkbox" data-accept="${esc(f.key)}" ${o.accepted && o.accepted.has(f.key) ? "checked" : ""} aria-label="Accept fix">` : "";
    fix = `<label class="fixbox">${box}<span><b>Suggested fix:</b> ${before}${after}${f.fix.note ? ` <span class="muted small">· ${esc(f.fix.note)}</span>` : ""}${f.fix.overlaps ? ' <span class="muted small">· covered by another fix</span>' : ""}</span></label>`;
  } else if (f.severity !== "review" || f.rule_id === "R-CONF-01") {
    fix = f.target === "image"
      ? `<div class="fixbox" style="background:#f8fafc"><span><b>Needs a design change.</b> <span class="muted">Swap to the nearest brand colour shown above.</span></span></div>`
      : `<div class="fixbox" style="background:#f8fafc"><span><b>Needs a human rewrite.</b> <span class="muted">No safe automatic fix for this one.</span></span></div>`;
  }
  const dec = o.decision ? `<div class="notice small" style="margin-top:8px">${o.decision.action === "dismissed" ? "Dismissed" : "Contested"} by <b>${esc(o.decision.by_name)}</b> (${esc(ROLE_LABEL[o.decision.by_role] || o.decision.by_role)}): “${esc(o.decision.reason)}”</div>` : "";
  const contest = o.contest ? (o.contests && o.contests[f.key]
      ? `<div class="notice small" style="margin-top:8px">You contested this: “${esc(o.contests[f.key])}” <a href="#" data-uncontest="${esc(f.key)}">undo</a></div>`
      : (f.severity !== "high" ? `<button class="btn sm" style="margin-top:8px" data-contest="${esc(f.key)}">Contest with a reason</button>` : `<div class="tiny muted" style="margin-top:6px">High severity — only Compliance can dismiss this.</div>`)) : "";
  const actions = o.actions || "";
  return `<div class="fcard ${f.severity} ${o.decision && o.decision.action === "dismissed" ? "dismissed" : ""}" id="f-${o.prefix || ""}${f.n}" data-n="${f.n}">
    <div class="hd"><span class="tag ${f.severity}">${f.severity}</span><span class="rid">${esc(f.rule_id)}</span><span class="ttl">${esc(f.title)}</span>
      ${f.engine === "ai" ? '<span class="tag ai">AI · verified</span>' : f.engine === "vision" ? '<span class="tag vision">Measured</span>' : '<span class="tag grey">Rule</span>'}
      <span class="muted tiny" style="margin-left:auto">#${f.n} · ${esc(f.location || "")}</span></div>
    ${f.quote ? `<div class="quote">“${esc(f.quote)}”</div>` : ""}
    <div>${esc(f.message)}</div>${metric}
    <div class="ev">${ev}</div>${fix}${dec}${contest}${actions}</div>`;
}

function gauge(score, level) {
  const c = 2 * Math.PI * 44, off = c * (1 - score / 100);
  const col = score >= 50 ? "var(--high)" : score >= 20 ? "#e59a14" : score > 0 ? "var(--rev)" : "var(--proof)";
  return `<div class="gauge"><svg width="104" height="104" viewBox="0 0 104 104"><circle cx="52" cy="52" r="44" stroke="#eef2f7" stroke-width="10" fill="none"/>
    <circle cx="52" cy="52" r="44" stroke="${col}" stroke-width="10" fill="none" stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${off}" transform="rotate(-90 52 52)"/></svg>
    <div class="v"><div><b>${score}</b><span>${esc(level)} risk</span></div></div></div>`;
}
function riskBlock(risk) {
  const max = Math.max(1, ...Object.values(risk.breakdown || {}));
  const bars = Object.entries(risk.breakdown || {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<div class="bar"><span>${esc(k)}</span><span class="t"><i style="width:${(100 * v) / max}%"></i></span><span class="muted">+${v}</span></div>`).join("");
  return `<div class="risk">${gauge(risk.score, risk.level)}<div class="bars">${bars || '<div class="muted small">No issues found against Brand Memory.</div>'}
    <div class="counts"><span class="tag high">${risk.counts.high} high</span><span class="tag medium">${risk.counts.medium} medium</span><span class="tag review">${risk.counts.review} review</span></div>
    <div class="tiny muted" style="margin-top:6px">Score = 25 per high + 10 per medium + 4 per review item (max 100).</div></div></div>`;
}
function aiNotice(ai) {
  if (!ai) return "";
  if (!ai.used) return `<div class="notice ai small">🛡️ <b>AI review:</b> ${esc(ai.error || "not used")} All findings above come from exact, repeatable rule checks.</div>`;
  const ex = (ai.dropped_examples || []).map((d) => `<li>“${esc(d.quote)}” — ${esc(d.reason)}</li>`).join("");
  return `<div class="notice ai small">🛡️ <b>Evidence verifier</b> (${esc(ai.model)}): the AI proposed <b>${ai.checked}</b> issue(s).
    <b>${ai.dropped}</b> dropped for having no evidence, <b>${ai.merged}</b> merged with rule findings, <b>${ai.checked - ai.dropped - ai.merged}</b> kept.
    ${ai.redactions ? `${ai.redactions} personal/confidential item(s) were masked before sending.` : "No personal data was sent."}
    ${ex ? `<ul style="margin:6px 0 0 16px;padding:0">${ex}</ul>` : ""}</div>`;
}
function wordDiff(a, b) {
  const A = a.split(/(\s+)/), B = b.split(/(\s+)/);
  const n = A.length, m = B.length;
  if (n * m > 400000) return esc(b);
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const ops = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) { ops.push(["=", A[i]]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) ops.push(["-", A[i++]]);
    else ops.push(["+", B[j++]]);
  }
  while (i < n) ops.push(["-", A[i++]]);
  while (j < m) ops.push(["+", B[j++]]);
  let out = "", del = "", ins = "", pend = "";
  const flush = () => { const tail = /\s$/.test(ins || del) ? " " : ""; if (del.trim()) out += `<del>${esc(del.trim())}</del>`; if (ins.trim()) out += (del.trim() ? " " : "") + `<ins>${esc(ins.trim())}</ins>`; out += tail; del = ins = ""; };
  for (const [t, tok] of ops) {
    const ws = !tok.trim();
    if (t === "=" && ws && (del || ins)) { pend += tok; continue; }
    if (t === "=") { if (del || ins) { flush(); out += pend; } else out += pend; pend = ""; out += esc(tok); continue; }
    if (pend) { if (del) del += pend; if (ins) ins += pend; if (!del && !ins) out += pend; pend = ""; }
    if (t === "-") del += tok; else ins += tok;
  }
  flush(); out += pend;
  return out;
}
function guardBlock(p) {
  if (!p || !p.total) return "";
  return `<div class="notice ${p.ok ? "ok" : "warn"} small"><b>Purpose Guard:</b> ${p.kept}/${p.total} key elements of the creator's message kept.
    <div class="guard">${p.items.map((i) => `<span class="${i.kept ? "" : "lost"}">${i.kept ? "✓" : "✗"} ${esc(i.item)}</span>`).join("")}</div></div>`;
}
function imageBlock(info, src) {
  if (!info) return "";
  const cols = info.colours.map((c) => `<div class="${c.on_palette ? "" : "off"}"><i class="swatch" style="background:${c.hex}"></i>${c.hex} · ${c.share}% · ΔE ${c.delta_e} → ${esc(c.nearest || "")}</div>`).join("");
  return `<div class="card"><h3>🎨 Image analysis <span class="tag vision">measured</span></h3>
    ${src ? `<img class="imgprev" src="${src}" alt="Uploaded creative">` : ""}
    <div class="row small" style="margin-top:8px"><span><b>${info.palette_match}%</b> of pixels on brand palette</span><span>·</span><span>Estimated main contrast <b>${info.contrast_estimate ?? "–"}:1</b></span><span>·</span><span>${info.width}×${info.height}px</span></div>
    <div class="colours">${cols}</div></div>`;
}

/* ---------------------------------------------------------------- router */
const routes = { "": home, check, queue, brand: brandPage, insights: insightsPage, certificates: certPage, trust: trustPage };
function route() {
  const h = location.hash.replace(/^#\/?/, "");
  const [name, arg] = h.split("/");
  $$("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.r === name));
  const fn = routes[name] || home;
  window.scrollTo(0, 0);
  Promise.resolve(fn(arg)).catch((e) => { $("#app").innerHTML = `<div class="notice err">${esc(e.message)}</div>`; });
}
window.addEventListener("hashchange", route);

async function refreshHeader() {
  try {
    S.health = await api("/api/health");
    const p = $("#aipill");
    p.textContent = S.health.ai ? `AI: ${S.health.model}` : "AI: off (rules only)";
    p.classList.toggle("on", S.health.ai);
    p.title = S.health.ai ? "Gemini is configured. Every AI finding passes the evidence verifier." : "No API key set. All deterministic checks still run.";
    const subs = await api("/api/submissions");
    const waiting = subs.filter((s) => (S.role === "compliance" && s.status === "compliance_review") || (S.role === "reviewer" && s.status === "in_review") || (S.role === "creator" && s.status === "changes_requested")).length;
    const q = $("#qcount"); q.hidden = !waiting; q.textContent = waiting;
  } catch (e) {}
}
$("#role").value = S.role;
$("#role").onchange = (e) => { S.role = e.target.value; try { localStorage.setItem("bp_role", S.role); } catch (er) {} toast(`Now acting as ${ROLE_LABEL[S.role]} · ${PEOPLE[S.role]}`); refreshHeader(); route(); };

/* ---------------------------------------------------------------- home */
async function home() {
  let ins = null;
  try { ins = await api("/api/insights"); } catch (e) {}
  $("#app").innerHTML = `
  <section class="hero">
    <div>
      <div class="eyebrow">Brand governance · before you publish</div>
      <h1 style="margin:10px 0 12px">Every claim checked.<br>Every flag <em>proven</em>.</h1>
      <p class="lead">BrandProof AI checks posts, ads, documents and images against your approved facts, rules and palette. Each issue shows the exact guideline behind it and a fix that keeps the creator's message. A person always approves, and every approval gets a tamper-evident Proof Certificate.</p>
      <div class="row" style="margin-top:16px">
        <button class="btn pri" id="go-demo">▶ Start the demo — no sign-up</button>
        <a class="btn" href="#/check">Check your own content</a>
      </div>
      <p class="small muted" style="margin-top:10px">Demo brand: <b>ABC Electronics</b> (fictional) with Brand Memory v${S.health ? S.health.brand_version : 1}. Use the “Acting as” menu to switch between Creator, Compliance, Reviewer and Brand Admin.</p>
    </div>
    <div class="demo-ad">
      <div class="bar">AI-generated draft · Instagram · Riya Sharma</div>
      <div style="padding:16px" class="doc" id="hero-doc"></div>
      <div style="padding:10px 14px" class="row small"><span class="tag high">4 high</span><span class="tag medium">3 medium</span><span class="muted">→ fixed to risk 0 with the offer, call-to-action and product kept</span></div>
    </div>
  </section>
  <section class="card" style="margin-top:18px"><h3>How it works</h3>
    <div class="steps">
      <div class="step"><span class="n">1</span><b>Brand Memory</b><span class="muted small">Admin imports the brand book. Facts, prices, rules, terms and palette are versioned with validity dates and approved by a person.</span></div>
      <div class="step"><span class="n">2</span><b>Check</b><span class="muted small">Exact rule checks for numbers, terms, colours and contrast run in code. AI judges tone and implied claims, and must cite a real rule and quote real text.</span></div>
      <div class="step"><span class="n">3</span><b>Fix &amp; Purpose Guard</b><span class="muted small">Each fix changes only the flagged words. Purpose Guard confirms the product, offer and call-to-action survive.</span></div>
      <div class="step"><span class="n">4</span><b>Approve &amp; Prove</b><span class="muted small">High-risk claims go to Compliance, then a Reviewer. Approval issues a hash-chained Proof Certificate.</span></div>
    </div></section>
  ${ins ? `<section class="grid g4" style="margin-top:16px">
    <div class="card kpi"><b>${ins.totals.issues_caught}</b><span>issues caught before publishing</span></div>
    <div class="card kpi"><b>${ins.totals.avg_risk_first} → ${ins.totals.avg_risk_approved}</b><span>average risk: first draft → approved</span></div>
    <div class="card kpi"><b>${ins.totals.certificates}</b><span>Proof Certificates in the chain</span></div>
    <div class="card kpi"><b>${ins.guideline_health.filter((h) => h.status === "unclear").length}</b><span>guideline(s) flagged as unclear</span></div>
  </section><p class="tiny muted">Numbers include the sample review history that ships with the demo.</p>` : ""}
  <section class="grid g3" style="margin-top:12px">
    <div class="card"><h3>📌 No evidence, no flag</h3><p class="muted small" style="margin:0">If the AI cannot quote the draft and cite a real rule, the finding is dropped. The app shows how many were dropped.</p></div>
    <div class="card"><h3>🕒 Catches outdated facts</h3><p class="muted small" style="margin:0">Facts have validity dates. Last season's price is flagged as <i>outdated</i>, with both versions shown.</p></div>
    <div class="card"><h3>🧭 Finds unclear rules</h3><p class="muted small" style="margin:0">When reviewers keep overriding a rule, Insights marks the guideline as unclear and drafts a clearer version for the admin.</p></div>
  </section>`;
  $("#hero-doc").innerHTML = esc(SAMPLES.risky.text);
  $("#go-demo").onclick = () => { CK.reset(SAMPLES.risky); S.autorun = true; if (S.role !== "creator") { S.role = "creator"; $("#role").value = "creator"; try { localStorage.setItem("bp_role", "creator"); } catch (e) {} } location.hash = "#/check"; };
}

/* ---------------------------------------------------------------- check */
const CK = {
  st: null,
  reset(sample) {
    this.st = { title: sample?.title || "", channel: sample?.channel || "Instagram", goal: sample?.goal || "", ai: !!sample?.ai, confidential: false,
      text: sample?.text || "", original: null, image: null, alt: "", result: null, accepted: new Set(), contests: {}, fixed: null, file: null };
  },
};
CK.reset();

async function check(sample) {
  if (sample && SAMPLES[sample]) { CK.reset(SAMPLES[sample]); S.autorun = true; history.replaceState(null, "", "#/check"); }
  const st = CK.st;
  $("#app").innerHTML = `
  <div class="page-h"><div><h2>Check content</h2><p>Paste a draft, or upload a PDF, DOCX or image. BrandProof checks it against Brand Memory before anyone publishes.</p></div>
    <div class="row small"><span class="muted">Try a sample:</span>
      <button class="btn sm" data-s="risky">Risky AI ad</button><button class="btn sm" data-s="outdated">Outdated facts</button>
      <button class="btn sm" data-s="confidential">Confidential leak</button><button class="btn sm" data-s="clean">Clean copy</button>
      <a class="btn sm" href="/static/samples/ABC_Diwali_Brochure.pdf" download>⬇ sample PDF</a>
      <a class="btn sm" href="/static/samples/diwali_poster_offbrand.png" download>⬇ sample image</a></div></div>
  <div class="split">
    <div class="stack">
      <div class="card stack">
        <div class="grid g2" style="gap:10px">
          <div><label class="f">Title</label><input class="inp" id="c-title" value="${esc(st.title)}" placeholder="e.g. Diwali Instagram post"></div>
          <div><label class="f">Channel</label><select class="inp" id="c-channel">${["Instagram", "Facebook", "Twitter/X", "Email", "Website", "SMS", "App notification", "Print", "Brochure / PDF"].map((c) => `<option ${c === st.channel ? "selected" : ""}>${c}</option>`).join("")}</select></div>
        </div>
        <div><label class="f">Creator's goal (Purpose Guard keeps this intact)</label><input class="inp" id="c-goal" value="${esc(st.goal)}" placeholder="e.g. Promote the Diwali offer and drive purchases"></div>
        <div><label class="f">Content</label><textarea class="inp" id="c-text" placeholder="Paste caption, ad copy, email or page text…">${esc(st.text)}</textarea></div>
        <div class="drop" id="c-drop">📎 Drop a <b>PDF, DOCX, TXT</b> or <b>PNG/JPG</b> here, or <a href="#" id="c-browse">browse</a><input type="file" id="c-file" hidden accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp"><div id="c-fileinfo" class="small" style="margin-top:6px"></div></div>
        <div id="c-imgbox" ${st.image ? "" : "hidden"}><label class="f">Image alt text</label><input class="inp" id="c-alt" value="${esc(st.alt)}" placeholder="Describe the image for screen-reader users"></div>
        <div class="grid g2" style="gap:8px">
          <label class="chk"><input type="checkbox" id="c-ai" ${st.ai ? "checked" : ""}> Draft was written with an AI tool (recorded on the certificate)</label>
          <label class="chk"><input type="checkbox" id="c-conf" ${st.confidential ? "checked" : ""}> <span><b>Confidential mode</b> — send nothing to any AI service</span></label>
        </div>
        <div class="row"><button class="btn pri" id="c-run">Run BrandProof check</button><button class="btn" id="c-clear">Clear</button>
          <span class="small muted">Brand Memory v${S.health ? S.health.brand_version : "?"}</span></div>
      </div>
      <div id="c-image"></div>
      <div id="c-fixed"></div>
    </div>
    <div class="stack" id="c-results">${st.result ? "" : `<div class="card empty">Run a check to see the risk score, highlighted issues, evidence and suggested fixes.<br><br><span class="small">Tip: “Risky AI ad” shows most of the checks at once.</span></div>`}</div>
  </div>`;

  const sync = () => { st.title = $("#c-title").value; st.channel = $("#c-channel").value; st.goal = $("#c-goal").value; st.text = $("#c-text").value; st.ai = $("#c-ai").checked; st.confidential = $("#c-conf").checked; st.alt = $("#c-alt") ? $("#c-alt").value : ""; };
  $$("[data-s]").forEach((b) => (b.onclick = () => { CK.reset(SAMPLES[b.dataset.s]); check().then(() => $("#c-run").click()); }));
  $("#c-clear").onclick = () => { CK.reset(); check(); };
  $("#c-browse").onclick = (e) => { e.preventDefault(); $("#c-file").click(); };
  const drop = $("#c-drop");
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]); };
  $("#c-file").onchange = (e) => e.target.files[0] && loadFile(e.target.files[0]);

  async function loadFile(file) {
    sync();
    const fd = new FormData(); fd.append("file", file);
    $("#c-fileinfo").innerHTML = '<span class="muted">Reading file…</span>';
    try {
      const r = await api("/api/extract", { method: "POST", body: fd });
      if (r.kind === "image") {
        st.image = r.image; st.file = r.filename;
        $("#c-imgbox").hidden = false;
        $("#c-fileinfo").innerHTML = `🖼️ <b>${esc(r.filename)}</b> attached — palette, contrast and alt text will be checked. <a href="#" id="c-rmimg">remove</a>`;
        $("#c-rmimg").onclick = (e) => { e.preventDefault(); st.image = null; $("#c-imgbox").hidden = true; $("#c-fileinfo").innerHTML = ""; };
        if (!st.title) $("#c-title").value = st.title = r.filename.replace(/\.\w+$/, "");
      } else {
        st.text = r.text; $("#c-text").value = r.text; st.file = r.filename;
        st.pages = r.pages; st.pagesText = r.text;
        $("#c-fileinfo").innerHTML = `📄 <b>${esc(r.filename)}</b> — ${r.page_count ? r.page_count + " page(s), " : ""}${r.text.split(/\n\s*\n/).length} paragraph(s) extracted. Issues will show page and paragraph.`;
        if (!st.title) $("#c-title").value = st.title = r.filename.replace(/\.\w+$/, "");
      }
    } catch (e) { $("#c-fileinfo").innerHTML = `<span style="color:var(--high)">${esc(e.message)}</span>`; }
  }

  $("#c-run").onclick = async () => {
    sync();
    if (!st.text.trim() && !st.image) return toast("Add some text or an image first.", true);
    const btn = $("#c-run"); busy(btn, true, "Checking…");
    try {
      st.result = await api("/api/check", { method: "POST", body: { text: st.text, goal: st.goal, confidential: st.confidential, image: st.image, alt_text: st.alt, pages: st.text === st.pagesText ? st.pages : null } });
      st.original = st.text; st.fixed = null; st.contests = {};
      st.accepted = new Set(st.result.findings.filter((f) => f.fix && !f.fix.overlaps && f.fix.target !== "alt").map((f) => f.key));
      renderResults();
    } catch (e) { toast(e.message, true); }
    busy(btn, false);
  };

  function renderResults() {
    const r = st.result; if (!r) return;
    const nFix = st.accepted.size;
    $("#c-results").innerHTML = `
      <div class="card"><div class="row between"><h3 style="margin:0">Risk assessment</h3><span class="small muted">Brand Memory v${r.brand_version}</span></div><div style="margin-top:10px">${riskBlock(r.risk)}</div></div>
      ${r.findings.filter((f) => f.target !== "image").length || st.text ? `<div class="card"><h3>Highlighted draft</h3><div class="doc" id="c-doc">${highlight(st.original || "", r.findings)}</div>
        <div class="tiny muted" style="margin-top:6px">Click a highlight to jump to its finding. Readability: Flesch ${r.metrics.readability.flesch ?? "–"} (${r.metrics.readability.words} words).</div></div>` : ""}
      <div class="card"><div class="row between"><h3 style="margin:0">Findings (${r.findings.length})</h3>
        <div class="row"><button class="btn sm" id="c-all">Select all fixes</button><button class="btn ok" id="c-apply" ${nFix ? "" : "disabled"}>Apply ${nFix} fix${nFix === 1 ? "" : "es"}</button></div></div>
        <div class="findings" style="margin-top:10px">${r.findings.length ? r.findings.map((f) => findingCard(f, { selectable: true, accepted: st.accepted, contest: true, contests: st.contests })).join("") : '<div class="notice ok">✅ No issues found. This draft matches Brand Memory.</div>'}</div>
        <div style="margin-top:10px">${aiNotice(r.ai)}</div></div>
      <div class="card"><div class="row between"><div><h3 style="margin:0">Submit for review</h3><div class="small muted">${submitHint(r)}</div></div>
        <button class="btn pri" id="c-submit">Submit ${st.fixed ? "revised" : "this"} version →</button></div></div>`;
    $("#c-image").innerHTML = imageBlock(r.image, st.image);
    bindDoc($("#c-results"), "");
    $$("[data-accept]").forEach((c) => (c.onchange = () => { c.checked ? st.accepted.add(c.dataset.accept) : st.accepted.delete(c.dataset.accept); renderResults(); }));
    $$("[data-contest]").forEach((b) => (b.onclick = async () => { const why = await ask("Why should this finding not apply?", "e.g. This is a dated festival offer, so urgency is factual.", "Contest"); if (why) { st.contests[b.dataset.contest] = why; renderResults(); } }));
    $$("[data-uncontest]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); delete st.contests[a.dataset.uncontest]; renderResults(); }));
    $("#c-all").onclick = () => { r.findings.forEach((f) => f.fix && !f.fix.overlaps && f.fix.target !== "alt" && st.accepted.add(f.key)); renderResults(); };
    $("#c-apply").onclick = applyFixes;
    $("#c-submit").onclick = submit;
    renderFixed();
  }
  function submitHint(r) {
    if (S.role !== "creator") return `Switch to the <b>Creator</b> role to submit.`;
    const open = (st.fixed ? st.fixed.recheck.risk : r.risk).counts.high;
    return open ? `${open} high-severity issue(s) still open → it will go to <b>Compliance</b> first, then a Reviewer.` : "No high-severity issues → it goes straight to a <b>Reviewer</b>.";
  }
  async function applyFixes() {
    const btn = $("#c-apply"); busy(btn, true, "Applying…");
    try {
      const fx = await api("/api/fix", { method: "POST", body: { text: st.original, findings: st.result.findings, accepted: [...st.accepted], goal: st.goal } });
      st.fixed = fx; renderResults();
      $("#c-fixed").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) { toast(e.message, true); busy(btn, false); }
  }
  function renderFixed() {
    const fx = st.fixed;
    if (!fx) { $("#c-fixed").innerHTML = ""; return; }
    $("#c-fixed").innerHTML = `<div class="card stack"><div class="row between"><h3 style="margin:0">✨ Revised version</h3>
        <span class="row small">Risk <b style="text-decoration:line-through;color:var(--muted)">${st.result.risk.score}</b> → <b style="color:${fx.recheck.risk.score ? "var(--med)" : "var(--proof)"}">${fx.recheck.risk.score}</b></span></div>
      <div class="diff">${wordDiff(st.original, fx.text)}</div>
      ${guardBlock(fx.purpose)}
      <div><label class="f">Edit before submitting (optional)</label><textarea class="inp" id="c-fixtext" style="min-height:90px">${esc(fx.text)}</textarea></div>
      ${fx.recheck.findings.length ? `<div class="notice warn small">Still open after fixes: ${fx.recheck.findings.map((f) => `<b>${esc(f.rule_id)}</b> ${esc(f.title)}`).join(" · ")}</div>` : '<div class="notice ok small">✅ The revised text passes every rule check.</div>'}
      <div class="tiny muted">Accepted AI rewrites are labelled “AI-assisted” in the audit trail until a reviewer approves them.</div></div>`;
    $("#c-fixtext").oninput = (e) => { fx.text = e.target.value; };
  }
  async function submit() {
    sync();
    if (S.role !== "creator") return toast("Switch to the Creator role (top-right) to submit.", true);
    const btn = $("#c-submit"); busy(btn, true, "Submitting…");
    const final = st.fixed ? st.fixed.text : st.original;
    const findingsForContest = st.fixed ? [] : Object.entries(st.contests).map(([key, reason]) => ({ key, reason }));
    try {
      const s = await api("/api/submissions", { method: "POST", body: { title: st.title || "Untitled", channel: st.channel, creator: PEOPLE.creator, goal: st.goal,
        ai_generated: st.ai, confidential: st.confidential, text: final, original_text: st.original, dismissals: findingsForContest, image: st.image, alt_text: st.alt, role: "creator" } });
      toast(`Submitted · ${STATUS_LABEL[s.status]}`);
      CK.reset(); refreshHeader();
      location.hash = `#/queue/${s.id}`;
    } catch (e) { toast(e.message, true); busy(btn, false); }
  }
  if (st.result) renderResults();
  if (S.autorun) { S.autorun = false; $("#c-run").click(); }
}

function bindDoc(root, prefix) {
  $$(".hl,.ins", root).forEach((h) => (h.onclick = () => {
    const c = $(`#f-${prefix}${h.dataset.n}`, root) || $(`#f-${prefix}${h.dataset.n}`);
    if (c) { c.scrollIntoView({ behavior: "smooth", block: "center" }); c.classList.remove("flash"); void c.offsetWidth; c.classList.add("flash"); }
  }));
}

/* ---------------------------------------------------------------- queue */
async function queue(id) {
  if (id) return submissionPage(+id);
  const subs = await api("/api/submissions");
  const mine = (s) => (S.role === "compliance" && s.status === "compliance_review") || (S.role === "reviewer" && s.status === "in_review") || (S.role === "creator" && s.status === "changes_requested");
  const rows = subs.map((s) => `<tr class="click" data-id="${s.id}"><td>${mine(s) ? "👉 " : ""}<b>${esc(s.title)}</b>${s.demo ? ' <span class="tag grey">sample</span>' : ""}<div class="tiny muted">${esc(s.channel)} · ${esc(s.creator)}</div></td>
    <td><span class="status st-${s.status}">${STATUS_LABEL[s.status] || s.status}</span></td><td><b>${s.risk}</b></td><td>v${s.current_version}</td><td>${s.has_certificate ? '<span class="tag ok">✓ certified</span>' : ""}</td><td class="small muted">${fmtDate(s.updated_at)}</td></tr>`).join("");
  const waiting = subs.filter(mine).length;
  $("#app").innerHTML = `<div class="page-h"><div><h2>Review queue</h2><p>Creator → Compliance (if high-risk claims) → Reviewer → Proof Certificate.</p></div>
    <div class="notice small">Acting as <b>${ROLE_LABEL[S.role]}</b>: ${waiting ? `<b>${waiting}</b> item(s) need your action (👉).` : "nothing waiting for you."}</div></div>
    <div class="card"><table class="t"><thead><tr><th>Content</th><th>Status</th><th>Risk</th><th>Version</th><th>Proof</th><th>Updated</th></tr></thead><tbody>${rows || '<tr><td colspan="6" class="empty">No submissions yet.</td></tr>'}</tbody></table></div>`;
  $$("tr[data-id]").forEach((tr) => (tr.onclick = () => (location.hash = `#/queue/${tr.dataset.id}`)));
}

async function submissionPage(id) {
  const s = await api(`/api/submissions/${id}`);
  const cur = s.versions[s.versions.length - 1];
  let vi = s.versions.length - 1;
  const decFor = (v, key) => s.decisions.filter((d) => d.version === v && d.finding_key === key).slice(-1)[0];
  const flow = ["Submitted", "Compliance", "Reviewer", "Certified"];
  const pos = { compliance_review: 1, in_review: 2, approved: 4, changes_requested: 1, rejected: 1 }[s.status] ?? 0;
  const hadCompliance = s.events.some((e) => e.action === "cleared claims") || s.status === "compliance_review";
  const stepper = flow.map((l, i) => {
    let c = i < pos ? "done" : i === pos ? "cur" : "";
    if (i === 1 && !hadCompliance && pos > 1) c = "done";
    if ((s.status === "rejected" || s.status === "changes_requested") && i === pos) c = "bad cur";
    return `<div class="${c}">${l}${i === 1 && !hadCompliance && pos > 1 ? " (skipped)" : ""}</div>`;
  }).join("");

  const act = (action, extra = {}) => api(`/api/submissions/${id}/action`, { method: "POST", body: { action, role: S.role, name: PEOPLE[S.role], ...extra } });
  const canDismiss = (f) => (S.role === "compliance") || (S.role === "reviewer" && f.severity !== "high");

  function actionsPanel() {
    const r = S.role, st = s.status;
    let html = "";
    if (r === "compliance" && st === "compliance_review") html = `<p class="small">Check every high-severity claim. Dismiss a finding only with a reason (it is recorded on the certificate). <b>${s.open_high}</b> high finding(s) open.</p>
      <div class="row"><button class="btn ok" data-a="clear_claims" ${s.open_high ? "disabled" : ""}>✓ Clear claims → send to Reviewer</button><button class="btn" data-a="request_changes">Request changes</button><button class="btn bad" data-a="reject">Reject</button></div>`;
    else if (r === "reviewer" && st === "in_review") html = `<p class="small">Final brand review. Approving issues a Proof Certificate for <b>v${cur.version}</b>.</p>
      <div class="row"><button class="btn ok" data-a="approve">✓ Approve &amp; issue certificate</button><button class="btn" data-a="request_changes">Request changes</button><button class="btn bad" data-a="reject">Reject</button></div>`;
    else if (r === "creator" && ["changes_requested", "compliance_review", "in_review"].includes(st)) html = `<p class="small">${st === "changes_requested" ? "The reviewer asked for changes. Edit the text and resubmit; it will be checked again." : "You can still resubmit an improved version."}</p>
      <textarea class="inp" id="s-new" style="min-height:100px">${esc(cur.text)}</textarea><div class="row" style="margin-top:8px"><button class="btn pri" id="s-resub">Resubmit as v${cur.version + 1}</button><button class="btn" id="s-autofix">Apply all suggested fixes</button></div>`;
    else if (st === "approved") html = `<p class="small">Approved and certified. Nothing left to do.</p>`;
    else if (st === "rejected") html = `<p class="small">This content was rejected.</p>`;
    else html = `<p class="small muted">Nothing for <b>${ROLE_LABEL[r]}</b> to do here right now. Switch role (top-right) to continue the workflow.</p>`;
    return html;
  }

  function render() {
    const v = s.versions[vi];
    const latest = vi === s.versions.length - 1;
    const tabs = s.versions.map((x, i) => `<button class="${i === vi ? "on" : ""}" data-v="${i}">v${x.version} · risk ${x.risk}</button>`).join("") + (s.versions.length > 1 ? `<button data-diff="1">Compare v${s.versions[0].version} → v${cur.version}</button>` : "");
    const cards = v.findings.map((f) => {
      const d = decFor(v.version, f.key);
      const actions = latest && !(d && d.action === "dismissed") && canDismiss(f) && ["compliance_review", "in_review"].includes(s.status) ? `<button class="btn sm" style="margin-top:8px" data-dismiss="${esc(f.key)}">Dismiss with reason</button>` : "";
      return findingCard(f, { decision: d, actions, prefix: "s" });
    }).join("");
    $("#app").innerHTML = `
      <div class="page-h"><div><a href="#/queue" class="small">← Review queue</a><h2 style="margin-top:4px">${esc(s.title)} ${s.demo ? '<span class="tag grey">sample</span>' : ""}</h2>
        <p>${esc(s.channel)} · by ${esc(s.creator)} · goal: “${esc(s.goal || "—")}” ${s.ai_generated ? '· <span class="tag ai">AI-assisted draft</span>' : ""}</p></div>
        <span class="status st-${s.status}" style="font-size:14px">${STATUS_LABEL[s.status]}</span></div>
      <div class="card" style="margin-bottom:16px"><div class="stepper">${stepper}</div></div>
      <div class="split">
        <div class="stack">
          <div class="card"><div class="vtabs">${tabs}</div><div id="s-view"><div class="doc" id="s-doc">${highlight(v.text, v.findings)}</div>
            ${v.image ? `<img class="imgprev" style="margin-top:10px" src="${v.image}" alt="Submitted creative">` : ""}
            <div class="tiny muted" style="margin-top:6px">${esc(v.note || "")} · Brand Memory v${v.brand_version} · ${fmtDate(v.created_at)}</div></div></div>
          <div class="card"><h3>Actions · ${ROLE_LABEL[S.role]}</h3>${actionsPanel()}</div>
          ${s.certificate ? certCard(s.certificate) : ""}
          <div class="card"><h3>Comments</h3>${s.comments.map((c) => `<div class="small" style="margin-bottom:8px"><b>${esc(c.author)}</b> <span class="muted">(${esc(ROLE_LABEL[c.role] || c.role)}) · ${fmtDate(c.created_at)}</span><div>${esc(c.text)}</div></div>`).join("") || '<p class="small muted">No comments yet.</p>'}
            <div class="row"><input class="inp" id="s-comment" placeholder="Add a comment as ${esc(PEOPLE[S.role])}…" style="flex:1"><button class="btn" id="s-csend">Post</button></div></div>
          <div class="card"><h3>Audit trail</h3><div class="tl">${s.events.map((e) => `<div><b>${esc(e.actor)}</b> <span class="muted">(${esc(ROLE_LABEL[e.role] || e.role)})</span> ${esc(e.action)} <span class="muted">${esc(e.detail || "")} · ${fmtDate(e.created_at)}</span></div>`).join("")}</div></div>
        </div>
        <div class="stack">
          <div class="card"><h3>Risk · v${v.version}</h3>${riskBlock(riskOf(v.findings))}</div>
          ${v.image_info ? imageBlock(v.image_info) : ""}
          <div class="card"><h3>Findings in v${v.version} (${v.findings.length})</h3><div class="findings">${cards || '<div class="notice ok">✅ No open issues in this version.</div>'}</div>
            <div style="margin-top:10px">${aiNotice(v.ai_info)}</div></div>
        </div>
      </div>`;
    bindDoc($("#app"), "s");
    $$("[data-v]").forEach((b) => (b.onclick = () => { vi = +b.dataset.v; render(); }));
    const d = $("[data-diff]"); if (d) d.onclick = () => { $("#s-view").innerHTML = `<div class="diff">${wordDiff(s.versions[0].text, cur.text)}</div><div class="tiny muted" style="margin-top:6px">Red = removed, green = added.</div>`; $$(".vtabs button").forEach((x) => x.classList.toggle("on", x === d)); };
    $$("[data-dismiss]").forEach((b) => (b.onclick = async () => {
      const why = await ask("Reason for dismissing this finding", "This reason is recorded in the audit trail and on the Proof Certificate.", "Dismiss");
      if (!why) return;
      try { Object.assign(s, await act("dismiss", { finding_key: b.dataset.dismiss, reason: why })); toast("Finding dismissed with reason"); render(); } catch (e) { toast(e.message, true); }
    }));
    $$("[data-a]").forEach((b) => (b.onclick = async () => {
      const a = b.dataset.a; let reason = "";
      if (a === "reject" || a === "request_changes") { reason = await ask(a === "reject" ? "Why is this rejected?" : "What should the creator change?", "", a === "reject" ? "Reject" : "Request changes"); if (!reason) return; }
      busy(b, true);
      try { Object.assign(s, await act(a, { reason })); toast(a === "approve" ? "Approved — Proof Certificate issued 🎉" : "Done"); refreshHeader(); submissionPage(id); } catch (e) { toast(e.message, true); busy(b, false); }
    }));
    const rs = $("#s-resub");
    if (rs) rs.onclick = async () => { busy(rs, true, "Checking…"); try { await act("resubmit", { text: $("#s-new").value, reason: "Revised after review" }); toast("Resubmitted and re-checked"); refreshHeader(); submissionPage(id); } catch (e) { toast(e.message, true); busy(rs, false); } };
    const af = $("#s-autofix");
    if (af) af.onclick = async () => { try { const fx = await api("/api/fix", { method: "POST", body: { text: cur.text, findings: cur.findings, accepted: cur.findings.filter((f) => f.fix && !f.fix.overlaps).map((f) => f.key), goal: s.goal } }); $("#s-new").value = fx.text; toast(`Fixes applied · new risk ${fx.recheck.risk.score} · Purpose Guard ${fx.purpose.kept}/${fx.purpose.total}`); } catch (e) { toast(e.message, true); } };
    $("#s-csend").onclick = async () => { const t = $("#s-comment").value.trim(); if (!t) return; try { Object.assign(s, await act("comment", { text: t })); render(); } catch (e) { toast(e.message, true); } };
  }
  render();
}
function riskOf(findings) {
  const W = { high: 25, medium: 10, review: 4 }, counts = { high: 0, medium: 0, review: 0 }, breakdown = {};
  let t = 0;
  findings.forEach((f) => { t += W[f.severity]; counts[f.severity]++; breakdown[f.category] = (breakdown[f.category] || 0) + W[f.severity]; });
  const score = Math.min(100, t);
  return { score, level: score >= 50 ? "High" : score >= 20 ? "Medium" : score > 0 ? "Low" : "Clear", counts, breakdown };
}

/* ---------------------------------------------------------------- certificates */
function certCard(c, full = false) {
  const p = c.payload;
  return `<div class="cert"><div class="row" style="align-items:flex-start;gap:14px"><div class="seal">#${c.number}</div><div style="flex:1;min-width:0">
    <div class="row between"><h3 style="margin:0">Proof Certificate #${c.number}</h3><span class="tag ok">✓ approved</span></div>
    <div class="small"><b>${esc(p.title)}</b> · ${esc(p.channel)} · v${p.version} by ${esc(p.creator)} · Brand Memory v${p.brand_memory_version} · AI: ${esc(p.ai_model)}${p.ai_generated_draft ? " · AI-assisted draft" : ""}</div>
    <div class="small muted">Approvals: ${p.approvers.map((a) => `${esc(a.name)} (${esc(ROLE_LABEL[a.role] || a.role)}, ${esc(a.action)})`).join(" → ") || "—"}</div>
    ${p.decisions.length ? `<div class="small muted">Decisions recorded: ${p.decisions.map((d) => `${esc(d.rule)} ${esc(d.action)} by ${esc(d.by)} — “${esc(d.reason)}”`).join("; ")}</div>` : ""}
    <div class="grid g2" style="gap:6px;margin-top:8px"><div><div class="tiny muted">Content hash (SHA-256)</div><div class="hash">${full ? c.content_hash : short(c.content_hash)}</div></div>
    <div><div class="tiny muted">Certificate hash · chained to #${c.number - 1 || "genesis"}</div><div class="hash">${full ? c.cert_hash : short(c.cert_hash)}</div></div></div>
    <div class="tiny muted" style="margin-top:6px">Issued ${fmtDate(p.issued_at)} · previous ${short(p.prev_hash)}</div></div></div></div>`;
}
async function certPage() {
  const d = await api("/api/certificates");
  const list = d.certificates.slice().reverse();
  $("#app").innerHTML = `<div class="page-h"><div><h2>Proof Certificates</h2><p>Every approval creates a certificate with the content's SHA-256 hash, the Brand Memory version, every decision and the AI used. Each certificate includes the hash of the one before it, so changing any past record breaks the chain.</p></div></div>
    <div class="grid g2" style="margin-bottom:16px">
      <div class="notice ${d.chain.ok ? "ok" : "err"}"><b>${d.chain.ok ? "✓ Chain intact" : "✗ Chain broken"}</b> — ${d.chain.count} certificate(s) re-hashed and verified just now.</div>
      <div class="card"><h3>Is this the approved text?</h3><textarea class="inp" id="v-text" style="min-height:70px" placeholder="Paste the exact text that is about to be published…"></textarea>
        <div class="row" style="margin-top:8px"><button class="btn pri" id="v-go">Verify</button><span id="v-out" class="small"></span></div></div>
    </div>
    <div class="stack">${list.map((c, i) => certCard(c, true) + (i < list.length - 1 ? '<div class="chainlink">⛓ chained</div>' : "")).join("") || '<div class="card empty">No certificates yet. Approve something in the Review queue.</div>'}</div>`;
  $("#v-go").onclick = async () => {
    const t = $("#v-text").value; if (!t.trim()) return;
    const r = await api("/api/certificates/verify", { method: "POST", body: { text: t } });
    $("#v-out").innerHTML = r.match ? `<span style="color:var(--proof)">✓ Matches certificate ${r.certificates.map((c) => "#" + c.number + " (" + esc(c.title) + ")").join(", ")}</span>` : `<span style="color:var(--high)">✗ No certificate matches this exact text. It has not been approved, or it was changed after approval.</span>`;
  };
}

/* ---------------------------------------------------------------- brand memory */
async function brandPage() {
  const b = await api("/api/brand");
  S.brand = b;
  const admin = S.role === "admin";
  const today = b.today;
  const facts = b.facts.slice().sort((x, y) => x.key.localeCompare(y.key) || (y.valid_from || "").localeCompare(x.valid_from || ""));
  $("#app").innerHTML = `<div class="page-h"><div><h2>Brand Memory <span class="tag grey">v${b.version}</span></h2><p>${esc(b.meta.brand_name)} · ${esc(b.meta.brand_book)} · tone: ${esc(b.meta.tone)}</p></div>
    ${admin ? '<span class="tag ok">You can edit (Brand Admin)</span>' : '<div class="notice small">Read-only. Switch to <b>Brand Admin</b> to edit or import.</div>'}</div>
  <div class="grid g2">
    <div class="card"><h3>📥 Import a brand book or update</h3><p class="small muted" style="margin-top:0">Upload a PDF, DOCX or TXT. BrandProof extracts facts (price, discount, warranty, specs), terms and confidential items as <b>pending</b> candidates. Nothing changes until the admin approves.</p>
      <div class="row"><input type="file" id="b-file" accept=".pdf,.docx,.txt,.md" ${admin ? "" : "disabled"}><button class="btn pri" id="b-imp" ${admin ? "" : "disabled"}>Extract</button></div>
      <div class="small" style="margin-top:6px"><a href="/static/samples/ABC_Brand_Update_Nov2026.docx" download>⬇ Sample brand update (DOCX)</a> — try importing it.</div>
      <div id="b-cands" style="margin-top:10px">${candList(b.candidates, admin)}</div></div>
    <div class="card"><h3>🕒 Version history</h3><div class="tl" style="max-height:260px;overflow:auto">${b.versions.map((v) => `<div><b>v${v.version}</b> ${esc(v.note)} <span class="muted">· ${fmtDate(v.created_at)}</span></div>`).join("")}</div></div>
  </div>
  <div class="card" style="margin-top:16px"><div class="row between"><h3 style="margin:0">Approved facts</h3><span class="small muted">Expired facts stay on record, so old prices can be flagged as <i>outdated</i>.</span></div>
    <table class="t" style="margin-top:8px"><thead><tr><th>ID</th><th>Fact</th><th>Value</th><th>Valid</th><th>Source</th></tr></thead><tbody>
    ${facts.map((f) => { const exp = f.valid_to && f.valid_to < today; return `<tr class="${exp ? "exp" : ""}"><td class="mono">${esc(f.id)}</td><td>${esc(f.label)}</td><td><b>${esc(f.value)}</b> ${esc(f.unit || "")}</td><td class="small">${esc(f.valid_from || "")} → ${esc(f.valid_to || "now")}${exp ? ' <span class="tag grey" style="text-decoration:none">expired</span>' : ""}</td><td class="small muted">${esc(f.source || "")}</td></tr>`; }).join("")}</tbody></table>
    ${admin ? `<div class="grid g4" style="gap:8px;margin-top:10px"><select class="inp" id="nf-key">${[["price", "Product price (MRP)", "INR"], ["max_discount", "Maximum discount", "%"], ["warranty_years", "Warranty", "years"], ["battery_hours", "Battery life (tested)", "hours"], ["ip_rating", "Water resistance rating", ""], ["tagline", "Approved tagline", ""], ["product_name", "Official product name", ""]].map(([k, l, u]) => `<option value="${k}" data-l="${l}" data-u="${u}">${l}</option>`).join("")}</select>
      <input class="inp" id="nf-val" placeholder="New value"><input class="inp" id="nf-src" placeholder="Source (e.g. Price List Dec 2026)"><button class="btn pri" id="nf-add">Set new value (old one expires)</button></div>` : ""}</div>
  <div class="card" style="margin-top:16px"><h3>Rules</h3><table class="t"><thead><tr><th>ID</th><th>Rule</th><th>Severity</th><th>Source</th>${admin ? "<th>On</th>" : ""}</tr></thead><tbody>
    ${b.rules.map((r) => `<tr><td class="mono">${esc(r.id)}</td><td><b>${esc(r.title)}</b><div class="small muted">${esc(r.description)}</div></td><td><span class="tag ${r.severity}">${r.severity}</span></td><td class="small muted">${esc(r.source)}</td>${admin ? `<td><input type="checkbox" data-rule="${esc(r.id)}" ${r.enabled ? "checked" : ""}></td>` : ""}</tr>`).join("")}</tbody></table></div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card"><h3>Terminology</h3><table class="t"><thead><tr><th>Avoid</th><th>Use instead</th></tr></thead><tbody>${b.terms.map((t) => `<tr><td>${esc(t.avoid)}</td><td><b>${esc(t.prefer)}</b><div class="tiny muted">${esc(t.note || "")}</div></td></tr>`).join("")}</tbody></table>
      ${admin ? '<div class="row" style="margin-top:8px"><input class="inp" id="nt-a" placeholder="Avoid" style="flex:1"><input class="inp" id="nt-p" placeholder="Use instead" style="flex:1"><button class="btn" id="nt-add">Add</button></div>' : ""}</div>
    <div class="stack"><div class="card"><h3>Palette</h3><div class="pal">${b.palette.map((p) => `<div><i style="background:${p.hex}"></i><span><b>${esc(p.name)}</b><br><span class="mono">${p.hex}</span></span></div>`).join("")}</div><p class="tiny muted">Image colours must be within ΔE 20 (CIE76) of one of these.</p></div>
      <div class="card"><h3>🔒 Confidential terms</h3><div class="row">${(b.meta.confidential_terms || []).map((t) => `<span class="tag high" style="text-transform:none">${esc(t)}</span>`).join("")}</div><p class="tiny muted">These are flagged as high severity and masked before any AI call.</p></div>
      <div class="card"><h3>Voice profile</h3><p class="small" style="margin:0">${esc(b.meta.voice_profile)}</p></div></div>
  </div>`;
  if (!admin) return;
  $("#b-imp").onclick = async () => {
    const f = $("#b-file").files[0]; if (!f) return toast("Choose a file first", true);
    const fd = new FormData(); fd.append("file", f); fd.append("role", S.role);
    const btn = $("#b-imp"); busy(btn, true, "Extracting…");
    try { const r = await api("/api/brand/import", { method: "POST", body: fd }); toast(`${r.created} candidate(s) found — review them below`); $("#b-cands").innerHTML = candList(r.candidates, true); bindCands(); } catch (e) { toast(e.message, true); }
    busy(btn, false);
  };
  bindCands();
  $("#nf-add").onclick = async () => {
    const o = $("#nf-key").selectedOptions[0], val = $("#nf-val").value.trim(); if (!val) return toast("Enter a value", true);
    try { await api("/api/brand/facts", { method: "POST", body: { key: o.value, label: o.dataset.l, value: val, unit: o.dataset.u, source: $("#nf-src").value || "Added by Brand Admin", role: S.role } }); toast("Brand Memory updated"); refreshHeader(); brandPage(); } catch (e) { toast(e.message, true); }
  };
  $("#nt-add").onclick = async () => {
    const a = $("#nt-a").value.trim(), p = $("#nt-p").value.trim(); if (!a || !p) return;
    try { await api("/api/brand/terms", { method: "POST", body: { avoid: a, prefer: p, role: S.role } }); toast("Term added"); brandPage(); } catch (e) { toast(e.message, true); }
  };
  $$("[data-rule]").forEach((c) => (c.onchange = async () => { try { await api(`/api/brand/rules/${c.dataset.rule}/update`, { method: "POST", body: { role: S.role, enabled: c.checked } }); toast(`${c.dataset.rule} ${c.checked ? "enabled" : "disabled"}`); refreshHeader(); } catch (e) { toast(e.message, true); } }));
}
function candList(cands, admin) {
  if (!cands.length) return '<p class="small muted">No pending candidates.</p>';
  return `<div class="small" style="font-weight:600;margin-bottom:6px">Pending approval (${cands.length})</div>` + cands.map((c) => {
    const p = c.payload;
    const what = c.kind === "fact" ? `<b>${esc(p.label)}</b>: ${p.current ? `<del>${esc(p.current)}</del> → ` : ""}<b>${esc(p.value)}</b> ${esc(p.unit || "")} <span class="tag ${p.change === "update" ? "medium" : "ok"}">${p.change}</span>`
      : c.kind === "term" ? `Term: avoid “${esc(p.avoid)}” → use “<b>${esc(p.prefer)}</b>”` : `Confidential: <b>${esc(p.term)}</b>`;
    return `<div class="fcard" style="margin-bottom:6px"><div>${what}</div><div class="tiny muted">from ${esc(c.source)}: “…${esc(c.snippet)}…”</div>
      ${admin ? `<div class="row" style="margin-top:6px"><button class="btn sm ok" data-cand="${c.id}" data-d="approve">Approve</button><button class="btn sm" data-cand="${c.id}" data-d="reject">Reject</button></div>` : ""}</div>`;
  }).join("");
}
function bindCands() {
  $$("[data-cand]").forEach((b) => (b.onclick = async () => { try { const r = await api(`/api/brand/candidates/${b.dataset.cand}/${b.dataset.d}`, { method: "POST", body: { role: S.role } }); toast(b.dataset.d === "approve" ? `Approved · Brand Memory v${r.brand_version}` : "Rejected"); refreshHeader(); brandPage(); } catch (e) { toast(e.message, true); } }));
}

/* ---------------------------------------------------------------- insights */
async function insightsPage() {
  const d = await api("/api/insights");
  const max = Math.max(1, ...d.top_rules.map((r) => r.count));
  $("#app").innerHTML = `<div class="page-h"><div><h2>Insights</h2><p>Repeated mistakes, who needs support, and which guidelines are unclear.</p></div>${d.has_demo ? '<span class="tag grey">includes sample history</span>' : ""}</div>
  <div class="grid g4">
    <div class="card kpi"><b>${d.totals.submissions}</b><span>submissions reviewed</span></div>
    <div class="card kpi"><b>${d.totals.issues_caught}</b><span>issues caught in first drafts</span></div>
    <div class="card kpi"><b>${d.totals.avg_risk_first} → ${d.totals.avg_risk_approved}</b><span>avg risk: first draft → approved</span></div>
    <div class="card kpi"><b>${d.totals.certificates}</b><span>Proof Certificates issued</span></div>
  </div>
  <div class="card" style="margin-top:16px"><h3>🧭 Guideline health — is the rule clear?</h3>
    <p class="small muted" style="margin-top:0">Disagreement = share of flags that reviewers dismissed or creators contested. A high rate means the guideline itself is unclear, not just that people make mistakes.</p>
    <table class="t"><thead><tr><th>Rule</th><th>Flags</th><th>Dismissed</th><th>Contested</th><th>Disagreement</th><th>Status</th><th></th></tr></thead><tbody>
    ${d.guideline_health.map((h) => `<tr><td><span class="mono">${esc(h.rule_id)}</span> ${esc(h.title)}${h.suggestion ? `<div class="small" style="margin-top:4px;color:var(--med)">${esc(h.suggestion)}</div>` : ""}<div class="small" id="sg-${esc(h.rule_id)}"></div></td><td>${h.flagged}</td><td>${h.dismissed}</td><td>${h.contested}</td><td><b>${h.disagreement}%</b></td>
      <td><span class="tag ${h.status === "unclear" ? "high" : h.status === "watch" ? "medium" : "ok"}">${h.status}</span></td><td>${h.status !== "clear" ? `<button class="btn sm" data-sg="${esc(h.rule_id)}">Draft clearer rule</button>` : ""}</td></tr>`).join("")}</tbody></table></div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card"><h3>Most repeated mistakes</h3>${d.top_rules.map((r) => `<div class="bar" style="grid-template-columns:200px 1fr 30px"><span class="small"><span class="mono">${esc(r.rule_id)}</span> ${esc(r.title)}</span><span class="t"><i style="width:${(100 * r.count) / max}%"></i></span><b>${r.count}</b></div>`).join("")}</div>
    <div class="card"><h3>By creator / agency</h3><table class="t"><thead><tr><th>Creator</th><th>High</th><th>Medium</th><th>Review</th><th>Total</th></tr></thead><tbody>${d.by_creator.map((c) => `<tr><td>${esc(c.creator)}</td><td>${c.high || 0}</td><td>${c.medium || 0}</td><td>${c.review || 0}</td><td><b>${c.total}</b></td></tr>`).join("")}</tbody></table>
      <h3 style="margin-top:14px">By channel</h3><div class="row">${d.by_channel.map((c) => `<span class="tag grey" style="text-transform:none">${esc(c.channel)}: ${c.count}</span>`).join("")}</div></div>
  </div>`;
  $$("[data-sg]").forEach((b) => (b.onclick = async () => {
    busy(b, true, "Drafting…");
    try {
      const r = await api(`/api/insights/suggest/${b.dataset.sg}`, { method: "POST" });
      $(`#sg-${b.dataset.sg}`).innerHTML = `<div class="notice ok" style="margin-top:6px"><b>Suggested rule${r.ai ? " (AI draft)" : ""}:</b> ${esc(r.suggestion)}
        ${S.role === "admin" ? `<div style="margin-top:6px"><button class="btn sm ok" data-apply="${esc(b.dataset.sg)}">Apply to Brand Memory</button></div>` : '<div class="tiny muted">Only the Brand Admin can apply this.</div>'}</div>`;
      const ap = $(`[data-apply="${b.dataset.sg}"]`);
      if (ap) ap.onclick = async () => { try { await api(`/api/brand/rules/${b.dataset.sg}/update`, { method: "POST", body: { role: S.role, description: r.suggestion } }); toast("Rule updated · new Brand Memory version"); refreshHeader(); } catch (e) { toast(e.message, true); } };
    } catch (e) { toast(e.message, true); }
    busy(b, false);
  }));
}

/* ---------------------------------------------------------------- trust & feedback */
async function trustPage() {
  const [a, fb] = await Promise.all([api("/api/about"), api("/api/feedback")]);
  $("#app").innerHTML = `<div class="page-h"><div><h2>Trust, data &amp; feedback</h2><p>How BrandProof uses AI, what leaves the server, and what it is built with.</p></div></div>
  <div class="grid g2">
    <div class="card stack"><h3>🤖 How AI is used</h3>
      <div class="small"><b>Provider:</b> ${esc(a.ai.provider)} · <b>Model:</b> ${esc(a.ai.model)}</div>
      <div class="small"><b>AI is used only for:</b> ${a.ai.used_for.map(esc).join(", ")}.</div>
      <div class="small"><b>Checked in code (no AI, always works):</b> ${a.deterministic_checks.map(esc).join(", ")}.</div>
      <div class="notice ai small"><b>Evidence verifier:</b> an AI finding is kept only if it quotes text that really exists in the draft and cites a real rule ID from Brand Memory. Everything else is dropped and counted on screen.</div>
      <div class="notice small"><b>Human control:</b> nothing is auto-fixed or auto-published. Creators accept fixes one by one. Only Compliance can dismiss a high-severity finding. Only a Reviewer can approve.</div></div>
    <div class="card stack"><h3>🔒 Data handling</h3>
      <ul class="small" style="margin:0;padding-left:18px">
        <li>Emails, phone numbers and confidential terms are masked before any AI call.</li>
        <li><b>Confidential mode</b> sends nothing to any AI service. Only the rule engine runs.</li>
        <li>Brand Memory, drafts, decisions and certificates are stored in this app's own database (SQLite).</li>
        <li>Every decision is recorded in an audit trail, and approvals are sealed in hash-chained Proof Certificates.</li>
        <li>AI-assisted drafts and AI-suggested rewrites are labelled in the record.</li>
        <li>Demo roles are switched from the header. Real sign-in comes in Round 3.</li></ul>
      <h3 style="margin-top:6px">🧰 Built with</h3>
      <table class="t small"><tbody>
        <tr><td>Python 3 · FastAPI · Uvicorn · Pydantic</td><td class="muted">API &amp; validation (MIT/BSD)</td></tr>
        <tr><td>SQLite</td><td class="muted">storage (public domain)</td></tr>
        <tr><td>pypdf · python-docx</td><td class="muted">PDF/DOCX text extraction (BSD/MIT)</td></tr>
        <tr><td>Pillow</td><td class="muted">image colours, ΔE &amp; contrast (MIT-CMU)</td></tr>
        <tr><td>httpx → Google Gemini API</td><td class="muted">optional AI (BSD · Google API terms)</td></tr>
        <tr><td>Vanilla JS + CSS, Google Fonts (Inter, Space Grotesk, JetBrains Mono)</td><td class="muted">frontend (OFL fonts)</td></tr>
        <tr><td>Render</td><td class="muted">hosting</td></tr></tbody></table>
      <div class="small">API docs: <a href="/docs" target="_blank">/docs</a> (OpenAPI)</div></div>
  </div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card stack"><h3>💬 Give feedback (user testing)</h3>
      <div class="grid g2" style="gap:8px"><input class="inp" id="fb-name" placeholder="Your name"><input class="inp" id="fb-role" placeholder="Role (student, marketer, designer…)"></div>
      ${[["ease", "How easy was it to use?"], ["trust", "How much do you trust the findings?"], ["useful", "How useful would this be for a real team?"]].map(([k, l]) => `<div class="row between small"><span>${l}</span><select class="inp" id="fb-${k}" style="width:90px">${[5, 4, 3, 2, 1].map((n) => `<option>${n}</option>`).join("")}</select></div>`).join("")}
      <textarea class="inp" id="fb-liked" style="min-height:60px" placeholder="What worked well?"></textarea>
      <textarea class="inp" id="fb-improve" style="min-height:60px" placeholder="What should we improve?"></textarea>
      <button class="btn pri" id="fb-send">Send feedback</button></div>
    <div class="card"><h3>Feedback received (${fb.count})</h3>
      ${fb.count ? `<div class="row small" style="margin-bottom:8px"><span class="tag ok" style="text-transform:none">Ease ${fb.average.ease}/5</span><span class="tag ok" style="text-transform:none">Trust ${fb.average.trust}/5</span><span class="tag ok" style="text-transform:none">Useful ${fb.average.useful}/5</span></div>` : ""}
      ${fb.items.map((f) => `<div class="small" style="border-top:1px solid var(--line);padding:7px 0"><b>${esc(f.name)}</b> <span class="muted">${esc(f.role)} · ${f.ease}/${f.trust}/${f.useful}</span>${f.liked ? `<div>👍 ${esc(f.liked)}</div>` : ""}${f.improve ? `<div>🔧 ${esc(f.improve)}</div>` : ""}</div>`).join("") || '<p class="small muted">No feedback yet.</p>'}</div>
  </div>`;
  $("#fb-send").onclick = async () => {
    const name = $("#fb-name").value.trim(); if (!name) return toast("Please add your name", true);
    try { await api("/api/feedback", { method: "POST", body: { name, role: $("#fb-role").value, ease: +$("#fb-ease").value, trust: +$("#fb-trust").value, useful: +$("#fb-useful").value, liked: $("#fb-liked").value, improve: $("#fb-improve").value } }); toast("Thank you! Feedback saved."); trustPage(); } catch (e) { toast(e.message, true); }
  };
}

refreshHeader().then(route);
