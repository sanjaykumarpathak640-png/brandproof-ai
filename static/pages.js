/* BrandProof AI — pages: Brand Memory, Insights, Certificates, Team, Accuracy, Trust, demo guide, router. */
"use strict";

const FACT_KEYS = [["price", "Product price (MRP)", "INR"], ["max_discount", "Maximum discount", "%"], ["warranty_years", "Warranty", "years"],
  ["battery_hours", "Battery life (tested)", "hours"], ["ip_rating", "Water resistance rating", ""], ["tagline", "Approved tagline", ""], ["product_name", "Official product name", ""]];

/* ---------------------------------------------------------------- brand memory */
async function brandPage() {
  const b = await load(api("/api/brand"));
  const admin = S.role === "admin";
  const canAdmin = S.me.roles.includes("admin");
  const today = b.today;
  const facts = b.facts.slice().sort((x, y) => x.key.localeCompare(y.key) || (y.valid_from || "").localeCompare(x.valid_from || ""));
  $("#app").innerHTML = `<div class="page-h"><div><h2>Brand Memory <span class="tag grey">v${b.version}</span></h2><p>${esc(b.meta.brand_name)} · ${esc(b.meta.brand_book || "")} · tone: ${esc(b.meta.tone)}</p></div>
    ${admin ? '<span class="tag ok">You can edit (Brand Admin)</span>' : `<div class="notice small">Read-only. ${canAdmin ? `<button class="btn sm" id="b-toadmin">Switch to Brand Admin</button>` : "Only a Brand Admin can edit."}</div>`}</div>
  <div class="grid g2">
    <div class="card"><h3>📥 Import a brand book or update</h3><p class="small muted" style="margin-top:0">Upload a PDF, DOCX or TXT. Facts (price, discount, warranty, specs), terms and confidential items become <b>pending</b> candidates. Simple “Label: value” lines are read by patterns; free-form brand books are read by AI, and every value must appear in the document. Nothing changes until the admin approves.</p>
      <div class="row"><input type="file" id="b-file" accept=".pdf,.docx,.txt,.md" ${admin ? "" : "disabled"} aria-label="Brand book file"><button class="btn pri" id="b-imp" ${admin ? "" : "disabled"}>Extract</button></div>
      <div class="small" style="margin-top:6px"><a href="/static/samples/ABC_Brand_Update_Nov2026.docx" download>⬇ Sample brand update (DOCX)</a> — try importing it.</div>
      <div id="b-cands" style="margin-top:10px">${candList(b.candidates, admin)}</div></div>
    <div class="card"><h3>🕒 Version history</h3><div class="tl" style="max-height:280px;overflow:auto">${b.versions.map((v) => `<div><b>v${v.version}</b> ${esc(v.note)} <span class="muted">· ${fmtDate(v.created_at)}</span></div>`).join("")}</div></div>
  </div>
  <div class="card" style="margin-top:16px"><div class="row between"><h3 style="margin:0">Approved facts</h3><span class="small muted">Expired facts stay on record, so old prices can be flagged as <i>outdated</i>.</span></div>
    <table class="t" style="margin-top:8px"><thead><tr><th>ID</th><th>Fact</th><th>Value</th><th>Valid</th><th>Source</th></tr></thead><tbody>
    ${facts.map((f) => { const exp = f.valid_to && f.valid_to < today; return `<tr class="${exp ? "exp" : ""}"><td class="mono">${esc(f.id)}</td><td>${esc(f.label)}</td><td><b>${esc(f.value)}</b> ${esc(f.unit || "")}</td><td class="small">${esc(f.valid_from || "")} → ${esc(f.valid_to || "now")}${exp ? ' <span class="tag grey">expired</span>' : ""}</td><td class="small muted">${esc(f.source || "")}</td></tr>`; }).join("") || '<tr><td colspan="5" class="empty">No facts yet. Import a brand book or add one below.</td></tr>'}</tbody></table>
    ${admin ? `<div class="editor"><div class="small"><b>Change a fact</b> — preview which approved content would be affected before you save.</div>
      <div class="grid g4" style="gap:8px;margin-top:6px"><select class="inp" id="nf-key" aria-label="Fact">${FACT_KEYS.map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select>
      <input class="inp" id="nf-val" placeholder="New value" maxlength="120" aria-label="New value"><input class="inp" id="nf-src" placeholder="Source (e.g. Price List Dec 2026)" maxlength="120" aria-label="Source">
      <button class="btn pri" id="nf-prev">Preview impact</button></div><div id="nf-out"></div></div>` : ""}</div>
  <div class="card" style="margin-top:16px"><h3>Rules</h3><table class="t"><thead><tr><th>ID</th><th>Rule</th><th>Severity</th><th>Source</th>${admin ? "<th>On</th>" : ""}</tr></thead><tbody>
    ${b.rules.map((r) => `<tr><td class="mono">${esc(r.id)}</td><td><b>${esc(r.title)}</b><div class="small muted">${esc(r.description)}</div></td><td><span class="tag ${r.severity}">${r.severity}</span></td><td class="small muted">${esc(r.source)}</td>${admin ? `<td><input type="checkbox" data-rule="${esc(r.id)}" ${r.enabled ? "checked" : ""} aria-label="Enable ${esc(r.id)}"></td>` : ""}</tr>`).join("")}</tbody></table>
    <div id="rule-out"></div></div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card"><h3>Terminology</h3><table class="t"><thead><tr><th>Avoid</th><th>Use instead</th></tr></thead><tbody>${b.terms.map((t) => `<tr><td>${esc(t.avoid)}</td><td><b>${esc(t.prefer)}</b><div class="tiny muted">${esc(t.note || "")}</div></td></tr>`).join("") || '<tr><td colspan="2" class="empty">No terms yet.</td></tr>'}</tbody></table>
      ${admin ? '<div class="row" style="margin-top:8px"><input class="inp" id="nt-a" placeholder="Avoid" maxlength="60" style="flex:1" aria-label="Word to avoid"><input class="inp" id="nt-p" placeholder="Use instead" maxlength="60" style="flex:1" aria-label="Preferred word"><button class="btn" id="nt-prev">Preview impact</button></div><div id="nt-out"></div>' : ""}
      <h3 style="margin-top:16px">🔒 Confidential terms</h3><div class="row">${(b.meta.confidential_terms || []).map((t) => `<span class="tag high" style="text-transform:none">${esc(t)}</span>`).join("") || '<span class="small muted">None yet.</span>'}</div>
      ${admin ? '<div class="row" style="margin-top:8px"><input class="inp" id="nc-t" placeholder="e.g. Project Orion" maxlength="80" style="flex:1" aria-label="Confidential term"><button class="btn" id="nc-prev">Preview impact</button></div><div id="nc-out"></div>' : ""}
      <p class="tiny muted">Confidential terms are flagged as high severity and masked before any AI call.</p></div>
    <div class="stack">
      <div class="card"><h3>🏷️ Approved logo</h3>${b.logo_data ? `<img src="${b.logo_data}" alt="Approved logo" class="logoimg">` : '<p class="small muted">No logo yet. Posters will skip the logo check until one is added.</p>'}
        ${admin ? '<div class="row" style="margin-top:8px"><input type="file" id="lg-file" accept=".png,.jpg,.jpeg,.webp" aria-label="Logo file"><button class="btn" id="lg-up">Upload logo</button></div>' : ""}
        <p class="tiny muted">Every poster is checked for this logo: pixel template matching first, then the vision model for resized or recoloured versions.</p></div>
      <div class="card"><h3>Palette</h3><div class="pal">${b.palette.map((p) => `<div><i style="background:${p.hex}"></i><span><b>${esc(p.name)}</b><br><span class="mono">${p.hex}</span></span></div>`).join("") || '<span class="small muted">No colours yet.</span>'}</div>
        ${admin ? `<div style="margin-top:8px"><label class="f" for="pal-in">Edit colours <span class="muted">(one per line: Name #HEX)</span></label><textarea class="inp" id="pal-in" style="min-height:90px">${esc(b.palette.map((p) => `${p.name} ${p.hex}`).join("\n"))}</textarea><button class="btn" id="pal-save" style="margin-top:6px">Save palette</button></div>` : ""}
        <p class="tiny muted">Image colours must be within ΔE 20 (CIE76) of one of these.</p></div>
      <div class="card"><h3>Brand profile</h3>${admin ? `<div class="stack"><div><label class="f" for="bp-name">Brand name</label><input class="inp" id="bp-name" maxlength="80" value="${esc(b.meta.brand_name || "")}"></div>
        <div><label class="f" for="bp-tone">Tone</label><input class="inp" id="bp-tone" maxlength="120" value="${esc(b.meta.tone || "")}"></div>
        <div><label class="f" for="bp-voice">Voice profile</label><textarea class="inp" id="bp-voice" style="min-height:70px" maxlength="400">${esc(b.meta.voice_profile || "")}</textarea></div><button class="btn" id="bp-save">Save profile</button></div>`
        : `<p class="small" style="margin:0"><b>Tone:</b> ${esc(b.meta.tone)}<br>${esc(b.meta.voice_profile)}</p>`}</div>
    </div>
  </div>`;
  const ta = $("#b-toadmin"); if (ta) ta.onclick = () => { setRole("admin"); brandPage(); };
  bindCands();
  if (!admin) return;
  $("#b-imp").onclick = (e) => {
    const f = $("#b-file").files[0]; if (!f) return toast("Choose a file first", true);
    once(e.currentTarget, "Extracting…", async () => {
      const fd = new FormData(); fd.append("file", f);
      const r = await api("/api/brand/import", { method: "POST", body: fd, timeout: 120000 });
      toast(r.created ? `${r.created} candidate(s) found — review them below` : (r.message || "Nothing new found."), !r.created);
      if (r.ai_note) toast(r.ai_note, true);
      $("#b-cands").innerHTML = candList(r.candidates, true); bindCands();
    });
  };
  const preview = (btn, out, change) => once(btn, "Checking approved content…", async () => {
    const r = await api("/api/brand/impact", { method: "POST", body: change });
    $(out).innerHTML = impactBlock(r);
    guideMark("impact");
    $(out + " [data-apply]").onclick = (e) => once(e.currentTarget, "Saving…", async () => {
      const res = await api("/api/brand/change", { method: "POST", body: change });
      toast(`Saved · Brand Memory v${res.brand_version}`); S.me.brand_version = res.brand_version; brandPage();
    });
    $(out + " [data-cancel]").onclick = () => { $(out).innerHTML = ""; };
  });
  $("#nf-prev").onclick = (e) => { const v = $("#nf-val").value.trim(); if (!v) return toast("Enter a new value", true); preview(e.currentTarget, "#nf-out", { kind: "fact", key: $("#nf-key").value, value: v, source: $("#nf-src").value }); };
  $("#nt-prev").onclick = (e) => { const a = $("#nt-a").value.trim(), p = $("#nt-p").value.trim(); if (!a || !p) return toast("Enter both words", true); preview(e.currentTarget, "#nt-out", { kind: "term", avoid: a, prefer: p }); };
  $("#nc-prev").onclick = (e) => { const t = $("#nc-t").value.trim(); if (!t) return toast("Enter a term", true); preview(e.currentTarget, "#nc-out", { kind: "confidential", term: t }); };
  $$("[data-rule]").forEach((c) => (c.onchange = () => { const on = c.checked; c.checked = !on; preview(c, "#rule-out", { kind: "rule", rule_id: c.dataset.rule, enabled: on }); }));
  $("#lg-up").onclick = (e) => { const f = $("#lg-file").files[0]; if (!f) return toast("Choose an image", true); if (f.size > 2 * 1024 * 1024) return toast("Logo must be under 2 MB", true);
    once(e.currentTarget, "Uploading…", async () => { const r = await api("/api/brand/logo", { method: "POST", body: { image: await fileToDataURL(f), name: f.name } }); toast(`Logo saved · v${r.brand_version}`); brandPage(); }); };
  $("#pal-save").onclick = (e) => {
    const colours = $("#pal-in").value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => { const m = l.match(/^(.*?)[\s,]*(#?[0-9a-fA-F]{6})$/); return m ? { name: m[1].trim() || "Colour", hex: m[2] } : { name: l, hex: "bad" }; });
    once(e.currentTarget, "Saving…", async () => { const r = await api("/api/brand/palette", { method: "POST", body: { colours } }); toast(`Palette saved · v${r.brand_version}`); brandPage(); });
  };
  $("#bp-save").onclick = (e) => once(e.currentTarget, "Saving…", async () => { const r = await api("/api/brand/profile", { method: "POST", body: { brand_name: $("#bp-name").value, tone: $("#bp-tone").value, voice_profile: $("#bp-voice").value } }); toast(`Profile saved · v${r.brand_version}`); brandPage(); });
}
function impactBlock(r) {
  const c = r.change;
  const what = c.kind === "fact" ? `Set <b>${esc(c.key)}</b> to <b>${esc(c.value)}</b>` : c.kind === "rule" ? `${c.enabled ? "Enable" : "Disable"} rule <b>${esc(c.rule_id)}</b>` : c.kind === "term" ? `Avoid “${esc(c.avoid)}” → use “${esc(c.prefer)}”` : `Mark “${esc(c.term)}” as confidential`;
  const items = r.newly_flagged.map((s) => `<div class="fcard medium" style="margin-top:6px"><b>${esc(s.title)}</b> <span class="muted small">(${esc(s.channel)})</span> <a class="small" href="#/queue/${s.id}">open</a>
    ${s.findings.map((f) => `<div class="small"><span class="tag ${f.severity}">${f.severity}</span> <span class="mono">${esc(f.rule_id)}</span> “${esc(f.quote)}” — ${esc(f.message)}</div>`).join("")}</div>`).join("");
  const cleared = r.no_longer_flagged.map((s) => `<li>${esc(s.title)}</li>`).join("");
  return `<div class="impact"><div class="row between"><div><b>Impact preview:</b> ${what}</div><span class="small muted">${r.checked} approved item(s) re-checked</span></div>
    <div class="row" style="margin:6px 0"><span class="tag ${r.newly_flagged.length ? "high" : "ok"}">${r.newly_flagged.length} would now be flagged</span><span class="tag grey">${r.no_longer_flagged.length} no longer flagged</span><span class="tag grey">${r.unchanged} unchanged</span></div>
    ${items}${cleared ? `<div class="small" style="margin-top:6px">No longer flagged:<ul style="margin:4px 0 0 16px;padding:0">${cleared}</ul></div>` : ""}
    <div class="row" style="margin-top:8px"><button class="btn ok" data-apply>Apply change</button><button class="btn" data-cancel>Cancel</button>
    ${r.newly_flagged.length ? '<span class="small muted">Already-published items above would need an update after this change.</span>' : ""}</div></div>`;
}
function candList(cands, admin) {
  if (!cands.length) return '<p class="small muted">No pending candidates.</p>';
  return `<div class="small" style="font-weight:600;margin-bottom:6px">Pending approval (${cands.length})</div>` + cands.map((c) => {
    const p = c.payload;
    const what = c.kind === "fact" ? `<b>${esc(p.label)}</b>: ${p.current ? `<del>${esc(p.current)}</del> → ` : ""}<b>${esc(p.value)}</b> ${esc(p.unit || "")} <span class="tag ${p.change === "update" ? "medium" : "ok"}">${p.change}</span>`
      : c.kind === "term" ? `Term: avoid “${esc(p.avoid)}” → use “<b>${esc(p.prefer)}</b>”` : `Confidential: <b>${esc(p.term)}</b>`;
    return `<div class="fcard" style="margin-bottom:6px"><div>${what} <span class="tag ${String(c.method || "").startsWith("AI") ? "ai" : "grey"}">${esc(c.method || "pattern")}</span></div><div class="tiny muted">from ${esc(c.source)}: “…${esc(c.snippet)}…”</div>
      ${admin ? `<div class="row" style="margin-top:6px"><button class="btn sm ok" data-cand="${c.id}" data-d="approve">Approve</button><button class="btn sm" data-cand="${c.id}" data-d="reject">Reject</button></div>` : ""}</div>`;
  }).join("");
}
function bindCands() {
  $$("[data-cand]").forEach((b) => (b.onclick = () => once(b, "…", async () => {
    const r = await api(`/api/brand/candidates/${b.dataset.cand}/${b.dataset.d}`, { method: "POST" });
    toast(b.dataset.d === "approve" ? `Approved · Brand Memory v${r.brand_version}` : "Rejected"); S.me.brand_version = r.brand_version; brandPage();
  })));
}

/* ---------------------------------------------------------------- insights */
async function insightsPage() {
  const d = await load(api("/api/insights"));
  if (!d.totals.submissions) { $("#app").innerHTML = `<div class="page-h"><div><h2>Insights</h2><p>Repeated mistakes, who needs support, and which guidelines are unclear.</p></div></div><div class="card empty">No data yet. Insights appear after your team submits and reviews content. <a href="#/check">Check something now</a>.</div>`; return; }
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
  $$("[data-sg]").forEach((b) => (b.onclick = () => once(b, "Drafting…", async () => {
    const r = await api(`/api/insights/suggest/${b.dataset.sg}`, { method: "POST" });
    $(`#sg-${b.dataset.sg}`).innerHTML = `<div class="notice ok" style="margin-top:6px"><b>Suggested rule${r.ai ? " (AI draft)" : ""}:</b> ${esc(r.suggestion)}
      ${S.role === "admin" ? `<div style="margin-top:6px"><button class="btn sm ok" data-applyrule="${esc(b.dataset.sg)}">Preview &amp; apply to Brand Memory</button></div>` : '<div class="tiny muted">Only the Brand Admin can apply this.</div>'}</div>`;
    const ap = $(`[data-applyrule="${b.dataset.sg}"]`);
    if (ap) ap.onclick = () => once(ap, "Saving…", async () => { const res = await api("/api/brand/change", { method: "POST", body: { kind: "rule", rule_id: b.dataset.sg, description: r.suggestion } }); toast(`Rule updated · Brand Memory v${res.brand_version}`); S.me.brand_version = res.brand_version; });
  })));
}

/* ---------------------------------------------------------------- certificates */
async function certPage() {
  const d = await load(api("/api/certificates"));
  const list = d.certificates.slice().reverse();
  $("#app").innerHTML = `<div class="page-h"><div><h2>Proof Certificates</h2><p>Every approval creates a certificate with the content's SHA-256 hash, the Brand Memory version, every decision, the approvers' identities and the AI used. Each certificate includes the hash of the one before it, so changing any past record breaks the chain.</p></div></div>
    <div class="grid g2" style="margin-bottom:16px">
      <div class="notice ${d.chain.ok ? "ok" : "err"}"><b>${d.chain.ok ? "✓ Chain intact" : "✗ Chain broken"}</b> — ${d.chain.count} certificate(s) re-hashed and verified just now.</div>
      <div class="card"><h3>Is this the approved text?</h3><textarea class="inp" id="v-text" style="min-height:70px" maxlength="20000" placeholder="Paste the exact text that is about to be published…"></textarea>
        <div class="row" style="margin-top:8px"><button class="btn pri" id="v-go">Verify</button><span id="v-out" class="small" role="status"></span></div></div>
    </div>
    <div class="stack">${list.map((c, i) => certCard(c, true) + (i < list.length - 1 ? '<div class="chainlink">⛓ chained</div>' : "")).join("") || '<div class="card empty">No certificates yet. Approve something in the <a href="#/queue">Review queue</a>.</div>'}</div>`;
  $("#v-go").onclick = (e) => {
    const t = $("#v-text").value; if (!t.trim()) return toast("Paste some text first", true);
    once(e.currentTarget, "Checking…", async () => {
      const r = await api("/api/certificates/verify", { method: "POST", body: { text: t } });
      $("#v-out").innerHTML = r.match ? `<span style="color:var(--proof)">✓ Matches certificate ${r.certificates.map((c) => "#" + c.number + " (" + esc(c.title) + ")").join(", ")}</span>` : `<span style="color:var(--high)">✗ No certificate matches this exact text. It has not been approved, or it was changed after approval.</span>`;
    });
  };
}

/* ---------------------------------------------------------------- team */
async function teamPage() {
  const t = await load(api("/api/team"));
  if (t.demo) {
    $("#app").innerHTML = `<div class="page-h"><div><h2>Team</h2><p>Who can do what in this workspace.</p></div></div>
      <div class="card stack"><div class="notice">This is a <b>demo sandbox</b>: the four demo people below are role personas you can switch between with “Acting as”. In a real team workspace every person signs in with their own account, holds only the roles an admin gives them, and their verified identity is recorded on each Proof Certificate.</div>
      <table class="t"><thead><tr><th>Person</th><th>Role</th></tr></thead><tbody>${t.members.map((m) => `<tr><td>${esc(m.name)}</td><td>${m.roles.map((r) => `<span class="tag grey">${ROLE_LABEL[r]}</span>`).join(" ")}</td></tr>`).join("")}</tbody></table>
      <div class="row"><a class="btn pri" href="#/signup">Create a real team workspace</a><span class="small muted">Free · invite teammates by link · data kept in your own workspace</span></div></div>`;
    guideMark("team");
    return;
  }
  const admin = S.role === "admin";
  const link = (code) => `${location.origin}/#/join/${code}`;
  $("#app").innerHTML = `<div class="page-h"><div><h2>Team · ${esc(S.me.org_name)}</h2><p>${t.members.length} member(s). Roles decide who can submit, clear claims, approve and edit Brand Memory.</p></div></div>
    <div class="grid g2">
      <div class="card"><h3>Members</h3><table class="t"><thead><tr><th>Name</th><th>Roles</th>${admin ? "<th></th>" : ""}</tr></thead><tbody>
        ${t.members.map((m) => `<tr><td><b>${esc(m.name)}</b><div class="tiny muted">${esc(m.email)}${m.user_id === S.me.user.id ? " · you" : ""}</div></td>
          <td>${admin ? Object.keys(ROLE_LABEL).map((r) => `<label class="chk inline"><input type="checkbox" data-mrole="${m.user_id}" value="${r}" ${m.roles.includes(r) ? "checked" : ""}> ${ROLE_LABEL[r]}</label>`).join(" ") : m.roles.map((r) => `<span class="tag grey">${ROLE_LABEL[r]}</span>`).join(" ")}</td>
          ${admin ? `<td>${m.user_id !== S.me.user.id ? `<button class="btn sm bad" data-rm="${m.user_id}">Remove</button>` : ""}</td>` : ""}</tr>`).join("")}</tbody></table>
        ${admin ? '<button class="btn sm" id="m-save" style="margin-top:8px">Save role changes</button>' : ""}</div>
      <div class="card stack"><h3>Invite people</h3>${admin ? `
        <div class="row">${Object.keys(ROLE_LABEL).map((r) => `<label class="chk inline"><input type="checkbox" class="inv-role" value="${r}" ${r === "creator" ? "checked" : ""}> ${ROLE_LABEL[r]}</label>`).join("")}</div>
        <div class="row"><input class="inp" id="inv-email" type="email" placeholder="Email (optional — locks the link to this person)" style="flex:1"><button class="btn pri" id="inv-go">Create invite link</button></div>
        <div id="inv-out"></div>
        ${t.invites.length ? `<div class="small"><b>Open invite links</b>${t.invites.map((i) => `<div class="invite"><span class="mono">${esc(link(i.code))}</span> <span class="muted">${esc(i.roles)}${i.email ? " · " + esc(i.email) : ""}</span></div>`).join("")}</div>` : ""}
        <p class="tiny muted">Four-eyes rule: in a team with more than one member, nobody can approve content they submitted themselves.</p>`
        : '<p class="small muted">Only a Brand Admin can invite people.</p>'}</div>
    </div>`;
  if (!admin) return;
  $("#inv-go").onclick = (e) => {
    const roles = $$(".inv-role:checked").map((c) => c.value); if (!roles.length) return toast("Choose at least one role", true);
    once(e.currentTarget, "Creating…", async () => {
      const r = await api("/api/team/invites", { method: "POST", body: { roles, email: $("#inv-email").value || null } });
      const url = link(r.code);
      $("#inv-out").innerHTML = `<div class="notice ok small">Invite link for ${r.roles.map((x) => ROLE_LABEL[x]).join(", ")}:<div class="row" style="margin-top:6px"><input class="inp mono" value="${esc(url)}" readonly id="inv-url" style="flex:1"><button class="btn sm" id="inv-copy">Copy</button></div></div>`;
      $("#inv-copy").onclick = async () => { try { await navigator.clipboard.writeText(url); toast("Link copied"); } catch (er) { $("#inv-url").select(); toast("Press Ctrl+C to copy"); } };
    });
  };
  $("#m-save").onclick = (e) => once(e.currentTarget, "Saving…", async () => {
    const ids = [...new Set($$("[data-mrole]").map((c) => c.dataset.mrole))];
    for (const id of ids) {
      const roles = $$(`[data-mrole="${id}"]:checked`).map((c) => c.value);
      await api(`/api/team/members/${id}`, { method: "POST", body: { roles } });
    }
    toast("Roles saved"); await loadMe(); teamPage();
  });
  $$("[data-rm]").forEach((b) => (b.onclick = () => once(b, "…", async () => { await api(`/api/team/members/${b.dataset.rm}`, { method: "DELETE" }); toast("Member removed"); teamPage(); })));
}

/* ---------------------------------------------------------------- accuracy */
async function accuracyPage() {
  const d = await load(api("/api/benchmark"));
  const r = d.rules_all;
  const pct = (x) => `${Math.round(x * 1000) / 10}%`;
  const groupRows = Object.entries(r.groups).map(([k, v]) => `<tr><td>${esc(k.replace("lang:", "Language: ").replace("form:", "Written as: ").replace("ai_only", "Meaning-based (AI-only)").replace("rule_detectable", "Rule-detectable"))}</td><td>${v.n}</td><td>${pct(v.precision)}</td><td>${pct(v.recall)}</td></tr>`).join("");
  const ai = d.ai_run;
  const aiBlock = ai && !ai.error ? `<div class="card"><h3>Rules vs rules + AI · hard subset (${ai.subset_size} samples, ${esc(ai.model)})</h3>
      <p class="small muted" style="margin-top:0">Non-English, written-in-words, paraphrased and meaning-based samples, plus clean ones (to catch false alarms). Run on ${fmtDate(d.ai_run_at)}${ai.models_used ? ` · answers from ${Object.entries(ai.models_used).map(([m, n]) => `${esc(m)} (${n})`).join(", ")}` : ""}${ai.ai_errors ? ` · ${ai.ai_errors} AI call(s) failed and counted as misses` : ""}.</p>
      <table class="t"><thead><tr><th></th><th>Precision</th><th>Recall</th><th>F1</th><th>Missed</th><th>False alarms</th></tr></thead><tbody>
      <tr><td>Rules only</td><td>${pct(ai.rules_only.precision)}</td><td>${pct(ai.rules_only.recall)}</td><td>${ai.rules_only.f1}</td><td>${ai.rules_only.false_negatives}</td><td>${ai.rules_only.false_positives}</td></tr>
      <tr><td><b>Rules + AI</b></td><td><b>${pct(ai.rules_plus_ai.precision)}</b></td><td><b>${pct(ai.rules_plus_ai.recall)}</b></td><td><b>${ai.rules_plus_ai.f1}</b></td><td>${ai.rules_plus_ai.false_negatives}</td><td>${ai.rules_plus_ai.false_positives}</td></tr></tbody></table>
      <p class="small">Meaning-based samples (AI-only): rules recall ${pct((ai.rules_only.groups.ai_only || {}).recall || 0)} → rules + AI recall <b>${pct((ai.rules_plus_ai.groups.ai_only || {}).recall || 0)}</b>.</p></div>`
    : `<div class="card"><h3>Rules vs rules + AI</h3><p class="small muted">${d.ai_running
        ? `The AI comparison is running${d.progress ? ` · ${d.progress.done} / ${d.progress.total} samples` : ""}. This page refreshes by itself.`
        : "The AI comparison has not been run on this server yet."}</p>
        ${!d.ai_running && d.ai_available && S.role === "admin" ? `<button class="btn" id="bench-run">Run the AI comparison (about 30 min)</button>` : ""}
        ${!d.ai_running && S.role !== "admin" ? `<p class="small muted">A Brand Admin can start it.</p>` : ""}</div>`;
  $("#app").innerHTML = `<div class="page-h"><div><h2>Accuracy</h2><p>How often BrandProof is right, measured on a labelled set of ${r.samples} ad samples in English, Hindi and Hinglish.</p></div></div>
    <div class="grid g4">
      <div class="card kpi"><b>${r.samples}</b><span>labelled samples</span></div>
      <div class="card kpi"><b>${pct(r.precision)}</b><span>precision (flags that were right) · rules only</span></div>
      <div class="card kpi"><b>${pct(r.recall)}</b><span>recall (issues caught) · rules only</span></div>
      <div class="card kpi"><b>${r.false_positives}</b><span>false alarms on ${r.samples} samples</span></div>
    </div>
    <div class="grid g2" style="margin-top:16px">
      <div class="card"><h3>By language and how the claim is written</h3><table class="t"><thead><tr><th>Group</th><th>n</th><th>Precision</th><th>Recall</th></tr></thead><tbody>${groupRows}</tbody></table></div>
      ${aiBlock}
    </div>
    <div class="card" style="margin-top:16px"><h3>Where the rules miss (${r.mismatches.length})</h3>
      <p class="small muted" style="margin-top:0">Shown openly so you know what to expect. Most are meaning-based claims that only the AI layer can judge.</p>
      <table class="t small"><thead><tr><th>Sample</th><th>Expected</th><th>Rules found</th></tr></thead><tbody>${r.mismatches.slice(0, 40).map((m) => `<tr><td>${esc(m.text)} ${m.ai_only ? '<span class="tag ai">AI-only</span>' : ""}</td><td class="mono">${esc(m.expected.join(", ") || "—")}</td><td class="mono">${esc(m.got.join(", ") || "—")}</td></tr>`).join("")}</tbody></table></div>
    <p class="tiny muted">The samples are written by our team from templates for the fictional ABC Electronics brand, so treat these numbers as a regression check, not a general accuracy claim. Source: benchmark/samples.json in the repository.</p>`;
  const b = $("#bench-run");
  if (b) b.onclick = (ev) => once(ev.currentTarget, "Starting…", async () => {
    const res = await api("/api/benchmark/run", { method: "POST" });
    toast(res.message || `Started on ${res.subset} samples`, !res.started);
    route();
  });
  if (d.ai_running) setTimeout(() => { if (location.hash.startsWith("#/accuracy")) route(); }, 15000);
}

/* ---------------------------------------------------------------- trust & feedback */
async function trustPage() {
  const [a, fb] = await load(Promise.all([api("/api/about", { allow401: true }), api("/api/feedback", { allow401: true })]));
  $("#app").innerHTML = `<div class="page-h"><div><h2>Trust, data &amp; feedback</h2><p>How BrandProof uses AI, what leaves the server, and what it is built with.</p></div></div>
  <div class="grid g2">
    <div class="card stack"><h3>🤖 How AI is used</h3>
      <div class="small"><b>Provider:</b> ${esc(a.ai.provider)} · <b>Model:</b> ${esc(a.ai.model)}</div>
      <div class="small"><b>AI is used only for:</b> ${a.ai.used_for.map(esc).join(", ")}.</div>
      <div class="small"><b>Checked in code (no AI, always works):</b> ${a.deterministic_checks.map(esc).join(", ")}.</div>
      <div class="notice ai small"><b>Evidence verifier:</b> an AI finding is kept only if it quotes text that really exists in the draft and cites a real rule ID from Brand Memory. AI-extracted brand facts are kept only if the value appears in the document. Everything else is dropped and counted on screen.</div>
      <div class="notice small"><b>Human control:</b> nothing is auto-fixed or auto-published. Creators accept fixes one by one. Only Compliance can dismiss a high-severity finding. Only a Reviewer can approve, and never their own submission in a team.</div></div>
    <div class="card stack"><h3>🔒 Data handling</h3>
      <ul class="small" style="margin:0;padding-left:18px">
        <li>Every workspace's data is separated by workspace ID on every query. Demo sandboxes are private per visitor and deleted after 48 hours of inactivity.</li>
        <li>Passwords are hashed with scrypt; sessions are HTTP-only cookies.</li>
        <li>Emails, phone numbers and confidential terms are masked before any AI call. <b>Confidential mode</b> sends nothing to any AI service.</li>
        <li>AI results are cached by content hash, so the same content is never sent twice.</li>
        <li>Storage: ${esc(a.storage)}. Every decision is in the audit trail; approvals are sealed in hash-chained Proof Certificates.</li></ul>
      <h3 style="margin-top:6px">🧰 Built with</h3>
      <table class="t small"><tbody>
        <tr><td>Python 3.12 · FastAPI · Uvicorn · Pydantic</td><td class="muted">API &amp; validation (MIT/BSD)</td></tr>
        <tr><td>PostgreSQL (psycopg 3) / SQLite</td><td class="muted">storage</td></tr>
        <tr><td>pypdf · python-docx</td><td class="muted">PDF/DOCX text extraction (BSD/MIT)</td></tr>
        <tr><td>Pillow · NumPy</td><td class="muted">colour ΔE, per-text contrast, logo template matching (MIT-CMU/BSD)</td></tr>
        <tr><td>httpx → Google Gemini API</td><td class="muted">optional AI (BSD · Google API terms)</td></tr>
        <tr><td>Vanilla JS + CSS, Google Fonts (Inter, Space Grotesk, JetBrains Mono)</td><td class="muted">frontend (OFL fonts)</td></tr>
        <tr><td>Render</td><td class="muted">hosting</td></tr></tbody></table>
      <div class="small">API docs: <a href="/docs" target="_blank" rel="noopener">/docs</a> (OpenAPI) · <a href="#/accuracy">Accuracy report</a></div></div>
  </div>
  <div class="grid g2" style="margin-top:16px">
    <form class="card stack" id="fb-form"><h3>💬 Give feedback (user testing)</h3>
      <div class="grid g2" style="gap:8px"><input class="inp" id="fb-name" maxlength="80" placeholder="Your name" aria-label="Your name" required><input class="inp" id="fb-role" maxlength="80" placeholder="Role (student, marketer, designer…)" aria-label="Your role"></div>
      ${[["ease", "How easy was it to use?"], ["trust", "How much do you trust the findings?"], ["useful", "How useful would this be for a real team?"]].map(([k, l]) => `<div class="row between small"><label for="fb-${k}">${l}</label><select class="inp" id="fb-${k}" style="width:90px">${[5, 4, 3, 2, 1].map((n) => `<option>${n}</option>`).join("")}</select></div>`).join("")}
      <textarea class="inp" id="fb-liked" maxlength="1000" style="min-height:60px" placeholder="What worked well?" aria-label="What worked well"></textarea>
      <textarea class="inp" id="fb-improve" maxlength="1000" style="min-height:60px" placeholder="What should we improve?" aria-label="What to improve"></textarea>
      <button class="btn pri" id="fb-send">Send feedback</button></form>
    <div class="card"><h3>Feedback received (${fb.count})</h3>
      ${fb.count ? `<div class="row small" style="margin-bottom:8px"><span class="tag ok" style="text-transform:none">Ease ${fb.average.ease}/5</span><span class="tag ok" style="text-transform:none">Trust ${fb.average.trust}/5</span><span class="tag ok" style="text-transform:none">Useful ${fb.average.useful}/5</span></div>` : ""}
      ${fb.items.map((f) => `<div class="small" style="border-top:1px solid var(--line);padding:7px 0"><b>${esc(f.name)}</b> <span class="muted">${esc(f.role)} · ${f.ease}/${f.trust}/${f.useful}</span>${f.liked ? `<div>👍 ${esc(f.liked)}</div>` : ""}${f.improve ? `<div>🔧 ${esc(f.improve)}</div>` : ""}</div>`).join("") || '<p class="small muted">No feedback yet.</p>'}</div>
  </div>`;
  $("#fb-form").onsubmit = (e) => {
    e.preventDefault();
    const name = $("#fb-name").value.trim(); if (!name) return toast("Please add your name", true);
    once($("#fb-send"), "Sending…", async () => { await api("/api/feedback", { method: "POST", allow401: true, body: { name, role: $("#fb-role").value, ease: +$("#fb-ease").value, trust: +$("#fb-trust").value, useful: +$("#fb-useful").value, liked: $("#fb-liked").value, improve: $("#fb-improve").value } }); toast("Thank you! Feedback saved."); trustPage(); });
  };
}

/* ---------------------------------------------------------------- demo guide */
const GUIDE = [
  { id: "check", t: "Check a risky AI-written ad", go: () => { CK.reset(SAMPLES.risky); S.autorun = true; setRole("creator", true); location.hash = "#/check"; route(); } },
  { id: "fix", t: "Apply the suggested fixes", go: () => { location.hash = "#/check"; toast("Click “Apply fixes” under Findings."); } },
  { id: "submit", t: "Submit it for review", go: () => { location.hash = "#/check"; toast("Click “Submit … version” at the bottom of the results."); } },
  { id: "compliance", t: "As Compliance, clear the claims", go: () => openNext("compliance_review", "compliance"), opt: true },
  { id: "approve", t: "As Reviewer, approve → Proof Certificate", go: () => openNext("in_review", "reviewer") },
  { id: "image", t: "Check a poster: text in image + logo", go: () => { setRole("creator", true); location.hash = "#/check"; route().then(() => { const b = $('[data-img="offbrand"]'); if (b) b.click(); }); } },
  { id: "hindi", t: "Check Hinglish / Hindi copy", go: () => { CK.reset(SAMPLES.hinglish); S.autorun = true; setRole("creator", true); location.hash = "#/check"; route(); } },
  { id: "impact", t: "As Brand Admin, preview a rule change", go: () => { setRole("admin", true); location.hash = "#/brand"; toast("Change a fact (e.g. Maximum discount → 15) and click “Preview impact”."); } },
  { id: "team", t: "See how real teams sign in", go: () => { location.hash = "#/team"; } },
];
async function openNext(status, role) {
  setRole(role, true); renderHeader();
  try {
    const subs = await api("/api/submissions");
    const s = subs.find((x) => x.status === status && !x.demo) || subs.find((x) => x.status === status);
    if (s) { location.hash = `#/queue/${s.id}`; return; }
  } catch (e) {}
  location.hash = "#/queue"; toast(`Nothing is waiting for ${ROLE_LABEL[role]} yet.`);
}
function guideMark(id) {
  const g = store.get("guide", null); if (!g) return;
  if (!g.done[id]) { g.done[id] = true; if (id === "approve") g.done.compliance = true; store.set("guide", g); renderGuide(); }
}
function renderGuide() {
  let el = $("#guide");
  const g = store.get("guide", null);
  if (!S.me || !S.me.demo || !g) { if (el) el.remove(); document.body.classList.remove("with-guide"); return; }
  if (g.open === undefined) g.open = window.innerWidth > 960;
  document.body.classList.toggle("with-guide", !!g.open);
  if (!el) { el = document.createElement("aside"); el.id = "guide"; el.setAttribute("aria-label", "Demo guide"); document.body.appendChild(el); }
  const done = GUIDE.filter((s) => g.done[s.id]).length;
  el.className = "guide" + (g.open ? "" : " closed");
  el.innerHTML = g.open ? `<div class="row between"><b>Demo guide · ${done}/${GUIDE.length}</b><button class="btn sm ghost" id="g-min" aria-label="Minimise guide">–</button></div>
    <div class="gbar"><i style="width:${(100 * done) / GUIDE.length}%"></i></div>
    <ol>${GUIDE.map((s) => `<li class="${g.done[s.id] ? "done" : ""}"><span>${g.done[s.id] ? "✓" : "○"} ${esc(s.t)}${s.opt ? ' <span class="muted tiny">(if needed)</span>' : ""}</span>${g.done[s.id] ? "" : `<button class="btn sm" data-g="${s.id}">Go</button>`}</li>`).join("")}</ol>
    <div class="tiny muted">Everything happens in your private sandbox.</div>`
    : `<button class="btn sm pri" id="g-open">Demo guide · ${done}/${GUIDE.length}</button>`;
  const mn = $("#g-min"); if (mn) mn.onclick = () => { g.open = false; store.set("guide", g); renderGuide(); };
  const op = $("#g-open"); if (op) op.onclick = () => { g.open = true; store.set("guide", g); renderGuide(); };
  $$("[data-g]", el).forEach((b) => (b.onclick = () => GUIDE.find((s) => s.id === b.dataset.g).go()));
}

/* ---------------------------------------------------------------- router & boot */
const PUBLIC = { "": landing, signin: signinPage, signup: signupPage, join: joinPage, trust: trustPage };
const PRIVATE = { home, check, queue, brand: brandPage, insights: insightsPage, certificates: certPage, team: teamPage, accuracy: accuracyPage };
async function route() {
  const h = location.hash.replace(/^#\/?/, "");
  const [name, arg] = h.split("/");
  $$("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.r === name));
  let fn = PUBLIC[name] || PRIVATE[name] || landing;
  if (PRIVATE[name] && !S.me) { fn = landing; }
  if (name === "" && S.me) fn = home;
  S.seq++;
  window.scrollTo(0, 0);
  try { await fn(arg); }
  catch (e) { if (e instanceof Stale) return; $("#app").innerHTML = `<div class="card empty"><b>Something went wrong.</b><br>${esc(e.message)}<br><br><button class="btn" onclick="route()">Try again</button></div>`; }
  renderGuide();
}
window.addEventListener("hashchange", route);
window.addEventListener("unhandledrejection", (e) => { if (e.reason && e.reason.message) toast(e.reason.message, true); });

(async function boot() {
  const slow = setTimeout(() => { $("#app").innerHTML = `<div class="card empty"><span class="spin dark"></span> Waking up the server… free hosting sleeps when idle, this takes up to a minute the first time.</div>`; }, 2500);
  try { S.health = await api("/api/health", { allow401: true, timeout: 120000 }); } catch (e) {}
  clearTimeout(slow);
  const p = $("#aipill");
  if (S.health) { p.textContent = S.health.ai ? `AI: ${S.health.model}` : "AI: off (rules only)"; p.classList.toggle("on", !!S.health.ai); }
  await loadMe();
  refreshCounts();
  route();
})();
