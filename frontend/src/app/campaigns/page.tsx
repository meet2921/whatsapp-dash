"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/AppLayout";
import { campaigns as campaignsApi, contacts as contactsApi, phones as phonesApi, templates as templatesApi } from "@/lib/api";
import type { Campaign, CampaignRecipient, ContactTag, PhoneNumber, Template } from "@/types/api";

type Modal = "create" | "recipients" | "detail" | null;

const STATUS_STYLE: Record<string, [string, string]> = {
  draft:     ["#f3f4f6", "#374151"],
  scheduled: ["#fef9c3", "#a16207"],
  running:   ["#dbeafe", "#1d4ed8"],
  paused:    ["#fef3c7", "#92400e"],
  completed: ["#dcfce7", "#15803d"],
  failed:    ["#fee2e2", "#b91c1c"],
};

function pct(n: number, total: number) {
  if (!total) return "0%";
  return `${Math.round((n / total) * 100)}%`;
}

export default function CampaignsPage() {
  const [list, setList] = useState<Campaign[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [modal, setModal] = useState<Modal>(null);
  const [selected, setSelected] = useState<Campaign | null>(null);
  const [recipients, setRecipients] = useState<CampaignRecipient[]>([]);
  const [recipientsTotal, setRecipientsTotal] = useState(0);

  // Form state
  const [templates, setTemplates] = useState<Template[]>([]);
  const [phones, setPhones] = useState<PhoneNumber[]>([]);
  const [tags, setTags] = useState<ContactTag[]>([]);
  const [form, setForm] = useState({ name: "", template_id: "", phone_number_id: "" });
  const [tplVars, setTplVars] = useState<Record<string, string>>({});
  const [selectedTpl, setSelectedTpl] = useState<Template | null>(null);
  const [addMode, setAddMode] = useState<"all_opted_in" | "tag" | "phones">("all_opted_in");
  const [addTag, setAddTag] = useState("");
  const [addPhones, setAddPhones] = useState("");

  const notify = (msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(null), 3000); };

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [p, t] = await Promise.all([campaignsApi.list({ limit: 50 }), phonesApi.list()]);
      setList(p.items);
      setTotal(p.total);
      setPhones(t);
    } catch (e) { if (!silent) setError(e instanceof Error ? e.message : "Failed"); }
    finally { if (!silent) setLoading(false); }
  };

  useEffect(() => {
    load();
    const interval = setInterval(() => load(true), 5000);
    return () => clearInterval(interval);
  }, []);

  function getCompVarNums(comp: Record<string, unknown>): number[] {
    const text = typeof comp.text === "string" ? comp.text : "";
    const nums = [...new Set((text.match(/\{\{(\d+)\}\}/g) ?? []).map(m => parseInt(m.slice(2, -2))))];
    return nums.sort((a, b) => a - b);
  }

  function getTplVarFields(tpl: Template): Array<{ key: string; label: string }> {
    const comps = (tpl.components ?? []) as Array<Record<string, unknown>>;
    const fields: Array<{ key: string; label: string }> = [];
    for (const comp of comps) {
      const ct = (typeof comp.type === "string" ? comp.type : "").toUpperCase();
      if (ct !== "HEADER" && ct !== "BODY") continue;
      const nums = getCompVarNums(comp);
      for (const n of nums) {
        fields.push({ key: `${ct}-${n}`, label: `${ct} {{${n}}}` });
      }
    }
    return fields;
  }

  function resolvePreviewVar(key: string, vars: Record<string, string>): string {
    const val = vars[key] ?? "";
    if (val === "@contact.name") return "John Doe";
    if (val === "@contact.phone") return "+91 98765 43210";
    return val || `{{${key}}}`;
  }

  function buildPreview(tpl: Template | null, vars: Record<string, string>) {
    if (!tpl) return { header: null, body: null, footer: null, buttons: [] as string[] };
    const comps = (tpl.components ?? []) as Array<Record<string, unknown>>;
    let header: string | null = null;
    let body: string | null = null;
    let footer: string | null = null;
    const buttons: string[] = [];
    for (const comp of comps) {
      const ct = (typeof comp.type === "string" ? comp.type : "").toUpperCase();
      const text = typeof comp.text === "string" ? comp.text : "";
      if (ct === "HEADER") {
        header = text.replace(/\{\{(\d+)\}\}/g, (_: string, n: string) => resolvePreviewVar(`HEADER-${n}`, vars));
      } else if (ct === "BODY") {
        body = text.replace(/\{\{(\d+)\}\}/g, (_: string, n: string) => resolvePreviewVar(`BODY-${n}`, vars));
      } else if (ct === "FOOTER") {
        footer = text;
      } else if (ct === "BUTTONS") {
        const btns = comp.buttons as Array<Record<string, unknown>> ?? [];
        btns.forEach(b => { if (typeof b.text === "string") buttons.push(b.text); });
      }
    }
    return { header, body, footer, buttons };
  }

  async function openCreate() {
    try {
      const [t, tg] = await Promise.all([templatesApi.list(), contactsApi.listTags()]);
      setTemplates(t.filter(t => t.status === "APPROVED"));
      setTags(tg);
    } catch { /* ignore */ }
    setForm({ name: "", template_id: "", phone_number_id: "" });
    setTplVars({});
    setSelectedTpl(null);
    setModal("create");
    setError(null);
  }

  function handleTplSelect(tplId: string) {
    setForm(f => ({ ...f, template_id: tplId }));
    const tpl = templates.find(t => t.id === tplId) ?? null;
    setSelectedTpl(tpl);
    setTplVars({});
  }

  async function handleCreate(e: React.SyntheticEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      const c = await campaignsApi.create({ ...form, template_variables: tplVars });
      notify("Campaign created!"); setModal(null);
      // Auto-open recipient add
      setSelected(c); setModal("recipients");
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleAddRecipients(e: React.SyntheticEvent) {
    e.preventDefault(); if (!selected) return;
    setBusy(true); setError(null);
    try {
      const body: { phones?: string[]; tag_id?: string; all_opted_in?: boolean } = {};
      if (addMode === "all_opted_in") body.all_opted_in = true;
      else if (addMode === "tag") body.tag_id = addTag;
      else body.phones = addPhones.split(/[\n,]+/).map(p => p.trim()).filter(Boolean);
      const res = await campaignsApi.addRecipients(selected.id, body);
      notify(`Added ${res.added} recipients (total: ${res.total_recipients})`);
      const updated = await campaignsApi.get(selected.id);
      setSelected(updated);
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleLaunch(c: Campaign) {
    if (!confirm(`Launch campaign "${c.name}" to ${c.total_recipients} recipients?`)) return;
    setBusy(true);
    try {
      await campaignsApi.launch(c.id);
      notify("Campaign launched!"); load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handlePause(c: Campaign) {
    setBusy(true);
    try { await campaignsApi.pause(c.id); notify("Paused."); load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleResume(c: Campaign) {
    setBusy(true);
    try { await campaignsApi.resume(c.id); notify("Resumed."); load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleDelete(c: Campaign) {
    if (!confirm(`Delete campaign "${c.name}"?`)) return;
    setBusy(true);
    try { await campaignsApi.delete(c.id); notify("Deleted."); load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function openDetail(c: Campaign) {
    setSelected(c); setModal("detail");
    try {
      const r = await campaignsApi.listRecipients(c.id, { limit: 100 });
      setRecipients(r.items); setRecipientsTotal(r.total);
    } catch { setRecipients([]); }
  }

  const templateName = (id: string | null) => templates.find(t => t.id === id)?.name ?? id?.slice(0, 8) ?? "—";
  const phoneName = (id: string | null) => {
    const p = phones.find(p => p.id === id);
    return p ? (p.display_name ?? p.display_number ?? p.phone_number_id) : id?.slice(0, 8) ?? "—";
  };

  return (
    <AppLayout>
      <div style={{ maxWidth: 1100 }}>
        {/* Header */}
        <div style={s.header}>
          <div>
            <h1 style={s.pageTitle}>Campaigns</h1>
            <p style={s.pageSubtitle}>Bulk WhatsApp broadcasts · {total} campaign{total !== 1 ? "s" : ""}</p>
          </div>
          <button onClick={openCreate} style={s.btnGreen}>+ New Campaign</button>
        </div>

        {error && <div style={s.error}>{error}<button onClick={() => setError(null)} style={s.closeBtn}>✕</button></div>}
        {success && <div style={s.success}>{success}</div>}

        {loading ? (
          <div style={s.loading}>Loading campaigns…</div>
        ) : list.length === 0 ? (
          <div style={s.empty}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>📣</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: "#374151", marginBottom: 8 }}>No campaigns yet</div>
            <div style={{ color: "#9ca3af", fontSize: 14, marginBottom: 20 }}>Create a campaign to send bulk template messages to your contacts</div>
            <button onClick={openCreate} style={s.btnGreen}>Create First Campaign</button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {list.map(c => {
              const [bg, color] = STATUS_STYLE[c.status] ?? ["#f3f4f6", "#374151"];
              const progress = c.total_recipients > 0 ? ((c.sent_count + c.failed_count) / c.total_recipients) * 100 : 0;
              return (
                <div key={c.id} style={s.card}>
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                        <span style={{ fontSize: 15, fontWeight: 700, color: "#111827" }}>{c.name}</span>
                        <span style={{ padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600, background: bg, color }}>{c.status}</span>
                      </div>
                      <div style={{ fontSize: 12, color: "#9ca3af" }}>
                        Template: <b style={{ color: "#374151" }}>{templateName(c.template_id)}</b>
                        {" · "}From: <b style={{ color: "#374151" }}>{phoneName(c.phone_number_id)}</b>
                        {c.scheduled_at && <> · Scheduled: <b style={{ color: "#374151" }}>{new Date(c.scheduled_at).toLocaleString()}</b></>}
                      </div>
                    </div>

                    {/* Actions */}
                    <div style={{ display: "flex", gap: 6, flexShrink: 0, flexWrap: "wrap" }}>
                      {c.status === "draft" && (
                        <>
                          <button onClick={() => { setSelected(c); setModal("recipients"); }} style={s.tinyBtn}>+ Recipients</button>
                          <button onClick={() => handleLaunch(c)} disabled={busy || c.total_recipients === 0} style={{ ...s.tinyBtn, background: "#25D366", color: "#fff", border: "none" }}>🚀 Launch</button>
                        </>
                      )}
                      {c.status === "scheduled" && (
                        <button onClick={() => handleLaunch(c)} disabled={busy} style={{ ...s.tinyBtn, background: "#25D366", color: "#fff", border: "none" }}>▶ Send Now</button>
                      )}
                      {c.status === "running" && (
                        <button onClick={() => handlePause(c)} disabled={busy} style={{ ...s.tinyBtn, background: "#fef3c7", color: "#92400e", border: "1px solid #fcd34d" }}>⏸ Pause</button>
                      )}
                      {c.status === "paused" && (
                        <button onClick={() => handleResume(c)} disabled={busy} style={{ ...s.tinyBtn, background: "#dbeafe", color: "#1d4ed8", border: "1px solid #93c5fd" }}>▶ Resume</button>
                      )}
                      <button onClick={() => openDetail(c)} style={s.tinyBtn}>📊 Stats</button>
                      {(c.status === "draft" || c.status === "completed" || c.status === "failed") && (
                        <button onClick={() => handleDelete(c)} disabled={busy} style={{ ...s.tinyBtn, color: "#b91c1c" }}>✕</button>
                      )}
                    </div>
                  </div>

                  {/* Stats bar */}
                  <div style={{ display: "flex", gap: 16, marginTop: 12, flexWrap: "wrap" }}>
                    {[
                      { label: "Total", value: c.total_recipients, color: "#6b7280" },
                      { label: "Sent", value: c.sent_count, color: "#3b82f6" },
                      { label: "Delivered", value: c.delivered_count, color: "#25D366" },
                      { label: "Read", value: c.read_count, color: "#128C4B" },
                      { label: "Failed", value: c.failed_count, color: "#ef4444" },
                    ].map(stat => (
                      <div key={stat.label} style={{ textAlign: "center" as const }}>
                        <div style={{ fontSize: 18, fontWeight: 800, color: stat.color }}>{stat.value}</div>
                        <div style={{ fontSize: 10, color: "#9ca3af", fontWeight: 600, textTransform: "uppercase" as const }}>{stat.label}</div>
                      </div>
                    ))}
                    {c.total_recipients > 0 && (
                      <div style={{ flex: 1, alignSelf: "center", minWidth: 120 }}>
                        <div style={{ height: 6, background: "#f3f4f6", borderRadius: 99, overflow: "hidden" }}>
                          <div style={{ width: `${progress}%`, height: "100%", background: "#25D366", borderRadius: 99, transition: "width 0.5s" }} />
                        </div>
                        <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 2 }}>{Math.round(progress)}% processed</div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Create campaign modal — two-column with live preview */}
      {modal === "create" && (() => {
        const preview = buildPreview(selectedTpl, tplVars);
        return (
          <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 16 }}>
            <div style={{ background: "#fff", borderRadius: 16, width: "100%", maxWidth: 860, maxHeight: "92vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
              {/* Header */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "20px 28px 16px", borderBottom: "1px solid #f3f4f6" }}>
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#111827" }}>New Campaign</h2>
                <button onClick={() => setModal(null)} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#6b7280" }}>✕</button>
              </div>

              {/* Body: form + preview */}
              <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
                {/* Left: form */}
                <div style={{ flex: 1, overflowY: "auto", padding: "20px 28px" }}>
                  {error && <div style={{ ...s.error, marginBottom: 12 }}>{error}</div>}
                  <form onSubmit={handleCreate} style={s.form}>
                    <Field label="Campaign Name">
                      <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="April Promo Blast" required style={s.input} />
                    </Field>
                    <Field label="Template (must be APPROVED)">
                      <select value={form.template_id} onChange={e => handleTplSelect(e.target.value)} required style={s.input}>
                        <option value="">Select template…</option>
                        {templates.map(t => <option key={t.id} value={t.id}>{t.name} ({t.language})</option>)}
                      </select>
                      {templates.length === 0 && <span style={{ fontSize: 11, color: "#9ca3af" }}>No approved templates found.</span>}
                    </Field>

                    {selectedTpl && getTplVarFields(selectedTpl).length > 0 && (
                      <div style={{ background: "#f9fafb", borderRadius: 8, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 10 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", textTransform: "uppercase" as const, letterSpacing: "0.05em" }}>Template Variables</div>
                        <div style={{ fontSize: 12, color: "#9ca3af" }}>Choose "Contact Name" for personalised fields — auto-filled per recipient.</div>
                        {getTplVarFields(selectedTpl).map(({ key, label }) => {
                          const val = tplVars[key] ?? "";
                          const isContactField = val === "@contact.name" || val === "@contact.phone";
                          return (
                            <div key={key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                              <label style={{ fontSize: 12, fontWeight: 500, color: "#374151" }}>{label}</label>
                              <div style={{ display: "flex", gap: 6 }}>
                                <select
                                  value={isContactField ? val : "custom"}
                                  onChange={e => {
                                    const v = e.target.value;
                                    if (v === "custom") setTplVars(prev => ({ ...prev, [key]: "" }));
                                    else setTplVars(prev => ({ ...prev, [key]: v }));
                                  }}
                                  style={{ ...s.input, width: 150, flexShrink: 0, fontSize: 12 }}
                                >
                                  <option value="custom">Fixed value</option>
                                  <option value="@contact.name">Contact Name</option>
                                  <option value="@contact.phone">Contact Phone</option>
                                </select>
                                {!isContactField ? (
                                  <input
                                    value={val}
                                    onChange={e => setTplVars(v => ({ ...v, [key]: e.target.value }))}
                                    placeholder="Enter value…"
                                    style={{ ...s.input, flex: 1, fontSize: 12 }}
                                  />
                                ) : (
                                  <div style={{ flex: 1, padding: "9px 12px", background: "#e0f2fe", borderRadius: 8, fontSize: 12, color: "#0369a1", border: "1px solid #bae6fd" }}>
                                    Auto-filled from contact
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    <Field label="Sender Phone Number">
                      <select value={form.phone_number_id} onChange={e => setForm(f => ({ ...f, phone_number_id: e.target.value }))} required style={s.input}>
                        <option value="">Select phone…</option>
                        {phones.map(p => <option key={p.id} value={p.id}>{p.display_name ?? p.display_number ?? p.phone_number_id}</option>)}
                      </select>
                    </Field>
                    <button type="submit" disabled={busy} style={busy ? { ...s.btnGreen, opacity: 0.6 } : s.btnGreen}>{busy ? "Creating…" : "Create & Add Recipients →"}</button>
                  </form>
                </div>

                {/* Right: WhatsApp preview */}
                <div style={{ width: 260, background: "#f0f2f5", borderLeft: "1px solid #e5e7eb", display: "flex", flexDirection: "column", alignItems: "center", padding: "20px 16px", flexShrink: 0 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "#9ca3af", textTransform: "uppercase" as const, letterSpacing: "0.05em", marginBottom: 16 }}>Message Preview</div>
                  {/* Phone frame */}
                  <div style={{ width: 220, background: "#111827", borderRadius: 32, padding: "10px 6px", boxShadow: "0 8px 32px rgba(0,0,0,0.18)" }}>
                    {/* Status bar */}
                    <div style={{ background: "#25D366", borderRadius: "24px 24px 0 0", padding: "6px 12px 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 9, color: "#fff", fontWeight: 600 }}>9:41</span>
                      <div style={{ width: 40, height: 6, background: "#111827", borderRadius: 99, margin: "0 auto" }} />
                      <span style={{ fontSize: 9, color: "#fff" }}>●●●</span>
                    </div>
                    {/* Chat header */}
                    <div style={{ background: "#075e54", padding: "6px 10px", display: "flex", alignItems: "center", gap: 8 }}>
                      <div style={{ width: 28, height: 28, borderRadius: "50%", background: "#25D366", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, color: "#fff", fontWeight: 700, flexShrink: 0 }}>W</div>
                      <div>
                        <div style={{ fontSize: 10, fontWeight: 700, color: "#fff" }}>{phoneName(form.phone_number_id) || "Your Number"}</div>
                        <div style={{ fontSize: 8, color: "#b2dfdb" }}>online</div>
                      </div>
                    </div>
                    {/* Chat body */}
                    <div style={{ background: "#e5ddd5", minHeight: 280, padding: "10px 6px", backgroundImage: "url(\"data:image/svg+xml,%3Csvg width='40' height='40' viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='%23c5b9a9' fill-opacity='0.15'%3E%3Cpath d='M20 20h20v20H20zM0 0h20v20H0z'/%3E%3C/g%3E%3C/svg%3E\")" }}>
                      {!selectedTpl ? (
                        <div style={{ textAlign: "center", color: "#9ca3af", fontSize: 11, paddingTop: 40 }}>Select a template to preview</div>
                      ) : (
                        <div style={{ background: "#fff", borderRadius: "8px 8px 8px 0", padding: "8px 10px", maxWidth: "92%", boxShadow: "0 1px 2px rgba(0,0,0,0.1)", fontSize: 11, lineHeight: 1.5, color: "#111827" }}>
                          {preview.header && (
                            <div style={{ fontWeight: 700, marginBottom: 5, color: "#111827", fontSize: 11 }}>{preview.header}</div>
                          )}
                          {preview.body && (
                            <div style={{ whiteSpace: "pre-wrap", color: "#374151" }}>{preview.body}</div>
                          )}
                          {preview.footer && (
                            <div style={{ marginTop: 4, fontSize: 10, color: "#9ca3af" }}>{preview.footer}</div>
                          )}
                          <div style={{ textAlign: "right", fontSize: 9, color: "#9ca3af", marginTop: 4 }}>
                            {new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} ✓✓
                          </div>
                          {preview.buttons.length > 0 && (
                            <div style={{ marginTop: 6, borderTop: "1px solid #f3f4f6", paddingTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
                              {preview.buttons.map((btn, i) => (
                                <div key={i} style={{ textAlign: "center", color: "#0099ff", fontSize: 11, fontWeight: 600 }}>{btn}</div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                  {selectedTpl && (
                    <div style={{ marginTop: 12, fontSize: 10, color: "#9ca3af", textAlign: "center" }}>
                      Contact Name shown as "John Doe" for preview
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Add recipients modal */}
      {modal === "recipients" && selected && (
        <ModalWrap title={`Add Recipients — ${selected.name}`} onClose={() => setModal(null)}>
          {error && <div style={{ ...s.error, marginBottom: 12 }}>{error}</div>}
          <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 16 }}>
            Current recipients: <b style={{ color: "#111827" }}>{selected.total_recipients}</b>
          </div>
          <form onSubmit={handleAddRecipients} style={s.form}>
            <Field label="Add From">
              <div style={{ display: "flex", gap: 8 }}>
                {[["all_opted_in", "All Opted-in"], ["tag", "By Tag"], ["phones", "Phone List"]] .map(([v, l]) => (
                  <label key={v} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 13, cursor: "pointer" }}>
                    <input type="radio" value={v} checked={addMode === v} onChange={() => setAddMode(v as typeof addMode)} />
                    {l}
                  </label>
                ))}
              </div>
            </Field>
            {addMode === "tag" && (
              <Field label="Tag">
                <select value={addTag} onChange={e => setAddTag(e.target.value)} required style={s.input}>
                  <option value="">Select tag…</option>
                  {tags.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </Field>
            )}
            {addMode === "phones" && (
              <Field label="Phone Numbers (one per line or comma-separated)">
                <textarea value={addPhones} onChange={e => setAddPhones(e.target.value)} rows={5}
                  placeholder="+919876543210&#10;+918511511577" required
                  style={{ ...s.input, resize: "vertical", fontFamily: "monospace", fontSize: 12 }} />
              </Field>
            )}
            <button type="submit" disabled={busy} style={busy ? { ...s.btnGreen, opacity: 0.6 } : s.btnGreen}>{busy ? "Adding…" : "Add Recipients"}</button>
          </form>
          {selected.total_recipients > 0 && selected.status === "draft" && (
            <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid #f3f4f6" }}>
              <button onClick={() => handleLaunch(selected)} disabled={busy} style={{ ...s.btnGreen, width: "100%" }}>
                🚀 Launch Now ({selected.total_recipients} recipients)
              </button>
            </div>
          )}
        </ModalWrap>
      )}

      {/* Detail / stats modal */}
      {modal === "detail" && selected && (
        <ModalWrap title={`${selected.name} — Stats`} onClose={() => { setModal(null); setSelected(null); }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 20 }}>
            {[
              { label: "Total", value: selected.total_recipients, color: "#6b7280" },
              { label: "Sent", value: selected.sent_count, color: "#3b82f6" },
              { label: "Delivered", value: selected.delivered_count, color: "#25D366" },
              { label: "Read", value: selected.read_count, color: "#128C4B" },
              { label: "Failed", value: selected.failed_count, color: "#ef4444" },
              { label: "Pending", value: selected.total_recipients - selected.sent_count - selected.failed_count, color: "#9ca3af" },
            ].map(stat => (
              <div key={stat.label} style={{ textAlign: "center" as const, padding: "12px 8px", background: "#f9fafb", borderRadius: 8 }}>
                <div style={{ fontSize: 24, fontWeight: 800, color: stat.color }}>{stat.value}</div>
                <div style={{ fontSize: 11, color: "#9ca3af", fontWeight: 600, textTransform: "uppercase" as const, marginTop: 2 }}>{stat.label}</div>
              </div>
            ))}
          </div>

          {/* Rates */}
          {selected.sent_count > 0 && (
            <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
              {[
                { label: "Delivery Rate", value: pct(selected.delivered_count, selected.sent_count), color: "#25D366" },
                { label: "Read Rate", value: pct(selected.read_count, selected.sent_count), color: "#128C4B" },
                { label: "Failure Rate", value: pct(selected.failed_count, selected.sent_count), color: "#ef4444" },
              ].map(r => (
                <div key={r.label} style={{ flex: 1, padding: "10px", background: "#f9fafb", borderRadius: 8, textAlign: "center" as const }}>
                  <div style={{ fontSize: 20, fontWeight: 800, color: r.color }}>{r.value}</div>
                  <div style={{ fontSize: 11, color: "#9ca3af" }}>{r.label}</div>
                </div>
              ))}
            </div>
          )}

          {/* Recipients sample */}
          {recipients.length > 0 && (
            <>
              <div style={s.fieldLabel}>Recipients ({recipientsTotal})</div>
              <div style={{ maxHeight: 240, overflowY: "auto", marginTop: 8, border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 12 }}>
                {recipients.map(r => (
                  <div key={r.id} style={{ display: "flex", alignItems: "center", padding: "8px 12px", borderBottom: "1px solid #f3f4f6", gap: 10 }}>
                    <span style={{ fontFamily: "monospace", flex: 1 }}>{r.phone}</span>
                    <RecipientBadge status={r.status} />
                    {r.error_message && <span style={{ color: "#b91c1c", fontSize: 11, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.error_message}</span>}
                  </div>
                ))}
              </div>
            </>
          )}
        </ModalWrap>
      )}
    </AppLayout>
  );
}

function RecipientBadge({ status }: { status: string }) {
  const map: Record<string, [string, string]> = {
    queued:    ["#f3f4f6", "#374151"],
    sent:      ["#dbeafe", "#1d4ed8"],
    delivered: ["#dcfce7", "#15803d"],
    read:      ["#dcfce7", "#128C4B"],
    failed:    ["#fee2e2", "#b91c1c"],
  };
  const [bg, color] = map[status] ?? ["#f3f4f6", "#374151"];
  return <span style={{ padding: "2px 8px", borderRadius: 999, fontSize: 10, fontWeight: 600, background: bg, color, flexShrink: 0 }}>{status}</span>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><label style={{ fontSize: 13, fontWeight: 500, color: "#374151" }}>{label}</label>{children}</div>;
}
function ModalWrap({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 16 }}>
      <div style={{ background: "#fff", borderRadius: 16, padding: "28px 32px", width: "100%", maxWidth: 540, maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#111827" }}>{title}</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#6b7280" }}>✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  header:    { display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24, gap: 16 },
  pageTitle: { fontSize: 24, fontWeight: 700, color: "#111827", margin: "0 0 4px" },
  pageSubtitle: { fontSize: 14, color: "#6b7280", margin: 0 },
  btnGreen:  { padding: "9px 16px", background: "#25D366", color: "#fff", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer" },
  error:     { marginBottom: 16, padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, color: "#991b1b", fontSize: 13, display: "flex", justifyContent: "space-between", alignItems: "center" },
  success:   { marginBottom: 16, padding: "10px 14px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, color: "#166534", fontSize: 13 },
  closeBtn:  { background: "none", border: "none", cursor: "pointer", color: "#991b1b", fontSize: 16, marginLeft: 8 },
  loading:   { color: "#6b7280", fontSize: 14, padding: "40px 0" },
  empty:     { textAlign: "center", padding: "60px 20px", background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" },
  card:      { background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb", padding: "16px 20px" },
  tinyBtn:   { padding: "5px 12px", border: "1px solid #e5e7eb", borderRadius: 6, background: "#f9fafb", color: "#374151", fontSize: 12, fontWeight: 500, cursor: "pointer" },
  form:      { display: "flex", flexDirection: "column", gap: 14 },
  input:     { padding: "9px 12px", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 13, color: "#111827", outline: "none" },
  fieldLabel:{ fontSize: 11, color: "#9ca3af", fontWeight: 600, textTransform: "uppercase" as const, letterSpacing: "0.05em" },
};
