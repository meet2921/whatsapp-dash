"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

export type SignupStatus =
  | "idle"
  | "waiting_sdk"   // SDK script loading
  | "waiting_meta"  // Meta popup open, waiting for user
  | "connecting"    // exchanging code with our backend
  | "success"
  | "error";

export interface ConnectedWaba {
  id: string;
  waba_id: string;
  business_name: string | null;
  currency: string | null;
  timezone_id: string | null;
  message_template_namespace: string | null;
  account_review_status: string | null;
  status: string;
}

export interface EmbeddedSignupResult {
  wabas_connected: number;
  phone_numbers_saved: number;
  wabas: ConnectedWaba[];
}

/** Session info from Meta's sessionInfoVersion:3 — arrives before the code */
export interface MetaSessionInfo {
  event: "FINISH" | "CANCEL" | "ERROR";
  phoneNumberId?: string;
  wabaId?: string;
}

interface UseEmbeddedSignupOptions {
  authToken: string;
  onSuccess?: (result: EmbeddedSignupResult) => void;
  onError?: (message: string) => void;
  /** Optional: called as soon as Meta sends session info (before backend call) */
  onSessionInfo?: (info: MetaSessionInfo) => void;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const META_APP_ID = process.env.NEXT_PUBLIC_META_APP_ID ?? "";
const META_CONFIG_ID = process.env.NEXT_PUBLIC_META_CONFIG_ID ?? "";

// ── SDK readiness helper ──────────────────────────────────────────────────────

/**
 * Wait for window.FB to be initialized by the SDK loaded in layout.tsx.
 * Polls every 100ms, times out after 10s.
 */
function waitForFB(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof window !== "undefined" && window.FB) {
      resolve();
      return;
    }
    const start = Date.now();
    const interval = setInterval(() => {
      if (window.FB) {
        clearInterval(interval);
        resolve();
      } else if (Date.now() - start > 10_000) {
        clearInterval(interval);
        reject(new Error("Meta SDK did not load within 10 seconds."));
      }
    }, 100);
  });
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useEmbeddedSignup({
  authToken,
  onSuccess,
  onError,
  onSessionInfo,
}: UseEmbeddedSignupOptions) {
  const [status, setStatus] = useState<SignupStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EmbeddedSignupResult | null>(null);
  const [sessionInfo, setSessionInfo] = useState<MetaSessionInfo | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // Session info listener — Meta sends a postMessage from the popup with
  // WA_EMBEDDED_SIGNUP event containing the phone_number_id and waba_id
  // BEFORE the FB.login callback fires.
  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (event.origin !== "https://www.facebook.com") return;
      try {
        const parsed =
          typeof event.data === "string" ? JSON.parse(event.data) : event.data;
        if (parsed?.type !== "WA_EMBEDDED_SIGNUP") return;

        const info: MetaSessionInfo = {
          event: parsed.event,
          phoneNumberId: parsed.data?.phone_number_id,
          wabaId: parsed.data?.waba_id,
        };
        setSessionInfo(info);
        onSessionInfo?.(info);
      } catch {
        // not a JSON message — ignore
      }
    }

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [onSessionInfo]);

  const launch = useCallback(async () => {
    if (!META_APP_ID) {
      const msg = "NEXT_PUBLIC_META_APP_ID is not set in environment variables.";
      setError(msg);
      onError?.(msg);
      return;
    }

    setStatus("waiting_sdk");
    setError(null);
    setResult(null);
    setSessionInfo(null);

    // Wait for the SDK loaded in layout.tsx to be ready
    try {
      await waitForFB();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Meta SDK failed to load.";
      if (mountedRef.current) { setStatus("error"); setError(msg); }
      onError?.(msg);
      return;
    }

    if (!mountedRef.current) return;
    setStatus("waiting_meta");

    // FB.login callback must be a plain (non-async) function.
    // Kick off async work inside via a void IIFE.
    window.FB.login(
      (response) => {
        if (!mountedRef.current) return;

        // User closed the popup or denied
        if (!response.authResponse?.code) {
          const msg =
            response.status === "not_authorized"
              ? "Authorization declined. Please allow the requested permissions."
              : "Meta popup was closed without completing authorization.";
          setStatus("error");
          setError(msg);
          onError?.(msg);
          return;
        }

        const code = response.authResponse.code;
        setStatus("connecting");

        // Async work in a plain void IIFE — FB.login callback stays synchronous
        void (async () => {
          try {
            const res = await fetch(`${API_URL}/waba/connect/embedded-signup`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${authToken}`,
              },
              body: JSON.stringify({ code }),
            });

            if (!res.ok) {
              const body = await res.json().catch(() => ({}));
              throw new Error(body.detail ?? `Backend error ${res.status}`);
            }

            const data: EmbeddedSignupResult = await res.json();
            if (!mountedRef.current) return;
            setStatus("success");
            setResult(data);
            onSuccess?.(data);
          } catch (err) {
            if (!mountedRef.current) return;
            const msg =
              err instanceof Error ? err.message : "Unknown error contacting backend.";
            setStatus("error");
            setError(msg);
            onError?.(msg);
          }
        })();
      },
      {
        config_id: META_CONFIG_ID,
        response_type: "code",
        override_default_response_type: true,
        extras: {
          setup: {},
          featureType: "",
          sessionInfoVersion: "3",
        },
      }
    );
  }, [authToken, onSuccess, onError]);

  const reset = useCallback(() => {
    setStatus("idle");
    setError(null);
    setResult(null);
    setSessionInfo(null);
  }, []);

  return { launch, status, error, result, sessionInfo, reset };
}
