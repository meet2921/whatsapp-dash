"use client";

import { useState } from "react";
import { loginUser } from "@/store/auth";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await loginUser(email, password);
      window.location.href = "/dashboard";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={s.page}>
      <div style={s.card}>
        <div style={s.logo}>
          <svg viewBox="0 0 40 40" width="40" height="40" fill="none">
            <circle cx="20" cy="20" r="20" fill="#25D366" />
            <path d="M28 12C25.8 9.8 22.9 8.5 19.8 8.5c-6.4-.1-11.6 5.1-11.6 11.4 0 2 .5 4 1.5 5.7L8 31l5.9-1.5c1.6.9 3.4 1.4 5.2 1.4 6.4 0 11.6-5.1 11.6-11.4 0-3-1.2-5.9-3-7.9z" fill="white" />
          </svg>
          <span style={s.logoText}>TierceMsg</span>
        </div>

        <h1 style={s.title}>Welcome back</h1>
        <p style={s.subtitle}>Sign in to your account</p>

        {error && <div style={s.error}>{error}</div>}

        <form onSubmit={handleSubmit} style={s.form}>
          <div style={s.field}>
            <label style={s.label}>Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              style={s.input}
            />
          </div>
          <div style={s.field}>
            <label style={s.label}>Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              style={s.input}
            />
          </div>
          <button type="submit" disabled={loading} style={loading ? { ...s.btn, ...s.btnDisabled } : s.btn}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  page: { minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f9fafb", fontFamily: "system-ui,-apple-system,sans-serif" },
  card: { width: 380, padding: "40px 36px", background: "#fff", borderRadius: 16, border: "1px solid #e5e7eb", boxShadow: "0 4px 24px rgba(0,0,0,0.07)" },
  logo: { display: "flex", alignItems: "center", gap: 10, marginBottom: 28 },
  logoText: { fontSize: 20, fontWeight: 700, color: "#111827" },
  title: { fontSize: 22, fontWeight: 700, color: "#111827", margin: "0 0 4px" },
  subtitle: { fontSize: 14, color: "#6b7280", margin: "0 0 24px" },
  form: { display: "flex", flexDirection: "column", gap: 16 },
  field: { display: "flex", flexDirection: "column", gap: 6 },
  label: { fontSize: 13, fontWeight: 500, color: "#374151" },
  input: { padding: "9px 12px", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 14, outline: "none", color: "#111827" },
  btn: { padding: "11px", background: "#25D366", color: "#fff", border: "none", borderRadius: 8, fontSize: 15, fontWeight: 600, cursor: "pointer", marginTop: 4 },
  btnDisabled: { background: "#9ca3af", cursor: "not-allowed" },
  error: { marginBottom: 16, padding: "10px 12px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, color: "#991b1b", fontSize: 13 },
};
