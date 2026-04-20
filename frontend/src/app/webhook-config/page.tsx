"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/AppLayout";
import { webhookConfig } from "@/lib/api";
import type { WebhookStatus } from "@/types/api";

export default function WebhookConfigPage() {
  const [list, setList] = useState<WebhookStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    webhookConfig.status()
      .then(setList)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const notify = (msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(null), 3000); };

  async function handleSubscribe(wabaId: string) {
    setBusy(wabaId); setError(null);
    try {
      await webhookConfig.subscribe(wabaId);
      notify("Webhook subscribed successfully!"); load();
    } catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(null); }
  }

  async function handleUnsubscribe(wabaId: string) {
    setBusy(wabaId); setError(null);
    try {
      await webhookConfig.unsubscribe(wabaId);
      notify("Webhook unsubscribed."); load();
    } catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(null); }
  }

  return (
    <AppLayout>
      <div style={{ maxWidth: 900 }}>
        <div style={s.header}>
          <div>
            <h1 style={s.pageTitle}>Webhook Configuration</h1>
            <p style={s.pageSubtitle}>Manage Meta webhook subscriptions for your WABA accounts</p>
          </div>
          <button onClick={load} style={s.refreshBtn}>↻ Refresh</button>
        </div>

        {error && (
          <div style={s.error}>
            {error}
            <button onClick={() => setError(null)} style={s.closeBtn}>✕</button>
          </div>
        )}
        {success && <div style={s.success}>{success}</div>}

        <div style={s.infoBox}>
          <span style={{ fontSize: 16, marginRight: 8 }}>ℹ️</span>
          <span>
            Webhook subscriptions allow Meta to push message events to your server in real time.
            Subscribe each WABA account to receive inbound messages and delivery updates.
          </span>
        </div>

        {loading ? (
          <div style={s.loading}>Loading webhook status…</div>
        ) : list.length === 0 ? (
          <div style={s.emptyState}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>⚙️</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: "#374151", marginBottom: 8 }}>No WABA accounts found</div>
            <div style={{ color: "#9ca3af", fontSize: 14 }}>Add a WABA account first to configure webhooks.</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {list.map(item => (
              <div key={item.waba_id} style={s.card}>
                <div style={s.cardLeft}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                    <span style={{ ...s.badge, ...(item.is_subscribed ? s.badgeGreen : s.badgeGray) }}>
                      {item.is_subscribed ? "● Subscribed" : "○ Not subscribed"}
                    </span>
                    {item.business_name && (
                      <span style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>{item.business_name}</span>
                    )}
                  </div>
                  <div style={s.metaRow}>
                    <span style={s.metaLabel}>WABA ID</span>
                    <span style={s.metaValue}>{item.meta_waba_id}</span>
                  </div>
                  {item.is_subscribed && item.subscribed_fields.length > 0 && (
                    <div style={s.metaRow}>
                      <span style={s.metaLabel}>Fields</span>
                      <span style={s.metaValue}>{item.subscribed_fields.join(", ")}</span>
                    </div>
                  )}
                  {item.error && (
                    <div style={{ fontSize: 12, color: "#b91c1c", marginTop: 6 }}>⚠ {item.error}</div>
                  )}
                </div>
                <div style={s.cardActions}>
                  {item.is_subscribed ? (
                    <button
                      onClick={() => handleUnsubscribe(item.waba_id)}
                      disabled={busy === item.waba_id}
                      style={{ ...s.btn, ...s.btnDanger, opacity: busy === item.waba_id ? 0.6 : 1 }}
                    >
                      {busy === item.waba_id ? "Working…" : "Unsubscribe"}
                    </button>
                  ) : (
                    <button
                      onClick={() => handleSubscribe(item.waba_id)}
                      disabled={busy === item.waba_id}
                      style={{ ...s.btn, ...s.btnGreen, opacity: busy === item.waba_id ? 0.6 : 1 }}
                    >
                      {busy === item.waba_id ? "Working…" : "Subscribe"}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppLayout>
  );
}

const s: Record<string, React.CSSProperties> = {
  header:      { display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24, gap: 16 },
  pageTitle:   { fontSize: 24, fontWeight: 700, color: "#111827", margin: "0 0 4px" },
  pageSubtitle:{ fontSize: 14, color: "#6b7280", margin: 0 },
  refreshBtn:  { padding: "8px 16px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#fff", fontSize: 13, cursor: "pointer", color: "#374151", fontWeight: 500 },
  error:       { marginBottom: 16, padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, color: "#991b1b", fontSize: 13, display: "flex", justifyContent: "space-between", alignItems: "center" },
  success:     { marginBottom: 16, padding: "10px 14px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, color: "#166534", fontSize: 13 },
  closeBtn:    { background: "none", border: "none", cursor: "pointer", color: "#991b1b", fontSize: 16, marginLeft: 8 },
  infoBox:     { display: "flex", alignItems: "flex-start", gap: 4, padding: "12px 16px", background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8, fontSize: 13, color: "#1e40af", marginBottom: 20, lineHeight: 1.5 },
  loading:     { color: "#6b7280", fontSize: 14 },
  emptyState:  { textAlign: "center", padding: "60px 20px", background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb" },
  card:        { background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb", padding: "16px 20px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 },
  cardLeft:    { flex: 1, minWidth: 0 },
  cardActions: { flexShrink: 0 },
  badge:       { padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600 },
  badgeGreen:  { background: "#dcfce7", color: "#15803d" },
  badgeGray:   { background: "#f3f4f6", color: "#6b7280" },
  metaRow:     { display: "flex", alignItems: "center", gap: 8, marginTop: 4 },
  metaLabel:   { fontSize: 11, color: "#9ca3af", fontWeight: 500, textTransform: "uppercase" as const, letterSpacing: "0.04em", minWidth: 48 },
  metaValue:   { fontSize: 12, color: "#374151", fontFamily: "monospace" },
  btn:         { padding: "8px 18px", borderRadius: 8, border: "none", fontSize: 13, fontWeight: 600, cursor: "pointer" },
  btnGreen:    { background: "#25D366", color: "#fff" },
  btnDanger:   { background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca" } as React.CSSProperties,
};
