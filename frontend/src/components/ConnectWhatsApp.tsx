"use client";

import { useEmbeddedSignup, type EmbeddedSignupResult } from "@/hooks/useEmbeddedSignup";

interface ConnectWhatsAppProps {
  authToken: string;
  onSuccess?: (result: EmbeddedSignupResult) => void;
}

// ── Step indicator ────────────────────────────────────────────────────────────

const STEPS = [
  { key: "waiting_sdk",  label: "Loading Meta SDK" },
  { key: "waiting_meta", label: "Authorize on Meta" },
  { key: "connecting",   label: "Saving to system" },
  { key: "success",      label: "Connected!" },
];

function StepIndicator({ currentStatus }: { currentStatus: string }) {
  const activeIndex = STEPS.findIndex((s) => s.key === currentStatus);

  return (
    <div style={styles.steps}>
      {STEPS.map((step, i) => {
        const done = currentStatus === "success" || i < activeIndex;
        const active = step.key === currentStatus;
        return (
          <div key={step.key} style={styles.stepItem}>
            <div
              style={{
                ...styles.stepCircle,
                background: done ? "#25D366" : active ? "#1d4ed8" : "#e5e7eb",
                color: done || active ? "#fff" : "#9ca3af",
              }}
            >
              {done ? "✓" : i + 1}
            </div>
            <span
              style={{
                ...styles.stepLabel,
                color: done ? "#25D366" : active ? "#1d4ed8" : "#9ca3af",
                fontWeight: active ? 600 : 400,
              }}
            >
              {step.label}
            </span>
            {i < STEPS.length - 1 && (
              <div
                style={{
                  ...styles.stepLine,
                  background: done ? "#25D366" : "#e5e7eb",
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ConnectWhatsApp({ authToken, onSuccess }: ConnectWhatsAppProps) {
  const { launch, status, error, result, sessionInfo, reset } = useEmbeddedSignup({
    authToken,
    onSuccess,
  });

  const isLoading =
    status === "waiting_sdk" || status === "waiting_meta" || status === "connecting";

  // ── Success ───────────────────────────────────────────────────────────────
  if (status === "success" && result) {
    return (
      <div style={styles.card}>
        <div style={styles.successIcon}>✓</div>
        <h2 style={styles.title}>WhatsApp Connected!</h2>
        <p style={styles.subtitle}>
          {result.wabas_connected} WABA{result.wabas_connected !== 1 ? "s" : ""} connected
          {" · "}
          {result.phone_numbers_saved} phone number{result.phone_numbers_saved !== 1 ? "s" : ""} saved
        </p>

        <div style={styles.wabaList}>
          {result.wabas.map((waba) => (
            <div key={waba.id} style={styles.wabaRow}>
              <div style={styles.wabaIcon}>W</div>
              <div style={{ flex: 1 }}>
                <div style={styles.wabaName}>{waba.business_name ?? waba.waba_id}</div>
                <div style={styles.wabaMeta}>
                  ID: {waba.waba_id}
                  {waba.currency ? ` · ${waba.currency}` : ""}
                  {waba.message_template_namespace ? " · Templates ready" : ""}
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end" }}>
                <span style={{ ...styles.badge, ...styles.badgeGreen }}>{waba.status}</span>
                {waba.account_review_status && (
                  <span style={{ ...styles.badge, ...styles.badgeBlue }}>
                    {waba.account_review_status}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>

        <button onClick={reset} style={styles.secondaryButton}>
          Connect another account
        </button>
      </div>
    );
  }

  // ── Loading / progress ────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div style={styles.card}>
        <h2 style={styles.title}>Connecting WhatsApp…</h2>
        <p style={styles.subtitle}>Please complete the authorization in the Meta popup.</p>

        <StepIndicator currentStatus={status} />

        {status === "waiting_meta" && (
          <div style={styles.infoBox}>
            <strong>Meta popup is open.</strong>
            <br />
            Log in to Facebook, select your WhatsApp Business Account, and grant the
            requested permissions.
          </div>
        )}

        {status === "connecting" && sessionInfo?.wabaId && (
          <div style={styles.infoBox}>
            <strong>Authorization received.</strong>
            <br />
            WABA ID: <code>{sessionInfo.wabaId}</code>
            {sessionInfo.phoneNumberId && (
              <> · Phone: <code>{sessionInfo.phoneNumberId}</code></>
            )}
          </div>
        )}

        {status === "connecting" && (
          <div style={styles.statusBox}>Saving to TierceMsg…</div>
        )}
      </div>
    );
  }

  // ── Idle / Error ──────────────────────────────────────────────────────────
  return (
    <div style={styles.card}>
      {/* Header */}
      <div style={styles.iconWrap}>
        <svg viewBox="0 0 48 48" width="52" height="52" fill="none">
          <circle cx="24" cy="24" r="24" fill="#25D366" />
          <path
            d="M34.5 13.5C32.1 11.1 28.9 9.6 25.4 9.5c-7.4-.1-13.5 5.9-13.5 13.3 0 2.3.6 4.6 1.8 6.6L11.5 36l6.9-1.8c1.9 1 4 1.6 6.1 1.6 7.4 0 13.5-5.9 13.5-13.3 0-3.5-1.4-6.9-3.5-9z"
            fill="white"
          />
        </svg>
      </div>

      <h2 style={styles.title}>Connect WhatsApp Business</h2>
      <p style={styles.subtitle}>
        Connect your WhatsApp Business Account to start sending messages,
        managing templates, and running campaigns.
      </p>

      {/* What happens steps */}
      <div style={styles.stepsPreview}>
        {[
          "Click the button below",
          "Log in to Facebook in the popup",
          "Select your WhatsApp Business Account",
          "Grant the requested permissions",
          "Done — your account is connected!",
        ].map((step, i) => (
          <div key={i} style={styles.previewStep}>
            <div style={styles.previewNum}>{i + 1}</div>
            <span style={styles.previewText}>{step}</span>
          </div>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div style={styles.errorBox}>
          <strong>Error: </strong>{error}
        </div>
      )}

      {/* CTA */}
      <button onClick={launch} style={styles.primaryButton}>
        Connect with Meta
      </button>

      <p style={styles.hint}>
        A secure Meta popup will open. Your credentials are never shared with us.
      </p>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  card: {
    maxWidth: 480,
    margin: "40px auto",
    padding: "40px 32px",
    borderRadius: 20,
    border: "1px solid #e5e7eb",
    boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
    fontFamily: "system-ui, -apple-system, sans-serif",
    textAlign: "center",
    background: "#fff",
  },
  iconWrap: {
    display: "flex",
    justifyContent: "center",
    marginBottom: 20,
  },
  title: {
    fontSize: 22,
    fontWeight: 700,
    color: "#111827",
    margin: "0 0 8px",
  },
  subtitle: {
    fontSize: 14,
    color: "#6b7280",
    margin: "0 0 24px",
    lineHeight: 1.6,
  },

  // Steps preview (idle state)
  stepsPreview: {
    background: "#f9fafb",
    borderRadius: 12,
    padding: "16px 20px",
    marginBottom: 24,
    textAlign: "left",
  },
  previewStep: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "6px 0",
  },
  previewNum: {
    width: 24,
    height: 24,
    borderRadius: "50%",
    background: "#25D366",
    color: "#fff",
    fontSize: 12,
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  previewText: {
    fontSize: 13,
    color: "#374151",
  },

  // Step indicator (loading state)
  steps: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    margin: "24px 0",
    gap: 0,
  },
  stepItem: {
    display: "flex",
    alignItems: "center",
    gap: 6,
  },
  stepCircle: {
    width: 28,
    height: 28,
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 12,
    fontWeight: 700,
    flexShrink: 0,
  },
  stepLabel: {
    fontSize: 11,
    whiteSpace: "nowrap",
  },
  stepLine: {
    width: 24,
    height: 2,
    margin: "0 4px",
  },

  // Buttons
  primaryButton: {
    display: "block",
    width: "100%",
    padding: "13px 24px",
    background: "#25D366",
    color: "#fff",
    border: "none",
    borderRadius: 10,
    fontSize: 15,
    fontWeight: 600,
    cursor: "pointer",
    letterSpacing: "0.01em",
  },
  secondaryButton: {
    display: "inline-block",
    marginTop: 16,
    padding: "10px 20px",
    background: "transparent",
    color: "#6b7280",
    border: "1px solid #e5e7eb",
    borderRadius: 8,
    fontSize: 14,
    cursor: "pointer",
  },

  // Alerts
  errorBox: {
    marginBottom: 16,
    padding: "12px 14px",
    background: "#fef2f2",
    border: "1px solid #fecaca",
    borderRadius: 8,
    color: "#991b1b",
    fontSize: 13,
    textAlign: "left",
    lineHeight: 1.5,
  },
  infoBox: {
    marginBottom: 12,
    padding: "12px 14px",
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    borderRadius: 8,
    color: "#1e40af",
    fontSize: 13,
    textAlign: "left",
    lineHeight: 1.6,
  },
  statusBox: {
    padding: "10px 14px",
    background: "#f0fdf4",
    border: "1px solid #bbf7d0",
    borderRadius: 8,
    color: "#166534",
    fontSize: 13,
  },

  // Success WABA list
  successIcon: {
    width: 60,
    height: 60,
    background: "#25D366",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 28,
    color: "#fff",
    margin: "0 auto 16px",
  },
  wabaList: {
    margin: "20px 0 24px",
    textAlign: "left",
  },
  wabaRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 0",
    borderBottom: "1px solid #f3f4f6",
  },
  wabaIcon: {
    width: 36,
    height: 36,
    borderRadius: 8,
    background: "#dcfce7",
    color: "#16a34a",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 700,
    fontSize: 16,
    flexShrink: 0,
  },
  wabaName: {
    fontSize: 14,
    fontWeight: 600,
    color: "#111827",
    marginBottom: 2,
  },
  wabaMeta: {
    fontSize: 11,
    color: "#9ca3af",
  },
  badge: {
    padding: "2px 8px",
    borderRadius: 999,
    fontSize: 10,
    fontWeight: 700,
    textTransform: "uppercase" as const,
    letterSpacing: "0.04em",
  },
  badgeGreen: {
    background: "#dcfce7",
    color: "#16a34a",
  },
  badgeBlue: {
    background: "#dbeafe",
    color: "#1d4ed8",
  },

  hint: {
    marginTop: 14,
    fontSize: 12,
    color: "#9ca3af",
    lineHeight: 1.5,
  },
};
