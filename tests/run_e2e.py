"""End-to-end browser test (Playwright). Start tests/fake_ai_server.py first, then: python tests/run_e2e.py"""
from playwright.sync_api import sync_playwright
import os, sys
B=os.environ.get("BASE_URL","http://127.0.0.1:8010"); O=os.environ.get("SHOTS","/tmp/brandproof_shots/"); os.makedirs(O, exist_ok=True)
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
errs=[]
def log(*a): print(*a, flush=True)
with sync_playwright() as p:
    br=p.chromium.launch()
    ctx=br.new_context(viewport={"width":1360,"height":900}, device_scale_factor=1)
    pg=ctx.new_page(); pg.set_default_timeout(20000)
    pg.on("pageerror", lambda e: errs.append("pageerror: "+str(e)))
    pg.on("console", lambda m: m.type=="error" and "fonts.g" not in m.text and errs.append("console: "+m.text))
    pg.goto(B+"/#/"); pg.wait_for_selector("#go-demo"); pg.screenshot(path=O+"01_landing.png")
    pg.click("#go-demo"); pg.wait_for_selector(".fcard"); pg.wait_for_timeout(400)
    log("risk", pg.inner_text(".gauge .v b"), "findings", len(pg.query_selector_all(".fcard")), "guide", pg.inner_text("#guide b"))
    pg.screenshot(path=O+"02_check.png", full_page=True)
    pg.click("#c-apply"); pg.wait_for_selector(".diff"); pg.wait_for_timeout(300)
    # double click submit
    pg.click("#c-submit"); 
    pg.wait_for_selector(".stepper"); pg.wait_for_timeout(500)
    log("status after submit", pg.inner_text(".page-h .status"), pg.inner_text(".nextstep"))
    pg.click("[data-switch]"); pg.wait_for_timeout(600)
    log("role now", pg.eval_on_selector("#role","e=>e.value"))
    btn=pg.query_selector("[data-a=approve]"); log("approve btn", bool(btn))
    btn.click(); pg.wait_for_selector(".cert"); pg.wait_for_timeout(400)
    log("status", pg.inner_text(".page-h .status")); pg.screenshot(path=O+"03_approved.png", full_page=True)
    # refresh resilience
    pg.reload(); pg.wait_for_selector(".cert"); log("after reload ok", pg.inner_text(".page-h .status"))
    # approve twice via API
    sid=pg.url.split("/")[-1]
    r=pg.evaluate(f"""fetch('/api/submissions/{sid}/action',{{method:'POST',headers:{{'Content-Type':'application/json','X-Acting-Role':'reviewer'}},body:JSON.stringify({{action:'approve'}})}}).then(r=>r.status)""")
    log("approve twice ->", r)
    # risky submit w/o fixes -> compliance
    pg.select_option("#role","creator"); pg.wait_for_timeout(300)
    pg.goto(B+"/#/check/hinglish"); pg.wait_for_selector(".fcard"); pg.wait_for_timeout(300)
    log("hinglish findings", [e.inner_text() for e in pg.query_selector_all(".fcard .rid")])
    pg.screenshot(path=O+"04_hinglish.png", full_page=True)
    pg.click("#c-submit"); pg.wait_for_selector(".stepper"); pg.wait_for_timeout(400)
    log("status", pg.inner_text(".page-h .status"))
    pg.click("[data-switch]"); pg.wait_for_timeout(500)
    # dismiss all highs via chips
    for i in range(6):
        d=pg.query_selector(".fcard.high [data-dismiss]")
        if not d: break
        d.click(); pg.click("[data-chip]"); pg.click("[data-ok]"); pg.wait_for_timeout(500)
    pg.click("[data-a=clear_claims]"); pg.wait_for_timeout(600); log("after clear", pg.inner_text(".page-h .status"))
    pg.click("[data-switch]"); pg.wait_for_timeout(400)
    pg.click("[data-a=request_changes]"); pg.click("[data-chip]"); pg.click("[data-ok]"); pg.wait_for_timeout(600)
    log("after request changes", pg.inner_text(".page-h .status"))
    pg.click("[data-switch]"); pg.wait_for_timeout(400)
    pg.click("#s-autofix"); pg.wait_for_timeout(500); pg.click("#s-resub"); pg.wait_for_timeout(800)
    log("after resubmit", pg.inner_text(".page-h .status"), pg.inner_text(".vtabs"))
    # image
    pg.goto(B+"/#/check"); pg.wait_for_selector("[data-img=offbrand]"); pg.click("[data-img=offbrand]"); pg.wait_for_selector(".imgwrap"); pg.wait_for_timeout(800)
    log("image findings", [e.inner_text() for e in pg.query_selector_all(".fcard .rid")])
    pg.screenshot(path=O+"05_image.png", full_page=True)
    # brand impact preview
    pg.select_option("#role","admin"); pg.wait_for_timeout(300)
    pg.goto(B+"/#/brand"); pg.wait_for_selector("#nf-key")
    pg.select_option("#nf-key","max_discount"); pg.fill("#nf-val","10"); pg.click("#nf-prev"); pg.wait_for_selector(".impact"); pg.wait_for_timeout(300)
    log("impact", pg.inner_text(".impact .row"))
    pg.screenshot(path=O+"06_impact.png", full_page=True)
    pg.click("#nf-out [data-apply]"); pg.wait_for_timeout(800)
    pg.set_input_files("#b-file",os.path.join(ROOT,"static","samples","ABC_Brand_Update_Nov2026.docx")); pg.click("#b-imp"); pg.wait_for_timeout(1000)
    log("cands", len(pg.query_selector_all("[data-cand][data-d=approve]")))
    pg.goto(B+"/#/insights"); pg.wait_for_timeout(800); pg.click("[data-sg]"); pg.wait_for_timeout(600); pg.screenshot(path=O+"07_insights.png", full_page=True)
    pg.goto(B+"/#/accuracy"); pg.wait_for_timeout(1500); pg.screenshot(path=O+"08_accuracy.png", full_page=True)
    pg.goto(B+"/#/certificates"); pg.wait_for_timeout(800); pg.screenshot(path=O+"09_certs.png")
    pg.goto(B+"/#/team"); pg.wait_for_timeout(600)
    log("guide", pg.inner_text("#guide b"))
    # empty input
    pg.goto(B+"/#/check"); pg.wait_for_selector("#c-clear"); pg.click("#c-clear"); pg.wait_for_timeout(200); pg.click("#c-run"); pg.wait_for_timeout(300); log("empty toast", pg.inner_text(".toast"))
    # ---- team flow
    c2=br.new_context(viewport={"width":1360,"height":900}); a=c2.new_page(); a.set_default_timeout(20000)
    a.on("pageerror", lambda e: errs.append("A pageerror: "+str(e)))
    a.goto(B+"/#/signup"); a.wait_for_selector("#nm")
    a.fill("#nm","Ayush Kumar"); a.fill("#org","Bug Hunters Marketing"); a.fill("#em","ayush@example.com"); a.fill("#pw","short"); a.click("#go"); a.wait_for_timeout(500); log("short pw", a.inner_text(".toast"))
    a.fill("#pw","password123"); a.click("#go"); a.wait_for_timeout(1200); log("signed up", a.inner_text("#ws"))
    a.goto(B+"/#/team"); a.wait_for_selector("#inv-go"); a.uncheck(".inv-role[value=creator]"); a.check(".inv-role[value=reviewer]"); a.click("#inv-go"); a.wait_for_selector("#inv-url")
    url=a.input_value("#inv-url"); log("invite", url)
    a.screenshot(path=O+"10_team.png", full_page=True)
    # admin submits as creator
    a.select_option("#role","creator"); a.goto(B+"/#/check/clean"); a.wait_for_selector(".fcard, #c-results .notice.ok"); a.wait_for_timeout(300); a.click("#c-submit"); a.wait_for_selector(".stepper"); a.wait_for_timeout(300)
    sub_url=a.url
    c3=br.new_context(viewport={"width":1360,"height":900}); r_=c3.new_page(); r_.set_default_timeout(20000)
    r_.goto(url.replace("http://127.0.0.1:8010",B)); r_.wait_for_selector("#nm"); r_.fill("#nm","Kanika Reviewer"); r_.fill("#em","kanika@example.com"); r_.fill("#pw","password123"); r_.click("#go"); r_.wait_for_timeout(1200)
    log("joined", r_.inner_text("#ws"), r_.eval_on_selector("#role","e=>[...e.options].map(o=>o.value)"))
    # four-eyes: admin tries to approve own
    a.select_option("#role","reviewer"); a.wait_for_timeout(300); a.goto(sub_url); a.wait_for_selector("[data-a=approve]"); a.click("[data-a=approve]"); a.wait_for_timeout(600); log("own approve", a.inner_text(".toast"))
    r_.goto(sub_url.replace("http://127.0.0.1:8010",B)); r_.wait_for_selector("[data-a=approve]"); r_.click("[data-a=approve]"); r_.wait_for_selector(".cert"); log("cert identity", r_.inner_text(".cert .small.muted"))
    r_.screenshot(path=O+"11_verified_cert.png", full_page=True)
    # isolation: reviewer cannot see demo submission id 1
    st=r_.evaluate("fetch('/api/submissions/1').then(r=>r.status)"); log("cross-org access", st)
    # logout/login
    a.click("#signout"); a.wait_for_timeout(500); a.goto(B+"/#/signin"); a.fill("#em","ayush@example.com"); a.fill("#pw","wrongpass1"); a.click("#go"); a.wait_for_timeout(600); log("bad login", a.inner_text(".toast"))
    a.fill("#pw","password123"); a.click("#go"); a.wait_for_timeout(800); log("login", a.inner_text("#ws"))
    # mobile
    m=br.new_context(viewport={"width":390,"height":844}); mp=m.new_page(); mp.goto(B+"/#/"); mp.wait_for_selector("#go-demo"); mp.click("#go-demo"); mp.wait_for_selector(".fcard"); mp.wait_for_timeout(500); mp.screenshot(path=O+"12_mobile.png")
    br.close()
print("ERRORS:", errs)
