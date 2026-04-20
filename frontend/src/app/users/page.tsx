"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/AppLayout";
import { users as usersApi } from "@/lib/api";
import type { User } from "@/types/api";

type Modal = "create" | "edit" | null;

const ROLES = ["admin", "agent", "viewer"];

export default function UsersPage() {
  const [list, setList] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<Modal>(null);
  const [selected, setSelected] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [createForm, setCreateForm] = useState({ email: "", password: "", full_name: "", role: "agent" });
  const [editForm, setEditForm] = useState({ full_name: "", role: "agent", is_active: true });

  const load = () => {
    setLoading(true);
    usersApi.list()
      .then(setList)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const notify = (msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(null), 3000); };

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      await usersApi.create(createForm);
      notify("User created!"); setModal(null);
      setCreateForm({ email: "", password: "", full_name: "", role: "agent" });
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault(); if (!selected) return; setBusy(true); setError(null);
    try {
      await usersApi.update(selected.id, editForm);
      notify("User updated!"); setModal(null); load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleDelete(u: User) {
    if (!confirm(`Delete user "${u.full_name ?? u.email}"? This cannot be undone.`)) return;
    setBusy(true);
    try { await usersApi.delete(u.id); notify("User deleted."); load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Delete failed"); }
    finally { setBusy(false); }
  }

  function openEdit(u: User) {
    setSelected(u);
    setEditForm({ full_name: u.full_name ?? "", role: u.role, is_active: u.is_active ?? true });
    setModal("edit");
  }

  return (
    <AppLayout>
      <div style={{ maxWidth: 1100 }}>
        <div style={s.header}>
          <div>
            <h1 style={s.pageTitle}>Users</h1>
            <p style={s.pageSubtitle}>Manage team members and their access levels</p>
          </div>
          <button onClick={() => setModal("create")} style={s.btnGreen}>+ Invite User</button>
        </div>

        {error && <div style={s.error}>{error} <button onClick={() => setError(null)} style={s.closeBtn}>✕</button></div>}
        {success && <div style={s.success}>{success}</div>}

        {loading ? <div style={s.loading}>Loading…</div> : list.length === 0 ? (
          <div style={s.emptyState}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>👥</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: "#374151", marginBottom: 8 }}>No users yet</div>
            <button onClick={() => setModal("create")} style={s.btnGreen}>Invite First User</button>
          </div>
        ) : (
          <div style={s.tableWrap}>
            <table style={s.table}>
              <thead>
                <tr>
                  {["Name", "Email", "Role", "Status", "Created", "Actions"].map(h => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {list.map(u => (
                  <tr key={u.id}>
                    <td style={{ ...s.td, fontWeight: 500 }}>{u.full_name ?? "—"}</td>
                    <td style={{ ...s.td, color: "#6b7280" }}>{u.email}</td>
                    <td style={s.td}><RoleBadge role={u.role} /></td>
                    <td style={s.td}>
                      <span style={{
                        padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600,
                        background: u.is_active ? "#dcfce7" : "#f3f4f6",
                        color: u.is_active ? "#15803d" : "#6b7280",
                      }}>
                        {u.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td style={{ ...s.td, fontSize: 12, color: "#9ca3af" }}>
                      {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                    </td>
                    <td style={s.td}>
                      <div style={{ display: "flex", gap: 6 }}>
                        <TinyBtn onClick={() => openEdit(u)} disabled={busy}>Edit</TinyBtn>
                        <TinyBtn onClick={() => handleDelete(u)} disabled={busy} danger>Delete</TinyBtn>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create modal */}
      {modal === "create" && (
        <ModalWrap onClose={() => setModal(null)} title="Invite User">
          {error && <div style={s.error}>{error}</div>}
          <form onSubmit={handleCreate} style={s.form}>
            <Field label="Full Name">
              <input value={createForm.full_name} onChange={e => setCreateForm(f => ({ ...f, full_name: e.target.value }))}
                placeholder="Jane Smith" required style={s.input} />
            </Field>
            <Field label="Email">
              <input type="email" value={createForm.email} onChange={e => setCreateForm(f => ({ ...f, email: e.target.value }))}
                placeholder="jane@company.com" required style={s.input} />
            </Field>
            <Field label="Password">
              <input type="password" value={createForm.password} onChange={e => setCreateForm(f => ({ ...f, password: e.target.value }))}
                placeholder="Min 8 characters" required minLength={8} style={s.input} />
            </Field>
            <Field label="Role">
              <select value={createForm.role} onChange={e => setCreateForm(f => ({ ...f, role: e.target.value }))} style={s.input}>
                {ROLES.map(r => <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
              </select>
            </Field>
            <RoleHint role={createForm.role} />
            <button type="submit" disabled={busy} style={busy ? { ...s.btnGreen, opacity: 0.6 } : s.btnGreen}>
              {busy ? "Creating…" : "Create User"}
            </button>
          </form>
        </ModalWrap>
      )}

      {/* Edit modal */}
      {modal === "edit" && selected && (
        <ModalWrap onClose={() => setModal(null)} title={`Edit: ${selected.full_name ?? selected.email}`}>
          {error && <div style={s.error}>{error}</div>}
          <form onSubmit={handleEdit} style={s.form}>
            <Field label="Full Name">
              <input value={editForm.full_name} onChange={e => setEditForm(f => ({ ...f, full_name: e.target.value }))}
                placeholder="Jane Smith" style={s.input} />
            </Field>
            <Field label="Role">
              <select value={editForm.role} onChange={e => setEditForm(f => ({ ...f, role: e.target.value }))} style={s.input}>
                {ROLES.map(r => <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
              </select>
            </Field>
            <RoleHint role={editForm.role} />
            <Field label="Status">
              <select value={editForm.is_active ? "active" : "inactive"} onChange={e => setEditForm(f => ({ ...f, is_active: e.target.value === "active" }))} style={s.input}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </Field>
            <button type="submit" disabled={busy} style={busy ? { ...s.btnGreen, opacity: 0.6 } : s.btnGreen}>
              {busy ? "Saving…" : "Save Changes"}
            </button>
          </form>
        </ModalWrap>
      )}
    </AppLayout>
  );
}

function RoleHint({ role }: { role: string }) {
  const hints: Record<string, string> = {
    admin: "Full access: manage users, WABAs, templates, and messages.",
    agent: "Can send messages and view conversations. Cannot manage users or WABAs.",
    viewer: "Read-only access to conversations and templates.",
  };
  const hint = hints[role];
  if (!hint) return null;
  return <div style={{ fontSize: 12, color: "#6b7280", padding: "8px 12px", background: "#f9fafb", borderRadius: 6 }}>{hint}</div>;
}

function RoleBadge({ role }: { role: string }) {
  const colors: Record<string, [string, string]> = {
    admin:  ["#dbeafe", "#1d4ed8"],
    agent:  ["#dcfce7", "#15803d"],
    viewer: ["#f3f4f6", "#6b7280"],
  };
  const [bg, color] = colors[role] ?? ["#f3f4f6", "#6b7280"];
  return <span style={{ padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600, background: bg, color }}>{role}</span>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div style={{ display: "flex", flexDirection: "column", gap: 6 }}><label style={{ fontSize: 13, fontWeight: 500, color: "#374151" }}>{label}</label>{children}</div>;
}

function TinyBtn({ children, onClick, disabled, danger }: { children: React.ReactNode; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  return <button onClick={onClick} disabled={disabled} style={{ padding: "5px 10px", border: "1px solid #e5e7eb", borderRadius: 6, background: danger ? "#fef2f2" : "#f9fafb", color: danger ? "#b91c1c" : "#374151", fontSize: 12, cursor: disabled ? "not-allowed" : "pointer" }}>{children}</button>;
}

function ModalWrap({ children, onClose, title }: { children: React.ReactNode; onClose: () => void; title: string }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 16 }}>
      <div style={{ background: "#fff", borderRadius: 16, padding: "28px 32px", width: "100%", maxWidth: 480, maxHeight: "90vh", overflowY: "auto" }}>
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
  loading:   { color: "#6b7280", fontSize: 14 },
  btnGreen:  { padding: "9px 18px", background: "#25D366", color: "#fff", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer" },
  error:     { marginBottom: 16, padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, color: "#991b1b", fontSize: 13, display: "flex", justifyContent: "space-between", alignItems: "center" },
  success:   { marginBottom: 16, padding: "10px 14px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, color: "#166534", fontSize: 13 },
  closeBtn:  { background: "none", border: "none", cursor: "pointer", color: "#991b1b", fontSize: 16 },
  emptyState:{ textAlign: "center", padding: "60px 20px", background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" },
  tableWrap: { background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb", overflowX: "auto" },
  table:     { width: "100%", borderCollapse: "collapse" },
  th:        { padding: "10px 14px", textAlign: "left", fontSize: 12, fontWeight: 600, color: "#6b7280", borderBottom: "1px solid #f3f4f6", whiteSpace: "nowrap" },
  td:        { padding: "12px 14px", fontSize: 13, color: "#374151", borderBottom: "1px solid #f9fafb" },
  form:      { display: "flex", flexDirection: "column", gap: 14 },
  input:     { padding: "9px 12px", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 14, color: "#111827", outline: "none" },
};
