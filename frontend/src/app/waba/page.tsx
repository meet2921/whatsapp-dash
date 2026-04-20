"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/AppLayout";
import { ConnectWhatsApp } from "@/components/ConnectWhatsApp";
import { waba as wabaApi } from "@/lib/api";
import { getToken } from "@/store/auth";
import type { WabaAccount } from "@/types/api";
import type { EmbeddedSignupResult } from "@/hooks/useEmbeddedSignup";

type Modal = "connect_token" | "embedded" | "create" | "update" | "diagnose" | null;

export default function WabaPage() {
  const [wabas, setWabas] = useState<WabaAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<Modal>(null);
  const [selected, setSelected] = useState<WabaAccount | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // connect/token form
  const [tokenInput, setTokenInput] = useState("");
  const [wabaIdInput, setWabaIdInput] = useState("");

  // create form
  const [createForm, setCreateForm] = useState({ business_id: "", name: "", currency: "USD", timezone_id: "1", access_token: "" });

  // update form
  const [updateForm, setUpdateForm] = useState({ access_token: "", business_name: "" });

  const [busy, setBusy] = useState(false);

  const load = () => {
    setLoading(true);
    wabaApi.list().then(setWabas).catch(e => setError(e.message)).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  function notify(msg: string) { setSuccess(msg); setTimeout(() => setSuccess(null), 3000); }

  async function handleConnectToken(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      await wabaApi.connectToken(tokenInput, wabaIdInput);
      notify("WABA connected successfully!"); setModal(null); load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleCreate(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      await wabaApi.create(createForm);
      notify("WABA created on Meta!"); setModal(null); load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleUpdate(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault(); if (!selected) return; setBusy(true); setError(null);
    try {
      await wabaApi.update(selected.id, { access_token: updateForm.access_token || undefined, business_name: updateForm.business_name || undefined });
      notify("WABA updated!"); setModal(null); load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleSync(w: WabaAccount) {
    setBusy(true); setError(null);
    try { await wabaApi.sync(w.id); notify("Synced from Meta!"); load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Sync failed"); }
    finally { setBusy(false); }
  }

  const [diagResult, setDiagResult] = useState<Record<string, unknown> | null>(null);
  const [diagWaba, setDiagWaba] = useState<WabaAccount | null>(null);

  async function handleDiagnose(w: WabaAccount) {
    setBusy(true); setError(null); setDiagResult(null); setDiagWaba(w); setModal("diagnose");
    try {
      const result = await wabaApi.verifyToken(w.id);
      setDiagResult(result);
    } catch (err) { setError(err instanceof Error ? err.message : "Diagnosis failed"); }
    finally { setBusy(false); }
  }

  async function handleDelete(w: WabaAccount) {
    if (!confirm(`Disconnect "${w.business_name ?? w.waba_id}"?`)) return;
    setBusy(true);
    try { await wabaApi.delete(w.id); notify("WABA disconnected."); load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Delete failed"); }
    finally { setBusy(false); }
  }

  function openUpdate(w: WabaAccount) {
    setSelected(w); setUpdateForm({ access_token: "", business_name: w.business_name ?? "" }); setModal("update");
  }

  return (
    <AppLayout>
      <div style={{ maxWidth: 1100 }}>
        <div style={s.header}>
          <div>
            <h1 style={s.pageTitle}>WABA Accounts</h1>
            <p style={s.pageSubtitle}>Manage your WhatsApp Business Accounts</p>
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <Btn onClick={() => setModal("embedded")} green>+ Embedded Signup</Btn>
            <Btn onClick={() => setModal("connect_token")}>+ Connect Token</Btn>
            <Btn onClick={() => setModal("create")}>+ Create New</Btn>
          </div>
        </div>

        {error && <div style={s.error}>{error} <button onClick={() => setError(null)} style={s.closeBtn}>✕</button></div>}
        {success && <div style={s.success}>{success}</div>}

        {loading ? <div style={s.loading}>Loading…</div> : wabas.length === 0 ? (
          <div style={s.emptyState}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>📱</div>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: "#374151" }}>No WABAs connected</div>
            <div style={{ color: "#9ca3af", marginBottom: 20, fontSize: 14 }}>Connect your first WhatsApp Business Account</div>
            <Btn green onClick={() => setModal("embedded")}>Connect with Meta</Btn>
          </div>
        ) : (
          <div style={s.grid}>
            {wabas.map(w => (
              <div key={w.id} style={s.card}>
                <div style={s.cardHeader}>
                  <div style={s.cardIcon}>W</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={s.cardTitle}>{w.business_name ?? "Unnamed WABA"}</div>
                    <div style={s.cardSub}>{w.waba_id}</div>
                  </div>
                  <span style={{ ...s.badge, ...(w.status === "active" ? s.badgeGreen : s.badgeGray) }}>{w.status}</span>
                </div>

                <div style={s.cardBody}>
                  <Field label="Currency" value={w.currency} />
                  <Field label="Timezone" value={w.timezone_id} />
                  <Field label="Review" value={w.account_review_status} />
                  <Field label="Namespace" value={w.message_template_namespace} mono />
                </div>

                <div style={s.cardActions}>
                  <ActionBtn onClick={() => handleSync(w)} disabled={busy}>↻ Sync</ActionBtn>
                  <ActionBtn onClick={() => openUpdate(w)} disabled={busy}>✎ Edit</ActionBtn>
                  <ActionBtn onClick={() => handleDiagnose(w)} disabled={busy}>🔍 Diagnose</ActionBtn>
                  <ActionBtn onClick={() => handleDelete(w)} disabled={busy} danger>✕ Remove</ActionBtn>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modal: Embedded Signup */}
      {modal === "embedded" && (
        <ModalWrap onClose={() => setModal(null)} title="Connect via Embedded Signup">
          <ConnectWhatsApp
            authToken={getToken()}
            onSuccess={(res: EmbeddedSignupResult) => { notify(`${res.wabas_connected} WABA(s) connected!`); setModal(null); load(); }}
          />
        </ModalWrap>
      )}

      {/* Modal: Connect Token */}
      {modal === "connect_token" && (
        <ModalWrap onClose={() => setModal(null)} title="Connect with Token">
          <p style={s.modalDesc}>Use a token from Meta Graph Explorer. Needs <code>whatsapp_business_management</code> permission.</p>
          {error && <div style={s.error}>{error}</div>}
          <form onSubmit={handleConnectToken} style={s.form}>
            <FormField label="Meta Access Token" value={tokenInput} onChange={setTokenInput} placeholder="EAAxxxx..." required />
            <FormField label="WABA ID" value={wabaIdInput} onChange={setWabaIdInput} placeholder="1533509561531653" required />
            <Btn type="submit" green disabled={busy}>{busy ? "Connecting…" : "Connect WABA"}</Btn>
          </form>
        </ModalWrap>
      )}

      {/* Modal: Create New WABA */}
      {modal === "create" && (
        <ModalWrap onClose={() => setModal(null)} title="Create New WABA on Meta">
          <p style={s.modalDesc}>Creates a new WhatsApp Business Account under your Meta Business. Requires a system user token with <code>business_management</code> permission.</p>
          {error && <div style={s.error}>{error}</div>}
          <form onSubmit={handleCreate} style={s.form}>
            <FormField label="Business ID" value={createForm.business_id} onChange={v => setCreateForm(f => ({ ...f, business_id: v }))} placeholder="952335270486240" required />
            <FormField label="WABA Name" value={createForm.name} onChange={v => setCreateForm(f => ({ ...f, name: v }))} placeholder="My WhatsApp Business" required />
            <FormField label="Currency" value={createForm.currency} onChange={v => setCreateForm(f => ({ ...f, currency: v }))} placeholder="USD" required />
            <FormField label="Timezone ID" value={createForm.timezone_id} onChange={v => setCreateForm(f => ({ ...f, timezone_id: v }))} placeholder="1 (UTC) or 292 (IST)" required />
            <FormField label="Access Token" value={createForm.access_token} onChange={v => setCreateForm(f => ({ ...f, access_token: v }))} placeholder="System user token…" required />
            <Btn type="submit" green disabled={busy}>{busy ? "Creating…" : "Create WABA"}</Btn>
          </form>
        </ModalWrap>
      )}

      {/* Modal: Diagnose Token */}
      {modal === "diagnose" && diagWaba && (
        <ModalWrap onClose={() => { setModal(null); setDiagResult(null); }} title={`Token Diagnosis: ${diagWaba.business_name ?? diagWaba.waba_id}`}>
          {busy && <div style={{ color: "#6b7280", fontSize: 14, marginBottom: 12 }}>Running diagnostics…</div>}
          {error && <div style={s.error}>{error}</div>}
          {diagResult && (() => {
            const checks = diagResult.checks as Record<string, Record<string, unknown>> | undefined;
            const perms = checks?.token_permissions ?? {};
            const sysUser = checks?.system_user ?? {};
            const readWaba = checks?.read_waba ?? {};
            const listTpl = checks?.list_templates ?? {};
            const diagnosis = String(diagResult.diagnosis ?? "");
            const isOk = diagnosis.startsWith("OK:");
            return (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <DiagRow label="System user" value={sysUser.name ? `${sysUser.name} (${sysUser.id})` : sysUser.error ? `Error: ${sysUser.error}` : undefined} />
                <DiagRow label="whatsapp_business_messaging" value={perms.whatsapp_business_messaging === "granted"} />
                <DiagRow label="whatsapp_business_management" value={perms.whatsapp_business_management === "granted"} />
                <DiagRow label="WABA readable" value={readWaba.ok as boolean} />
                <DiagRow label="Templates readable" value={listTpl.ok as boolean} />
                <DiagRow label="Templates writable (create)" value={(checks?.create_template as Record<string, unknown>)?.ok as boolean} />
                <div style={{ marginTop: 8, padding: "12px 14px", borderRadius: 8, background: isOk ? "#f0fdf4" : "#fef2f2", border: `1px solid ${isOk ? "#bbf7d0" : "#fecaca"}` }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: isOk ? "#166534" : "#991b1b" }}>
                    {isOk ? "✅" : "❌"} {diagnosis}
                  </div>
                </div>
              </div>
            );
          })()}
        </ModalWrap>
      )}

      {/* Modal: Update WABA */}
      {modal === "update" && selected && (
        <ModalWrap onClose={() => setModal(null)} title={`Edit: ${selected.business_name ?? selected.waba_id}`}>
          {error && <div style={s.error}>{error}</div>}
          <form onSubmit={handleUpdate} style={s.form}>
            <FormField label="Business Name" value={updateForm.business_name} onChange={v => setUpdateForm(f => ({ ...f, business_name: v }))} placeholder="Display name" />
            <FormField label="New Access Token (leave blank to keep current)" value={updateForm.access_token} onChange={v => setUpdateForm(f => ({ ...f, access_token: v }))} placeholder="EAAxxxx..." />
            <Btn type="submit" green disabled={busy}>{busy ? "Saving…" : "Save Changes"}</Btn>
          </form>
        </ModalWrap>
      )}
    </AppLayout>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function DiagRow({ label, value }: { label: string; value: string | boolean | null | undefined }) {
  const ok = value === true;
  const bad = value === false;
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 10px", background: "#f9fafb", borderRadius: 6 }}>
      <span style={{ fontSize: 13, color: "#374151" }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 600, color: ok ? "#15803d" : bad ? "#b91c1c" : "#6b7280" }}>
        {value === true ? "✅ yes" : value === false ? "❌ no" : (value ?? "—")}
      </span>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string | null | undefined; mono?: boolean }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <span style={{ fontSize: 11, color: "#9ca3af", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}: </span>
      <span style={{ fontSize: 12, color: "#374151", fontFamily: mono ? "monospace" : undefined }}>{value ?? "—"}</span>
    </div>
  );
}

function FormField({ label, value, onChange, placeholder, required }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; required?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={{ fontSize: 13, fontWeight: 500, color: "#374151" }}>{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} required={required}
        style={{ padding: "9px 12px", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 14, color: "#111827", outline: "none" }} />
    </div>
  );
}

function Btn({ children, onClick, green, danger, disabled, type }: { children: React.ReactNode; onClick?: () => void; green?: boolean; danger?: boolean; disabled?: boolean; type?: "submit" | "button" }) {
  return (
    <button type={type ?? "button"} onClick={onClick} disabled={disabled} style={{
      padding: "9px 16px", borderRadius: 8, border: "none", fontSize: 13, fontWeight: 600, cursor: disabled ? "not-allowed" : "pointer",
      background: disabled ? "#e5e7eb" : green ? "#25D366" : danger ? "#fee2e2" : "#f3f4f6",
      color: disabled ? "#9ca3af" : green ? "#fff" : danger ? "#b91c1c" : "#374151",
    }}>{children}</button>
  );
}

function ActionBtn({ children, onClick, disabled, danger }: { children: React.ReactNode; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      flex: 1, padding: "7px", border: "1px solid #e5e7eb", borderRadius: 6, background: danger ? "#fef2f2" : "#f9fafb",
      color: danger ? "#b91c1c" : "#374151", fontSize: 12, fontWeight: 500, cursor: disabled ? "not-allowed" : "pointer",
    }}>{children}</button>
  );
}

function ModalWrap({ children, onClose, title }: { children: React.ReactNode; onClose: () => void; title: string }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 16 }}>
      <div style={{ background: "#fff", borderRadius: 16, padding: "28px 32px", width: "100%", maxWidth: 520, maxHeight: "90vh", overflowY: "auto" }}>
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
  header:      { display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24, gap: 16 },
  pageTitle:   { fontSize: 24, fontWeight: 700, color: "#111827", margin: "0 0 4px" },
  pageSubtitle:{ fontSize: 14, color: "#6b7280", margin: 0 },
  loading:     { color: "#6b7280", fontSize: 14 },
  error:       { marginBottom: 16, padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, color: "#991b1b", fontSize: 13, display: "flex", justifyContent: "space-between", alignItems: "center" },
  success:     { marginBottom: 16, padding: "10px 14px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, color: "#166534", fontSize: 13 },
  closeBtn:    { background: "none", border: "none", cursor: "pointer", color: "#991b1b", fontSize: 16 },
  emptyState:  { textAlign: "center", padding: "60px 20px", background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" },
  grid:        { display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(320px,1fr))", gap: 16 },
  card:        { background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb", overflow: "hidden" },
  cardHeader:  { display: "flex", alignItems: "center", gap: 12, padding: "16px 20px", borderBottom: "1px solid #f3f4f6" },
  cardIcon:    { width: 40, height: 40, background: "#dcfce7", color: "#15803d", borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 18, flexShrink: 0 },
  cardTitle:   { fontSize: 14, fontWeight: 600, color: "#111827", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  cardSub:     { fontSize: 11, color: "#9ca3af", fontFamily: "monospace", marginTop: 2 },
  cardBody:    { padding: "14px 20px" },
  cardActions: { display: "flex", gap: 8, padding: "12px 16px", borderTop: "1px solid #f3f4f6", background: "#fafafa" },
  badge:       { padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600, textTransform: "uppercase" },
  badgeGreen:  { background: "#dcfce7", color: "#15803d" },
  badgeGray:   { background: "#f3f4f6", color: "#6b7280" },
  form:        { display: "flex", flexDirection: "column", gap: 14 },
  modalDesc:   { fontSize: 13, color: "#6b7280", marginBottom: 16, lineHeight: 1.6 },
};
