/* BrandProof AI — frontend core (vanilla JS, no build step).
   app.js: state, API client, shared renderers, auth screens, Check and Review pages.
   pages.js: Brand Memory, Insights, Certificates, Team, Accuracy, Trust, demo guide, router start. */
"use strict";

const ROLE_LABEL = { creator: "Creator", compliance: "Compliance", reviewer: "Reviewer", admin: "Brand Admin" };
const DEMO_PEOPLE = { creator: "Riya Sharma", compliance: "Neha Verma", reviewer: "Kabir Singh", admin: "Ayush (Brand Admin)" };
const STATUS_LABEL = { draft: "Draft", compliance_review: "Waiting for Compliance", in_review: "Waiting for Reviewer", approved: "Approved", rejected: "Rejected", changes_requested: "Changes requested" };
const SAMPLES = {
  risky: { title: "Diwali Instagram post", channel: "Instagram", goal: "Promote the Diwali offer and drive purchases", ai: true,
    text: "ABC Electronics – India's No. 1 Brand! Buy SoundPods Pro for just ₹7,000. Get 50% OFF. 100% guaranteed performance with lifetime warranty!!" },
  hinglish: { title: "Hinglish WhatsApp promo", channel: "WhatsApp", goal: "Drive Diwali sales", ai: true,
    text: "Diwali Dhamaka! SoundPods Pro sirf saat hazaar rupaye mein, aadhe daam par! Saath mein aajeevan warranty. Jaldi karo, aakhri mauka!" },
  hindi: { title: "Hindi newspaper ad", channel: "Print", goal: "Diwali sale awareness", ai: false,
    text: "सिर्फ सात हज़ार रुपये में SoundPods Pro! पचास प्रतिशत की छूट और आजीवन वारंटी। भारत का नंबर 1 ब्रांड।" },
  outdated: { title: "Product page update", channel: "Website", goal: "Explain features and price", ai: false,
    text: "Meet Sound Pods Pro: forty hours of battery, fully waterproof and now only ₹12,000. Get yours today." },
  confidential: { title: "Launch teaser", channel: "Twitter/X", goal: "Build excitement for upcoming launch", ai: true,
    text: "OMG something big is coming! Project Falcon is almost here and the new SoundPods Max will be the best earbuds in India. Hurry, pre-order now!!" },
  clean: { title: "Retail standee", channel: "Print", goal: "In-store awareness", ai: false,
    text: "SoundPods Pro – Smart Technology for Everyday Life. Enjoy 30 hours of playback and an approved 2-year warranty. Now up to 20% off this Diwali. T&C apply." },
};
const SAMPLE_IMAGES = {
  offbrand: { file: "diwali_poster_offbrand.png", title: "Diwali poster (agency draft)", label: "Off-brand poster" },
  hinglish: { file: "hinglish_poster.png", title: "Hinglish Diwali poster", label: "Hinglish poster" },
  onbrand: { file: "diwali_poster_onbrand.png", title: "Diwali poster (final)", label: "On-brand poster" },
};

const S = { me: null, role: "creator", health: null, seq: 0 };
class Stale extends Error {}
async function load(promise) { // ignore results of a page the user has already left
  const seq = S.seq; const r = await promise;
  if (seq !== S.seq) throw new Stale("stale");
  return r;
}
const store = {
  get(k, d) { try { const v = sessionStorage.getItem("bp_" + k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
  set(k, v) { try { sessionStorage.setItem("bp_" + k, JSON.stringify(v)); } catch (e) {} },
  del(k) { try { sessionStorage.removeItem("bp_" + k); } catch (e) {} },
};

/* ---------------------------------------------------------------- helpers */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (s) => { try { return new Date(s).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); } catch (e) { return s; } };
const short = (h) => (h ? h.slice(0, 10) + "…" + h.slice(-6) : "");
const actorName = () => (S.me && !S.me.demo ? S.me.user.name : DEMO_PEOPLE[S.role]);

async function api(path, opts = {}) {
  const o = { credentials: "same-origin", ...opts };
  o.headers = { "X-Acting-Role": S.role, ...(opts.headers || {}) };
  if (o.body && !(o.body instanceof FormData)) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(o.body); }
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), opts.timeout || 90000);
  o.signal = ctl.signal;
  let r;
  try { r = await fetch(path, o); }
  catch (e) {
    clearTimeout(timer);
    throw new Error(e.name === "AbortError" ? "The server took too long to answer. Please try again." : "Can't reach the server. Check your connection and try again.");
  }
  clearTimeout(timer);
  let data = null;
  try { data = await r.json(); } catch (e) {}
  if (r.status === 401 && !opts.allow401) {
    S.me = null; renderHeader();
    if (!/^#\/(signin|signup|join)/.test(location.hash)) location.hash = "#/";
    throw new Error((data && data.detail) || "Please start the demo or sign in.");
  }
  if (!r.ok) {
    const err = new Error((data && (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))) || `Request failed (${r.status})`);
    err.status = r.status; throw err;
  }
  return data;
}
function toast(msg, err = false) {
  $$(".toast").forEach((t) => t.remove());
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.setAttribute("role", err ? "alert" : "status");
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), err ? 6000 : 3400);
}
function ask(title, placeholder = "", ok = "Confirm", chips = []) {
  return new Promise((res) => {
    const bg = document.createElement("div");
    bg.className = "modal-bg";
    bg.innerHTML = `<div class="modal" role="dialog" aria-modal="true"><h3 style="margin-bottom:10px">${esc(title)}</h3>
      ${chips.length ? `<div class="row" style="margin-bottom:8px">${chips.map((c) => `<button class="btn sm" data-chip="${esc(c)}">${esc(c)}</button>`).join("")}</div>` : ""}
      <textarea class="inp" style="min-height:90px" maxlength="500" placeholder="${esc(placeholder)}"></textarea>
      <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-x>Cancel</button><button class="btn pri" data-ok>${esc(ok)}</button></div></div>`;
    document.body.appendChild(bg);
    const ta = $("textarea", bg); ta.focus();
    const onKey = (e) => { if (e.key === "Escape") done(null); };
    const done = (v) => { bg.remove(); document.removeEventListener("keydown", onKey); res(v); };
    document.addEventListener("keydown", onKey);
    $$("[data-chip]", bg).forEach((c) => (c.onclick = () => { ta.value = c.dataset.chip; ta.focus(); }));
    $("[data-x]", bg).onclick = () => done(null);
    $("[data-ok]", bg).onclick = () => { const v = ta.value.trim(); if (!v) { ta.style.borderColor = "var(--high)"; ta.placeholder = "A reason is required"; return; } done(v); };
    bg.onclick = (e) => { if (e.target === bg) done(null); };
  });
}
function busy(btn, on, label) {
  if (!btn) return;
  if (on) { btn.dataset.l = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spin"></span> ${label || "Working…"}`; }
  else { btn.disabled = false; if (btn.dataset.l) btn.innerHTML = btn.dataset.l; }
}
async function once(btn, label, fn) { // runs fn with the button locked: no double submits
  if (btn && btn.disabled) return;
  busy(btn, true, label);
  try { return await fn(); } catch (e) { toast(e.message, true); } finally { if (btn && document.body.contains(btn)) busy(btn, false); }
}
function fileToDataURL(file) {
  return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(file); });
}
async function urlToDataURL(url) { const b = await (await fetch(url)).blob(); return fileToDataURL(b); }
function setRole(r, quiet) {
  if (!S.me || !S.me.roles.includes(r)) return;
  S.role = r; store.set("role", r);
  const sel = $("#role"); if (sel) sel.value = r;
  if (!quiet) toast(`Now acting as ${ROLE_LABEL[r]}${S.me.demo ? " · " + DEMO_PEOPLE[r] : ""}`);
}

