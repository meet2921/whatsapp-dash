"use client";

import { auth } from "@/lib/api";
import type { UserMe } from "@/types/api";

const TOKEN_KEY = "access_token";

export function saveToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

export async function loginUser(email: string, password: string): Promise<UserMe> {
  const res = await auth.login(email, password);
  saveToken(res.access_token);
  return auth.me();
}

export function logoutUser() {
  clearToken();
  window.location.href = "/login";
}
