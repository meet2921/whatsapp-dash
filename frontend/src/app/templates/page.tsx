"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/AppLayout";
import { templates as templatesApi, waba as wabaApi } from "@/lib/api";
import type { Template, WabaAccount } from "@/types/api";

// ── Template Library data ──────────────────────────────────────────────────────
interface LibBtn { type: "URL" | "PHONE_NUMBER" | "QUICK_REPLY"; text: string; url?: string; phone?: string }
interface LibTemplate {
  id: string; name: string; displayName: string;
  category: "UTILITY" | "MARKETING" | "AUTHENTICATION"; subcategory: string;
  header?: string; body: string; footer?: string; buttons?: LibBtn[];
  varNames: string[]; // human labels for {{1}}, {{2}} …
}

const LIBRARY: LibTemplate[] = [
  // UTILITY — Account updates
  { id:"acct_created", name:"account_creation_confirmation", displayName:"Account creation confirmation",
    category:"UTILITY", subcategory:"Account updates",
    body:"Hi {{1}},\n\nYour new account has been created successfully.\n\nPlease verify {{2}} to complete your profile.",
    buttons:[{type:"URL",text:"Verify account",url:"https://www.example.com"}],
    varNames:["Customer name","Verification link"] },
  { id:"address_upd", name:"address_update", displayName:"Address update",
    category:"UTILITY", subcategory:"Account updates",
    body:"Hi {{1}}, your delivery address has been successfully updated to {{2}}. Contact {{3}} for any inquiries.",
    varNames:["Customer name","New address","Support contact"] },
  // UTILITY — Order management
  { id:"order_conf", name:"order_confirmation", displayName:"Order confirmation",
    category:"UTILITY", subcategory:"Order management",
    header:"Your order is confirmed!",
    body:"Hi {{1}},\n\nThank you for your order #{{2}}!\n\nTotal: {{3}}\nEstimated delivery: {{4}}",
    footer:"Reply TRACK to track your order",
    varNames:["Customer name","Order ID","Amount","Delivery date"] },
  { id:"order_cancel", name:"order_cancelled", displayName:"Order cancelled",
    category:"UTILITY", subcategory:"Order management",
    body:"Hi {{1}},\n\nWe're sorry, your order #{{2}} has been cancelled.\n\nRefund of {{3}} will be processed within 5-7 business days.",
    varNames:["Customer name","Order ID","Refund amount"] },
  { id:"order_update", name:"order_status_update", displayName:"Order status update",
    category:"UTILITY", subcategory:"Order management",
    body:"Hi {{1}}, your order #{{2}} status has been updated to: *{{3}}*.\n\nExpected completion: {{4}}.",
    varNames:["Customer name","Order ID","Status","Date"] },
  // UTILITY — Shipping updates
  { id:"shipping_upd", name:"shipping_update", displayName:"Shipping update",
    category:"UTILITY", subcategory:"Shipping updates",
    body:"Great news, {{1}}! 📦\n\nYour order #{{2}} has been shipped.\nTracking ID: {{3}}\nExpected delivery: {{4}}",
    buttons:[{type:"URL",text:"Track order",url:"https://track.example.com"}],
    varNames:["Customer name","Order ID","Tracking ID","Delivery date"] },
  { id:"delivered", name:"delivery_confirmation", displayName:"Delivery confirmation",
    category:"UTILITY", subcategory:"Shipping updates",
    body:"Hi {{1}}, your package has been delivered to {{2}}. 🎉\n\nThank you for shopping with us!",
    varNames:["Customer name","Delivery address"] },
  // UTILITY — Appointment management
  { id:"appt_reminder", name:"appointment_reminder", displayName:"Appointment reminder",
    category:"UTILITY", subcategory:"Appointment management",
    body:"Hi {{1}},\n\nThis is a reminder for your appointment:\n📅 Date: {{2}}\n⏰ Time: {{3}}\n📍 Location: {{4}}",
    buttons:[{type:"QUICK_REPLY",text:"Confirm"},{type:"QUICK_REPLY",text:"Reschedule"}],
    varNames:["Customer name","Date","Time","Location"] },
  { id:"appt_cancel", name:"appointment_cancelled", displayName:"Appointment cancelled",
    category:"UTILITY", subcategory:"Appointment management",
    body:"Hi {{1}},\n\nYour appointment on {{2}} has been cancelled.\n\nWe hope to see you another time.",
    varNames:["Customer name","Appointment date"] },
  // UTILITY — Payment updates
  { id:"pay_conf", name:"payment_confirmation", displayName:"Payment confirmation",
    category:"UTILITY", subcategory:"Payment updates",
    body:"Hi {{1}}, ✅\n\nWe've received your payment of {{2}} for {{3}}.\n\nTransaction ID: {{4}}\nDate: {{5}}",
    varNames:["Customer name","Amount","Description","Transaction ID","Date"] },
  { id:"pay_failed", name:"payment_failed", displayName:"Payment failed",
    category:"UTILITY", subcategory:"Payment updates",
    body:"Hi {{1}},\n\nYour payment of {{2}} for {{3}} has failed.\n\nPlease retry or contact our support team.",
    buttons:[{type:"URL",text:"Retry payment",url:"https://pay.example.com"}],
    varNames:["Customer name","Amount","Description"] },
  // UTILITY — Customer feedback
  { id:"feedback", name:"feedback_request", displayName:"Customer feedback request",
    category:"UTILITY", subcategory:"Customer feedback",
    body:"Hi {{1}},\n\nHow was your experience with {{2}}? ⭐\n\nYour feedback helps us improve!",
    buttons:[{type:"QUICK_REPLY",text:"😊 Great"},{type:"QUICK_REPLY",text:"😐 Okay"},{type:"QUICK_REPLY",text:"😞 Poor"}],
    varNames:["Customer name","Product/service"] },
  // MARKETING — Promotions
  { id:"promo", name:"promotional_offer", displayName:"Promotional offer",
    category:"MARKETING", subcategory:"Promotions",
    header:"Special Offer Just for You!",
    body:"Hi {{1}},\n\nGet {{2}} off on your next purchase!\n\nUse code: *{{3}}*\nValid until: {{4}}",
    footer:"T&C apply",
    buttons:[{type:"URL",text:"Shop now",url:"https://www.example.com"}],
    varNames:["Customer name","Discount","Coupon code","Expiry date"] },
  { id:"flash_sale", name:"flash_sale", displayName:"Flash sale alert",
    category:"MARKETING", subcategory:"Promotions",
    header:"Flash Sale - Today Only!",
    body:"Hi {{1}},\n\nOur biggest sale is LIVE! Up to {{2}} off on {{3}}.\n\nEnds at midnight. Don't miss it!",
    buttons:[{type:"URL",text:"Shop sale",url:"https://www.example.com"}],
    varNames:["Customer name","Discount %","Categories"] },
  // MARKETING — Product announcements
  { id:"new_product", name:"new_product_launch", displayName:"New product launch",
    category:"MARKETING", subcategory:"Product announcements",
    header:"Introducing {{1}}",
    body:"Hi {{2}},\n\nWe're excited to announce the launch of *{{1}}*!\n\n{{3}}\n\nBe among the first to experience it.",
    buttons:[{type:"URL",text:"Learn more",url:"https://www.example.com"}],
    varNames:["Product name","Customer name","Product description"] },
  // MARKETING — Events
  { id:"event_inv", name:"event_invitation", displayName:"Event invitation",
    category:"MARKETING", subcategory:"Event invitations",
    body:"Hi {{1}},\n\nYou're invited to *{{2}}*! 🎊\n\n📅 Date: {{3}}\n⏰ Time: {{4}}\n📍 Venue: {{5}}",
    buttons:[{type:"QUICK_REPLY",text:"I'll attend"},{type:"QUICK_REPLY",text:"Can't make it"}],
    varNames:["Customer name","Event name","Date","Time","Venue"] },
  // AUTHENTICATION
  { id:"otp", name:"otp_verification", displayName:"OTP / Verification code",
    category:"AUTHENTICATION", subcategory:"OTP / Verification",
    body:"*{{1}}* is your verification code for *{{2}}*.\n\nThis code expires in {{3}} minutes. Do not share this code with anyone.",
    varNames:["OTP code","App name","Expiry minutes"] },
  { id:"login_alert", name:"login_alert", displayName:"New login alert",
    category:"AUTHENTICATION", subcategory:"OTP / Verification",
    body:"Hi {{1}},\n\nA new login was detected on your account from *{{2}}* at {{3}}.\n\nIf this wasn't you, please secure your account immediately.",
    buttons:[{type:"URL",text:"Secure account",url:"https://security.example.com"}],
    varNames:["Customer name","Device/location","Time"] },
];

