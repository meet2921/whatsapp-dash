"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/AppLayout";
import { phones, waba as wabaApi } from "@/lib/api";
import type { PhoneNumber, WabaAccount } from "@/types/api";

type Modal = "add" | "register" | "verify" | "request_code" | null;

export default function PhoneNumbersPage() {
  const [list, setList] = useState<PhoneNumber[]>([]);
  const [wabas, setWabas] = useState<WabaAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<Modal>(null);
  const [selected, setSelected] = useState<PhoneNumber | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // forms
  const [addForm, setAddForm] = useState({ waba_id: "", phone_number_id: "" });
  const [pin, setPin] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpMethod, setOtpMethod] = useState("SMS");

  const load = () => {
    setLoading(true);
    Promise.all([phones.list(), wabaApi.list()])
      .then(([p, w]) => { setList(p); setWabas(w); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const notify = (msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(null), 3000); };

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      await phones.add(addForm.waba_id, addForm.phone_number_id);
      notify("Phone number added!"); setModal(null); load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleSync(p: PhoneNumber) {
    setBusy(true);
    try { await phones.sync(p.id); notify("Synced!"); load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Sync failed"); }
    finally { setBusy(false); }
  }

  async function handleDelete(p: PhoneNumber) {
    if (!confirm(`Remove ${p.display_number ?? p.phone_number_id}?`)) return;
    setBusy(true);
    try { await phones.delete(p.id); notify("Phone number removed."); load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault(); if (!selected) return; setBusy(true); setError(null);
    try {
      const res = await phones.register(selected.id, pin);
      notify(res.success ? "Registered successfully!" : "Registration failed"); setModal(null);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleDeregister(p: PhoneNumber) {
    if (!confirm("Deregister this number? It will stop sending messages.")) return;
    setBusy(true);
    try {
      const res = await phones.deregister(p.id);
      notify(res.success ? "Deregistered." : "Deregister failed"); load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleRequestCode(e: React.FormEvent) {
    e.preventDefault(); if (!selected) return; setBusy(true); setError(null);
    try {
      const res = await phones.requestCode(selected.id, otpMethod, "en_US");
      notify(res.success ? `OTP sent via ${otpMethod}!` : "Request failed"); setModal("verify");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  async function handleVerifyCode(e: React.FormEvent) {
    e.preventDefault(); if (!selected) return; setBusy(true); setError(null);
    try {
      const res = await phones.verifyCode(selected.id, otpCode);
      notify(res.success ? "Phone verified!" : "Verification failed"); setModal(null); load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setBusy(false); }
  }

  const wabaName = (id: string) => wabas.find(w => w.id === id)?.business_name ?? id.slice(0, 8);

  return (
    <AppLayout>
      <div style={{ maxWidth: 1100 }}>
        <div style={s.header}>
          <div>
            <h1 style={s.pageTitle}>Phone Numbers</h1>
            <p style={s.pageSubtitle}>Manage WhatsApp phone numbers linked to your WABAs</p>
          </div>
          <button onClick={() => setModal("add")} style={s.btnGreen}>+ Add Phone Number</button>
        </div>

        {error && <div style={s.error}>{error} <button onClick={() => setError(null)} style={s.closeBtn}>✕</button></div>}
        {success && <div style={s.success}>{success}</div>}

        {loading ? <div style={s.loading}>Loading…</div> : list.length === 0 ? (
          <div style={s.emptyState}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>☎</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: "#374151", marginBottom: 8 }}>No phone numbers yet</div>
            <button onClick={() => setModal("add")} style={s.btnGreen}>Add Phone Number</button>
          </div>
        ) : (
          <div style={s.tableWrap}>
            <table style={s.table}>
              <thead>
                <tr>{["Number", "Name", "WABA", "Quality", "Limit", "Verification", "Mode", "Active", "Actions"].map(h => <th key={h} style={s.th}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {list.map(p => (
                  <tr key={p.id}>
                    <td style={{ ...s.td, fontWeight: 600 }}>{p.display_number ?? "—"}</td>
                    <td style={s.td}>{p.display_name ?? "—"}</td>
                    <td style={{ ...s.td, fontSize: 11, color: "#9ca3af" }}>{wabaName(p.waba_id)}</td>
                    <td style={s.td}><QBadge q={p.quality_rating} /></td>
                    <td style={s.td}>{p.messaging_limit ?? "—"}</td>
                    <td style={s.td}><SBadge text={p.code_verification_status} green={p.code_verification_status === "VERIFIED"} /></td>
                    <td style={s.td}>{p.account_mode ?? "—"}</td>
                    <td style={s.td}>{p.is_active ? "✅" : "❌"}</td>
                    <td style={{ ...s.td, whiteSpace: "nowrap" }}>
                      <div style={{ display: "flex", gap: 6 }}>
                        <TinyBtn onClick={() => handleSync(p)} disabled={busy}>Sync</TinyBtn>
                        <TinyBtn onClick={() => { setSelected(p); setPin(""); setModal("register"); }} disabled={busy}>Register</TinyBtn>
                        <TinyBtn onClick={() => { setSelected(p); setOtpCode(""); setModal("request_code"); }} disabled={busy}>OTP</TinyBtn>
                        {p.is_active && <TinyBtn onClick={() => handleDeregister(p)} disabled={busy} danger>Dereg.</TinyBtn>}
                        <TinyBtn onClick={() => handleDelete(p)} disabled={busy} danger>✕</TinyBtn>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add modal */}
      {modal === "add" && (
        <Modal onClose={() => setModal(null)} title="Add Phone Number">
          <p style={s.modalDesc}>The phone number must already exist on Meta. We'll fetch all its details automatically.</p>
          {error && <div style={s.error}>{error}</div>}
          <form onSubmit={handleAdd} style={s.form}>
            <div style={s.field}>
              <label style={s.label}>WABA Account</label>
              <select value={addForm.waba_id} onChange={e => setAddForm(f => ({ ...f, waba_id: e.target.value }))} required style={s.input}>
                <option value="">Select WABA…</option>
                {wabas.map(w => <option key={w.id} value={w.id}>{w.business_name ?? w.waba_id}</option>)}
              </select>
            </div>
            <div style={s.field}>
              <label style={s.label}>Meta Phone Number ID</label>
              <input value={addForm.phone_number_id} onChange={e => setAddForm(f => ({ ...f, phone_number_id: e.target.value }))}
                placeholder="e.g. 1083044768220443" required style={s.input} />
            </div>
            <button type="submit" disabled={busy} style={busy ? { ...s.btnGreen, opacity: 0.6 } : s.btnGreen}>{busy ? "Adding…" : "Add Phone Number"}</button>
          </form>
        </Modal>
      )}

      {/* Register modal */}
      {modal === "register" && selected && (
        <Modal onClose={() => setModal(null)} title={`Register ${selected.display_number ?? selected.phone_number_id}`}>
          <p style={s.modalDesc}>Set a 6-digit PIN for this phone number. Store it safely — you'll need it for re-registration.</p>
          {error && <div style={s.error}>{error}</div>}
          <form onSubmit={handleRegister} style={s.form}>
            <div style={s.field}>
              <label style={s.label}>6-digit PIN</label>
              <input type="text" value={pin} onChange={e => setPin(e.target.value)} maxLength={6} pattern="[0-9]{6}" placeholder="123456" required style={s.input} />
            </div>
            <button type="submit" disabled={busy} style={busy ? { ...s.btnGreen, opacity: 0.6 } : s.btnGreen}>{busy ? "Registering…" : "Register"}</button>
          </form>
        </Modal>
      )}

      {/* Request OTP modal */}
      {modal === "request_code" && selected && (
        <Modal onClose={() => setModal(null)} title={`Request OTP — ${selected.display_number ?? selected.phone_number_id}`}>
          {error && <div style={s.error}>{error}</div>}
          <form onSubmit={handleRequestCode} style={s.form}>
            <div style={s.field}>
              <label style={s.label}>OTP Method</label>
              <select value={otpMethod} onChange={e => setOtpMethod(e.target.value)} style={s.input}>
                <option value="SMS">SMS</option>
                <option value="VOICE">Voice Call</option>
              </select>
            </div>
            <button type="submit" disabled={busy} style={busy ? { ...s.btnGreen, opacity: 0.6 } : s.btnGreen}>{busy ? "Sending…" : "Send OTP"}</button>
          </form>
        </Modal>
      )}

      {/* Verify OTP modal */}
      {modal === "verify" && selected && (
        <Modal onClose={() => setModal(null)} title="Verify OTP">
          <p style={s.modalDesc}>Enter the OTP you received.</p>
          {error && <div style={s.error}>{error}</div>}
          <form onSubmit={handleVerifyCode} style={s.form}>
            <div style={s.field}>
              <label style={s.label}>OTP Code</label>
              <input value={otpCode} onChange={e => setOtpCode(e.target.value)} placeholder="123456" required style={s.input} />
            </div>
            <button type="submit" disabled={busy} style={busy ? { ...s.btnGreen, opacity: 0.6 } : s.btnGreen}>{busy ? "Verifying…" : "Verify"}</button>
          </form>
        </Modal>
      )}
    </AppLayout>
  );
}

function QBadge({ q }: { q: string | null }) {
  const c: Record<string, [string, string]> = { GREEN: ["#dcfce7","#15803d"], YELLOW: ["#fef9c3","#a16207"], RED: ["#fee2e2","#b91c1c"] };
  const [bg, color] = c[q ?? ""] ?? ["#f3f4f6","#6b7280"];
  return <span style={{ padding:"2px 8px",borderRadius:999,fontSize:11,fontWeight:600,background:bg,color }}>{q ?? "N/A"}</span>;
}
function SBadge({ text, green }: { text: string | null; green?: boolean }) {
  return <span style={{ padding:"2px 8px",borderRadius:999,fontSize:11,fontWeight:600,background:green?"#dcfce7":"#f3f4f6",color:green?"#15803d":"#6b7280" }}>{text ?? "—"}</span>;
}
function TinyBtn({ children, onClick, disabled, danger }: { children: React.ReactNode; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  return <button onClick={onClick} disabled={disabled} style={{ padding:"4px 8px",border:"1px solid #e5e7eb",borderRadius:6,background:danger?"#fef2f2":"#f9fafb",color:danger?"#b91c1c":"#374151",fontSize:11,cursor:disabled?"not-allowed":"pointer" }}>{children}</button>;
}
function Modal({ children, onClose, title }: { children: React.ReactNode; onClose: () => void; title: string }) {
  return (
    <div style={{ position:"fixed",inset:0,background:"rgba(0,0,0,0.5)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:100,padding:16 }}>
      <div style={{ background:"#fff",borderRadius:16,padding:"28px 32px",width:"100%",maxWidth:480,maxHeight:"90vh",overflowY:"auto" }}>
        <div style={{ display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:20 }}>
          <h2 style={{ margin:0,fontSize:18,fontWeight:700,color:"#111827" }}>{title}</h2>
          <button onClick={onClose} style={{ background:"none",border:"none",fontSize:20,cursor:"pointer",color:"#6b7280" }}>✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  header: { display:"flex",alignItems:"flex-start",justifyContent:"space-between",marginBottom:24,gap:16 },
  pageTitle: { fontSize:24,fontWeight:700,color:"#111827",margin:"0 0 4px" },
  pageSubtitle: { fontSize:14,color:"#6b7280",margin:0 },
  loading: { color:"#6b7280",fontSize:14 },
  btnGreen: { padding:"9px 18px",background:"#25D366",color:"#fff",border:"none",borderRadius:8,fontSize:13,fontWeight:600,cursor:"pointer" },
  error: { marginBottom:16,padding:"10px 14px",background:"#fef2f2",border:"1px solid #fecaca",borderRadius:8,color:"#991b1b",fontSize:13,display:"flex",justifyContent:"space-between",alignItems:"center" },
  success: { marginBottom:16,padding:"10px 14px",background:"#f0fdf4",border:"1px solid #bbf7d0",borderRadius:8,color:"#166534",fontSize:13 },
  closeBtn: { background:"none",border:"none",cursor:"pointer",color:"#991b1b",fontSize:16 },
  emptyState: { textAlign:"center",padding:"60px 20px",background:"#fff",borderRadius:12,border:"1px solid #e5e7eb" },
  tableWrap: { background:"#fff",borderRadius:12,border:"1px solid #e5e7eb",overflowX:"auto" },
  table: { width:"100%",borderCollapse:"collapse" },
  th: { padding:"10px 14px",textAlign:"left",fontSize:12,fontWeight:600,color:"#6b7280",borderBottom:"1px solid #f3f4f6",whiteSpace:"nowrap" },
  td: { padding:"12px 14px",fontSize:13,color:"#374151",borderBottom:"1px solid #f9fafb" },
  form: { display:"flex",flexDirection:"column",gap:14 },
  field: { display:"flex",flexDirection:"column",gap:6 },
  label: { fontSize:13,fontWeight:500,color:"#374151" },
  input: { padding:"9px 12px",border:"1px solid #d1d5db",borderRadius:8,fontSize:14,color:"#111827",outline:"none" },
  modalDesc: { fontSize:13,color:"#6b7280",marginBottom:16,lineHeight:1.6 },
};
