// ── Auth ──────────────────────────────────────────────────────────────────────
export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserMe {
  id: string;
  org_id: string;
  email: string;
  full_name: string;
  role: "super_admin" | "org_admin" | "agent" | "viewer";
  is_active: boolean;
}

// ── Org ───────────────────────────────────────────────────────────────────────
export interface Org {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  is_suspended: boolean;
  created_at: string;
}

// ── WABA ─────────────────────────────────────────────────────────────────────
export interface WabaAccount {
  id: string;
  org_id: string;
  waba_id: string;
  business_name: string | null;
  status: string;
  business_id: string | null;
  currency: string | null;
  timezone_id: string | null;
  message_template_namespace: string | null;
  account_review_status: string | null;
  created_at: string | null;
  updated_at: string | null;
}

// ── Phone Number ─────────────────────────────────────────────────────────────
export interface PhoneNumber {
  id: string;
  org_id: string;
  waba_id: string;
  phone_number_id: string;
  display_number: string | null;
  display_name: string | null;
  quality_rating: string | null;
  messaging_limit: string | null;
  is_active: boolean;
  created_at: string | null;
  code_verification_status: string | null;
  platform_type: string | null;
  throughput_level: string | null;
  account_mode: string | null;
  name_status: string | null;
  last_onboarded_time: string | null;
}

// ── Template ──────────────────────────────────────────────────────────────────
export interface Template {
  id: string;
  org_id: string;
  waba_id: string;
  meta_template_id: string | null;
  name: string;
  category: string;
  language: string;
  status: string;
  components: Record<string, unknown>[];
  rejection_reason: string | null;
  created_at: string | null;
  updated_at: string | null;
}

// ── Conversation ──────────────────────────────────────────────────────────────
export interface Conversation {
  id: string;
  org_id: string;
  contact_id: string;
  phone_number_id: string;
  status: string;
  assigned_to: string | null;
  last_message_at: string | null;
  session_expires_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  contact_phone: string | null;
  contact_name: string | null;
}

// ── Message ───────────────────────────────────────────────────────────────────
export interface Message {
  id: string;
  org_id: string;
  conversation_id: string;
  wa_message_id: string | null;
  direction: "inbound" | "outbound";
  status: string;
  message_type: string;
  content: Record<string, unknown>;
  cost_credits: number | null;
  sent_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
  created_at: string | null;
}

// ── User ──────────────────────────────────────────────────────────────────────
export interface User {
  id: string;
  org_id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  last_login: string | null;
  created_at: string;
}

// ── Embedded Signup ───────────────────────────────────────────────────────────
export interface EmbeddedSignupResult {
  wabas_connected: number;
  phone_numbers_saved: number;
  wabas: WabaAccount[];
}

// ── Analytics ─────────────────────────────────────────────────────────────────
export interface AnalyticsOverview {
  total_messages_sent: number;
  total_messages_delivered: number;
  total_messages_read: number;
  total_messages_failed: number;
  total_inbound: number;
  total_conversations: number;
  delivery_rate: number;
  read_rate: number;
  today_sent: number;
  today_delivered: number;
  today_inbound: number;
}

export interface DailyStat {
  date: string;
  sent: number;
  delivered: number;
  read: number;
  failed: number;
  inbound: number;
}

// ── QR Code ───────────────────────────────────────────────────────────────────
export interface QrCode {
  code: string;
  prefilled_message: string;
  deep_link_url: string;
  qr_image_url?: string;
  phone_number_id: string;
  phone_internal_id: string;
  display_number?: string;
  display_name?: string;
}

// ── Contact ───────────────────────────────────────────────────────────────────
export interface ContactTag {
  id: string;
  name: string;
  color: string | null;
}

export interface Contact {
  id: string;
  org_id: string;
  phone: string;
  name: string | null;
  email: string | null;
  language: string;
  is_opted_in: boolean;
  opted_in_at: string | null;
  opted_out_at: string | null;
  lead_status: string | null;
  attributes: Record<string, unknown>;
  tags: ContactTag[];
  created_at: string | null;
}

export interface ContactsPage {
  total: number;
  offset: number;
  limit: number;
  items: Contact[];
}

// ── Campaign ──────────────────────────────────────────────────────────────────
export interface Campaign {
  id: string;
  org_id: string;
  name: string;
  template_id: string | null;
  phone_number_id: string | null;
  status: string;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  total_recipients: number;
  sent_count: number;
  delivered_count: number;
  read_count: number;
  failed_count: number;
  estimated_cost: number | null;
  actual_cost: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CampaignsPage {
  total: number;
  offset: number;
  limit: number;
  items: Campaign[];
}

export interface CampaignRecipient {
  id: string;
  phone: string;
  status: string;
  template_variables: Record<string, unknown>;
  error_message: string | null;
}

// ── Webhook Status ────────────────────────────────────────────────────────────
export interface WebhookStatus {
  waba_id: string;
  meta_waba_id: string;
  business_name?: string;
  is_subscribed: boolean;
  subscribed_apps: Record<string, unknown>[];
  subscribed_fields: string[];
  error?: string | null;
}
