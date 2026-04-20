"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/AppLayout";
import { analytics } from "@/lib/api";
import type { AnalyticsOverview, DailyStat } from "@/types/api";

// ── Colour palette (dark-green brand) ────────────────────────────────────────
const C = {
  green:      "#25D366",
  greenDark:  "#128C4B",
  greenLight: "#dcfce7",
  greenMid:   "#16a34a",
  blue:       "#3b82f6",
  blueDark:   "#1d4ed8",
  blueLight:  "#dbeafe",
  yellow:     "#f59e0b",
  yellowDark: "#a16207",
  yellowLight:"#fef9c3",
  red:        "#ef4444",
  redDark:    "#b91c1c",
  redLight:   "#fee2e2",
  purple:     "#8b5cf6",
  purpleLight:"#ede9fe",
  teal:       "#14b8a6",
  tealLight:  "#ccfbf1",
  bg:         "#f0fdf4",
  card:       "#fff",
  border:     "#d1fae5",
  text:       "#111827",
  muted:      "#6b7280",
  sidebar:    "#111827",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({
  label, value, icon, accent, bg, textColor,
}: {
  label: string; value: number | string; icon: string;
  accent: string; bg: string; textColor: string;
}) {
  return (
    <div style={{
      background: bg,
      border: `1.5px solid ${accent}33`,
      borderRadius: 14,
      padding: "20px 22px",
      display: "flex",
      flexDirection: "column",
      gap: 6,
      position: "relative",
      overflow: "hidden",
    }}>
      {/* accent bar top */}
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 3, background: accent, borderRadius: "14px 14px 0 0" }} />
      <div style={{ fontSize: 22 }}>{icon}</div>
      <div style={{ fontSize: 28, fontWeight: 800, color: textColor, lineHeight: 1 }}>{fmt(Number(value))}</div>
      <div style={{ fontSize: 12, fontWeight: 600, color: textColor, opacity: 0.75, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</div>
    </div>
  );
}

function RateGauge({ label, rate, color, bg }: { label: string; rate: number; color: string; bg: string }) {
  const clamped = Math.min(Math.max(rate, 0), 100);
  return (
    <div style={{ background: bg, border: `1.5px solid ${color}33`, borderRadius: 14, padding: "24px 28px", flex: 1, minWidth: 200 }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: C.muted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>{label}</div>
      <div style={{ fontSize: 48, fontWeight: 900, color, lineHeight: 1, marginBottom: 16 }}>
        {clamped.toFixed(1)}<span style={{ fontSize: 22, fontWeight: 600 }}>%</span>
      </div>
      {/* Progress bar track */}
      <div style={{ height: 10, background: `${color}22`, borderRadius: 99, overflow: "hidden" }}>
        <div style={{
          height: "100%",
          width: `${clamped}%`,
          background: `linear-gradient(90deg, ${color}aa, ${color})`,
          borderRadius: 99,
          transition: "width 0.8s cubic-bezier(.4,0,.2,1)",
        }} />
      </div>
      <div style={{ fontSize: 11, color: C.muted, marginTop: 6 }}>{clamped.toFixed(2)}% of outbound messages</div>
    </div>
  );
}

function TodayCard({ label, value, icon, color }: { label: string; value: number; icon: string; color: string }) {
  return (
    <div style={{
      background: C.card,
      border: `1.5px solid ${color}33`,
      borderRadius: 12,
      padding: "16px 20px",
      display: "flex",
      alignItems: "center",
      gap: 14,
      flex: 1,
    }}>
      <div style={{ width: 44, height: 44, borderRadius: 12, background: `${color}18`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, flexShrink: 0 }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 800, color, lineHeight: 1 }}>{fmt(value)}</div>
        <div style={{ fontSize: 12, color: C.muted, fontWeight: 500, marginTop: 3 }}>{label}</div>
      </div>
    </div>
  );
}

// ── Bar Chart ─────────────────────────────────────────────────────────────────

const BAR_COLORS = {
  sent:      { fill: C.blue,   label: "Sent" },
  delivered: { fill: C.green,  label: "Delivered" },
  read:      { fill: C.greenDark, label: "Read" },
};

type BarKey = keyof typeof BAR_COLORS;

const BAR_H = 160; // fixed pixel height for bar area

function BarChart({ data }: { data: DailyStat[] }) {
  const last14 = data.slice(-14);
  const maxVal = Math.max(
    ...last14.map(d => Math.max(d.sent, d.delivered, d.read, d.inbound)),
    1,
  );

  const px = (v: number) => Math.max((v / maxVal) * BAR_H, v > 0 ? 3 : 0);

  return (
    <div>
      {/* Legend */}
      <div style={{ display: "flex", gap: 20, marginBottom: 18, flexWrap: "wrap" }}>
        {(Object.entries(BAR_COLORS) as [BarKey, { fill: string; label: string }][]).map(([k, v]) => (
          <div key={k} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 12, height: 12, borderRadius: 3, background: v.fill }} />
            <span style={{ fontSize: 12, color: C.muted, fontWeight: 500 }}>{v.label}</span>
          </div>
        ))}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 12, height: 12, borderRadius: 3, background: C.teal }} />
          <span style={{ fontSize: 12, color: C.muted, fontWeight: 500 }}>Inbound</span>
        </div>
      </div>

      {/* Chart area */}
      {last14.length === 0 ? (
        <div style={{ color: C.muted, fontSize: 13, textAlign: "center", padding: "40px 0" }}>No data for this period.</div>
      ) : (
        <div style={{ display: "flex", alignItems: "flex-end", gap: 4, paddingBottom: 28, borderBottom: `1px solid ${C.border}` }}>
          {last14.map((day) => (
            <div key={day.date} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 0, position: "relative" }}>
              {/* bars group — anchored to bottom */}
              <div style={{ width: "100%", display: "flex", gap: 1, alignItems: "flex-end", height: BAR_H }}>
                <div title={`Sent: ${day.sent}`} style={{
                  flex: 1, height: px(day.sent),
                  background: `linear-gradient(180deg, ${C.blue}bb, ${C.blue})`,
                  borderRadius: "2px 2px 0 0",
                }} />
                <div title={`Delivered: ${day.delivered}`} style={{
                  flex: 1, height: px(day.delivered),
                  background: `linear-gradient(180deg, ${C.green}bb, ${C.green})`,
                  borderRadius: "2px 2px 0 0",
                }} />
                <div title={`Read: ${day.read}`} style={{
                  flex: 1, height: px(day.read),
                  background: `linear-gradient(180deg, ${C.greenDark}bb, ${C.greenDark})`,
                  borderRadius: "2px 2px 0 0",
                }} />
                <div title={`Inbound: ${day.inbound}`} style={{
                  flex: 1, height: px(day.inbound),
                  background: `linear-gradient(180deg, ${C.teal}bb, ${C.teal})`,
                  borderRadius: "2px 2px 0 0",
                }} />
              </div>
              {/* date label */}
              <div style={{
                position: "absolute", bottom: -22,
                fontSize: 9, color: C.muted, whiteSpace: "nowrap",
                transform: "rotate(-35deg)", transformOrigin: "top center",
              }}>
                {shortDate(day.date)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [daily, setDaily] = useState<DailyStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.allSettled([
      analytics.overview().then(setOverview),
      analytics.daily(30).then(setDaily),
    ])
      .then(results => {
        const failed = results.find(r => r.status === "rejected") as PromiseRejectedResult | undefined;
        if (failed) setError(String(failed.reason));
      })
      .finally(() => setLoading(false));
  }, []);

  const statCards = overview ? [
    { label: "Messages Sent",      value: overview.total_messages_sent,      icon: "📤", accent: C.blue,      bg: C.blueLight,   textColor: C.blueDark },
    { label: "Delivered",          value: overview.total_messages_delivered,  icon: "✅", accent: C.green,     bg: C.greenLight,  textColor: C.greenMid },
    { label: "Read",               value: overview.total_messages_read,       icon: "👁️", accent: C.greenDark, bg: C.greenLight,  textColor: C.greenDark },
    { label: "Failed",             value: overview.total_messages_failed,     icon: "❌", accent: C.red,       bg: C.redLight,    textColor: C.redDark },
    { label: "Inbound Received",   value: overview.total_inbound,             icon: "📥", accent: C.teal,      bg: C.tealLight,   textColor: "#0f766e" },
    { label: "Conversations",      value: overview.total_conversations,       icon: "💬", accent: C.purple,    bg: C.purpleLight, textColor: "#6d28d9" },
  ] : [];

  return (
    <AppLayout>
      <div style={{ maxWidth: 1200, fontFamily: "system-ui,-apple-system,sans-serif" }}>

        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
            <div style={{ width: 36, height: 36, background: C.green, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>
              📊
            </div>
            <h1 style={{ fontSize: 26, fontWeight: 800, color: C.text, margin: 0 }}>Analytics</h1>
          </div>
          <p style={{ fontSize: 14, color: C.muted, margin: 0, paddingLeft: 48 }}>
            Live message performance metrics for your organisation
          </p>
        </div>

        {loading && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, color: C.muted, fontSize: 14, padding: "40px 0" }}>
            <div style={{ width: 18, height: 18, border: `3px solid ${C.green}`, borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
            Loading analytics…
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        )}

        {error && !loading && (
          <div style={{ background: C.redLight, border: `1px solid ${C.red}44`, borderRadius: 10, padding: "14px 18px", color: C.redDark, fontSize: 13, marginBottom: 24 }}>
            Failed to load analytics: {error}
          </div>
        )}

        {!loading && overview && (
          <>
            {/* ── Stat cards row ─────────────────────────────────────────── */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14, marginBottom: 24 }}>
              {statCards.map(sc => (
                <StatCard key={sc.label} {...sc} />
              ))}
            </div>

            {/* ── Rate gauges ────────────────────────────────────────────── */}
            <div style={{ display: "flex", gap: 14, marginBottom: 24, flexWrap: "wrap" }}>
              <RateGauge
                label="Delivery Rate"
                rate={overview.delivery_rate}
                color={C.green}
                bg={C.greenLight}
              />
              <RateGauge
                label="Read Rate"
                rate={overview.read_rate}
                color={C.greenDark}
                bg={C.greenLight}
              />
              {/* Failure rate derived */}
              <RateGauge
                label="Failure Rate"
                rate={overview.total_messages_sent > 0
                  ? overview.total_messages_failed / overview.total_messages_sent * 100
                  : 0}
                color={C.red}
                bg={C.redLight}
              />
            </div>

            {/* ── Daily bar chart ────────────────────────────────────────── */}
            <div style={{
              background: C.card,
              border: `1.5px solid ${C.border}`,
              borderRadius: 16,
              padding: "24px 28px",
              marginBottom: 24,
              boxShadow: "0 1px 6px rgba(0,0,0,0.04)",
            }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
                <div>
                  <h2 style={{ fontSize: 16, fontWeight: 700, color: C.text, margin: 0 }}>Daily Message Volume</h2>
                  <p style={{ fontSize: 12, color: C.muted, margin: "3px 0 0" }}>Last 14 days — hover bars for exact counts</p>
                </div>
                <div style={{ background: C.greenLight, border: `1px solid ${C.green}44`, borderRadius: 8, padding: "4px 12px", fontSize: 12, fontWeight: 600, color: C.greenMid }}>
                  30-day window
                </div>
              </div>
              <BarChart data={daily} />
            </div>

            {/* ── Today's stats ──────────────────────────────────────────── */}
            <div style={{
              background: C.card,
              border: `1.5px solid ${C.border}`,
              borderRadius: 16,
              padding: "24px 28px",
              marginBottom: 24,
              boxShadow: "0 1px 6px rgba(0,0,0,0.04)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 18 }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: C.green, boxShadow: `0 0 0 3px ${C.greenLight}` }} />
                <h2 style={{ fontSize: 16, fontWeight: 700, color: C.text, margin: 0 }}>Today</h2>
                <span style={{ fontSize: 12, color: C.muted }}>{new Date().toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}</span>
              </div>
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                <TodayCard label="Sent Today"      value={overview.today_sent}      icon="📤" color={C.blue} />
                <TodayCard label="Delivered Today" value={overview.today_delivered}  icon="✅" color={C.green} />
                <TodayCard label="Inbound Today"   value={overview.today_inbound}    icon="📥" color={C.teal} />
              </div>
            </div>

            {/* ── Summary table ──────────────────────────────────────────── */}
            <div style={{
              background: C.card,
              border: `1.5px solid ${C.border}`,
              borderRadius: 16,
              overflow: "hidden",
              boxShadow: "0 1px 6px rgba(0,0,0,0.04)",
            }}>
              <div style={{ padding: "18px 24px", borderBottom: `1px solid ${C.border}` }}>
                <h2 style={{ fontSize: 16, fontWeight: 700, color: C.text, margin: 0 }}>All-time Summary</h2>
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: C.bg }}>
                    {["Metric", "Value", "Share of Outbound"].map(h => (
                      <th key={h} style={{ padding: "10px 20px", textAlign: "left", fontSize: 11, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: `1px solid ${C.border}` }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[
                    { label: "Sent",          value: overview.total_messages_sent,     share: 100, color: C.blue },
                    { label: "Delivered",      value: overview.total_messages_delivered, share: overview.delivery_rate, color: C.green },
                    { label: "Read",           value: overview.total_messages_read,      share: overview.read_rate, color: C.greenDark },
                    { label: "Failed",         value: overview.total_messages_failed,    share: overview.total_messages_sent > 0 ? overview.total_messages_failed / overview.total_messages_sent * 100 : 0, color: C.red },
                    { label: "Inbound",        value: overview.total_inbound,            share: null, color: C.teal },
                    { label: "Conversations",  value: overview.total_conversations,      share: null, color: C.purple },
                  ].map((row, i) => (
                    <tr key={row.label} style={{ background: i % 2 === 0 ? "#fff" : C.bg }}>
                      <td style={{ padding: "13px 20px", fontSize: 13, fontWeight: 600, color: C.text }}>
                        {row.label}
                      </td>
                      <td style={{ padding: "13px 20px", fontSize: 13, color: row.color, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                        {row.value.toLocaleString()}
                      </td>
                      <td style={{ padding: "13px 20px" }}>
                        {row.share !== null ? (
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <div style={{ flex: 1, maxWidth: 160, height: 6, background: `${row.color}22`, borderRadius: 99, overflow: "hidden" }}>
                              <div style={{ width: `${Math.min(row.share, 100)}%`, height: "100%", background: row.color, borderRadius: 99 }} />
                            </div>
                            <span style={{ fontSize: 12, color: C.muted, minWidth: 44, textAlign: "right" }}>
                              {row.share.toFixed(1)}%
                            </span>
                          </div>
                        ) : (
                          <span style={{ color: C.muted, fontSize: 12 }}>—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </AppLayout>
  );
}
