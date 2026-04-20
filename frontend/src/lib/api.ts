/**
 * Centralized API client for TierceMsg backend.
 * All endpoints mirror the FastAPI routes at /api/v1/
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("access_token") ?? "";
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  token?: string,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const t = token ?? getToken();
  if (t) headers["Authorization"] = `Bearer ${t}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const message = Array.isArray(detail)
      ? detail.map((e: { msg?: string; loc?: string[] }) => `${e.loc?.slice(-1)[0] ?? "field"}: ${e.msg ?? "invalid"}`).join(", ")
      : typeof detail === "string" ? detail : `HTTP ${res.status}`;
    throw new Error(message);
  }
  return data as T;
}

const get  = <T>(path: string) => request<T>("GET", path);
const post = <T>(path: string, body?: unknown) => request<T>("POST", path, body);
const patch = <T>(path: string, body?: unknown) => request<T>("PATCH", path, body);
const del  = <T>(path: string) => request<T>("DELETE", path);

// ── Auth ──────────────────────────────────────────────────────────────────────
export const auth = {
  login: (email: string, password: string) =>
    post<{ access_token: string; token_type: string }>("/auth/login", { email, password }),
  register: (email: string, password: string, full_name: string, org_name: string) =>
    post<{ access_token: string; token_type: string }>("/auth/register", {
      email, password, full_name, org_name,
    }),
  me: () => get<import("@/types/api").UserMe>("/auth/me"),
  refresh: () => post<{ access_token: string; token_type: string }>("/auth/refresh"),
};

// ── WABA ─────────────────────────────────────────────────────────────────────
export const waba = {
  list: () => get<import("@/types/api").WabaAccount[]>("/waba"),
  get: (id: string) => get<import("@/types/api").WabaAccount>(`/waba/${id}`),
  connectToken: (access_token: string, waba_id: string) =>
    post<import("@/types/api").EmbeddedSignupResult>("/waba/connect/token", { access_token, waba_id }),
  embeddedSignup: (code: string) =>
    post<import("@/types/api").EmbeddedSignupResult>("/waba/connect/embedded-signup", { code }),
  create: (body: { business_id: string; name: string; currency: string; timezone_id: string; access_token: string }) =>
    post<import("@/types/api").WabaAccount>("/waba/create", body),
  sync: (id: string) => post<import("@/types/api").WabaAccount>(`/waba/${id}/sync`),
  verifyToken: (id: string) => get<Record<string, unknown>>(`/waba/${id}/verify-token`),
  update: (id: string, body: { access_token?: string; business_name?: string; status?: string }) =>
    patch<import("@/types/api").WabaAccount>(`/waba/${id}`, body),
  delete: (id: string) => del<void>(`/waba/${id}`),
  getConfig: () => get<{ app_id: string; config_id: string }>("/waba/connect/config"),
};

// ── Phone Numbers ─────────────────────────────────────────────────────────────
export const phones = {
  list: () => get<import("@/types/api").PhoneNumber[]>("/waba/phone-numbers"),
  get: (id: string) => get<import("@/types/api").PhoneNumber>(`/waba/phone-numbers/${id}`),
  add: (waba_id: string, phone_number_id: string) =>
    post<import("@/types/api").PhoneNumber>("/waba/phone-numbers", { waba_id, phone_number_id }),
  sync: (id: string) => post<import("@/types/api").PhoneNumber>(`/waba/phone-numbers/${id}/sync`),
  delete: (id: string) => del<void>(`/waba/phone-numbers/${id}`),
  register: (id: string, pin: string) =>
    post<{ success: boolean }>(`/waba/phone-numbers/${id}/register`, { pin }),
  deregister: (id: string) =>
    post<{ success: boolean }>(`/waba/phone-numbers/${id}/deregister`),
  requestCode: (id: string, method = "SMS", language = "en_US") =>
    post<{ success: boolean }>(`/waba/phone-numbers/${id}/request-code`, { method, language }),
  verifyCode: (id: string, code: string) =>
    post<{ success: boolean }>(`/waba/phone-numbers/${id}/verify-code`, { code }),
};

// ── Templates ─────────────────────────────────────────────────────────────────
export const templates = {
  list: (waba_id?: string) =>
    get<import("@/types/api").Template[]>(`/templates${waba_id ? `?waba_id=${waba_id}` : ""}`),
  get: (id: string) => get<import("@/types/api").Template>(`/templates/${id}`),
  create: (body: { waba_id: string; name: string; category: string; language: string; components: unknown[] }) =>
    post<import("@/types/api").Template>("/templates", body),
  update: (id: string, components: unknown[]) =>
    patch<import("@/types/api").Template>(`/templates/${id}`, { components }),
  delete: (id: string) => del<void>(`/templates/${id}`),
  sync: (id: string) => post<import("@/types/api").Template>(`/templates/${id}/sync`),
  syncAll: (waba_id: string) =>
    post<import("@/types/api").Template[]>("/templates/sync-all", { waba_id }),
};

// ── Messages ─────────────────────────────────────────────────────────────────
export const messages = {
  sendText: (body: { phone_number_id: string; to: string; body: string }) =>
    post<{ message_id: string }>("/messages/send/text", body),
  sendTemplate: (body: { phone_number_id: string; to: string; template_name: string; language_code: string; components?: unknown[] }) =>
    post<{ message_id: string }>("/messages/send/template", body),
  markRead: (message_id: string, phone_number_id: string) =>
    post<void>("/messages/send/mark-read", { message_id, phone_number_id }),
  listConversations: () =>
    get<import("@/types/api").Conversation[]>("/messages/conversations"),
  getMessages: (conversation_id: string) =>
    get<import("@/types/api").Message[]>(`/messages/conversations/${conversation_id}/messages`),
  deleteConversation: (conversation_id: string) =>
    del<void>(`/messages/conversations/${conversation_id}`),
  sendMedia: async (formData: FormData) => {
    let r: Response;
    try {
      r = await fetch(`${BASE}/messages/send/media`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: formData,
      });
    } catch (err) {
      throw new Error(`Network error: ${err instanceof Error ? err.message : "unknown"}`);
    }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const detail = data.detail;
      const msg = Array.isArray(detail)
        ? detail.map((e: { msg?: string; loc?: string[] }) => `${e.loc?.slice(-1)[0]}: ${e.msg}`).join(", ")
        : typeof detail === "string" ? detail : `HTTP ${r.status}`;
      throw new Error(msg);
    }
    return data;
  },
};

// ── Users ─────────────────────────────────────────────────────────────────────
export const users = {
  list: () => get<import("@/types/api").User[]>("/users"),
  get: (id: string) => get<import("@/types/api").User>(`/users/${id}`),
  create: (body: { email: string; password: string; full_name: string; role: string }) =>
    post<import("@/types/api").User>("/users", body),
  update: (id: string, body: Partial<{ full_name: string; role: string; is_active: boolean }>) =>
    patch<import("@/types/api").User>(`/users/${id}`, body),
  delete: (id: string) => del<{ message: string }>(`/users/${id}`),
};

// ── Analytics ─────────────────────────────────────────────────────────────────
export const analytics = {
  overview: () => get<import("@/types/api").AnalyticsOverview>("/analytics/overview"),
  daily: (days?: number) => get<import("@/types/api").DailyStat[]>(`/analytics/daily${days ? `?days=${days}` : ""}`),
};

// ── Orgs ──────────────────────────────────────────────────────────────────────
export const orgs = {
  list: () => get<import("@/types/api").Org[]>("/orgs"),
  me: () => get<import("@/types/api").Org>("/orgs/me"),
  get: (id: string) => get<import("@/types/api").Org>(`/orgs/${id}`),
  create: (body: { name: string; slug: string }) =>
    post<import("@/types/api").Org>("/orgs", body),
  update: (id: string, body: Partial<{ name: string }>) =>
    patch<import("@/types/api").Org>(`/orgs/${id}`, body),
  suspend: (id: string, reason: string) =>
    post<{ message: string }>(`/orgs/${id}/suspend`, { reason }),
  unsuspend: (id: string) =>
    post<{ message: string }>(`/orgs/${id}/unsuspend`),
};

// ── QR Codes ──────────────────────────────────────────────────────────────────
export const qrCodes = {
  list: () => get<import("@/types/api").QrCode[]>("/waba/qr-codes"),
  create: (phone_number_id: string, prefilled_message: string) =>
    post<import("@/types/api").QrCode>("/waba/qr-codes", { phone_number_id, prefilled_message }),
  delete: (qr_code_id: string, phone_number_id: string) =>
    del<void>(`/waba/qr-codes/${qr_code_id}?phone_number_id=${encodeURIComponent(phone_number_id)}`),
};

// ── Contacts ──────────────────────────────────────────────────────────────────
export const contacts = {
  list: (params?: { search?: string; tag_id?: string; opted_in?: boolean; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.search) q.set("search", params.search);
    if (params?.tag_id) q.set("tag_id", params.tag_id);
    if (params?.opted_in !== undefined) q.set("opted_in", String(params.opted_in));
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    return get<import("@/types/api").ContactsPage>(`/contacts${q.toString() ? "?" + q : ""}`);
  },
  get: (id: string) => get<import("@/types/api").Contact>(`/contacts/${id}`),
  create: (body: { phone: string; name?: string; email?: string; language?: string; is_opted_in?: boolean; attributes?: Record<string, unknown> }) =>
    post<import("@/types/api").Contact>("/contacts", body),
  update: (id: string, body: Partial<{ name: string; email: string; language: string; is_opted_in: boolean; lead_status: string; attributes: Record<string, unknown> }>) =>
    patch<import("@/types/api").Contact>(`/contacts/${id}`, body),
  delete: (id: string) => del<void>(`/contacts/${id}`),
  import: (formData: FormData) =>
    fetch(`${BASE}/contacts/import`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken()}` },
      body: formData,
    }).then(async r => {
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || `HTTP ${r.status}`); }
      return r.json();
    }),
  listTags: () => get<import("@/types/api").ContactTag[]>("/contacts/tags"),
  createTag: (body: { name: string; color?: string }) =>
    post<import("@/types/api").ContactTag>("/contacts/tags", body),
  deleteTag: (id: string) => del<void>(`/contacts/tags/${id}`),
  addTag: (contact_id: string, tag_id: string) =>
    post<import("@/types/api").Contact>(`/contacts/${contact_id}/tags`, { tag_id }),
  removeTag: (contact_id: string, tag_id: string) =>
    del<import("@/types/api").Contact>(`/contacts/${contact_id}/tags/${tag_id}`),
  bulkDelete: (body: { ids?: string[]; all_matching?: boolean; search?: string; tag_id?: string; opted_in?: boolean }) =>
    post<{ deleted: number }>("/contacts/bulk-delete", body),
};

// ── Campaigns ─────────────────────────────────────────────────────────────────
export const campaigns = {
  list: (params?: { status_filter?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.status_filter) q.set("status_filter", params.status_filter);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    return get<import("@/types/api").CampaignsPage>(`/campaigns${q.toString() ? "?" + q : ""}`);
  },
  get: (id: string) => get<import("@/types/api").Campaign>(`/campaigns/${id}`),
  create: (body: { name: string; template_id: string; phone_number_id: string; scheduled_at?: string; template_variables?: Record<string, string> }) =>
    post<import("@/types/api").Campaign>("/campaigns", body),
  update: (id: string, body: Partial<{ name: string; template_id: string; phone_number_id: string; scheduled_at: string; template_variables: Record<string, string> }>) =>
    patch<import("@/types/api").Campaign>(`/campaigns/${id}`, body),
  delete: (id: string) => del<void>(`/campaigns/${id}`),
  addRecipients: (id: string, body: { phones?: string[]; tag_id?: string; all_opted_in?: boolean }) =>
    post<{ added: number; total_recipients: number }>(`/campaigns/${id}/recipients`, body),
  listRecipients: (id: string, params?: { limit?: number; offset?: number; status_filter?: string }) => {
    const q = new URLSearchParams();
    if (params?.status_filter) q.set("status_filter", params.status_filter);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    return get<{ total: number; items: import("@/types/api").CampaignRecipient[] }>(`/campaigns/${id}/recipients${q.toString() ? "?" + q : ""}`);
  },
  launch: (id: string, scheduled_at?: string) =>
    post<import("@/types/api").Campaign>(`/campaigns/${id}/launch`, { scheduled_at: scheduled_at ?? null }),
  pause: (id: string) => post<import("@/types/api").Campaign>(`/campaigns/${id}/pause`),
  resume: (id: string) => post<import("@/types/api").Campaign>(`/campaigns/${id}/resume`),
};

// ── Webhook Config ────────────────────────────────────────────────────────────
export const webhookConfig = {
  status: () => get<import("@/types/api").WebhookStatus[]>("/webhook-config/status"),
  subscribe: (waba_id: string) => post<{ success: boolean; meta_waba_id: string; action: string }>(`/webhook-config/${waba_id}/subscribe`),
  unsubscribe: (waba_id: string) => post<{ success: boolean; meta_waba_id: string; action: string }>(`/webhook-config/${waba_id}/unsubscribe`),
};