const SUBCATS: Record<string, string[]> = {
  UTILITY: ["Account updates","Order management","Shipping updates","Appointment management","Payment updates","Customer feedback"],
  MARKETING: ["Promotions","Product announcements","Event invitations"],
  AUTHENTICATION: ["OTP / Verification"],
};
const LANGUAGES = ["en","en_US","hi","ar","es","pt_BR","fr","de","it","ja","ko","zh_CN"];

// ── Helpers ───────────────────────────────────────────────────────────────────
function renderBody(body: string, vars: string[]): string {
  let out = body;
  vars.forEach((v, i) => { out = out.replace(`{{${i+1}}}`, `[${v || `var${i+1}`}]`); });
  // replace unfilled
  out = out.replace(/\{\{(\d+)\}\}/g, (_, n) => `[var${n}]`);
  return out;
}

function WhatsAppBubble({ tpl, vars }: { tpl: LibTemplate; vars: string[] }) {
  const text = renderBody(tpl.body, vars);
  return (
    <div style={{ background:"#e5ddd5", borderRadius:12, padding:16, minHeight:180, display:"flex", flexDirection:"column", gap:8 }}>
      {tpl.header && (
        <div style={{ background:"#fff", borderRadius:"8px 8px 0 0", padding:"10px 14px", fontSize:13, fontWeight:700, color:"#111827", boxShadow:"0 1px 2px rgba(0,0,0,.1)" }}>
          {renderBody(tpl.header, vars)}
        </div>
      )}
      <div style={{ background:"#fff", borderRadius: tpl.header ? "0" : "0 8px 8px 8px", padding:"10px 14px", fontSize:13, color:"#111827", lineHeight:1.6, whiteSpace:"pre-line", boxShadow:"0 1px 2px rgba(0,0,0,.1)", position:"relative" }}>
        {!tpl.header && <div style={{ position:"absolute", top:0, left:-7, width:0, height:0, borderTop:"7px solid #fff", borderLeft:"7px solid transparent" }} />}
        {text}
        <span style={{ float:"right", fontSize:10, color:"#9ca3af", marginLeft:8, marginTop:4 }}>✓✓</span>
      </div>
      {tpl.footer && (
        <div style={{ background:"#fff", borderRadius:"0 0 8px 8px", padding:"6px 14px", fontSize:11, color:"#9ca3af", boxShadow:"0 1px 2px rgba(0,0,0,.1)" }}>
          {tpl.footer}
        </div>
      )}
      {tpl.buttons && tpl.buttons.map((b, i) => (
        <div key={i} style={{ background:"#fff", borderRadius:8, padding:"10px 14px", textAlign:"center", fontSize:13, fontWeight:500, color:"#25D366", boxShadow:"0 1px 2px rgba(0,0,0,.1)", cursor:"default" }}>
          {b.type === "URL" ? "🔗 " : b.type === "PHONE_NUMBER" ? "📞 " : "↩ "}{b.text}
        </div>
      ))}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
type View = "library" | "my-templates";

export default function TemplatesPage() {
  const [view, setView] = useState<View>("library");

  // Library state
  const [libCat, setLibCat] = useState<"UTILITY"|"MARKETING"|"AUTHENTICATION">("UTILITY");
  const [libSubcat, setLibSubcat] = useState("");
  const [libSearch, setLibSearch] = useState("");
  const [setupTpl, setSetupTpl] = useState<LibTemplate | null>(null);

  // My templates state
  const [list, setList] = useState<Template[]>([]);
  const [wabas, setWabas] = useState<WabaAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterWaba, setFilterWaba] = useState("");
  const [filterCat, setFilterCat] = useState("");
  const [mySearch, setMySearch] = useState("");
  const [viewTpl, setViewTpl] = useState<Template | null>(null);

  // Shared state
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Setup form
  const [setupForm, setSetupForm] = useState({
    waba_id: "", language: "en", name: "", vars: [] as string[],
    buttonUrls: [] as string[],
  });

  const load = () => {
    setLoading(true);
    Promise.all([templatesApi.list(filterWaba || undefined), wabaApi.list()])
      .then(([t, w]) => { setList(t); setWabas(w); if (w.length && !setupForm.waba_id) setSetupForm(f => ({ ...f, waba_id: w[0].id })); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [filterWaba]);

  const notify = (msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(null), 3500); };

  function openSetup(tpl: LibTemplate) {
    setSetupTpl(tpl);
    setSetupForm(f => ({
      ...f,
      name: tpl.name,
      language: "en",
      vars: new Array(tpl.varNames.length).fill(""),
      buttonUrls: (tpl.buttons || []).filter(b => b.type === "URL").map(b => b.url || ""),
    }));
    setError(null);
  }

  async function handleSetupSubmit(e: React.SyntheticEvent) {
    e.preventDefault();
    if (!setupTpl) return;
    setBusy(true); setError(null);
    try {
      // Find the highest {{N}} number in a string — tells us how many example values Meta needs
      const maxVarNum = (text: string) => {
        const nums = (text.match(/\{\{(\d+)\}\}/g) || []).map(m => parseInt(m.replace(/[{}]/g, ""), 10));
        return nums.length === 0 ? 0 : Math.max(...nums);
      };

      // Build example array — Meta requires sample values for every {{N}} variable.
      // varNames[i] labels {{i+1}} across all components (header shares numbering with body).
      // body_text is a 2D array: outer = message variants, inner = values for {{1}}…{{N}}.
      const allVarExamples = setupTpl.varNames.map((name, i) =>
        setupForm.vars[i]?.trim() || name || `sample_${i + 1}`
      );

      const components: Record<string, unknown>[] = [];

      // HEADER component
      if (setupTpl.header) {
        const hVarMax = maxVarNum(setupTpl.header);
        const headerComp: Record<string, unknown> = {
          type: "HEADER", format: "TEXT", text: setupTpl.header,
        };
        if (hVarMax > 0) {
          // header_text: one value per unique variable in the header
          headerComp.example = { header_text: allVarExamples.slice(0, hVarMax) };
        }
        components.push(headerComp);
      }

      // BODY component
      // body_text needs values for {{1}}…{{maxBodyVar}}, always starting from varNames[0].
      // (Header and body variables share the same varNames index — {{1}} in header and
      //  {{1}} in body both map to varNames[0].)
      const bodyVarMax = maxVarNum(setupTpl.body);
      const bodyComp: Record<string, unknown> = { type: "BODY", text: setupTpl.body };
      if (bodyVarMax > 0) {
        bodyComp.example = {
          body_text: [allVarExamples.slice(0, bodyVarMax)],
        };
      }
      components.push(bodyComp);

      // FOOTER component
      if (setupTpl.footer) components.push({ type: "FOOTER", text: setupTpl.footer });

      // BUTTONS component
      if (setupTpl.buttons && setupTpl.buttons.length > 0) {
        let urlIdx = 0;
        components.push({
          type: "BUTTONS",
          buttons: setupTpl.buttons.map(b => {
            if (b.type === "URL") {
              const url = setupForm.buttonUrls[urlIdx++] || b.url || "https://www.example.com";
              return { type: "URL", text: b.text, url };
            }
            if (b.type === "PHONE_NUMBER") return { type: "PHONE_NUMBER", text: b.text, phone_number: b.phone || "" };
            return { type: "QUICK_REPLY", text: b.text };
          }),
        });
      }

      await templatesApi.create({
        waba_id: setupForm.waba_id,
        name: setupForm.name.toLowerCase().replace(/\s+/g, "_"),
        category: setupTpl.category,
        language: setupForm.language,
        components,
      });
      notify(`Template "${setupForm.name}" submitted to Meta for review!`);
      setSetupTpl(null);
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleSync(t: Template) {
    setBusy(true);
    try { await templatesApi.sync(t.id); notify("Synced!"); load(); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  async function handleSyncAll() {
    const targets = filterWaba ? [filterWaba] : wabas.map(w => w.id);
    if (!targets.length) { setError("No WABA accounts"); return; }
    setBusy(true);
    try {
      let total = 0;
      for (const id of targets) { const r = await templatesApi.syncAll(id); total += r.length; }
      notify(`Synced ${total} templates!`); load();
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  async function handleDelete(t: Template) {
    if (!confirm(`Delete template "${t.name}"?`)) return;
    setBusy(true);
    try { await templatesApi.delete(t.id); notify("Deleted."); load(); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  // Filtered library
  const libFiltered = LIBRARY.filter(t =>
    t.category === libCat &&
    (!libSubcat || t.subcategory === libSubcat) &&
    (!libSearch || t.displayName.toLowerCase().includes(libSearch.toLowerCase()) || t.body.toLowerCase().includes(libSearch.toLowerCase()))
  );

  // Filtered my templates
  const myFiltered = list.filter(t =>
    (!filterCat || t.category === filterCat) &&
    (!mySearch || t.name.toLowerCase().includes(mySearch.toLowerCase()))
  );

  const statusColor: Record<string,[string,string]> = {
    APPROVED:["#dcfce7","#15803d"], PENDING:["#fef9c3","#a16207"],
    REJECTED:["#fee2e2","#b91c1c"], PAUSED:["#f3f4f6","#6b7280"],
  };

  return (
    <AppLayout>
      <div style={{ maxWidth: 1200 }}>
        {/* Header */}
        <div style={s.header}>
          <div>
            <h1 style={s.pageTitle}>Templates</h1>
            <p style={s.pageSubtitle}>Browse the library or manage your approved templates</p>
          </div>
          <div style={{ display:"flex", gap:8 }}>
            {view === "my-templates" && (
              <button onClick={handleSyncAll} disabled={busy} style={s.btnOutline}>↻ Sync from Meta</button>
            )}
          </div>
        </div>

        {/* Alerts */}
        {error && <div style={s.error}>{error}<button onClick={()=>setError(null)} style={s.closeBtn}>✕</button></div>}
        {success && <div style={s.success}>{success}</div>}

        {/* View tabs */}
        <div style={s.tabs}>
          <button onClick={()=>setView("library")} style={view==="library"?s.tabActive:s.tab}>📚 Template Library</button>
          <button onClick={()=>setView("my-templates")} style={view==="my-templates"?s.tabActive:s.tab}>
            📄 My Templates {list.length > 0 && <span style={s.badge}>{list.length}</span>}
          </button>
        </div>

        {/* ── LIBRARY VIEW ──────────────────────────────────────────────────── */}
        {view === "library" && (
          <div style={{ display:"flex", gap:0, background:"#fff", borderRadius:12, border:"1px solid #e5e7eb", overflow:"hidden" }}>
            {/* Sidebar */}
            <div style={s.sidebar}>
              {/* Category */}
              <div style={s.sideSection}>
                <div style={s.sideLabel}>Category</div>
                {(["UTILITY","MARKETING","AUTHENTICATION"] as const).map(cat => (
                  <label key={cat} style={s.radioRow}>
                    <input type="radio" name="cat" checked={libCat===cat} onChange={()=>{setLibCat(cat);setLibSubcat("");}}
                      style={{ accentColor:"#25D366" }} />
                    <span style={{ fontSize:13, color:"#374151" }}>
                      {cat === "UTILITY" ? "Utility" : cat === "MARKETING" ? "Marketing" : "Authentication"}
                      <span style={{ color:"#9ca3af", marginLeft:4 }}>({LIBRARY.filter(t=>t.category===cat).length})</span>
                    </span>
                  </label>
                ))}
              </div>

              {/* Subcategory */}
              <div style={s.sideSection}>
                <div style={s.sideLabel}>Subcategory</div>
                <label style={s.radioRow}>
                  <input type="radio" name="subcat" checked={libSubcat===""} onChange={()=>setLibSubcat("")} style={{ accentColor:"#25D366" }} />
                  <span style={{ fontSize:13, color:"#374151" }}>All</span>
                </label>
                {SUBCATS[libCat].map(sub => (
                  <label key={sub} style={s.radioRow}>
                    <input type="radio" name="subcat" checked={libSubcat===sub} onChange={()=>setLibSubcat(sub)} style={{ accentColor:"#25D366" }} />
                    <span style={{ fontSize:13, color:"#374151" }}>
                      {sub}
                      <span style={{ color:"#9ca3af", marginLeft:4 }}>({LIBRARY.filter(t=>t.category===libCat&&t.subcategory===sub).length})</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            {/* Main content */}
            <div style={{ flex:1, padding:20 }}>
              {/* Search */}
              <div style={{ marginBottom:16, display:"flex", justifyContent:"space-between", alignItems:"center", gap:12 }}>
                <input value={libSearch} onChange={e=>setLibSearch(e.target.value)}
                  placeholder={`Search ${libCat.toLowerCase()} templates…`}
                  style={{ ...s.input, flex:1, maxWidth:400 }} />
                <span style={{ fontSize:13, color:"#6b7280" }}>Showing {libFiltered.length} templates</span>
              </div>

              {/* Cards grid */}
              {libFiltered.length === 0 ? (
                <div style={{ textAlign:"center", padding:"40px 20px", color:"#9ca3af" }}>No templates match your search</div>
              ) : (
                <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(240px,1fr))", gap:16 }}>
                  {libFiltered.map(tpl => (
                    <div key={tpl.id} onClick={()=>openSetup(tpl)} style={s.libCard}>
                      {/* Mini WhatsApp preview */}
                      <div style={{ background:"#e5ddd5", borderRadius:8, padding:10, marginBottom:10, minHeight:110 }}>
                        {tpl.header && (
                          <div style={{ background:"#fff", borderRadius:"4px 4px 0 0", padding:"6px 8px", fontSize:11, fontWeight:700, color:"#111827", marginBottom:2 }}>
                            {tpl.header.replace(/\{\{\d+\}\}/g,"{{…}}")}
                          </div>
                        )}
                        <div style={{ background:"#fff", borderRadius: tpl.header ? "0 0 4px 4px" : "0 4px 4px 4px", padding:"6px 8px", fontSize:11, color:"#374151", lineHeight:1.5, whiteSpace:"pre-line", maxHeight:72, overflow:"hidden" }}>
                          {tpl.body.replace(/\{\{(\d+)\}\}/g, (_, n) => `{{${tpl.varNames[+n-1]||"text"}}}`).slice(0,120)}
                        </div>
                        {tpl.buttons && tpl.buttons.slice(0,2).map((b,i) => (
                          <div key={i} style={{ background:"#fff", borderRadius:4, padding:"4px 8px", textAlign:"center", fontSize:10, color:"#25D366", marginTop:2 }}>{b.text}</div>
                        ))}
                      </div>
                      <div style={{ fontSize:12, color:"#6b7280", fontWeight:500 }}>{tpl.displayName}</div>
                      <div style={{ fontSize:11, color:"#9ca3af", marginTop:2 }}>{tpl.subcategory}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── MY TEMPLATES VIEW ─────────────────────────────────────────────── */}
        {view === "my-templates" && (
          <>
            <div style={{ display:"flex", gap:10, marginBottom:16, flexWrap:"wrap" }}>
              <input value={mySearch} onChange={e=>setMySearch(e.target.value)}
                placeholder="Search templates…" style={{ ...s.input, flex:1, minWidth:200 }} />
              <select value={filterWaba} onChange={e=>setFilterWaba(e.target.value)} style={s.select}>
                <option value="">All WABAs</option>
                {wabas.map(w=><option key={w.id} value={w.id}>{w.business_name??w.waba_id}</option>)}
              </select>
              <select value={filterCat} onChange={e=>setFilterCat(e.target.value)} style={s.select}>
                <option value="">All categories</option>
                {["MARKETING","UTILITY","AUTHENTICATION"].map(c=><option key={c}>{c}</option>)}
              </select>
            </div>
            {loading ? <div style={s.loading}>Loading…</div> : myFiltered.length === 0 ? (
              <div style={s.emptyState}>
                <div style={{ fontSize:48, marginBottom:12 }}>📄</div>
                <div style={{ fontSize:16, fontWeight:600, color:"#374151", marginBottom:8 }}>No templates yet</div>
                <div style={{ color:"#9ca3af", fontSize:14, marginBottom:20 }}>Pick a template from the library to get started</div>
                <button onClick={()=>setView("library")} style={s.btnGreen}>Browse Template Library</button>
              </div>
            ) : (
              <div style={s.grid}>
                {myFiltered.map(t => {
                  const [bg,color] = statusColor[t.status] ?? ["#f3f4f6","#6b7280"];
                  const bodyComp = t.components.find((c:any)=>c.type==="BODY") as any;
                  return (
                    <div key={t.id} style={s.myCard}>
                      <div style={{ display:"flex", gap:10, marginBottom:8, alignItems:"flex-start" }}>
                        <div style={{ flex:1, minWidth:0 }}>
                          <div style={{ fontSize:14, fontWeight:600, color:"#111827", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{t.name}</div>
                          <div style={{ fontSize:11, color:"#9ca3af", marginTop:2 }}>{t.language} · {t.category} · {wabas.find(w=>w.id===t.waba_id)?.business_name ?? t.waba_id.slice(0,8)}</div>
                        </div>
                        <span style={{ padding:"2px 8px", borderRadius:999, fontSize:11, fontWeight:600, background:bg, color, flexShrink:0 }}>{t.status}</span>
                      </div>
                      {t.rejection_reason && (
                        <div style={{ padding:"6px 10px", background:"#fef2f2", borderRadius:6, fontSize:12, color:"#991b1b", marginBottom:8 }}>{t.rejection_reason}</div>
                      )}
                      <div style={{ fontSize:12, color:"#6b7280", lineHeight:1.5, marginBottom:12 }}>
                        {bodyComp ? String(bodyComp.text||"").slice(0,100)+"…" : `${t.components.length} component(s)`}
                      </div>
                      <div style={{ display:"flex", gap:6 }}>
                        <button onClick={()=>setViewTpl(t)} style={s.tinyBtn}>View</button>
                        <button onClick={()=>handleSync(t)} disabled={busy} style={s.tinyBtn}>Sync</button>
                        <button onClick={()=>handleDelete(t)} disabled={busy} style={{ ...s.tinyBtn, color:"#b91c1c" }}>Delete</button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Setup modal ──────────────────────────────────────────────────────── */}
      {setupTpl && (
        <div style={s.overlay}>
          <div style={{ background:"#fff", borderRadius:16, width:"100%", maxWidth:860, maxHeight:"92vh", overflowY:"auto", display:"flex", flexDirection:"column" }}>
            {/* Modal header */}
            <div style={{ padding:"20px 28px", borderBottom:"1px solid #e5e7eb", display:"flex", alignItems:"flex-start", justifyContent:"space-between" }}>
              <div>
                <h2 style={{ margin:0, fontSize:18, fontWeight:700, color:"#111827" }}>{setupTpl.displayName}</h2>
                <p style={{ margin:"4px 0 0", fontSize:12, color:"#9ca3af" }}>
                  {setupTpl.category} › {setupTpl.subcategory}
                </p>
              </div>
              <button onClick={()=>setSetupTpl(null)} style={{ background:"none", border:"none", fontSize:22, cursor:"pointer", color:"#6b7280", lineHeight:1 }}>✕</button>
            </div>

            <div style={{ display:"flex", flex:1, minHeight:0 }}>
              {/* Left — form */}
              <div style={{ flex:"0 0 380px", padding:"24px 28px", borderRight:"1px solid #e5e7eb", overflowY:"auto" }}>
                {error && (
                  <div style={{ marginBottom:14, padding:"12px 14px", background:"#fef2f2", border:"1px solid #fecaca", borderRadius:8, fontSize:13, color:"#991b1b", lineHeight:1.6 }}>
                    {error.includes("PERMISSION_ERROR") ? (
                      <>
                        <div style={{ fontWeight:600, marginBottom:6 }}>Token missing <code>whatsapp_business_management</code> permission</div>
                        <div style={{ marginBottom:8 }}>
                          Your WABA access token can send messages but cannot manage templates. You need to regenerate it with both scopes.
                        </div>
                        <div style={{ marginBottom:6 }}>Steps to fix:</div>
                        <ol style={{ margin:"0 0 8px 18px", padding:0, fontSize:12 }}>
                          <li>Open <a href="https://business.facebook.com/settings/system-users" target="_blank" rel="noreferrer" style={{ color:"#1d4ed8" }}>Meta Business Manager → System Users</a></li>
                          <li>Select your System User → click <b>Generate New Token</b></li>
                          <li>Enable both <b>whatsapp_business_messaging</b> AND <b>whatsapp_business_management</b></li>
                          <li>Copy the new token and update it in <b>WABA Accounts</b></li>
                        </ol>
                        <div style={{ fontSize:12, color:"#b91c1c" }}>Alternatively: create the template directly in <a href="https://business.facebook.com/wa/manage/message-templates/" target="_blank" rel="noreferrer" style={{ color:"#1d4ed8" }}>WhatsApp Manager</a> and use <b>Sync from Meta</b> here.</div>
                      </>
                    ) : (
                      error
                    )}
                    <button onClick={()=>setError(null)} style={{ float:"right", background:"none", border:"none", cursor:"pointer", color:"#991b1b", fontSize:16, marginTop:-2 }}>✕</button>
                  </div>
                )}
                <p style={{ fontSize:13, color:"#6b7280", marginTop:0, marginBottom:20, lineHeight:1.6 }}>
                  Fill in the details below to submit this template to Meta. It will be reviewed within a few minutes to 24 hours.
                </p>
                <form onSubmit={handleSetupSubmit} style={{ display:"flex", flexDirection:"column", gap:14 }}>
                  {/* Name */}
                  <FormField label="Template name">
                    <input value={setupForm.name} onChange={e=>setSetupForm(f=>({...f,name:e.target.value}))}
                      placeholder="my_template_name" required style={s.input}
                      pattern="[a-z0-9_]+" title="Lowercase letters, numbers and underscores only" />
                    <span style={{ fontSize:11, color:"#9ca3af" }}>Lowercase, underscores only. No spaces.</span>
                  </FormField>

                  {/* WABA */}
                  <FormField label="WABA account">
                    <select value={setupForm.waba_id} onChange={e=>setSetupForm(f=>({...f,waba_id:e.target.value}))} required style={s.input}>
                      <option value="">Select WABA…</option>
                      {wabas.map(w=><option key={w.id} value={w.id}>{w.business_name??w.waba_id}</option>)}
                    </select>
                  </FormField>

                  {/* Language */}
                  <FormField label="Language">
                    <select value={setupForm.language} onChange={e=>setSetupForm(f=>({...f,language:e.target.value}))} style={s.input}>
                      {LANGUAGES.map(l=><option key={l}>{l}</option>)}
                    </select>
                  </FormField>

                  {/* Variables */}
                  {setupTpl.varNames.length > 0 && (
                    <div>
                      <div style={{ fontSize:12, fontWeight:600, color:"#374151", marginBottom:4 }}>Template variables — sample values</div>
                      <div style={{ fontSize:11, color:"#92400e", background:"#fffbeb", border:"1px solid #fde68a", borderRadius:6, padding:"5px 10px", marginBottom:8 }}>
                        ⚠ Meta requires sample values for every variable — for review only, not sent to users.
                      </div>
                      <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                        {setupTpl.varNames.map((name, i) => (
                          <div key={i} style={{ display:"flex", alignItems:"center", gap:8 }}>
                            <span style={{ fontSize:12, color:"#6b7280", minWidth:80, flexShrink:0 }}>{'{{' + (i+1) + '}}'} {name}</span>
                            <input value={setupForm.vars[i]||""} onChange={e=>{
                              const v=[...setupForm.vars]; v[i]=e.target.value; setSetupForm(f=>({...f,vars:v}));
                            }} placeholder={`e.g. ${name}`} style={{ ...s.input, flex:1, padding:"6px 10px", fontSize:12 }} />
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Button URLs */}
                  {setupTpl.buttons?.filter(b=>b.type==="URL").map((b, i) => (
                    <FormField key={i} label={`Button URL — "${b.text}"`}>
                      <input value={setupForm.buttonUrls[i]||b.url||""}
                        onChange={e=>{const v=[...setupForm.buttonUrls];v[i]=e.target.value;setSetupForm(f=>({...f,buttonUrls:v}));}}
                        placeholder="https://www.yoursite.com" type="url" style={s.input} />
                    </FormField>
                  ))}

                  <button type="submit" disabled={busy||!setupForm.waba_id}
                    style={{ ...s.btnGreen, opacity:busy||!setupForm.waba_id?0.6:1, marginTop:4 }}>
                    {busy ? "Submitting…" : "Submit to Meta"}
                  </button>
                </form>
              </div>

              {/* Right — preview */}
              <div style={{ flex:1, padding:"24px 28px", background:"#f9fafb", overflowY:"auto" }}>
                <div style={{ display:"flex", justifyContent:"space-between", marginBottom:12, alignItems:"center" }}>
                  <span style={{ fontSize:13, fontWeight:600, color:"#374151" }}>Preview</span>
                  <div style={{ display:"flex", gap:8 }}>
                    <span style={{ fontSize:11, padding:"2px 8px", background:"#dbeafe", color:"#1d4ed8", borderRadius:999, fontWeight:600 }}>{setupTpl.category}</span>
                  </div>
                </div>

                {/* Phone frame */}
                <div style={{ maxWidth:300, margin:"0 auto", background:"#fff", borderRadius:32, border:"8px solid #1f2937", padding:0, overflow:"hidden", boxShadow:"0 20px 40px rgba(0,0,0,.15)" }}>
                  {/* Status bar */}
                  <div style={{ background:"#1f2937", padding:"8px 16px 4px", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                    <span style={{ fontSize:10, color:"#fff", fontWeight:600 }}>9:41</span>
                    <span style={{ fontSize:10, color:"#fff" }}>●●●●●</span>
                  </div>
                  {/* Chat header */}
                  <div style={{ background:"#075E54", padding:"10px 16px", display:"flex", alignItems:"center", gap:10 }}>
                    <div style={{ width:32, height:32, borderRadius:"50%", background:"#25D366", display:"flex", alignItems:"center", justifyContent:"center", fontSize:14 }}>💼</div>
                    <div>
                      <div style={{ fontSize:13, fontWeight:600, color:"#fff" }}>Business</div>
                      <div style={{ fontSize:10, color:"rgba(255,255,255,0.7)" }}>online</div>
                    </div>
                  </div>
                  {/* Chat body */}
                  <div style={{ background:"#e5ddd5", padding:"12px 8px", minHeight:220 }}>
                    <WhatsAppBubble tpl={setupTpl} vars={setupForm.vars} />
                  </div>
                </div>

                <p style={{ fontSize:11, color:"#9ca3af", textAlign:"center", marginTop:12 }}>
                  Text in brackets are dynamic variables
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* View existing template detail modal */}
      {viewTpl && (
        <div style={s.overlay}>
          <div style={{ background:"#fff", borderRadius:16, padding:"28px 32px", width:"100%", maxWidth:540, maxHeight:"90vh", overflowY:"auto" }}>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:16 }}>
              <h2 style={{ margin:0, fontSize:18, fontWeight:700, color:"#111827" }}>{viewTpl.name}</h2>
              <button onClick={()=>setViewTpl(null)} style={{ background:"none", border:"none", fontSize:20, cursor:"pointer", color:"#6b7280" }}>✕</button>
            </div>
            <div style={{ display:"flex", gap:8, marginBottom:16, flexWrap:"wrap" }}>
              <span style={{ padding:"2px 8px", borderRadius:999, fontSize:11, fontWeight:600, background:"#dbeafe", color:"#1d4ed8" }}>{viewTpl.category}</span>
              <span style={{ padding:"2px 8px", borderRadius:999, fontSize:11, fontWeight:600, background:"#f3f4f6", color:"#374151" }}>{viewTpl.language}</span>
              <span style={{ padding:"2px 8px", borderRadius:999, fontSize:11, fontWeight:600, ...(statusColor[viewTpl.status]?{background:statusColor[viewTpl.status][0],color:statusColor[viewTpl.status][1]}:{background:"#f3f4f6",color:"#6b7280"}) }}>{viewTpl.status}</span>
            </div>
            <pre style={{ background:"#f9fafb", padding:16, borderRadius:8, fontSize:12, overflowX:"auto", lineHeight:1.6, maxHeight:340 }}>
              {JSON.stringify(viewTpl.components, null, 2)}
            </pre>
            {viewTpl.meta_template_id && <p style={{ fontSize:12, color:"#9ca3af", marginTop:8 }}>Meta ID: {viewTpl.meta_template_id}</p>}
          </div>
        </div>
      )}
    </AppLayout>
  );
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
      <label style={{ fontSize:12, fontWeight:600, color:"#374151" }}>{label}</label>
      {children}
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  header:    { display:"flex", alignItems:"flex-start", justifyContent:"space-between", marginBottom:20, gap:16 },
  pageTitle: { fontSize:24, fontWeight:700, color:"#111827", margin:"0 0 4px" },
  pageSubtitle: { fontSize:14, color:"#6b7280", margin:0 },
  btnGreen:  { padding:"9px 18px", background:"#25D366", color:"#fff", border:"none", borderRadius:8, fontSize:13, fontWeight:600, cursor:"pointer" },
  btnOutline:{ padding:"9px 14px", background:"#fff", color:"#374151", border:"1px solid #d1d5db", borderRadius:8, fontSize:13, fontWeight:500, cursor:"pointer" },
  tabs:      { display:"flex", gap:2, marginBottom:16, background:"#f3f4f6", padding:4, borderRadius:10, width:"fit-content" },
  tab:       { padding:"8px 18px", borderRadius:8, border:"none", background:"transparent", fontSize:13, fontWeight:500, color:"#6b7280", cursor:"pointer" },
  tabActive: { padding:"8px 18px", borderRadius:8, border:"none", background:"#fff", fontSize:13, fontWeight:600, color:"#111827", cursor:"pointer", boxShadow:"0 1px 3px rgba(0,0,0,.1)" },
  badge:     { display:"inline-block", padding:"1px 6px", borderRadius:999, fontSize:10, fontWeight:700, background:"#25D366", color:"#fff", marginLeft:6 },
  sidebar:   { width:220, flexShrink:0, borderRight:"1px solid #e5e7eb", padding:16 },
  sideSection:{ marginBottom:20 },
  sideLabel: { fontSize:11, fontWeight:700, color:"#9ca3af", textTransform:"uppercase" as const, letterSpacing:"0.07em", marginBottom:8 },
  radioRow:  { display:"flex", alignItems:"center", gap:8, padding:"4px 0", cursor:"pointer" },
  libCard:   { background:"#fff", border:"1px solid #e5e7eb", borderRadius:10, padding:12, cursor:"pointer", transition:"box-shadow .15s", },
  error:     { padding:"10px 14px", background:"#fef2f2", border:"1px solid #fecaca", borderRadius:8, color:"#991b1b", fontSize:13, display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16 },
  success:   { marginBottom:16, padding:"10px 14px", background:"#f0fdf4", border:"1px solid #bbf7d0", borderRadius:8, color:"#166534", fontSize:13 },
  closeBtn:  { background:"none", border:"none", cursor:"pointer", color:"#991b1b", fontSize:16 },
  loading:   { color:"#6b7280", fontSize:14, padding:"40px 0" },
  emptyState:{ textAlign:"center", padding:"60px 20px", background:"#fff", borderRadius:12, border:"1px solid #e5e7eb" },
  grid:      { display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(300px,1fr))", gap:16 },
  myCard:    { background:"#fff", borderRadius:12, border:"1px solid #e5e7eb", padding:16 },
  input:     { padding:"9px 12px", border:"1px solid #d1d5db", borderRadius:8, fontSize:13, color:"#111827", outline:"none" },
  select:    { padding:"9px 12px", border:"1px solid #d1d5db", borderRadius:8, fontSize:13, color:"#374151", background:"#fff" },
  tinyBtn:   { padding:"5px 10px", border:"1px solid #e5e7eb", borderRadius:6, background:"#f9fafb", color:"#374151", fontSize:12, cursor:"pointer" },
  overlay:   { position:"fixed", inset:0, background:"rgba(0,0,0,0.55)", display:"flex", alignItems:"center", justifyContent:"center", zIndex:100, padding:16 },
};
