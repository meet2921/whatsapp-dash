"use client";

import { useEffect } from "react";
import { isLoggedIn } from "@/store/auth";

export default function RootPage() {
  useEffect(() => {
    window.location.replace(isLoggedIn() ? "/dashboard" : "/login");
  }, []);

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", background: "#f9fafb", fontFamily: "system-ui" }}>
      <div style={{ color: "#6b7280", fontSize: 14 }}>Redirecting…</div>
    </div>
  );
}
