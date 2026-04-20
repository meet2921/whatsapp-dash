"use client";

import { useEffect, useRef, useState } from "react";
import { AppLayout } from "@/components/AppLayout";
import { contacts as contactsApi } from "@/lib/api";
import type { Contact, ContactTag, ContactsPage } from "@/types/api";

type Modal = "create" | "edit" | "tags" | null;

const TAG_COLORS = ["#25D366","#3b82f6","#f59e0b","#ef4444","#8b5cf6","#14b8a6","#f97316"];

export default function ContactsPage() {
  const [page, setPage] = useState<ContactsPage | null>(null);
  const [tags, setTags] = useState<ContactTag[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterTag, setFilterTag] = useState("");
  const [filterOpted, setFilterOpted] = useState<"" | "true" | "false">("");
  const [offset, setOffset] = useState(0);
  const LIMIT = 50;

  const [modal, setModal] = useState<Modal>(null);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<{ inserted: number; updated: number; skipped: number; errors: string[] } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Bulk selection
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [selectAll, setSelectAll] = useState(false); // "select all N across all pages" mode

  const [form, setForm] = useState({ phone: "", name: "", email: "", language: "en", is_opted_in: true });
  const [newTag, setNewTag] = useState({ name: "", color: TAG_COLORS[0] });

  const notify = (msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(null), 4000); };

  const load = async () => {
    setLoading(true);
    try {
      const [p, t] = await Promise.all([
        contactsApi.list({
          search: search || undefined,
          tag_id: filterTag || undefined,
          opted_in: filterOpted === "" ? undefined : filterOpted === "true",
          limit: LIMIT,
          offset,
        }),
        contactsApi.listTags(),
      ]);
      setPage(p);
      setTags(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [search, filterTag, filterOpted, offset]);
  // Clear selection when filters/page change
  useEffect(() => { setCheckedIds(new Set()); setSelectAll(false); }, [search, filterTag, filterOpted, offset]);

  async function handleCreate(e: React.SyntheticEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      await contactsApi.create({ ...form });
      notify("Contact created!"); setModal(null); setForm({ phone: "", name: "", email: "", language: "en", is_opted_in: true }); load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleEdit(e: React.SyntheticEvent) {
    e.preventDefault(); if (!selected) return;
    setBusy(true); setError(null);
    try {
      await contactsApi.update(selected.id, {
        name: form.name || undefined,
        email: form.email || undefined,
        language: form.language,
        is_opted_in: form.is_opted_in,
      });
      notify("Contact updated!"); setModal(null); load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleDelete(c: Contact) {
    if (!confirm(`Delete contact ${c.phone}?`)) return;
    setBusy(true);
    try { await contactsApi.delete(c.id); notify("Deleted."); load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleBulkDelete() {
    const total = selectAll ? (page?.total ?? 0) : checkedIds.size;
    if (!confirm(`Delete ${total} contact${total !== 1 ? "s" : ""}? This cannot be undone.`)) return;
    setBusy(true); setError(null);
    try {
      let result: { deleted: number };
      if (selectAll) {
        result = await contactsApi.bulkDelete({
          all_matching: true,
          search: search || undefined,
          tag_id: filterTag || undefined,
          opted_in: filterOpted === "" ? undefined : filterOpted === "true",
        });
      } else {
        result = await contactsApi.bulkDelete({ ids: Array.from(checkedIds) });
      }
      notify(`Deleted ${result.deleted} contact${result.deleted !== 1 ? "s" : ""}.`);
      setCheckedIds(new Set()); setSelectAll(false);
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true); setError(null); setImportResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await contactsApi.import(fd);
      setImportResult(res);
      notify(`Imported: ${res.inserted} new, ${res.updated} updated`);
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "Import failed"); }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  }

  async function handleCreateTag(e: React.SyntheticEvent) {
    e.preventDefault(); setBusy(true);
    try {
      await contactsApi.createTag(newTag);
      notify("Tag created!"); setNewTag({ name: "", color: TAG_COLORS[0] });
      const t = await contactsApi.listTags(); setTags(t);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleDeleteTag(tag: ContactTag) {
    if (!confirm(`Delete tag "${tag.name}"?`)) return;
    try {
      await contactsApi.deleteTag(tag.id);
      const t = await contactsApi.listTags(); setTags(t);
      notify("Tag deleted.");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  }

  async function toggleTag(contact: Contact, tag: ContactTag) {
    const has = contact.tags.some(t => t.id === tag.id);
    try {
      if (has) await contactsApi.removeTag(contact.id, tag.id);
      else await contactsApi.addTag(contact.id, tag.id);
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  }

  function openEdit(c: Contact) {
    setSelected(c);
    setForm({ phone: c.phone, name: c.name ?? "", email: c.email ?? "", language: c.language, is_opted_in: c.is_opted_in });
    setModal("edit");
  }

  // Checkbox helpers
  const pageIds = page?.items.map(c => c.id) ?? [];
  const allPageChecked = pageIds.length > 0 && pageIds.every(id => checkedIds.has(id));
  const somePageChecked = pageIds.some(id => checkedIds.has(id));

  function togglePageAll() {
    if (allPageChecked) {
      const next = new Set(checkedIds);
      pageIds.forEach(id => next.delete(id));
      setCheckedIds(next); setSelectAll(false);
    } else {
      const next = new Set(checkedIds);
      pageIds.forEach(id => next.add(id));
      setCheckedIds(next);
    }
  }

  function toggleRow(id: string) {
    const next = new Set(checkedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    setCheckedIds(next);
    if (selectAll) setSelectAll(false);
  }

  const anySelected = selectAll || checkedIds.size > 0;
  const selectionLabel = selectAll ? `All ${page?.total ?? 0} contacts selected` : `${checkedIds.size} selected`;

  const totalPages = Math.ceil((page?.total ?? 0) / LIMIT);
  const currentPage = Math.floor(offset / LIMIT) + 1;

  return (
    <AppLayout>
      <div style={{ maxWidth: 1100 }}>
        {/* Header */}
        <div style={s.header}>
          <div>
            <h1 style={s.pageTitle}>Contacts</h1>
            <p style={s.pageSubtitle}>{page?.total ?? "–"} contacts · {tags.length} tags</p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={() => setModal("tags")} style={s.btnOutline}>🏷 Tags</button>
            <button onClick={() => fileRef.current?.click()} disabled={busy} style={s.btnOutline}>⬆ Import CSV / Excel</button>
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" style={{ display: "none" }} onChange={handleImport} />
            <button onClick={() => { setError(null); setModal("create"); }} style={s.btnGreen}>+ New Contact</button>
          </div>
        </div>

        {/* Alerts */}
        {error && <div style={s.error}>{error}<button onClick={() => setError(null)} style={s.closeBtn}>✕</button></div>}
        {success && <div style={s.success}>{success}</div>}
        {importResult && (
          <div style={{ ...s.success, display: "block" }}>
            Import complete: <b>{importResult.inserted}</b> new · <b>{importResult.updated}</b> updated · <b>{importResult.skipped}</b> skipped
            {importResult.errors.length > 0 && <div style={{ color: "#b91c1c", marginTop: 4, fontSize: 12 }}>{importResult.errors.slice(0, 3).join(" · ")}</div>}
            <button onClick={() => setImportResult(null)} style={{ ...s.closeBtn, marginLeft: 8 }}>✕</button>
          </div>
        )}

        {/* CSV hint */}
        <div style={s.hint}>CSV or Excel columns: <code>phone, name, email, language, opted_in</code> — phone is required (E.164 or with country code). Any encoding accepted.</div>

        {/* Filters */}
        <div style={{ display: "flex", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
          <input value={search} onChange={e => { setSearch(e.target.value); setOffset(0); }}
            placeholder="Search phone, name, email…" style={{ ...s.input, flex: 1, minWidth: 200 }} />
          <select value={filterTag} onChange={e => { setFilterTag(e.target.value); setOffset(0); }} style={s.select}>
            <option value="">All tags</option>
            {tags.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <select value={filterOpted} onChange={e => { setFilterOpted(e.target.value as "" | "true" | "false"); setOffset(0); }} style={s.select}>
            <option value="">Opt-in: all</option>
            <option value="true">Opted in</option>
            <option value="false">Opted out</option>
          </select>
        </div>

        {/* Bulk action bar */}
        {anySelected && (
          <div style={s.bulkBar}>
            <span style={{ fontSize: 13, color: "#374151", fontWeight: 500 }}>{selectionLabel}</span>
            {/* Offer "select all N" when all on current page are checked but not in select-all mode */}
            {allPageChecked && !selectAll && (page?.total ?? 0) > pageIds.length && (
              <button onClick={() => setSelectAll(true)} style={s.bulkLink}>
                Select all {page?.total} contacts matching current filters
              </button>
            )}
            {selectAll && (
              <button onClick={() => { setSelectAll(false); setCheckedIds(new Set()); }} style={s.bulkLink}>
                Clear selection
              </button>
            )}
            <button onClick={handleBulkDelete} disabled={busy} style={s.btnDanger}>
              {busy ? "Deleting…" : `🗑 Delete ${selectAll ? `all ${page?.total}` : checkedIds.size}`}
            </button>
          </div>
        )}

        {/* Table */}
        {loading ? (
          <div style={s.loading}>Loading contacts…</div>
        ) : !page || page.items.length === 0 ? (
          <div style={s.empty}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>👤</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: "#374151", marginBottom: 8 }}>No contacts yet</div>
            <div style={{ color: "#9ca3af", fontSize: 14, marginBottom: 20 }}>Import a CSV or create contacts manually</div>
            <button onClick={() => setModal("create")} style={s.btnGreen}>Add First Contact</button>
          </div>
        ) : (
          <>
            <div style={s.tableWrap}>
              <table style={s.table}>
                <thead>
                  <tr style={{ background: "#f9fafb" }}>
                    <th style={{ ...s.th, width: 40, textAlign: "center" as const }}>
                      <input
                        type="checkbox"
                        checked={allPageChecked}
                        ref={el => { if (el) el.indeterminate = somePageChecked && !allPageChecked; }}
                        onChange={togglePageAll}
                        style={{ cursor: "pointer" }}
                      />
                    </th>
                    {["Phone", "Name", "Email", "Tags", "Opt-in", ""].map(h => (
                      <th key={h} style={s.th}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((c, i) => (
                    <tr key={c.id} style={{ background: checkedIds.has(c.id) ? "#eff6ff" : (i % 2 === 0 ? "#fff" : "#f9fafb") }}>
                      <td style={{ ...s.td, textAlign: "center" as const, width: 40 }}>
                        <input
                          type="checkbox"
                          checked={checkedIds.has(c.id)}
                          onChange={() => toggleRow(c.id)}
                          style={{ cursor: "pointer" }}
                        />
                      </td>
                      <td style={s.td}><span style={s.mono}>{c.phone}</span></td>
                      <td style={s.td}>{c.name ?? <span style={{ color: "#9ca3af" }}>—</span>}</td>
                      <td style={s.td}>{c.email ?? <span style={{ color: "#9ca3af" }}>—</span>}</td>
                      <td style={s.td}>
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {c.tags.map(t => (
                            <span key={t.id} style={{ ...s.tag, background: t.color ?? "#e5e7eb", color: "#fff" }}>{t.name}</span>
                          ))}
                        </div>
                      </td>
                      <td style={s.td}>
                        <span style={{ ...s.badge, background: c.is_opted_in ? "#dcfce7" : "#fee2e2", color: c.is_opted_in ? "#15803d" : "#b91c1c" }}>
                          {c.is_opted_in ? "✓ In" : "✗ Out"}
                        </span>
                      </td>
                      <td style={{ ...s.td, textAlign: "right" }}>
                        <button onClick={() => { setSelected(c); setModal("tags"); }} style={s.tinyBtn}>Tag</button>
                        <button onClick={() => openEdit(c)} style={{ ...s.tinyBtn, marginLeft: 4 }}>Edit</button>
                        <button onClick={() => handleDelete(c)} disabled={busy} style={{ ...s.tinyBtn, marginLeft: 4, color: "#b91c1c" }}>Del</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginTop: 16 }}>
                <button onClick={() => setOffset(Math.max(0, offset - LIMIT))} disabled={offset === 0} style={s.btnOutline}>← Prev</button>
                <span style={{ fontSize: 13, color: "#6b7280" }}>Page {currentPage} of {totalPages} ({page.total} total)</span>
                <button onClick={() => setOffset(offset + LIMIT)} disabled={offset + LIMIT >= page.total} style={s.btnOutline}>Next →</button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Create modal */}
      {modal === "create" && (
        <ModalWrap title="New Contact" onClose={() => setModal(null)}>
          {error && <div style={{ ...s.error, marginBottom: 12 }}>{error}</div>}
          <form onSubmit={handleCreate} style={s.form}>
            <Field label="Phone (E.164)"><input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} placeholder="+919876543210" required style={s.input} /></Field>
            <Field label="Name"><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="John Doe" style={s.input} /></Field>
            <Field label="Email"><input value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="john@example.com" style={s.input} /></Field>
            <Field label="Language">
              <select value={form.language} onChange={e => setForm(f => ({ ...f, language: e.target.value }))} style={s.input}>
                {["en", "en_US", "hi", "ar", "es", "pt_BR"].map(l => <option key={l} value={l}>{l}</option>)}
              </select>
            </Field>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#374151" }}>
              <input type="checkbox" checked={form.is_opted_in} onChange={e => setForm(f => ({ ...f, is_opted_in: e.target.checked }))} />
              Opted in to receive messages
            </label>
            <button type="submit" disabled={busy} style={busy ? { ...s.btnGreen, opacity: 0.6 } : s.btnGreen}>{busy ? "Creating…" : "Create Contact"}</button>
          </form>
        </ModalWrap>
      )}

      {/* Edit modal */}
      {modal === "edit" && selected && (
        <ModalWrap title={`Edit ${selected.phone}`} onClose={() => setModal(null)}>
          {error && <div style={{ ...s.error, marginBottom: 12 }}>{error}</div>}
          <form onSubmit={handleEdit} style={s.form}>
            <Field label="Name"><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="John Doe" style={s.input} /></Field>
            <Field label="Email"><input value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="john@example.com" style={s.input} /></Field>
            <Field label="Language">
              <select value={form.language} onChange={e => setForm(f => ({ ...f, language: e.target.value }))} style={s.input}>
                {["en", "en_US", "hi", "ar", "es", "pt_BR"].map(l => <option key={l} value={l}>{l}</option>)}
              </select>
            </Field>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#374151" }}>
              <input type="checkbox" checked={form.is_opted_in} onChange={e => setForm(f => ({ ...f, is_opted_in: e.target.checked }))} />
              Opted in
            </label>
            <button type="submit" disabled={busy} style={busy ? { ...s.btnGreen, opacity: 0.6 } : s.btnGreen}>{busy ? "Saving…" : "Save Changes"}</button>
          </form>
        </ModalWrap>
      )}

      {/* Tags modal */}
      {modal === "tags" && (
        <ModalWrap title={selected ? `Tags for ${selected.phone}` : "Manage Tags"} onClose={() => { setModal(null); setSelected(null); }}>
          {error && <div style={{ ...s.error, marginBottom: 12 }}>{error}</div>}

          {selected && (
            <div style={{ marginBottom: 20 }}>
              <div style={s.fieldLabel}>Assigned Tags</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                {tags.map(tag => {
                  const has = selected.tags.some(t => t.id === tag.id);
                  return (
                    <button key={tag.id} onClick={() => toggleTag(selected, tag)}
                      style={{ padding: "4px 12px", borderRadius: 999, fontSize: 12, fontWeight: 600, cursor: "pointer", border: "2px solid " + (tag.color ?? "#6b7280"), background: has ? (tag.color ?? "#6b7280") : "transparent", color: has ? "#fff" : (tag.color ?? "#6b7280") }}>
                      {tag.name}
                    </button>
                  );
                })}
                {tags.length === 0 && <span style={{ color: "#9ca3af", fontSize: 13 }}>No tags yet. Create one below.</span>}
              </div>
            </div>
          )}

          <div style={s.fieldLabel}>All Tags</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6, marginBottom: 16 }}>
            {tags.map(tag => (
              <div key={tag.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 12, height: 12, borderRadius: "50%", background: tag.color ?? "#6b7280", flexShrink: 0 }} />
                <span style={{ flex: 1, fontSize: 13, fontWeight: 500, color: "#374151" }}>{tag.name}</span>
                <button onClick={() => handleDeleteTag(tag)} style={{ fontSize: 11, color: "#b91c1c", background: "none", border: "none", cursor: "pointer" }}>Delete</button>
              </div>
            ))}
          </div>

          <div style={s.fieldLabel}>Create Tag</div>
          <form onSubmit={handleCreateTag} style={{ display: "flex", gap: 8, marginTop: 6, alignItems: "center" }}>
            <input value={newTag.name} onChange={e => setNewTag(n => ({ ...n, name: e.target.value }))} placeholder="Tag name" required style={{ ...s.input, flex: 1 }} />
            <div style={{ display: "flex", gap: 4 }}>
              {TAG_COLORS.map(c => (
                <button key={c} type="button" onClick={() => setNewTag(n => ({ ...n, color: c }))}
                  style={{ width: 20, height: 20, borderRadius: "50%", background: c, border: newTag.color === c ? "2px solid #111" : "2px solid transparent", cursor: "pointer", padding: 0 }} />
              ))}
            </div>
            <button type="submit" disabled={busy} style={{ ...s.btnGreen, padding: "7px 14px", fontSize: 12 }}>Add</button>
          </form>
        </ModalWrap>
      )}
    </AppLayout>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><label style={{ fontSize: 13, fontWeight: 500, color: "#374151" }}>{label}</label>{children}</div>;
}
function ModalWrap({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 16 }}>
      <div style={{ background: "#fff", borderRadius: 16, padding: "28px 32px", width: "100%", maxWidth: 500, maxHeight: "90vh", overflowY: "auto" }}>
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
  header:    { display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20, gap: 16 },
  pageTitle: { fontSize: 24, fontWeight: 700, color: "#111827", margin: "0 0 4px" },
  pageSubtitle: { fontSize: 14, color: "#6b7280", margin: 0 },
  btnGreen:  { padding: "9px 16px", background: "#25D366", color: "#fff", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer" },
  btnOutline:{ padding: "9px 14px", background: "#fff", color: "#374151", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: "pointer" },
  btnDanger: { padding: "7px 14px", background: "#ef4444", color: "#fff", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer" },
  bulkBar:   { display: "flex", alignItems: "center", gap: 12, marginBottom: 10, padding: "8px 14px", background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8, flexWrap: "wrap" as const },
  bulkLink:  { background: "none", border: "none", color: "#2563eb", fontSize: 13, cursor: "pointer", textDecoration: "underline", padding: 0 },
  error:     { marginBottom: 16, padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, color: "#991b1b", fontSize: 13, display: "flex", justifyContent: "space-between", alignItems: "center" },
  success:   { marginBottom: 16, padding: "10px 14px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, color: "#166534", fontSize: 13, display: "flex", alignItems: "center", justifyContent: "space-between" },
  closeBtn:  { background: "none", border: "none", cursor: "pointer", color: "#991b1b", fontSize: 16, marginLeft: 8 },
  loading:   { color: "#6b7280", fontSize: 14, padding: "40px 0" },
  empty:     { textAlign: "center", padding: "60px 20px", background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" },
  hint:      { fontSize: 12, color: "#9ca3af", background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 6, padding: "6px 12px", marginBottom: 14 },
  tableWrap: { background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb", overflow: "hidden" },
  table:     { width: "100%", borderCollapse: "collapse" },
  th:        { padding: "10px 16px", textAlign: "left" as const, fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase" as const, letterSpacing: "0.05em", borderBottom: "1px solid #e5e7eb" },
  td:        { padding: "11px 16px", fontSize: 13, color: "#374151", borderBottom: "1px solid #f3f4f6", verticalAlign: "middle" },
  mono:      { fontFamily: "monospace", fontSize: 12 },
  badge:     { padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600 },
  tag:       { padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600 },
  tinyBtn:   { padding: "4px 10px", border: "1px solid #e5e7eb", borderRadius: 6, background: "#f9fafb", color: "#374151", fontSize: 11, cursor: "pointer" },
  form:      { display: "flex", flexDirection: "column", gap: 14 },
  input:     { padding: "9px 12px", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 13, color: "#111827", outline: "none" },
  select:    { padding: "9px 12px", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 13, color: "#111827", background: "#fff" },
  fieldLabel:{ fontSize: 11, color: "#9ca3af", fontWeight: 600, textTransform: "uppercase" as const, letterSpacing: "0.05em" },
};
