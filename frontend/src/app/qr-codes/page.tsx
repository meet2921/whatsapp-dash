"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/AppLayout";
import { qrCodes as qrApi, phones as phonesApi } from "@/lib/api";
import type { QrCode, PhoneNumber } from "@/types/api";

export default function QrCodesPage() {
  const [list, setList] = useState<QrCode[]>([]);
  const [phones, setPhones] = useState<PhoneNumber[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedPhone, setSelectedPhone] = useState("");
  const [prefilledMsg, setPrefilledMsg] = useState("");

  const load = () => {
    setLoading(true);
    Promise.all([
      qrApi.list().catch(() => [] as QrCode[]),
      phonesApi.list().catch(() => [] as PhoneNumber[]),
    ]).then(([qrs, phs]) => { setList(qrs); setPhones(phs); setError(null); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const notify = (msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(null), 3000); };

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedPhone) { setError("Select a phone number"); return; }
    if (!prefilledMsg.trim()) { setError("Enter a prefilled message"); return; }
    setBusy(true); setError(null);
    try {
      await qrApi.create(selectedPhone, prefilledMsg.trim());
      notify("QR code created!"); setModal(false); setPrefilledMsg(""); setSelectedPhone(""); setError(null); load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed";
      // Surface a clearer message for Meta test number limitation
      const friendly = msg.includes("Unknown path components")
        ? "QR codes are not supported for test/sandbox phone numbers. Please use a verified live WhatsApp Business number."
        : msg;
      setError(friendly);
    }
    finally { setBusy(false); }
  }

  async function handleDelete(qr: QrCode) {
    if (!confirm(`Delete QR code for "${qr.prefilled_message}"?`)) return;
    setBusy(true);
    try {
      await qrApi.delete(qr.code, qr.phone_number_id);
      notify("QR code deleted."); load();
    } catch (err) { setError(err instanceof Error ? err.message : "Delete failed"); }
    finally { setBusy(false); }
  }

  const copy = (text: string) =>
    navigator.clipboard.writeText(text).then(() => notify("Copied!")).catch(() => {});

  return (
    <AppLayout>
      <div style={{ maxWidth: 1100 }}>
        <div style={s.header}>
          <div>
            <h1 style={s.pageTitle}>QR Codes & Entry Points</h1>
            <p style={s.pageSubtitle}>Create WhatsApp QR codes with pre-filled messages for easy customer entry points</p>
          </div>
          <Btn green onClick={() => { setError(null); setModal(true); }}>+ Create QR Code</Btn>
        </div>

        {error && <div style={s.error}>{error}<button onClick={() => setError(null)} style={s.closeBtn}>✕</button></div>}
        {success && <div style={s.success}>{success}</div>}

        {loading ? (
          <div style={s.loading}>Loading QR codes…</div>
        ) : list.length === 0 ? (
          <div style={s.emptyState}>
            <div style={{ fontSize: 52, marginBottom: 12 }}>🔗</div>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: "#374151" }}>No QR codes yet</div>
            <div style={{ color: "#9ca3af", marginBottom: 20, fontSize: 14 }}>
              Create QR codes so customers can start a WhatsApp conversation with a single scan
            </div>
            <Btn green onClick={() => setModal(true)}>Create First QR Code</Btn>
          </div>
        ) : (
          <div style={s.grid}>
            {list.map(qr => (
              <div key={qr.code} style={s.card}>
                <div style={s.cardTop}>
                  {qr.qr_image_url ? (
                    <img src={qr.qr_image_url} alt="QR" style={s.qrImg} />
                  ) : (
                    <div style={s.qrPlaceholder}>🔗</div>
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={s.cardTitle}>{qr.prefilled_message}</div>
                    <div style={s.cardSub}>
                      {qr.display_name && <span>{qr.display_name} · </span>}
                      {qr.display_number ?? qr.phone_number_id}
                    </div>
                    <span style={{ ...s.badge, ...s.badgeGreen, marginTop: 6, display: "inline-block" }}>
                      {qr.code}
                    </span>
                  </div>
                </div>

                <div style={s.cardBody}>
                  <div style={s.fieldLabel}>Deep Link URL</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 12, color: "#374151", fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                      {qr.deep_link_url}
                    </span>
                    <button onClick={() => copy(qr.deep_link_url)} style={s.copyBtn}>Copy</button>
                  </div>
                </div>

                <div style={s.cardActions}>
                  <button onClick={() => copy(qr.deep_link_url)} style={s.actionBtn}>🔗 Copy Link</button>
                  {qr.qr_image_url && (
                    <a href={qr.qr_image_url} download={`qr-${qr.code}.png`} target="_blank" rel="noreferrer"
                      style={{ ...s.actionBtn, textDecoration: "none", textAlign: "center" as const }}>
                      ⬇ Download QR
                    </a>
                  )}
                  <button onClick={() => handleDelete(qr)} disabled={busy} style={{ ...s.actionBtn, color: "#b91c1c", background: "#fef2f2" }}>✕ Delete</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {modal && (
        <div style={s.overlay}>
          <div style={s.modalBox}>
            <div style={s.modalHeader}>
              <h2 style={s.modalTitle}>Create QR Code</h2>
              <button onClick={() => setModal(false)} style={s.modalClose}>✕</button>
            </div>
            <p style={s.modalDesc}>
              Select a phone number and the message that will be pre-filled when a user scans the QR code.
            </p>
            {error && <div style={{ ...s.error, marginBottom: 14 }}>{error}</div>}
            <form onSubmit={handleCreate} style={s.form}>
              <div style={s.formGroup}>
                <label style={s.label}>Phone Number</label>
                <select value={selectedPhone} onChange={e => setSelectedPhone(e.target.value)} required style={s.select}>
                  <option value="">Select a phone number…</option>
                  {phones.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.display_name ? `${p.display_name} (${p.display_number ?? p.phone_number_id})` : (p.display_number ?? p.phone_number_id)}
                    </option>
                  ))}
                </select>
              </div>
              <div style={s.formGroup}>
                <label style={s.label}>Pre-filled Message</label>
                <input value={prefilledMsg} onChange={e => setPrefilledMsg(e.target.value)}
                  placeholder="Hello! I'd like to learn more…" required style={s.input} />
                <span style={{ fontSize: 12, color: "#9ca3af" }}>This message will be pre-typed when a user scans the QR code</span>
              </div>
              <Btn type="submit" green disabled={busy}>{busy ? "Creating…" : "Create QR Code"}</Btn>
            </form>
          </div>
        </div>
      )}
    </AppLayout>
  );
}

function Btn({ children, onClick, green, disabled, type }: { children: React.ReactNode; onClick?: () => void; green?: boolean; disabled?: boolean; type?: "submit" | "button" }) {
  return (
    <button type={type ?? "button"} onClick={onClick} disabled={disabled} style={{
      padding: "9px 16px", borderRadius: 8, border: "none", fontSize: 13, fontWeight: 600,
      cursor: disabled ? "not-allowed" : "pointer",
      background: disabled ? "#e5e7eb" : green ? "#25D366" : "#f3f4f6",
      color: disabled ? "#9ca3af" : green ? "#fff" : "#374151",
    }}>{children}</button>
  );
}

const s: Record<string, React.CSSProperties> = {
  header:       { display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24, gap: 16 },
  pageTitle:    { fontSize: 24, fontWeight: 700, color: "#111827", margin: "0 0 4px" },
  pageSubtitle: { fontSize: 14, color: "#6b7280", margin: 0 },
  loading:      { color: "#6b7280", fontSize: 14 },
  error:        { marginBottom: 16, padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, color: "#991b1b", fontSize: 13, display: "flex", justifyContent: "space-between", alignItems: "center" },
  success:      { marginBottom: 16, padding: "10px 14px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, color: "#166534", fontSize: 13 },
  closeBtn:     { background: "none", border: "none", cursor: "pointer", color: "#991b1b", fontSize: 16, marginLeft: 8 },
  emptyState:   { textAlign: "center", padding: "60px 20px", background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" },
  grid:         { display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(340px,1fr))", gap: 16 },
  card:         { background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb", overflow: "hidden" },
  cardTop:      { display: "flex", alignItems: "flex-start", gap: 14, padding: "16px 20px", borderBottom: "1px solid #f3f4f6" },
  qrImg:        { width: 80, height: 80, borderRadius: 8, border: "1px solid #e5e7eb", flexShrink: 0, objectFit: "contain" },
  qrPlaceholder:{ width: 80, height: 80, borderRadius: 8, background: "#f3f4f6", border: "1px solid #e5e7eb", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 32, flexShrink: 0 },
  cardTitle:    { fontSize: 14, fontWeight: 600, color: "#111827", lineHeight: 1.4 },
  cardSub:      { fontSize: 11, color: "#9ca3af", marginTop: 4 },
  cardBody:     { padding: "14px 20px" },
  cardActions:  { display: "flex", gap: 8, padding: "10px 16px", borderTop: "1px solid #f3f4f6", background: "#fafafa" },
  badge:        { padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600 },
  badgeGreen:   { background: "#dcfce7", color: "#15803d" },
  fieldLabel:   { fontSize: 11, color: "#9ca3af", fontWeight: 500, textTransform: "uppercase" as const, letterSpacing: "0.04em", marginBottom: 4 },
  copyBtn:      { padding: "4px 10px", background: "#f3f4f6", border: "1px solid #e5e7eb", borderRadius: 6, fontSize: 11, fontWeight: 500, cursor: "pointer", color: "#374151", flexShrink: 0 },
  actionBtn:    { flex: 1, padding: "7px", border: "1px solid #e5e7eb", borderRadius: 6, background: "#f9fafb", color: "#374151", fontSize: 12, fontWeight: 500, cursor: "pointer" },
  overlay:      { position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 16 },
  modalBox:     { background: "#fff", borderRadius: 16, padding: "28px 32px", width: "100%", maxWidth: 480, maxHeight: "90vh", overflowY: "auto" },
  modalHeader:  { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 },
  modalTitle:   { margin: 0, fontSize: 18, fontWeight: 700, color: "#111827" },
  modalClose:   { background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#6b7280" },
  modalDesc:    { fontSize: 13, color: "#6b7280", marginBottom: 16, lineHeight: 1.6 },
  form:         { display: "flex", flexDirection: "column", gap: 14 },
  formGroup:    { display: "flex", flexDirection: "column", gap: 6 },
  label:        { fontSize: 13, fontWeight: 500, color: "#374151" },
  input:        { padding: "9px 12px", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 14, color: "#111827", outline: "none" },
  select:       { padding: "9px 12px", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 14, color: "#111827", outline: "none", background: "#fff" },
};