/* ---------------------------------------------------------------- shared renderers */
function highlight(text, findings) {
  const spans = findings.filter((f) => !f.target && f.end > f.start).sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start));
  const inserts = findings.filter((f) => !f.target && f.end === f.start);
  let out = "", pos = 0;
  for (const f of spans) {
    if (f.start < pos) continue;
    out += esc(text.slice(pos, f.start));
    out += `<span class="hl ${f.severity}" data-n="${f.n}" tabindex="0" title="${esc(f.rule_id + ": " + f.title)}">${esc(text.slice(f.start, f.end))}<sup>${f.n}</sup></span>`;
    pos = f.end;
  }
  out += esc(text.slice(pos));
  for (const f of inserts) out += ` <span class="ins" data-n="${f.n}" tabindex="0">+ ${esc(f.fix ? f.fix.replacement.trim() : f.title)} <sup>${f.n}</sup></span>`;
  return out || '<span class="muted">(no text — image only)</span>';
}
const ENGINE_TAG = { ai: '<span class="tag ai">AI · verified</span>', vision: '<span class="tag vision">Image</span>', rules: '<span class="tag grey">Rule</span>' };
function findingCard(f, o = {}) {
  const ev = (f.evidence || []).map((e) => `<div><span class="ref">${esc(e.ref)}</span><span>${esc(e.text)}${e.valid ? ` <span class="muted">(${esc(e.valid)})</span>` : ""}${e.source ? ` <span class="muted">— ${esc(e.source)}</span>` : ""}</span></div>`).join("");
  const metric = f.metric && (f.metric.found || f.metric.swatch)
    ? `<div class="metric"><span class="a">${f.metric.swatch ? `<i class="swatch" style="background:${esc(f.metric.swatch)}"></i> ` : ""}Found: ${esc(f.metric.found)}</span><span class="b">${f.metric.approved ? "Approved: " + esc(f.metric.approved) : f.metric.limit ? "Limit: " + esc(f.metric.limit) : esc(f.metric.status || "")}${f.metric.nearest ? ` <i class="swatch" style="background:${esc(f.metric.nearest)}"></i>` : ""}</span></div>` : "";
  let fix = "";
  if (f.fix) {
    const before = f.quote && f.fix.target !== "alt" ? `<del>${esc(f.quote)}</del> → ` : (f.fix.target === "alt" ? "Alt text: " : "Add: ");
    const after = f.fix.replacement.trim() ? `<ins>${esc(f.fix.replacement.trim())}</ins>` : `<span class="muted">(remove)</span>`;
    const selectable = o.selectable && !f.fix.overlaps && f.fix.target !== "alt" && !f.fix.design_only;
    const box = selectable ? `<input type="checkbox" data-accept="${esc(f.key)}" ${o.accepted && o.accepted.has(f.key) ? "checked" : ""} aria-label="Accept fix ${f.n}">` : "";
    const useAlt = f.fix.target === "alt" && o.selectable && f.fix.replacement ? ` <button class="btn sm" data-usealt="${esc(f.fix.replacement)}">Use this alt text</button>` : "";
    fix = `<label class="fixbox">${box}<span><b>${f.fix.design_only ? "Change in the design:" : "Suggested fix:"}</b> ${before}${after}${f.fix.note ? ` <span class="muted small">· ${esc(f.fix.note)}</span>` : ""}${f.fix.overlaps ? ' <span class="muted small">· covered by another fix</span>' : ""}${useAlt}</span></label>`;
  } else if (f.target === "image" || f.target === "image_text") {
    fix = `<div class="fixbox neutral"><span><b>Needs a design change.</b> <span class="muted">${f.rule_id === "R-LOGO-01" ? "Add the approved logo from Brand Memory." : f.rule_id === "R-VIS-01" ? "Swap to the nearest brand colour shown above." : "Increase the contrast or move the text onto a plain area."}</span></span></div>`;
  } else if (f.severity !== "review" || f.rule_id === "R-CONF-01") {
    fix = `<div class="fixbox neutral"><span><b>Needs a human rewrite.</b> <span class="muted">No safe automatic fix for this one.</span></span></div>`;
  }
  const dec = o.decision ? `<div class="notice small" style="margin-top:8px">${o.decision.action === "dismissed" ? "Dismissed" : "Contested"} by <b>${esc(o.decision.by_name)}</b> (${esc(ROLE_LABEL[o.decision.by_role] || o.decision.by_role)}): “${esc(o.decision.reason)}”</div>` : "";
  const contest = o.contest ? (o.contests && o.contests[f.key]
      ? `<div class="notice small" style="margin-top:8px">You contested this: “${esc(o.contests[f.key])}” <a href="#" data-uncontest="${esc(f.key)}">undo</a></div>`
      : (f.severity !== "high" ? `<button class="btn sm" style="margin-top:8px" data-contest="${esc(f.key)}">Contest with a reason</button>` : `<div class="tiny muted" style="margin-top:6px">High severity — only Compliance can dismiss this.</div>`)) : "";
  return `<div class="fcard ${f.severity} ${o.decision && o.decision.action === "dismissed" ? "dismissed" : ""}" id="f-${o.prefix || ""}${f.n}" data-n="${f.n}">
    <div class="hd"><span class="tag ${f.severity}">${f.severity}</span><span class="rid">${esc(f.rule_id)}</span><span class="ttl">${esc(f.title)}</span>
      ${ENGINE_TAG[f.engine] || ""}<span class="muted tiny" style="margin-left:auto">#${f.n} · ${esc(f.location || "")}</span></div>
    ${f.quote ? `<div class="quote">“${esc(f.quote)}”</div>` : ""}
    <div>${esc(f.message)}</div>${metric}
    <div class="ev">${ev}</div>${fix}${dec}${contest}${o.actions || ""}</div>`;
}
function gauge(score, level) {
  const c = 2 * Math.PI * 44, off = c * (1 - score / 100);
  const col = score >= 50 ? "var(--high)" : score >= 20 ? "#e59a14" : score > 0 ? "var(--rev)" : "var(--proof)";
  return `<div class="gauge" role="img" aria-label="Risk ${score} of 100, ${esc(level)}"><svg width="104" height="104" viewBox="0 0 104 104"><circle cx="52" cy="52" r="44" stroke="#eef2f7" stroke-width="10" fill="none"/>
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
function riskOf(findings) {
  const W = { high: 25, medium: 10, review: 4 }, counts = { high: 0, medium: 0, review: 0 }, breakdown = {};
  let t = 0;
  findings.forEach((f) => { t += W[f.severity]; counts[f.severity]++; breakdown[f.category] = (breakdown[f.category] || 0) + W[f.severity]; });
  const score = Math.min(100, t);
  return { score, level: score >= 50 ? "High" : score >= 20 ? "Medium" : score > 0 ? "Low" : "Clear", counts, breakdown };
}
function aiNotice(ai, img) {
  if (!ai) return "";
  const read = img && img.creative && img.creative.text && img.creative.text.status === "ok";
  if (!ai.used && read) return `<div class="notice ai small">🛡️ <b>AI use:</b> ${esc(img.creative.text.model || "the vision model")} only read the words in the poster. Every finding above comes from the same exact, repeatable rules used for text.</div>`;
  if (!ai.used) return `<div class="notice ai small">🛡️ <b>AI review:</b> ${esc(ai.error || "not used")} All findings above come from exact, repeatable rule checks.</div>`;
  const ex = (ai.dropped_examples || []).map((d) => `<li>“${esc(d.quote)}” — ${esc(d.reason)}</li>`).join("");
  return `<div class="notice ai small">🛡️ <b>Evidence verifier</b> (${esc(ai.model)}${ai.cached ? ", cached result" : ""}): the AI proposed <b>${ai.checked}</b> issue(s).
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
  const ops = []; let i = 0, j = 0;
  while (i < n && j < m) { if (A[i] === B[j]) { ops.push(["=", A[i]]); i++; j++; } else if (dp[i + 1][j] >= dp[i][j + 1]) ops.push(["-", A[i++]]); else ops.push(["+", B[j++]]); }
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
function creativeBlock(info, src, findings) {
  if (!info) return "";
  const cr = info.creative || {};
  const txt = cr.text || {}, logo = cr.logo || {};
  const boxed = (findings || []).filter((f) => f.box);
  const boxes = [];
  boxed.forEach((f) => boxes.push({ box: f.box, n: f.n, sev: f.severity, label: `#${f.n} ${f.rule_id}` }));
  (txt.lines || []).forEach((l) => { if (l.box && !boxed.some((f) => f.box && f.box.join() === l.box.join())) boxes.push({ box: l.box, n: null, sev: "ok", label: "" }); });
  if (logo.present && logo.box) boxes.push({ box: logo.box, n: null, sev: "logo", label: "logo ✓" });
  const overlay = boxes.map((b) => { const [y0, x0, y1, x1] = b.box; return `<div class="obox ${b.sev}" ${b.n ? `data-n="${b.n}" tabindex="0"` : ""} style="top:${y0 / 10}%;left:${x0 / 10}%;height:${(y1 - y0) / 10}%;width:${(x1 - x0) / 10}%">${b.label ? `<span>${esc(b.label)}</span>` : ""}</div>`; }).join("");
  const cols = info.colours.map((c) => `<div class="${c.on_palette ? "" : "off"}"><i class="swatch" style="background:${c.hex}"></i>${c.hex} · ${c.share}% · ΔE ${c.delta_e} → ${esc(c.nearest || "")}</div>`).join("");
  const lines = (txt.lines || []).map((l) => `<tr><td>${esc(l.text)}</td><td>${l.contrast == null ? "–" : `<b style="color:${l.contrast < 3 ? "var(--high)" : "var(--proof)"}">${l.contrast}:1</b>`}</td></tr>`).join("");
  const txtStatus = txt.status === "ok" ? `<b>${(txt.lines || []).length}</b> text line(s) read by ${esc(txt.model || "the vision model")}${txt.cached ? " (cached)" : ""} and checked with the same rules as text.`
    : `<span class="muted">${esc(txt.reason || "Text in the image was not read.")}</span>`;
  const logoStatus = logo.status === "ok" ? (logo.present ? `<span class="tag ok">✓ logo found</span> <span class="muted small">by ${esc(logo.method)}${logo.score != null ? ` · pixel match ${logo.score}` : ""}${logo.altered ? " · looks altered" : ""}</span>` : `<span class="tag high">✗ logo not found</span> <span class="muted small">${esc(logo.method || "")}</span>`)
    : `<span class="muted small">${esc(logo.reason || "Logo not checked.")}</span>`;
  return `<div class="card"><h3>🖼️ Creative check <span class="tag vision">image</span></h3>
    ${src ? `<div class="imgwrap"><img src="${src}" alt="Uploaded creative">${overlay}</div>` : ""}
    <div class="small" style="margin-top:8px">📝 ${txtStatus}</div>
    ${lines ? `<table class="t small" style="margin-top:6px"><thead><tr><th>Text found in image</th><th>Contrast</th></tr></thead><tbody>${lines}</tbody></table>` : ""}
    <div class="small" style="margin-top:8px">🏷️ Logo: ${logoStatus}</div>
    <div class="row small" style="margin-top:8px"><span><b>${info.palette_match}%</b> of pixels on brand palette</span><span>·</span><span>${info.width}×${info.height}px</span></div>
    <div class="colours">${cols}</div></div>`;
}
function bindDoc(root, prefix) {
  $$(".hl,.ins,.obox[data-n]", root).forEach((h) => {
    const go = () => {
      const c = $(`#f-${prefix}${h.dataset.n}`);
      if (c) { c.scrollIntoView({ behavior: "smooth", block: "center" }); c.classList.remove("flash"); void c.offsetWidth; c.classList.add("flash"); }
    };
    h.onclick = go; h.onkeydown = (e) => { if (e.key === "Enter") go(); };
  });
}

/* ---------------------------------------------------------------- header & auth */
function renderHeader() {
  const me = S.me;
  $("#nav").hidden = !me;
  $("#ws").innerHTML = me ? `<span class="wsname" title="Workspace">${esc(me.org_name)}</span>${me.demo ? '<span class="tag demo">demo sandbox</span>' : '<span class="tag ok">team</span>'}` : "";
  const rb = $("#rolebox");
  if (!me) { rb.innerHTML = `<a class="btn sm" href="#/signin">Sign in</a>`; return; }
  rb.innerHTML = `<label for="role" class="muted small">Acting as</label>
    <select id="role" aria-label="Acting role">${me.roles.map((r) => `<option value="${r}" ${r === S.role ? "selected" : ""}>${ROLE_LABEL[r]}${me.demo ? " · " + DEMO_PEOPLE[r] : ""}</option>`).join("")}</select>
    <button class="btn sm ghost" id="signout" title="${me.demo ? "Leave the demo" : "Sign out"}">${me.demo ? "Exit demo" : "Sign out"}</button>`;
  $("#role").onchange = (e) => { setRole(e.target.value); refreshCounts(); route(); };
  $("#signout").onclick = async () => { try { await api("/api/auth/logout", { method: "POST", allow401: true }); } catch (e) {} S.me = null; store.del("guide"); renderHeader(); renderGuide(); location.hash = "#/"; route(); };
}
async function refreshCounts() {
  if (!S.me) return;
  try {
    const subs = await api("/api/submissions");
    const waiting = subs.filter((s) => (S.role === "compliance" && s.status === "compliance_review") || (S.role === "reviewer" && s.status === "in_review") || (S.role === "creator" && s.status === "changes_requested")).length;
    const q = $("#qcount"); q.hidden = !waiting; q.textContent = waiting;
  } catch (e) {}
}
async function loadMe() {
  try { S.me = await api("/api/auth/me", { allow401: true }); }
  catch (e) { S.me = null; }
  if (S.me) { const r = store.get("role", S.me.role); S.role = S.me.roles.includes(r) ? r : S.me.roles[0]; }
  renderHeader();
}
async function startDemo(btn) {
  return once(btn, "Preparing your private demo…", async () => {
    S.me = await api("/api/demo/start", { method: "POST" });
    S.role = "creator"; store.set("role", "creator"); store.set("guide", { open: window.innerWidth > 960, done: {} });
    renderHeader(); refreshCounts();
    CK.reset(SAMPLES.risky); S.autorun = true;
    location.hash = "#/check";
    renderGuide();
    toast("Your private demo is ready — the guide (bottom right) walks you through it.");
  });
}

/* ---------------------------------------------------------------- landing & auth pages */
async function landing() {
  if (S.me) return home();
  $("#app").innerHTML = `
  <section class="hero">
    <div>
      <div class="eyebrow">Brand governance · before you publish</div>
      <h1 style="margin:10px 0 12px">Every claim checked.<br>Every flag <em>proven</em>.</h1>
      <p class="lead">BrandProof AI checks posts, ads, documents and posters against your approved facts, rules, logo and palette — in English, Hindi and Hinglish. Every issue shows the exact guideline behind it and a fix that keeps the creator's message. A person always approves, and every approval gets a tamper-evident Proof Certificate.</p>
      <div class="row" style="margin-top:16px">
        <button class="btn pri big" id="go-demo">▶ Try the demo — no sign-up</button>
        <a class="btn big" href="#/signup">Create a team workspace</a>
      </div>
      <p class="small muted" style="margin-top:10px">The demo gives you a private sandbox with a fictional brand (ABC Electronics) and a step-by-step guide. Already have an account? <a href="#/signin">Sign in</a>.</p>
    </div>
    <div class="demo-ad">
      <div class="bar">AI-generated draft · Instagram</div>
      <div style="padding:16px" class="doc">${esc(SAMPLES.risky.text)}</div>
      <div style="padding:10px 14px" class="row small"><span class="tag high">4 high</span><span class="tag medium">3 medium</span><span class="muted">→ fixed to risk 0 with the offer, call-to-action and product kept</span></div>
    </div>
  </section>
  ${howItWorks()}`;
  $("#go-demo").onclick = (e) => startDemo(e.currentTarget);
}
function howItWorks() {
  return `<section class="card" style="margin-top:18px"><h3>How it works</h3>
    <div class="steps">
      <div class="step"><span class="n">1</span><b>Brand Memory</b><span class="muted small">Import your brand book. Facts, prices, rules, terms, logo and palette are versioned and approved by an admin.</span></div>
      <div class="step"><span class="n">2</span><b>Check</b><span class="muted small">Text, PDF, DOCX and posters. Numbers, terms, colours, contrast and logo are checked in code. AI reads text inside images and judges tone, and every AI finding must cite real evidence.</span></div>
      <div class="step"><span class="n">3</span><b>Fix &amp; Purpose Guard</b><span class="muted small">Each fix changes only the flagged words. Purpose Guard confirms the product, offer and call-to-action survive.</span></div>
      <div class="step"><span class="n">4</span><b>Approve &amp; Prove</b><span class="muted small">Compliance, then a Reviewer (four-eyes). Approval issues a hash-chained Proof Certificate with the verified approvers.</span></div>
    </div></section>`;
}
async function home() {
  if (!S.me) return landing();
  let ins = null;
  try { ins = await load(api("/api/insights")); } catch (e) { if (e instanceof Stale) throw e; }
  const blank = ins && !ins.totals.submissions;
  $("#app").innerHTML = `
  <div class="page-h"><div><h2>${esc(S.me.org_name)}</h2><p>${S.me.demo ? "Your private demo sandbox. Nothing here is shared with anyone else, and it is deleted after 48 hours of inactivity." : `Signed in as <b>${esc(S.me.user.name)}</b> · roles: ${S.me.roles.map((r) => ROLE_LABEL[r]).join(", ")}`}</p></div>
    <div class="row"><a class="btn pri" href="#/check">Check content</a><a class="btn" href="#/queue">Review queue</a></div></div>
  ${blank ? `<div class="card stack"><h3>👋 Get started in 3 steps</h3>
      <div class="steps"><div class="step"><span class="n">1</span><b>Set up Brand Memory</b><span class="muted small">Import your brand book (PDF/DOCX) or add prices, terms, logo and palette.</span><a class="btn sm" href="#/brand" style="margin-top:6px">Open Brand Memory</a></div>
      <div class="step"><span class="n">2</span><b>Invite your team</b><span class="muted small">Add Creators, Compliance and Reviewers with an invite link.</span><a class="btn sm" href="#/team" style="margin-top:6px">Invite people</a></div>
      <div class="step"><span class="n">3</span><b>Check your first post</b><span class="muted small">Paste text or upload a poster and submit it for review.</span><a class="btn sm" href="#/check" style="margin-top:6px">Check content</a></div></div></div>` : ""}
  ${ins && !blank ? `<section class="grid g4">
    <div class="card kpi"><b>${ins.totals.issues_caught}</b><span>issues caught before publishing</span></div>
    <div class="card kpi"><b>${ins.totals.avg_risk_first} → ${ins.totals.avg_risk_approved}</b><span>average risk: first draft → approved</span></div>
    <div class="card kpi"><b>${ins.totals.certificates}</b><span>Proof Certificates issued</span></div>
    <div class="card kpi"><b>${ins.guideline_health.filter((h) => h.status === "unclear").length}</b><span>guideline(s) flagged as unclear</span></div>
  </section>${ins.has_demo ? '<p class="tiny muted">Numbers include the sample review history that comes with the demo.</p>' : ""}` : ""}
  ${howItWorks()}`;
}
function authShell(title, sub, body) {
  $("#app").innerHTML = `<div class="authbox card stack"><h2>${title}</h2><p class="muted" style="margin:0">${sub}</p>${body}</div>`;
}
async function signinPage() {
  authShell("Sign in", "Welcome back to your BrandProof workspace.",
    `<form id="f" class="stack" novalidate><div><label class="f" for="em">Email</label><input class="inp" id="em" type="email" autocomplete="email" required></div>
     <div><label class="f" for="pw">Password</label><input class="inp" id="pw" type="password" autocomplete="current-password" required></div>
     <button class="btn pri" id="go">Sign in</button></form>
     <p class="small muted">New here? <a href="#/signup">Create a team workspace</a> or <a href="#" id="demo">try the demo</a>.</p>`);
  $("#demo").onclick = (e) => { e.preventDefault(); startDemo(); };
  $("#f").onsubmit = (e) => { e.preventDefault(); once($("#go"), "Signing in…", async () => {
    S.me = await api("/api/auth/login", { method: "POST", body: { email: $("#em").value, password: $("#pw").value }, allow401: true });
    S.role = S.me.roles[0]; store.set("role", S.role); renderHeader(); refreshCounts(); location.hash = "#/home"; toast(`Welcome back, ${S.me.user.name}`);
  }); };
}
async function signupPage() {
  authShell("Create your team workspace", "Free. Your brand data stays in your own workspace. You'll be the Brand Admin and can invite your team.",
    `<form id="f" class="stack" novalidate>
      <div class="grid g2" style="gap:10px"><div><label class="f" for="nm">Your name</label><input class="inp" id="nm" autocomplete="name" maxlength="80" required></div>
      <div><label class="f" for="org">Workspace / brand name</label><input class="inp" id="org" maxlength="80" placeholder="e.g. Acme Marketing" required></div></div>
      <div><label class="f" for="em">Work email</label><input class="inp" id="em" type="email" autocomplete="email" required></div>
      <div><label class="f" for="pw">Password <span class="muted">(min 8 characters)</span></label><input class="inp" id="pw" type="password" autocomplete="new-password" minlength="8" required></div>
      <fieldset class="choice"><legend class="f">Start with</legend>
        <label class="chk"><input type="radio" name="tpl" value="demo" checked> <span><b>Demo brand</b> — ABC Electronics facts, rules, logo and palette (good for trying everything)</span></label>
        <label class="chk"><input type="radio" name="tpl" value="blank"> <span><b>My own brand</b> — standard rules, then import your brand book</span></label></fieldset>
      <button class="btn pri" id="go">Create workspace</button></form>
      <p class="small muted">Already have an account? <a href="#/signin">Sign in</a>.</p>`);
  $("#f").onsubmit = (e) => { e.preventDefault(); once($("#go"), "Creating…", async () => {
    S.me = await api("/api/auth/signup", { method: "POST", body: { name: $("#nm").value, org_name: $("#org").value, email: $("#em").value, password: $("#pw").value, template: $("input[name=tpl]:checked").value }, allow401: true });
    S.role = "admin"; store.set("role", "admin"); renderHeader(); renderGuide(); location.hash = "#/home"; toast("Workspace created. Next: set up Brand Memory and invite your team.");
  }); };
}
async function joinPage(code) {
  let info;
  try { info = await load(api(`/api/invites/${encodeURIComponent(code)}`, { allow401: true })); }
  catch (e) { authShell("Invite link", "", `<div class="notice err">${esc(e.message)}</div><a class="btn" href="#/">Go to home</a>`); return; }
  authShell(`Join ${esc(info.org_name)}`, `You've been invited as <b>${info.roles.map((r) => ROLE_LABEL[r]).join(", ")}</b>.`,
    `<form id="f" class="stack" novalidate><div><label class="f" for="nm">Your name</label><input class="inp" id="nm" autocomplete="name" maxlength="80"></div>
      <div><label class="f" for="em">Email</label><input class="inp" id="em" type="email" autocomplete="email" value="${esc(info.email || "")}"></div>
      <div><label class="f" for="pw">Password <span class="muted">(new account: min 8 characters; existing account: your password)</span></label><input class="inp" id="pw" type="password" autocomplete="new-password"></div>
      <button class="btn pri" id="go">Join workspace</button></form>`);
  $("#f").onsubmit = (e) => { e.preventDefault(); once($("#go"), "Joining…", async () => {
    S.me = await api(`/api/invites/${encodeURIComponent(code)}/accept`, { method: "POST", body: { name: $("#nm").value, email: $("#em").value, password: $("#pw").value }, allow401: true });
    S.role = S.me.roles[0]; store.set("role", S.role); renderHeader(); refreshCounts(); location.hash = "#/home"; toast(`Welcome to ${S.me.org_name}`);
  }); };
}

/* ---------------------------------------------------------------- check */
const CK = {
  st: null,
  reset(sample) {
    this.st = { title: sample?.title || "", channel: sample?.channel || "Instagram", goal: sample?.goal || "", ai: !!sample?.ai, confidential: false,
      text: sample?.text || "", original: null, image: null, alt: "", result: null, accepted: new Set(), contests: {}, fixed: null, file: null, pages: null, pagesText: null };
    this.save();
  },
  save() { const s = this.st; store.set("ck", { title: s.title, channel: s.channel, goal: s.goal, ai: s.ai, confidential: s.confidential, text: s.text, alt: s.alt }); },
  restore() { const d = store.get("ck", null); this.reset(d || undefined); if (d) Object.assign(this.st, d); },
};
CK.restore();

async function check(sample) {
  if (sample && SAMPLES[sample]) { CK.reset(SAMPLES[sample]); S.autorun = true; history.replaceState(null, "", "#/check"); }
  const st = CK.st;
  const canSubmit = S.me.roles.includes("creator");
  $("#app").innerHTML = `
  <div class="page-h"><div><h2>Check content</h2><p>Paste a draft, or upload a PDF, DOCX or poster. BrandProof checks it against Brand Memory v${S.me.brand_version} before anyone publishes.</p></div></div>
  <div class="card samples"><span class="small muted">Try a sample →</span>
      <span class="small"><b>Text:</b></span><button class="btn sm" data-s="risky">Risky AI ad</button><button class="btn sm" data-s="hinglish">Hinglish</button><button class="btn sm" data-s="hindi">हिंदी</button>
      <button class="btn sm" data-s="outdated">Outdated facts</button><button class="btn sm" data-s="confidential">Confidential leak</button><button class="btn sm" data-s="clean">Clean copy</button>
      <span class="small"><b>Poster:</b></span>${Object.entries(SAMPLE_IMAGES).map(([k, v]) => `<button class="btn sm" data-img="${k}">${esc(v.label)}</button>`).join("")}
      <span class="small"><b>File:</b></span><button class="btn sm" data-pdf="1">Brochure PDF</button></div>
  <div class="split">
    <div class="stack">
      <div class="card stack">
        <div class="grid g2" style="gap:10px">
          <div><label class="f" for="c-title">Title</label><input class="inp" id="c-title" maxlength="120" value="${esc(st.title)}" placeholder="e.g. Diwali Instagram post"></div>
          <div><label class="f" for="c-channel">Channel</label><select class="inp" id="c-channel">${["Instagram", "Facebook", "Twitter/X", "WhatsApp", "Email", "Website", "SMS", "App notification", "Print", "Brochure / PDF", "Poster"].map((c) => `<option ${c === st.channel ? "selected" : ""}>${c}</option>`).join("")}</select></div>
        </div>
        <div><label class="f" for="c-goal">Creator's goal <span class="muted">(Purpose Guard keeps this intact)</span></label><input class="inp" id="c-goal" maxlength="200" value="${esc(st.goal)}" placeholder="e.g. Promote the Diwali offer and drive purchases"></div>
        <div><label class="f" for="c-text">Content <span class="muted">(English, Hindi or Hinglish)</span></label><textarea class="inp" id="c-text" maxlength="20000" placeholder="Paste caption, ad copy, email or page text…">${esc(st.text)}</textarea>
          <div class="tiny muted" id="c-count" style="text-align:right">${st.text.length}/20000</div></div>
        <div class="drop" id="c-drop" tabindex="0">📎 Drop a <b>PDF, DOCX, TXT</b> or a <b>poster (PNG/JPG)</b> here, or <a href="#" id="c-browse">browse</a><input type="file" id="c-file" hidden accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp"><div id="c-fileinfo" class="small" style="margin-top:6px">${st.image ? "🖼️ Image attached." : ""}</div></div>
        <div id="c-imgbox" ${st.image ? "" : "hidden"}><label class="f" for="c-alt">Image alt text</label><input class="inp" id="c-alt" maxlength="300" value="${esc(st.alt)}" placeholder="Describe the image for screen-reader users"></div>
        <div class="grid g2" style="gap:8px">
          <label class="chk"><input type="checkbox" id="c-ai" ${st.ai ? "checked" : ""}> Draft was written with an AI tool (recorded on the certificate)</label>
          <label class="chk"><input type="checkbox" id="c-conf" ${st.confidential ? "checked" : ""}> <span><b>Confidential mode</b> — send nothing to any AI service</span></label>
        </div>
        <div class="row"><button class="btn pri" id="c-run">Run BrandProof check</button><button class="btn" id="c-clear">Clear</button>
          <span class="small muted">${S.health && S.health.ai ? "AI on · " + esc(S.health.model) : "AI off · rules only"}</span></div>
      </div>
      <div id="c-image"></div>
      <div id="c-fixed"></div>
    </div>
    <div class="stack" id="c-results">${st.result ? "" : `<div class="card empty">Run a check to see the risk score, highlighted issues, evidence and suggested fixes.<br><br><span class="small">Tip: “Risky AI ad” shows most checks at once; “Off-brand poster” shows text-in-image, contrast and logo checks.</span></div>`}</div>
  </div>`;

  const sync = () => { st.title = $("#c-title").value; st.channel = $("#c-channel").value; st.goal = $("#c-goal").value; st.text = $("#c-text").value; st.ai = $("#c-ai").checked; st.confidential = $("#c-conf").checked; st.alt = $("#c-alt") ? $("#c-alt").value : ""; CK.save(); };
  ["#c-title", "#c-goal", "#c-alt"].forEach((s) => { const el = $(s); if (el) el.oninput = sync; });
  $("#c-text").oninput = () => { sync(); $("#c-count").textContent = `${st.text.length}/20000`; };
  $$("[data-s]").forEach((b) => (b.onclick = () => { CK.reset(SAMPLES[b.dataset.s]); check().then(() => $("#c-run").click()); }));
  $$("[data-img]").forEach((b) => (b.onclick = async () => {
    const s = SAMPLE_IMAGES[b.dataset.img];
    CK.reset({ title: s.title, channel: "Poster", goal: "Promote the Diwali offer", ai: false, text: "" });
    try { CK.st.image = await urlToDataURL(`/static/samples/${s.file}`); } catch (e) { return toast("Could not load the sample image.", true); }
    check().then(() => $("#c-run").click());
  }));
  $("[data-pdf]").onclick = async () => {
    try { const blob = await (await fetch("/static/samples/ABC_Diwali_Brochure.pdf")).blob(); await loadFile(new File([blob], "ABC_Diwali_Brochure.pdf", { type: "application/pdf" })); $("#c-run").click(); }
    catch (e) { toast("Could not load the sample PDF.", true); }
  };
  $("#c-clear").onclick = () => { CK.reset(); check(); };
  $("#c-browse").onclick = (e) => { e.preventDefault(); $("#c-file").click(); };
  const drop = $("#c-drop");
  drop.onkeydown = (e) => { if (e.key === "Enter") $("#c-file").click(); };
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]); };
  $("#c-file").onchange = (e) => { if (e.target.files[0]) loadFile(e.target.files[0]); e.target.value = ""; };

  async function loadFile(file) {
    sync();
    if (file.size > 6 * 1024 * 1024) return toast("That file is larger than 6 MB.", true);
    const fd = new FormData(); fd.append("file", file);
    $("#c-fileinfo").innerHTML = '<span class="muted">Reading file…</span>';
    try {
      const r = await api("/api/extract", { method: "POST", body: fd });
      if (r.kind === "image") {
        st.image = r.image; st.file = r.filename;
        $("#c-imgbox").hidden = false;
        $("#c-fileinfo").innerHTML = `🖼️ <b>${esc(r.filename)}</b> attached — text in the image, contrast, logo, palette and alt text will be checked. <a href="#" id="c-rmimg">remove</a>`;
        $("#c-rmimg").onclick = (e) => { e.preventDefault(); st.image = null; $("#c-imgbox").hidden = true; $("#c-fileinfo").innerHTML = ""; };
        if (!st.title) $("#c-title").value = st.title = r.filename.replace(/\.\w+$/, "");
      } else {
        st.text = r.text; $("#c-text").value = r.text; st.file = r.filename; st.pages = r.pages; st.pagesText = r.text;
        $("#c-count").textContent = `${st.text.length}/20000`;
        $("#c-fileinfo").innerHTML = `📄 <b>${esc(r.filename)}</b> — ${r.page_count ? r.page_count + " page(s), " : ""}${r.text.split(/\n\s*\n/).length} paragraph(s) extracted. Issues will show page and paragraph.`;
        if (!st.title) $("#c-title").value = st.title = r.filename.replace(/\.\w+$/, "");
      }
      CK.save();
    } catch (e) { $("#c-fileinfo").innerHTML = `<span style="color:var(--high)">${esc(e.message)}</span>`; }
  }

  $("#c-run").onclick = (ev) => {
    sync();
    if (!st.text.trim() && !st.image) { toast("Add some text or an image first.", true); $("#c-text").focus(); return; }
    once(ev.currentTarget, st.image ? "Reading the poster with AI… (first time up to ~40 s)" : "Checking…", async () => {
      st.result = await api("/api/check", { method: "POST", body: { text: st.text, goal: st.goal, confidential: st.confidential, image: st.image, alt_text: st.alt, pages: st.text === st.pagesText ? st.pages : null } });
      st.original = st.text; st.fixed = null; st.contests = {};
      st.accepted = new Set(st.result.findings.filter((f) => f.fix && !f.fix.overlaps && !f.fix.target && !f.fix.design_only).map((f) => f.key));
      renderResults(); guideMark("check");
      if (st.image) guideMark("image");
      if (/[ऀ-ॿ]|hazaar|rupaye|aajeevan|daam/i.test(st.text)) guideMark("hindi");
      if (window.innerWidth < 960) $("#c-results").scrollIntoView({ behavior: "smooth" });
    });
  };

  function renderResults() {
    const r = st.result; if (!r) return;
    const nFix = st.accepted.size;
    const textFindings = r.findings.filter((f) => !f.target);
    $("#c-results").innerHTML = `
      <div class="card"><div class="row between"><h3 style="margin:0">Risk assessment</h3><span class="small muted">Brand Memory v${r.brand_version}</span></div><div style="margin-top:10px">${riskBlock(r.risk)}</div></div>
      ${st.original ? `<div class="card"><h3>Highlighted draft</h3><div class="doc" id="c-doc">${highlight(st.original || "", r.findings)}</div>
        <div class="tiny muted" style="margin-top:6px">Click a highlight to jump to its finding. Readability: Flesch ${r.metrics.readability.flesch ?? "–"} (${r.metrics.readability.words} words).</div></div>` : ""}
      <div class="card"><div class="row between"><h3 style="margin:0">Findings (${r.findings.length})</h3>
        ${textFindings.some((f) => f.fix) ? `<div class="row"><button class="btn sm" id="c-all">Select all fixes</button><button class="btn ok" id="c-apply" ${nFix ? "" : "disabled"}>Apply ${nFix} fix${nFix === 1 ? "" : "es"}</button></div>` : ""}</div>
        <div class="findings" style="margin-top:10px">${r.findings.length ? r.findings.map((f) => findingCard(f, { selectable: true, accepted: st.accepted, contest: canSubmit, contests: st.contests })).join("") : '<div class="notice ok">✅ No issues found. This content matches Brand Memory.</div>'}</div>
        <div style="margin-top:10px">${aiNotice(r.ai, r.image)}</div></div>
      <div class="card"><div class="row between"><div><h3 style="margin:0">Submit for review</h3><div class="small muted">${submitHint(r)}</div></div>
        <button class="btn pri" id="c-submit" ${canSubmit ? "" : "disabled"}>Submit ${st.fixed ? "revised" : "this"} version →</button></div></div>`;
    $("#c-image").innerHTML = creativeBlock(r.image, st.image, r.findings);
    bindDoc(document, "");
    $$("[data-accept]").forEach((c) => (c.onchange = () => { c.checked ? st.accepted.add(c.dataset.accept) : st.accepted.delete(c.dataset.accept); renderResults(); }));
    $$("[data-contest]").forEach((b) => (b.onclick = async () => { const why = await ask("Why should this finding not apply?", "e.g. This is a dated festival offer, so urgency is factual.", "Contest"); if (why) { st.contests[b.dataset.contest] = why; renderResults(); } }));
    $$("[data-uncontest]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); delete st.contests[a.dataset.uncontest]; renderResults(); }));
    $$("[data-usealt]").forEach((b) => (b.onclick = () => { st.alt = b.dataset.usealt; const a = $("#c-alt"); if (a) a.value = st.alt; CK.save(); toast("Alt text added. Run the check again to clear this finding."); }));
    const all = $("#c-all"); if (all) all.onclick = () => { r.findings.forEach((f) => f.fix && !f.fix.overlaps && !f.fix.target && !f.fix.design_only && st.accepted.add(f.key)); renderResults(); };
    const ap = $("#c-apply"); if (ap) ap.onclick = (e) => once(e.currentTarget, "Applying…", applyFixes);
    $("#c-submit").onclick = (e) => submit(e.currentTarget);
    renderFixed();
  }
  function submitHint(r) {
    if (!canSubmit) return S.me.demo ? `Switch “Acting as” to <b>Creator</b> to submit.` : "You don't have the Creator role in this workspace.";
    const who = esc(S.me.demo ? DEMO_PEOPLE.creator : S.me.user.name);
    const open = (st.fixed ? st.fixed.recheck.risk : r.risk).counts.high;
    return `You'll submit as <b>Creator</b> (${who}). ` + (open ? `${open} high-severity issue(s) still open → it goes to <b>Compliance</b> first, then a Reviewer.` : "No high-severity issues → it goes straight to a <b>Reviewer</b>.");
  }
  async function applyFixes() {
    const fx = await api("/api/fix", { method: "POST", body: { text: st.original, findings: st.result.findings, accepted: [...st.accepted], goal: st.goal } });
    st.fixed = fx; renderResults(); guideMark("fix");
    $("#c-fixed").scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function renderFixed() {
    const fx = st.fixed;
    if (!fx) { $("#c-fixed").innerHTML = ""; return; }
    $("#c-fixed").innerHTML = `<div class="card stack"><div class="row between"><h3 style="margin:0">✨ Revised version</h3>
        <span class="row small">Risk <b style="text-decoration:line-through;color:var(--muted)">${st.result.risk.score}</b> → <b style="color:${fx.recheck.risk.score ? "var(--med)" : "var(--proof)"}">${fx.recheck.risk.score}</b></span></div>
      <div class="diff">${wordDiff(st.original, fx.text)}</div>
      ${guardBlock(fx.purpose)}
      <div><label class="f" for="c-fixtext">Edit before submitting (optional)</label><textarea class="inp" id="c-fixtext" style="min-height:90px" maxlength="20000">${esc(fx.text)}</textarea></div>
      ${fx.recheck.findings.length ? `<div class="notice warn small">Still open after fixes: ${fx.recheck.findings.map((f) => `<b>${esc(f.rule_id)}</b> ${esc(f.title)}`).join(" · ")}</div>` : '<div class="notice ok small">✅ The revised text passes every rule check.</div>'}
      <div class="tiny muted">Accepted AI rewrites are labelled “AI-assisted” in the audit trail until a reviewer approves them.</div></div>`;
    $("#c-fixtext").oninput = (e) => { fx.text = e.target.value; };
  }
  async function submit(btn) {
    sync();
    if (!canSubmit) return toast("You need the Creator role to submit.", true);
    if (S.role !== "creator") setRole("creator", true);
    return once(btn, "Submitting…", async () => {
      const final = st.fixed ? st.fixed.text : st.original;
      const dismissals = st.fixed ? [] : Object.entries(st.contests).map(([key, reason]) => ({ key, reason }));
      const s = await api("/api/submissions", { method: "POST", body: { title: st.title || "Untitled", channel: st.channel, goal: st.goal,
        ai_generated: st.ai, confidential: st.confidential, text: final, original_text: st.original, dismissals, image: st.image, alt_text: st.alt } });
      toast(`Submitted · ${STATUS_LABEL[s.status]}`); guideMark("submit");
      CK.reset(); refreshCounts();
      location.hash = `#/queue/${s.id}`;
    });
  }
  if (st.result) renderResults();
  if (S.autorun) { S.autorun = false; $("#c-run").click(); }
}

/* ---------------------------------------------------------------- queue & review */
async function queue(id) {
  if (id) return submissionPage(+id);
  const subs = await load(api("/api/submissions"));
  const mine = (s) => (S.role === "compliance" && s.status === "compliance_review") || (S.role === "reviewer" && s.status === "in_review") || (S.role === "creator" && s.status === "changes_requested");
  const filter = store.get("qf", "all");
  const shown = subs.filter((s) => filter === "all" || (filter === "mine" ? mine(s) : s.status === filter));
  const rows = shown.map((s) => `<tr class="click" data-id="${s.id}" tabindex="0"><td>${mine(s) ? "👉 " : ""}<b>${esc(s.title)}</b>${s.demo ? ' <span class="tag grey">sample</span>' : ""}<div class="tiny muted">${esc(s.channel)} · ${esc(s.creator)}</div></td>
    <td><span class="status st-${s.status}">${STATUS_LABEL[s.status] || s.status}</span></td><td><b>${s.risk}</b></td><td>v${s.current_version}</td><td>${s.has_certificate ? '<span class="tag ok">✓ certified</span>' : ""}</td><td class="small muted">${fmtDate(s.updated_at)}</td></tr>`).join("");
  const waiting = subs.filter(mine).length;
  const chip = (k, l) => `<button class="btn sm ${filter === k ? "on" : ""}" data-f="${k}">${l}</button>`;
  $("#app").innerHTML = `<div class="page-h"><div><h2>Review queue</h2><p>Creator → Compliance (if high-risk issues) → Reviewer → Proof Certificate.</p></div>
    <div class="notice small">Acting as <b>${ROLE_LABEL[S.role]}</b>: ${waiting ? `<b>${waiting}</b> item(s) need your action (👉).` : "nothing waiting for you."}</div></div>
    <div class="row" style="margin-bottom:10px">${chip("all", "All")}${chip("mine", "Needs my action")}${chip("compliance_review", "Compliance")}${chip("in_review", "Reviewer")}${chip("approved", "Approved")}${chip("changes_requested", "Changes requested")}</div>
    <div class="card">${subs.length ? `<table class="t"><thead><tr><th>Content</th><th>Status</th><th>Risk</th><th>Version</th><th>Proof</th><th>Updated</th></tr></thead><tbody>${rows || '<tr><td colspan="6" class="empty">Nothing in this filter.</td></tr>'}</tbody></table>`
      : `<div class="empty">No submissions yet. <a href="#/check">Check your first piece of content</a> and submit it for review.</div>`}</div>`;
  $$("[data-f]").forEach((b) => (b.onclick = () => { store.set("qf", b.dataset.f); queue(); }));
  $$("tr[data-id]").forEach((tr) => { tr.onclick = () => (location.hash = `#/queue/${tr.dataset.id}`); tr.onkeydown = (e) => { if (e.key === "Enter") tr.onclick(); }; });
}

async function submissionPage(id) {
  let s;
  try { s = await load(api(`/api/submissions/${id}`)); }
  catch (e) { if (e instanceof Stale) throw e; $("#app").innerHTML = `<div class="card empty">${esc(e.message)}<br><br><a class="btn" href="#/queue">← Back to the review queue</a></div>`; return; }
  let vi = s.versions.length - 1;
  const act = (action, extra = {}) => api(`/api/submissions/${id}/action`, { method: "POST", body: { action, ...extra } });

  function render() {
    const cur = s.versions[s.versions.length - 1];
    const v = s.versions[vi];
    const latest = vi === s.versions.length - 1;
    const decFor = (ver, key) => s.decisions.filter((d) => d.version === ver && d.finding_key === key).slice(-1)[0];
    const canDismiss = (f) => S.role === "compliance" || (S.role === "reviewer" && f.severity !== "high");
    const flow = ["Submitted", "Compliance", "Reviewer", "Certified"];
    const pos = { compliance_review: 1, in_review: 2, approved: 4, changes_requested: 1, rejected: 1 }[s.status] ?? 0;
    const hadCompliance = s.events.some((e) => e.action === "cleared claims") || s.status === "compliance_review";
    const stepper = flow.map((l, i) => {
      let c = i < pos ? "done" : i === pos ? "cur" : "";
      if (i === 1 && !hadCompliance && pos > 1) c = "done";
      if ((s.status === "rejected" || s.status === "changes_requested") && i === pos) c = "bad cur";
      return `<div class="${c}">${l}${i === 1 && !hadCompliance && pos > 1 ? " (not needed)" : ""}</div>`;
    }).join("");
    const nx = s.next || {};
    const canTake = nx.role && S.me.roles.includes(nx.role);
    const nextBanner = `<div class="nextstep ${nx.role === S.role ? "me" : ""}"><div><b>Next step:</b> ${esc(nx.text || "")}</div>
      ${nx.role && nx.role !== S.role ? (canTake ? `<button class="btn sm pri" data-switch="${nx.role}">Switch to ${ROLE_LABEL[nx.role]}${S.me.demo ? " · " + DEMO_PEOPLE[nx.role] : ""}</button>` : `<span class="small muted">Waiting for a ${ROLE_LABEL[nx.role]}.</span>`) : ""}</div>`;
    const tabs = s.versions.map((x, i) => `<button class="${i === vi ? "on" : ""}" data-v="${i}">v${x.version} · risk ${x.risk}</button>`).join("") + (s.versions.length > 1 ? `<button data-diff="1">Compare v${s.versions[0].version} → v${cur.version}</button>` : "");
    const reviewing = ["compliance_review", "in_review"].includes(s.status);
    const cards = v.findings.map((f) => {
      const d = decFor(v.version, f.key);
      const actions = latest && reviewing && !(d && d.action === "dismissed") && canDismiss(f) ? `<button class="btn sm" style="margin-top:8px" data-dismiss="${esc(f.key)}">Dismiss with reason</button>` : "";
      return findingCard(f, { decision: d, actions, prefix: "s" });
    }).join("");
    $("#app").innerHTML = `
      <div class="page-h"><div><a href="#/queue" class="small">← Review queue</a><h2 style="margin-top:4px">${esc(s.title)} ${s.demo ? '<span class="tag grey">sample</span>' : ""}</h2>
        <p>${esc(s.channel)} · by ${esc(s.creator)} · goal: “${esc(s.goal || "—")}” ${s.ai_generated ? '· <span class="tag ai">AI-assisted draft</span>' : ""}</p></div>
        <span class="status st-${s.status}" style="font-size:14px">${STATUS_LABEL[s.status]}</span></div>
      <div class="card" style="margin-bottom:12px"><div class="stepper">${stepper}</div></div>
      ${nextBanner}
      <div class="split">
        <div class="stack">
          <div class="card"><div class="vtabs">${tabs}</div><div id="s-view"><div class="doc">${highlight(v.text, v.findings)}</div>
            ${v.image ? `<div style="margin-top:10px">${creativeBlock(v.image_info, v.image, v.findings)}</div>` : ""}
            <div class="tiny muted" style="margin-top:6px">${esc(v.note || "")} · Brand Memory v${v.brand_version} · ${fmtDate(v.created_at)}</div></div></div>
          <div class="card"><h3>Actions · ${ROLE_LABEL[S.role]}</h3>${actionsPanel(cur)}</div>
          ${s.certificate ? certCard(s.certificate) : ""}
          <div class="card"><h3>Comments</h3>${s.comments.map((c) => `<div class="small" style="margin-bottom:8px"><b>${esc(c.author)}</b> <span class="muted">(${esc(ROLE_LABEL[c.role] || c.role)}) · ${fmtDate(c.created_at)}</span><div>${esc(c.text)}</div></div>`).join("") || '<p class="small muted">No comments yet.</p>'}
            <form class="row" id="s-cform"><input class="inp" id="s-comment" maxlength="1000" placeholder="Add a comment as ${esc(actorName())}…" style="flex:1"><button class="btn" id="s-csend">Post</button></form></div>
          <div class="card"><h3>Audit trail</h3><div class="tl">${s.events.map((e) => `<div><b>${esc(e.actor)}</b> <span class="muted">(${esc(ROLE_LABEL[e.role] || e.role)}${e.actor_user_id ? " · verified" : ""})</span> ${esc(e.action)} <span class="muted">${esc(e.detail || "")} · ${fmtDate(e.created_at)}</span></div>`).join("")}</div></div>
        </div>
        <div class="stack">
          <div class="card"><h3>Risk · v${v.version}</h3>${riskBlock(riskOf(v.findings))}</div>
          <div class="card"><h3>Findings in v${v.version} (${v.findings.length})</h3><div class="findings">${cards || '<div class="notice ok">✅ No open issues in this version.</div>'}</div>
            <div style="margin-top:10px">${aiNotice(v.ai_info, v.image_info)}</div></div>
        </div>
      </div>`;
    bindDoc(document, "s");
    $$("[data-switch]").forEach((b) => (b.onclick = () => { setRole(b.dataset.switch); refreshCounts(); render(); }));
    $$("[data-v]").forEach((b) => (b.onclick = () => { vi = +b.dataset.v; render(); }));
    const d = $("[data-diff]"); if (d) d.onclick = () => { $("#s-view").innerHTML = `<div class="diff">${wordDiff(s.versions[0].text, cur.text)}</div><div class="tiny muted" style="margin-top:6px">Red = removed, green = added.</div>`; $$(".vtabs button").forEach((x) => x.classList.toggle("on", x === d)); };
    $$("[data-dismiss]").forEach((b) => (b.onclick = async () => {
      const why = await ask("Reason for dismissing this finding", "This reason is recorded in the audit trail and on the Proof Certificate.", "Dismiss",
        ["Verified with the latest approved source", "Approved exception for this campaign", "False positive — wording is factual"]);
      if (!why) return;
      await once(b, "Saving…", async () => { Object.assign(s, await act("dismiss", { finding_key: b.dataset.dismiss, reason: why })); toast("Finding dismissed with reason"); render(); });
    }));
    $$("[data-a]").forEach((b) => (b.onclick = async () => {
      const a = b.dataset.a; let reason = "";
      if (a === "reject" || a === "request_changes") { reason = await ask(a === "reject" ? "Why is this rejected?" : "What should the creator change?", "", a === "reject" ? "Reject" : "Request changes", a === "request_changes" ? ["Please apply the suggested fixes", "Use the approved price and warranty", "Remove the confidential reference"] : []); if (!reason) return; }
      await once(b, a === "approve" ? "Approving…" : "Saving…", async () => {
        Object.assign(s, await act(a, { reason }));
        toast(a === "approve" ? "Approved — Proof Certificate issued 🎉" : a === "clear_claims" ? "Claims cleared — sent to the Reviewer" : "Done");
        if (a === "clear_claims") guideMark("compliance");
        if (a === "approve") guideMark("approve");
        refreshCounts(); vi = s.versions.length - 1; render();
      });
    }));
    const rs = $("#s-resub");
    if (rs) rs.onclick = () => once(rs, "Checking…", async () => { Object.assign(s, await act("resubmit", { text: $("#s-new").value, reason: "Revised after review" })); toast("Resubmitted and re-checked"); refreshCounts(); vi = s.versions.length - 1; render(); });
    const af = $("#s-autofix");
    if (af) af.onclick = () => once(af, "Applying…", async () => { const fx = await api("/api/fix", { method: "POST", body: { text: cur.text, findings: cur.findings, accepted: cur.findings.filter((f) => f.fix && !f.fix.overlaps && !f.fix.target && !f.fix.design_only).map((f) => f.key), goal: s.goal } }); $("#s-new").value = fx.text; toast(`Fixes applied · new risk ${fx.recheck.risk.score} · Purpose Guard ${fx.purpose.kept}/${fx.purpose.total}`); });
    $("#s-cform").onsubmit = (e) => { e.preventDefault(); const t = $("#s-comment").value.trim(); if (!t) return; once($("#s-csend"), "…", async () => { Object.assign(s, await act("comment", { text: t })); render(); }); };
  }
  function actionsPanel(cur) {
    const r = S.role, st = s.status;
    if (r === "compliance" && st === "compliance_review") return `<p class="small">Check every high-severity claim. Dismiss a finding only with a reason (it is recorded on the certificate). <b>${s.open_high}</b> high finding(s) open.</p>
      <div class="row"><button class="btn ok" data-a="clear_claims" ${s.open_high ? "disabled title='Dismiss or resolve the high findings first'" : ""}>✓ Clear claims → send to Reviewer</button><button class="btn" data-a="request_changes">Request changes</button><button class="btn bad" data-a="reject">Reject</button></div>`;
    if (r === "reviewer" && st === "in_review") return `<p class="small">Final brand check. Approving issues a Proof Certificate for <b>v${cur.version}</b>${S.me.demo ? "" : ` signed with your verified account (${esc(S.me.user.email)})`}.</p>
      <div class="row"><button class="btn ok" data-a="approve">✓ Approve &amp; issue certificate</button><button class="btn" data-a="request_changes">Request changes</button><button class="btn bad" data-a="reject">Reject</button></div>`;
    if (r === "creator" && ["changes_requested", "compliance_review", "in_review"].includes(st)) return `<p class="small">${st === "changes_requested" ? "The reviewer asked for changes. Edit the text (or apply the suggested fixes) and resubmit; it will be checked again." : "You can still resubmit an improved version."}</p>
      <textarea class="inp" id="s-new" style="min-height:100px" maxlength="20000">${esc(cur.text)}</textarea><div class="row" style="margin-top:8px"><button class="btn pri" id="s-resub">Resubmit as v${cur.version + 1}</button><button class="btn" id="s-autofix">Apply all suggested fixes</button></div>`;
    if (st === "approved") return `<p class="small">Approved and certified. Nothing left to do.</p>`;
    if (st === "rejected") return `<p class="small">This content was rejected.</p>`;
    return `<p class="small muted">Nothing for <b>${ROLE_LABEL[r]}</b> to do here right now.</p>`;
  }
  render();
}

function certCard(c, full = false) {
  const p = c.payload;
  return `<div class="cert"><div class="row" style="align-items:flex-start;gap:14px"><div class="seal">#${c.number}</div><div style="flex:1;min-width:0">
    <div class="row between"><h3 style="margin:0">Proof Certificate #${c.number}</h3><span class="tag ok">✓ approved</span></div>
    <div class="small"><b>${esc(p.title)}</b> · ${esc(p.channel)} · v${p.version} by ${esc(p.creator)} · Brand Memory v${p.brand_memory_version} · AI: ${esc(p.ai_model)}${p.ai_generated_draft ? " · AI-assisted draft" : ""}</div>
    <div class="small muted">Approvals: ${p.approvers.map((a) => `${esc(a.name)}${a.email ? ` &lt;${esc(a.email)}&gt;` : ""} (${esc(ROLE_LABEL[a.role] || a.role)}, ${esc(a.action)}${a.verified ? ", verified account" : ""})`).join(" → ") || "—"}</div>
    <div class="tiny muted">Identity: ${esc(p.identity || "")}</div>
    ${p.decisions.length ? `<div class="small muted">Decisions recorded: ${p.decisions.map((d) => `${esc(d.rule)} ${esc(d.action)} by ${esc(d.by)} — “${esc(d.reason)}”`).join("; ")}</div>` : ""}
    <div class="grid g2" style="gap:6px;margin-top:8px"><div><div class="tiny muted">Content hash (SHA-256)</div><div class="hash">${full ? c.content_hash : short(c.content_hash)}</div></div>
    <div><div class="tiny muted">Certificate hash · chained to #${c.number - 1 || "genesis"}</div><div class="hash">${full ? c.cert_hash : short(c.cert_hash)}</div></div></div>
    <div class="tiny muted" style="margin-top:6px">Issued ${fmtDate(p.issued_at)} · previous ${short(p.prev_hash)}</div></div></div></div>`;
}
