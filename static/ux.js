/* BrandProof v3.2 — interaction layer: page icons, count-up numbers, animated risk ring,
   draft ↔ finding hover linking, Ctrl/⌘+K command palette. Purely additive: it never changes data or the workflow. */
(function () {
  const reduce = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  const routeName = () => location.hash.replace(/^#\/?/, "").split("/")[0];

  /* ---------- count-up for numbers in stat tiles and the risk ring ---------- */
  function countUp(el) {
    if (el.dataset.cu || reduce()) return;
    el.dataset.cu = "1";
    const src = el.textContent;
    const parts = src.split(/(\d[\d,]*\.?\d*)/);
    const nums = parts.map((p, i) => (i % 2 ? parseFloat(p.replace(/,/g, "")) : null));
    if (!nums.some((n) => n != null && n > 1)) return;
    const dec = parts.map((p, i) => (i % 2 && p.includes(".") ? p.split(".")[1].length : 0));
    const t0 = performance.now(), dur = 700;
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = parts.map((p, i) => (i % 2 ? (nums[i] * e).toFixed(dec[i]).replace(/\B(?=(\d{3})+(?!\d))/g, p.includes(",") ? "," : "") : p)).join("");
      if (k < 1) requestAnimationFrame(step); else el.textContent = src;
    };
    requestAnimationFrame(step);
  }

  /* ---------- risk ring fills from empty ---------- */
  function animateGauge(g) {
    if (g.dataset.anim || reduce()) return;
    g.dataset.anim = "1";
    const ring = g.querySelectorAll("circle")[1];
    if (!ring) return;
    const target = ring.getAttribute("stroke-dashoffset"), full = ring.getAttribute("stroke-dasharray");
    ring.style.transition = "none";
    ring.setAttribute("stroke-dashoffset", full);
    ring.getBoundingClientRect();
    ring.style.transition = "stroke-dashoffset .9s cubic-bezier(.2,.8,.2,1)";
    requestAnimationFrame(() => ring.setAttribute("stroke-dashoffset", target));
    const b = g.querySelector(".v b"); if (b) countUp(b);
  }

  /* ---------- page title icon, taken from the sidebar ---------- */
  function pageIcon() {
    const h = document.querySelector("#app .page-h h2");
    if (!h || h.querySelector(".pg-ic")) return;
    const name = routeName() || "home";
    const src = document.querySelector(`#nav a[data-r="${name}"] svg`);
    if (!src) return;
    const wrap = document.createElement("span");
    wrap.className = "pg-ic"; wrap.setAttribute("aria-hidden", "true");
    wrap.appendChild(src.cloneNode(true));
    h.prepend(wrap);
  }

  function enhance() {
    pageIcon();
    document.querySelectorAll("#app .kpi b, #app .nums b").forEach(countUp);
    document.querySelectorAll("#app .gauge").forEach(animateGauge);
  }
  let pending = 0;
  const mo = new MutationObserver(() => { if (!pending) pending = requestAnimationFrame(() => { pending = 0; enhance(); }); });
  addEventListener("DOMContentLoaded", () => { const app = document.getElementById("app"); if (app) mo.observe(app, { childList: true, subtree: true }); });

  /* ---------- hovering a highlight lights up its finding, and the other way round ---------- */
  let lit = [];
  function light(n, scope) {
    lit.forEach((e) => e.classList.remove("lit")); lit = [];
    if (!n) return;
    const root = scope || document;
    lit = [...root.querySelectorAll(`.hl[data-n="${n}"], .ins[data-n="${n}"], .obox[data-n="${n}"], .fcard[data-n="${n}"]`)];
    lit.forEach((e) => e.classList.add("lit"));
  }
  document.addEventListener("mouseover", (e) => {
    const t = e.target.closest && e.target.closest(".hl[data-n], .ins[data-n], .obox[data-n], .fcard[data-n]");
    if (!t) { if (lit.length) light(null); return; }
    if (!lit.includes(t)) light(t.dataset.n, document.getElementById("app"));
  });

  /* ---------- command palette ---------- */
  const L = (k) => (typeof ROLE_LABEL !== "undefined" ? ROLE_LABEL[k] : k);
  function waitClick(hash, sel) {
    if (location.hash !== hash) location.hash = hash; else route();
    let tries = 0;
    const iv = setInterval(() => { const b = document.querySelector(sel); if (b) { clearInterval(iv); b.click(); } else if (++tries > 50) clearInterval(iv); }, 100);
  }
  function actions() {
    const go = (h, t, hint) => ({ t, hint: hint || "Open page", run: () => { location.hash = h; } });
    const a = [
      go("#/home", "Dashboard"), go("#/check", "Check content", "Paste text or upload a poster"), go("#/queue", "Review queue"),
      go("#/brand", "Brand Memory", "Facts, rules, logo, impact preview"), go("#/insights", "Insights"), go("#/certificates", "Proof Certificates"),
      go("#/team", "Team"), go("#/accuracy", "Accuracy benchmark"), go("#/trust", "Trust, data & feedback"), go("#/how", "How it works", "Roles, pages, judge path"),
      go("#/", "Main page", "Landing page"),
      { t: "Check the risky AI-written ad", hint: "Sample", run: () => waitClick("#/check", '[data-s="risky"]') },
      { t: "Check Hinglish copy", hint: "Sample", run: () => waitClick("#/check", '[data-s="hinglish"]') },
      { t: "Check Hindi copy (हिंदी)", hint: "Sample", run: () => waitClick("#/check", '[data-s="hindi"]') },
      { t: "Check an outdated price", hint: "Sample", run: () => waitClick("#/check", '[data-s="outdated"]') },
      { t: "Check a confidential leak", hint: "Sample", run: () => waitClick("#/check", '[data-s="confidential"]') },
      { t: "Check the off-brand poster", hint: "Sample · text in image + logo", run: () => waitClick("#/check", '[data-img="offbrand"]') },
      { t: "Check the on-brand poster", hint: "Sample · logo found", run: () => waitClick("#/check", '[data-img="onbrand"]') },
    ];
    if (S.me) (S.me.roles || []).forEach((r) => a.push({ t: `Act as ${L(r)}`, hint: "Switch role", run: () => { setRole(r); renderHeader(); route(); } }));
    return a;
  }
  let pal = null, sel = 0, list = [];
  function render(q) {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    list = actions().filter((a) => words.every((w) => (a.t + " " + a.hint).toLowerCase().includes(w)))
      .map((a, i) => ({ a, i, s: words.filter((w) => a.t.toLowerCase().includes(w)).length })).sort((x, y) => y.s - x.s || x.i - y.i).map((x) => x.a);
    sel = Math.min(sel, Math.max(0, list.length - 1));
    pal.querySelector("ul").innerHTML = list.map((a, i) => `<li role="option" aria-selected="${i === sel}" data-i="${i}" class="${i === sel ? "on" : ""}"><span>${esc(a.t)}</span><small>${esc(a.hint)}</small></li>`).join("")
      || `<li class="none">Nothing matches “${esc(q)}”. Try “poster”, “queue” or “reviewer”.</li>`;
    const on = pal.querySelector("li.on"); if (on) on.scrollIntoView({ block: "nearest" });
  }
  function close() { if (pal) { pal.remove(); pal = null; } }
  function open() {
    if (!S.me) return;
    if (pal) return close();
    pal = document.createElement("div");
    pal.className = "cmdk"; pal.setAttribute("role", "dialog"); pal.setAttribute("aria-label", "Jump to a page or action");
    pal.innerHTML = `<div class="cmdk-box"><input type="text" placeholder="Jump to a page, run a sample or switch role…" aria-label="Search pages and actions">
      <ul role="listbox"></ul><div class="cmdk-foot"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>Esc</kbd> close</span></div></div>`;
    document.body.appendChild(pal);
    const inp = pal.querySelector("input");
    sel = 0; render("");
    inp.focus();
    inp.oninput = () => { sel = 0; render(inp.value); };
    inp.onkeydown = (e) => {
      if (e.key === "ArrowDown") { sel = Math.min(list.length - 1, sel + 1); render(inp.value); e.preventDefault(); }
      else if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); render(inp.value); e.preventDefault(); }
      else if (e.key === "Enter" && list[sel]) { const a = list[sel]; close(); a.run(); }
      else if (e.key === "Escape") close();
    };
    pal.onclick = (e) => { const li = e.target.closest("li[data-i]"); if (li) { const a = list[+li.dataset.i]; close(); a.run(); } else if (e.target === pal) close(); };
  }
  window.openPalette = open;
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); open(); }
    else if (e.key === "Escape" && pal) close();
  });
})();
