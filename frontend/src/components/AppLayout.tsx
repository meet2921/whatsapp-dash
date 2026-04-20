"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { isLoggedIn, logoutUser } from "@/store/auth";
import { auth } from "@/lib/api";
import type { UserMe } from "@/types/api";

const NAV = [
  { href: "/dashboard",      icon: "⊞", label: "Dashboard" },
  { href: "/analytics",      icon: "📊", label: "Analytics" },
  { href: "/waba",           icon: "📱", label: "WABA Accounts" },
  { href: "/phone-numbers",  icon: "☎",  label: "Phone Numbers" },
  { href: "/templates",      icon: "📄", label: "Templates" },
  { href: "/contacts",       icon: "👤", label: "Contacts" },
  { href: "/campaigns",      icon: "📣", label: "Campaigns" },
  { href: "/conversations",  icon: "💬", label: "Conversations" },
  { href: "/users",          icon: "👥", label: "Users" },
  { href: "/qr-codes",       icon: "🔗", label: "QR Codes" },
  { href: "/webhook-config", icon: "⚙",  label: "Webhooks" },
];

export function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [user, setUser] = useState<UserMe | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (!isLoggedIn()) { window.location.href = "/login"; return; }
    auth.me().then(setUser).catch(() => { window.location.href = "/login"; });
  }, []);

  if (!user) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", fontFamily: "system-ui" }}>
        <div style={{ color: "#6b7280", fontSize: 14 }}>Loading…</div>
      </div>
    );
  }

  const sideW = collapsed ? 64 : 220;

  return (
    <div style={{ display: "flex", minHeight: "100vh", fontFamily: "system-ui,-apple-system,sans-serif", background: "#f9fafb" }}>
      {/* Sidebar */}
      <aside style={{ width: sideW, background: "#111827", display: "flex", flexDirection: "column", flexShrink: 0, transition: "width 0.2s" }}>
        {/* Logo */}
        <div style={{ padding: "20px 16px", display: "flex", alignItems: "center", gap: 10, borderBottom: "1px solid #1f2937" }}>
          <div style={{ width: 32, height: 32, background: "#25D366", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, flexShrink: 0 }}>💬</div>
          {!collapsed && <span style={{ color: "#fff", fontWeight: 700, fontSize: 16 }}>TierceMsg</span>}
          <button onClick={() => setCollapsed(c => !c)} style={{ marginLeft: "auto", background: "none", border: "none", color: "#6b7280", cursor: "pointer", fontSize: 16, padding: 0 }}>
            {collapsed ? "→" : "←"}
          </button>
        </div>

        {/* Nav links */}
        <nav style={{ flex: 1, padding: "12px 8px", display: "flex", flexDirection: "column", gap: 2 }}>
          {NAV.map(item => {
            const active = pathname.startsWith(item.href);
            return (
              <Link key={item.href} href={item.href} style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "10px 12px", borderRadius: 8, textDecoration: "none",
                background: active ? "#1f2937" : "transparent",
                color: active ? "#fff" : "#9ca3af",
                fontWeight: active ? 600 : 400, fontSize: 14,
                transition: "all 0.15s",
              }}>
                <span style={{ fontSize: 16, flexShrink: 0 }}>{item.icon}</span>
                {!collapsed && <span>{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* User + logout */}
        <div style={{ padding: "12px 8px", borderTop: "1px solid #1f2937" }}>
          {!collapsed && (
            <div style={{ padding: "8px 12px", marginBottom: 4 }}>
              <div style={{ color: "#fff", fontSize: 13, fontWeight: 500 }}>{user.full_name}</div>
              <div style={{ color: "#6b7280", fontSize: 11 }}>{user.role}</div>
            </div>
          )}
          <button onClick={logoutUser} style={{
            width: "100%", display: "flex", alignItems: "center", gap: 10,
            padding: "10px 12px", borderRadius: 8, background: "none",
            border: "none", color: "#ef4444", cursor: "pointer", fontSize: 14,
          }}>
            <span>⏻</span>
            {!collapsed && <span>Logout</span>}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main style={{ flex: 1, overflow: "auto", padding: "32px" }}>
        {children}
      </main>
    </div>
  );
}
