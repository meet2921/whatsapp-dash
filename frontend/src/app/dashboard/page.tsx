"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/AppLayout";
import { waba, phones, templates, messages } from "@/lib/api";
import type { WabaAccount, PhoneNumber, Template, Conversation } from "@/types/api";

export default function DashboardPage() {
  const [wabas, setWabas] = useState<WabaAccount[]>([]);
  const [phoneList, setPhoneList] = useState<PhoneNumber[]>([]);
  const [templateList, setTemplateList] = useState<Template[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      waba.list().then(setWabas),
      phones.list().then(setPhoneList),
      templates.list().then(setTemplateList),
      messages.listConversations().then(setConversations),
    ]).finally(() => setLoading(false));
  }, []);

  const stats = [
    { label: "WABA Accounts",  value: wabas.length,         icon: "📱", color: "#dbeafe", text: "#1d4ed8", href: "/waba" },
    { label: "Phone Numbers",  value: phoneList.length,     icon: "☎",  color: "#dcfce7", text: "#15803d", href: "/phone-numbers" },
    { label: "Templates",      value: templateList.length,  icon: "📄", color: "#fef9c3", text: "#a16207", href: "/templates" },
    { label: "Conversations",  value: conversations.length, icon: "💬", color: "#fce7f3", text: "#be185d", href: "/conversations" },
  ];

  return (
    <AppLayout>
      <div style={{ maxWidth: 1100 }}>
        <h1 style={s.pageTitle}>Dashboard</h1>
        <p style={s.pageSubtitle}>Overview of your WhatsApp Business platform</p>

        {loading ? (
          <div style={s.loading}>Loading…</div>
        ) : (
          <>
            {/* Stats cards */}
            <div style={s.statsGrid}>
              {stats.map(stat => (
                <a key={stat.label} href={stat.href} style={{ ...s.statCard, background: stat.color, textDecoration: "none" }}>
                  <div style={s.statIcon}>{stat.icon}</div>
                  <div style={{ ...s.statValue, color: stat.text }}>{stat.value}</div>
                  <div style={{ ...s.statLabel, color: stat.text }}>{stat.label}</div>
                </a>
              ))}
            </div>

            {/* Connected WABAs */}
            <div style={s.section}>
              <div style={s.sectionHeader}>
                <h2 style={s.sectionTitle}>Connected WABAs</h2>
                <a href="/waba" style={s.sectionLink}>Manage →</a>
              </div>
              {wabas.length === 0 ? (
                <div style={s.empty}>
                  No WABAs connected yet.{" "}
                  <a href="/waba" style={{ color: "#25D366" }}>Connect one →</a>
                </div>
              ) : (
                <div style={s.tableWrap}>
                  <table style={s.table}>
                    <thead>
                      <tr>
                        {["Business Name", "WABA ID", "Currency", "Review Status", "Status"].map(h => (
                          <th key={h} style={s.th}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {wabas.map(w => (
                        <tr key={w.id}>
                          <td style={s.td}>{w.business_name ?? "—"}</td>
                          <td style={{ ...s.td, fontFamily: "monospace", fontSize: 12 }}>{w.waba_id}</td>
                          <td style={s.td}>{w.currency ?? "—"}</td>
                          <td style={s.td}><Badge text={w.account_review_status ?? "—"} /></td>
                          <td style={s.td}><Badge text={w.status} green /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Active Phone Numbers */}
            <div style={s.section}>
              <div style={s.sectionHeader}>
                <h2 style={s.sectionTitle}>Phone Numbers</h2>
                <a href="/phone-numbers" style={s.sectionLink}>Manage →</a>
              </div>
              {phoneList.length === 0 ? (
                <div style={s.empty}>No phone numbers yet.</div>
              ) : (
                <div style={s.tableWrap}>
                  <table style={s.table}>
                    <thead>
                      <tr>
                        {["Number", "Name", "Quality", "Limit", "Verification", "Active"].map(h => (
                          <th key={h} style={s.th}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {phoneList.map(p => (
                        <tr key={p.id}>
                          <td style={{ ...s.td, fontWeight: 500 }}>{p.display_number ?? "—"}</td>
                          <td style={s.td}>{p.display_name ?? "—"}</td>
                          <td style={s.td}><QualityBadge rating={p.quality_rating} /></td>
                          <td style={s.td}>{p.messaging_limit ?? "—"}</td>
                          <td style={s.td}><Badge text={p.code_verification_status ?? "—"} green={p.code_verification_status === "VERIFIED"} /></td>
                          <td style={s.td}>{p.is_active ? "✅" : "❌"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </AppLayout>
  );
}

function Badge({ text, green }: { text: string; green?: boolean }) {
  return (
    <span style={{
      padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600,
      textTransform: "uppercase", letterSpacing: "0.04em",
      background: green ? "#dcfce7" : "#f3f4f6",
      color: green ? "#15803d" : "#374151",
    }}>{text}</span>
  );
}

function QualityBadge({ rating }: { rating: string | null }) {
  const map: Record<string, { bg: string; color: string }> = {
    GREEN:   { bg: "#dcfce7", color: "#15803d" },
    YELLOW:  { bg: "#fef9c3", color: "#a16207" },
    RED:     { bg: "#fee2e2", color: "#b91c1c" },
    UNKNOWN: { bg: "#f3f4f6", color: "#6b7280" },
  };
  const style = map[rating ?? "UNKNOWN"] ?? map.UNKNOWN;
  return (
    <span style={{ padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600, ...style }}>
      {rating ?? "UNKNOWN"}
    </span>
  );
}

const s: Record<string, React.CSSProperties> = {
  pageTitle:    { fontSize: 24, fontWeight: 700, color: "#111827", margin: "0 0 4px" },
  pageSubtitle: { fontSize: 14, color: "#6b7280", margin: "0 0 28px" },
  loading:      { color: "#6b7280", fontSize: 14 },
  statsGrid:    { display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 32 },
  statCard:     { padding: "20px 24px", borderRadius: 12, cursor: "pointer", transition: "transform 0.15s" },
  statIcon:     { fontSize: 24, marginBottom: 8 },
  statValue:    { fontSize: 32, fontWeight: 700, lineHeight: 1 },
  statLabel:    { fontSize: 13, fontWeight: 500, marginTop: 4 },
  section:      { background: "#fff", borderRadius: 12, border: "1px solid #e5e7eb", marginBottom: 24 },
  sectionHeader:{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: "1px solid #f3f4f6" },
  sectionTitle: { fontSize: 15, fontWeight: 600, color: "#111827", margin: 0 },
  sectionLink:  { fontSize: 13, color: "#25D366", textDecoration: "none" },
  tableWrap:    { overflowX: "auto" },
  table:        { width: "100%", borderCollapse: "collapse" },
  th:           { padding: "10px 16px", textAlign: "left", fontSize: 12, fontWeight: 600, color: "#6b7280", borderBottom: "1px solid #f3f4f6", whiteSpace: "nowrap" },
  td:           { padding: "12px 16px", fontSize: 13, color: "#374151", borderBottom: "1px solid #f9fafb" },
  empty:        { padding: "24px 20px", color: "#9ca3af", fontSize: 14 },
};
