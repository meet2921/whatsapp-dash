"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { AppLayout } from "@/components/AppLayout";
import { messages as messagesApi, phones, templates as templatesApi, auth as authApi } from "@/lib/api";
import { getToken } from "@/store/auth";
import type { Conversation, Message, PhoneNumber, Template } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

function mediaProxyUrl(mediaId: string): string {
  return `${API_BASE}/messages/media/${mediaId}?token=${getToken()}`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getMediaType(file: File): "image" | "video" | "audio" | "document" {
  if (file.type.startsWith("image/")) return "image";
  if (file.type.startsWith("video/")) return "video";
  if (file.type.startsWith("audio/")) return "audio";
  return "document";
}

function mediaTypeIcon(mt: string): string {
  if (mt === "image") return "🖼";
  if (mt === "video") return "🎬";
  if (mt === "audio") return "🎵";
  return "📄";
}

function extractText(content: Record<string, unknown>, templateList?: Template[]): string {
  if (typeof content.body === "string") return content.body;
  if (typeof content.text === "string") return content.text;
  if (typeof content.template_name === "string") {
    const tpl = templateList?.find(t => t.name === content.template_name);
    if (tpl) {
      const bodyComp = tpl.components.find((c: Record<string, unknown>) => c.type === "BODY") as Record<string, unknown> | undefined;
      if (bodyComp && typeof bodyComp.text === "string") return bodyComp.text;
    }
    return `📄 ${String(content.template_name)}`;
  }
  if (typeof content.emoji === "string") return content.emoji;
  if (content.type) return `[${String(content.type)}]`;
  return "(media)";
}

function statusTicks(status: string, direction: string) {
  if (direction !== "outbound") return null;
  if (status === "read") return <span style={{ color: "#53bdeb", fontSize: 13, marginLeft: 4 }}>✓✓</span>;
  if (status === "delivered") return <span style={{ color: "#fff", opacity: 0.8, fontSize: 13, marginLeft: 4 }}>✓✓</span>;
  if (status === "sent") return <span style={{ color: "#fff", opacity: 0.6, fontSize: 13, marginLeft: 4 }}>✓</span>;
  if (status === "failed") return <span style={{ color: "#ff6b6b", fontSize: 13, marginLeft: 4 }}>✗</span>;
  return null;
}

function fmtTime(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function convLabel(c: Conversation) {
  return c.contact_name || c.contact_phone || `+${c.contact_id.slice(0, 8)}`;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ConversationsPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [phoneList, setPhoneList] = useState<PhoneNumber[]>([]);
  const [templateList, setTemplateList] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [orgId, setOrgId] = useState<string | null>(null);
  const [wsStatus, setWsStatus] = useState<"connecting" | "connected" | "disconnected">("disconnected");
  const [unread, setUnread] = useState<Record<string, number>>({});
  const [search, setSearch] = useState("");
  const [lastPreviews, setLastPreviews] = useState<Record<string, string>>({});

  // Reply bar state
  const [replyText, setReplyText] = useState("");
  const [sendingReply, setSendingReply] = useState(false);
  const [deletingConv, setDeletingConv] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  // Template modal
  const [showTplModal, setShowTplModal] = useState(false);
  const [tplForm, setTplForm] = useState({ phone_number_id: "", to: "", template_id: "", template_name: "", language_code: "" });
  const [sendingTpl, setSendingTpl] = useState(false);


  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const selectedRef = useRef<Conversation | null>(null);
  selectedRef.current = selected;

  // ── Data loading ────────────────────────────────────────────────────────────

  const load = useCallback(() => {
    Promise.all([messagesApi.listConversations(), phones.list(), templatesApi.list()])
      .then(([c, p, t]) => { setConversations(c); setPhoneList(p); setTemplateList(t); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    authApi.me().then(u => setOrgId(u.org_id)).catch(() => {});
  }, [load]);

  const loadMessages = (conv: Conversation) => {
    setSelected(conv);
    setUnread(u => ({ ...u, [conv.id]: 0 }));
    setLoadingMsgs(true);
    setMsgs([]);
    messagesApi.getMessages(conv.id)
      .then(setMsgs)
      .catch(e => setError(e.message))
      .finally(() => setLoadingMsgs(false));
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  // ── WebSocket with auto-reconnect ──────────────────────────────────────────

  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelay = useRef(1000);
  const unmounted = useRef(false);

  const connectWs = useCallback((oid: string) => {
    if (unmounted.current) return;

    // NEXT_PUBLIC_WS_URL: explicit WS base (required when running Next.js dev server
    // directly on :3000 — it cannot proxy WS upgrades unlike nginx).
    // Leave unset in production; nginx /ws/ location handles the proxy.
    const wsBase = process.env.NEXT_PUBLIC_WS_URL
      ?? (() => {
        const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
        return apiBase.startsWith("http")
          ? apiBase.replace(/^http/, "ws").replace(/\/api\/v1$/, "")
          : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
      })();
    const token = getToken();
    const wsUrl = `${wsBase}/ws/inbox/${oid}?token=${token}`;

    setWsStatus("connecting");
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus("connected");
      reconnectDelay.current = 1000;
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.event === "ping") return;

        if (data.event === "new_message") {
          const preview = typeof data.content?.body === "string"
            ? data.content.body
            : data.message_type === "image" ? "📷 Image"
            : data.message_type === "audio" ? "🎵 Audio"
            : data.message_type === "video" ? "🎬 Video"
            : data.message_type === "document" ? "📄 Document"
            : "New message";

          setLastPreviews(p => ({ ...p, [data.conversation_id]: preview }));

          // Append to open thread
          if (selectedRef.current?.id === data.conversation_id) {
            const newMsg: Message = {
              id: data.message_id,
              org_id: "",
              conversation_id: data.conversation_id,
              wa_message_id: null,
              direction: data.direction,
              status: data.status,
              message_type: data.message_type,
              content: data.content ?? {},
              cost_credits: null,
              sent_at: null,
              delivered_at: null,
              read_at: null,
              created_at: data.created_at,
            };
            setMsgs(prev => prev.some(m => m.id === newMsg.id) ? prev : [...prev, newMsg]);
          } else if (data.direction === "inbound") {
            // Badge only for inbound messages in other conversations
            setUnread(u => ({ ...u, [data.conversation_id]: (u[data.conversation_id] ?? 0) + 1 }));
          }

          // Bump conversation to top
          setConversations(prev => {
            const idx = prev.findIndex(c => c.id === data.conversation_id);
            if (idx === -1) { load(); return prev; }
            const updated = { ...prev[idx], last_message_at: data.created_at };
            return [updated, ...prev.filter((_, i) => i !== idx)];
          });
        }

        if (data.event === "message_status_update") {
          setMsgs(prev => prev.map(m =>
            m.id === data.message_id || m.wa_message_id === data.wa_message_id
              ? { ...m, status: data.status }
              : m
          ));
        }
      } catch { /* ignore parse errors */ }
    };

    ws.onerror = () => {};

    ws.onclose = () => {
      if (unmounted.current) return;
      setWsStatus("disconnected");
      // Exponential backoff: 1s → 2s → 4s … capped at 30s
      reconnectTimer.current = setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, 30000);
        connectWs(oid);
      }, reconnectDelay.current);
    };
  }, [load]);

  useEffect(() => {
    if (!orgId) return;
    unmounted.current = false;
    connectWs(orgId);
    return () => {
      unmounted.current = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [orgId, connectWs]);

  // ── Send helpers ────────────────────────────────────────────────────────────

  const notify = (msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(null), 3000); };

  async function handleReply(e: { preventDefault(): void }) {
    e.preventDefault();
    if (!selected || sendingReply) return;

    const contactPhone = selected.contact_phone;
    if (!contactPhone) { setError("Contact phone not available"); return; }

    setSendingReply(true);
    setError(null);

    try {
      if (pendingFile) {
        const mt = getMediaType(pendingFile);
        const fd = new FormData();
        fd.append("phone_number_id", selected.phone_number_id);
        fd.append("to", contactPhone);
        fd.append("media_type", mt);
        if (replyText.trim()) fd.append("caption", replyText.trim());
        fd.append("file", pendingFile);
        await messagesApi.sendMedia(fd);
        setPendingFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
        setReplyText("");
      } else {
        if (!replyText.trim()) return;
        await messagesApi.sendText({
          phone_number_id: selected.phone_number_id,
          to: contactPhone,
          body: replyText.trim(),
        });
        setReplyText("");
        textareaRef.current?.focus();
      }
      messagesApi.getMessages(selected.id).then(setMsgs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send");
    } finally {
      setSendingReply(false);
    }
  }

  function handleReplyKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleReply(e);
    }
  }

  async function confirmDeleteConversation() {
    if (!selected) return;
    setShowDeleteConfirm(false);
    setDeletingConv(true);
    try {
      await messagesApi.deleteConversation(selected.id);
      setSelected(null);
      setMsgs([]);
      setConversations(prev => prev.filter(c => c.id !== selected.id));
      notify("Conversation deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete");
    } finally {
      setDeletingConv(false);
    }
  }

  async function handleSendTemplate(e: { preventDefault(): void }) {
    e.preventDefault(); setSendingTpl(true); setError(null);
    try {
      await messagesApi.sendTemplate({
        phone_number_id: tplForm.phone_number_id,
        to: tplForm.to,
        template_name: tplForm.template_name,
        language_code: tplForm.language_code,
      });
      notify("Template sent!"); setShowTplModal(false);
      load();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    finally { setSendingTpl(false); }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <AppLayout>
      <div style={{ height: "calc(100vh - 80px)", display: "flex", flexDirection: "column" }}>

        {/* Top bar */}
        <div style={s.topBar}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h1 style={s.pageTitle}>Conversations</h1>
            <span style={{
              width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
              background: wsStatus === "connected" ? "#00a884" : wsStatus === "connecting" ? "#f59e0b" : "#6b7280",
              boxShadow: wsStatus === "connected" ? "0 0 6px #00a884" : undefined,
            }} title={wsStatus === "connected" ? "Real-time connected" : wsStatus === "connecting" ? "Connecting…" : "Disconnected — reconnecting"} />
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <button onClick={() => setShowTplModal(true)} style={s.btnGreen}>📄 New Template Message</button>
          </div>
        </div>

        {error && (
          <div style={s.errorBanner}>
            {error}
            <button onClick={() => setError(null)} style={s.closeBtn}>✕</button>
          </div>
        )}
        {success && <div style={s.successBanner}>{success}</div>}

        {/* Main chat layout */}
        {loading ? (
          <div style={s.loading}>Loading…</div>
        ) : (
          <div style={s.chatLayout}>

            {/* ── Sidebar ── */}
            <div style={s.sidebar}>
              <div style={s.sidebarSearch}>
                <div style={s.searchIcon}>🔍</div>
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search conversations…"
                  style={{ background: "none", border: "none", outline: "none", flex: 1, fontSize: 13, color: "#e9edef" }}
                />
                {search && (
                  <button onClick={() => setSearch("")} style={{ background: "none", border: "none", color: "#8696a0", cursor: "pointer", fontSize: 14 }}>✕</button>
                )}
              </div>
              {conversations.length === 0 ? (
                <div style={{ padding: 24, textAlign: "center", color: "#8696a0", fontSize: 13 }}>
                  No conversations yet.<br />Send a template to start one.
                </div>
              ) : (
                conversations
                  .filter(c => !search || convLabel(c).toLowerCase().includes(search.toLowerCase()) || (c.contact_phone ?? "").includes(search))
                  .map(c => {
                    const badge = unread[c.id] ?? 0;
                    const preview = lastPreviews[c.id] ?? c.contact_phone ?? "WhatsApp conversation";
                    return (
                      <div
                        key={c.id}
                        onClick={() => { loadMessages(c); setUnread(u => ({ ...u, [c.id]: 0 })); }}
                        style={{ ...s.convItem, background: selected?.id === c.id ? "#2a3942" : "transparent" }}
                      >
                        <div style={s.avatar}>{convLabel(c)[0].toUpperCase()}</div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ ...s.convName, fontWeight: badge > 0 ? 700 : 500 }}>{convLabel(c)}</span>
                            <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                              {c.last_message_at && <span style={s.convTime}>{fmtTime(c.last_message_at)}</span>}
                              {badge > 0 && (
                                <span style={{ background: "#00a884", color: "#fff", borderRadius: 999, fontSize: 11, fontWeight: 700, minWidth: 18, height: 18, display: "flex", alignItems: "center", justifyContent: "center", padding: "0 4px" }}>
                                  {badge > 99 ? "99+" : badge}
                                </span>
                              )}
                            </div>
                          </div>
                          <div style={{ ...s.convPreview, fontWeight: badge > 0 ? 600 : 400, color: badge > 0 ? "#d1d7db" : "#8696a0" }}>
                            {preview}
                          </div>
                        </div>
                      </div>
                    );
                  })
              )}
            </div>

            {/* ── Thread ── */}
            {!selected ? (
              <div style={s.threadEmpty}>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 64, marginBottom: 16 }}>💬</div>
                  <div style={{ fontSize: 20, fontWeight: 600, color: "#d1d7db", marginBottom: 8 }}>TierceMsg</div>
                  <div style={{ fontSize: 14, color: "#8696a0" }}>Select a conversation to start messaging</div>
                </div>
              </div>
            ) : (
              <div style={s.thread}>

                {/* Thread header */}
                <div style={s.threadHeader}>
                  <div style={s.avatar}>{convLabel(selected)[0].toUpperCase()}</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, color: "#e9edef", fontSize: 15 }}>{convLabel(selected)}</div>
                    <div style={{ fontSize: 12, color: "#8696a0" }}>{selected.contact_phone ?? ""}</div>
                  </div>
                  <button onClick={() => loadMessages(selected)} style={s.iconBtn} title="Refresh">↻</button>
                  <button
                    onClick={() => setShowDeleteConfirm(true)}
                    disabled={deletingConv}
                    style={{ ...s.iconBtn, color: "#ef4444" }}
                    title="Delete conversation"
                  >
                    🗑
                  </button>
                  <span style={{
                    padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600,
                    background: selected.status === "open" ? "#00a884" : "#374151",
                    color: "#fff", marginLeft: 8,
                  }}>{selected.status}</span>
                </div>

                {/* Messages area */}
                <div style={s.messagesArea}>
                  {/* WhatsApp background pattern */}
                  <div style={s.chatBg} />

                  <div style={s.messagesInner}>
                    {loadingMsgs ? (
                      <div style={{ textAlign: "center", padding: 40, color: "#8696a0", fontSize: 13 }}>
                        Loading messages…
                      </div>
                    ) : msgs.length === 0 ? (
                      <div style={{ textAlign: "center", padding: 40, color: "#8696a0", fontSize: 13 }}>
                        No messages yet
                      </div>
                    ) : (
                      msgs.map(m => {
                        const outbound = m.direction === "outbound";
                        return (
                          <div key={m.id} style={{
                            display: "flex",
                            justifyContent: outbound ? "flex-end" : "flex-start",
                            marginBottom: 4,
                            paddingLeft: outbound ? "15%" : 0,
                            paddingRight: outbound ? 0 : "15%",
                          }}>
                            <div style={{
                              ...s.bubble,
                              background: outbound ? "#005c4b" : "#202c33",
                              borderRadius: outbound ? "8px 0 8px 8px" : "0 8px 8px 8px",
                              padding: m.message_type === "image" ? "4px 4px 6px" : undefined,
                            }}>
                              <MessageContent msg={m} templateList={templateList} />
                              <div style={s.bubbleMeta}>
                                <span style={{ color: "#8696a0", fontSize: 11 }}>{fmtTime(m.created_at)}</span>
                                {statusTicks(m.status, m.direction)}
                              </div>
                            </div>
                          </div>
                        );
                      })
                    )}
                    <div ref={bottomRef} />
                  </div>
                </div>

                {/* Reply bar */}
                <form onSubmit={handleReply} style={s.replyBar}>
                  {/* Hidden file input */}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*,video/*,audio/*,.pdf,.doc,.docx"
                    style={{ display: "none" }}
                    onChange={e => setPendingFile(e.target.files?.[0] ?? null)}
                  />

                  {/* File preview bar */}
                  {pendingFile && (
                    <div style={{
                      position: "absolute", bottom: "100%", left: 0, right: 0,
                      background: "#1a2a33", borderTop: "1px solid #2a3942",
                      padding: "8px 16px", display: "flex", alignItems: "center", gap: 10,
                    }}>
                      <span style={{ fontSize: 18 }}>{mediaTypeIcon(getMediaType(pendingFile))}</span>
                      <span style={{ flex: 1, fontSize: 13, color: "#e9edef", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {pendingFile.name}
                      </span>
                      <span style={{ fontSize: 11, color: "#8696a0", flexShrink: 0, textTransform: "uppercase" }}>
                        {getMediaType(pendingFile)}
                      </span>
                      <button
                        type="button"
                        onClick={() => { setPendingFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
                        style={{ background: "none", border: "none", color: "#8696a0", fontSize: 18, cursor: "pointer", padding: "2px 4px", lineHeight: 1 }}
                      >✕</button>
                    </div>
                  )}

                  {/* Attach / Template buttons */}
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    style={{ ...s.replyIconBtn, color: pendingFile ? "#00a884" : "#8696a0" }}
                    title="Attach file"
                  >📎</button>
                  <button
                    type="button"
                    onClick={() => { setTplForm(f => ({ ...f, phone_number_id: selected.phone_number_id, to: selected.contact_phone ?? "" })); setShowTplModal(true); }}
                    style={s.replyIconBtn}
                    title="Send template"
                  >📄</button>

                  <textarea
                    ref={textareaRef}
                    value={replyText}
                    onChange={e => setReplyText(e.target.value)}
                    onKeyDown={handleReplyKeyDown}
                    placeholder={pendingFile ? "Add a caption (optional)" : "Type a message"}
                    rows={1}
                    style={s.replyInput}
                  />
                  <button
                    type="submit"
                    disabled={sendingReply || (!replyText.trim() && !pendingFile)}
                    style={{ ...s.sendBtn, background: (replyText.trim() || pendingFile) ? "#00a884" : "#374151" }}
                    title="Send"
                  >
                    {sendingReply ? <span style={{ fontSize: 16 }}>…</span> : (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                        <path d="M2 12L22 2L14 22L11 13L2 12Z" fill="white" />
                      </svg>
                    )}
                  </button>
                </form>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Template Modal */}
      {showTplModal && (
        <div style={s.modalOverlay}>
          <div style={s.modalBox}>
            <div style={s.modalHeader}>
              <h2 style={s.modalTitle}>Send Template Message</h2>
              <button onClick={() => setShowTplModal(false)} style={s.modalClose}>✕</button>
            </div>
            <p style={{ fontSize: 13, color: "#8696a0", marginBottom: 16, lineHeight: 1.6 }}>
              Only <strong>APPROVED</strong> templates can be sent. Required to start or re-open a conversation.
            </p>
            {error && <div style={s.errorInline}>{error}</div>}
            <form onSubmit={handleSendTemplate} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <FormField label="Phone Number (sender)">
                <select
                  value={tplForm.phone_number_id}
                  onChange={e => setTplForm(f => ({ ...f, phone_number_id: e.target.value }))}
                  required style={s.input}
                >
                  <option value="">Select phone number…</option>
                  {phoneList.filter(p => p.is_active).map(p => (
                    <option key={p.id} value={p.id}>{p.display_number ?? p.phone_number_id}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="Recipient (E.164 format, e.g. +919876543210)">
                <input
                  value={tplForm.to}
                  onChange={e => setTplForm(f => ({ ...f, to: e.target.value }))}
                  placeholder="+919876543210" required style={s.input}
                />
              </FormField>
              <FormField label="Template">
                <select
                  value={tplForm.template_id}
                  onChange={e => {
                    const t = templateList.find(x => x.id === e.target.value);
                    setTplForm(f => ({ ...f, template_id: e.target.value, template_name: t?.name ?? "", language_code: t?.language ?? "en" }));
                  }}
                  required style={s.input}
                >
                  <option value="">Select template…</option>
                  {templateList.filter(t => t.status === "APPROVED").map(t => (
                    <option key={t.id} value={t.id}>{t.name} ({t.language})</option>
                  ))}
                </select>
              </FormField>
              <button
                type="submit"
                disabled={sendingTpl}
                style={{ ...s.btnGreen, opacity: sendingTpl ? 0.6 : 1, padding: "10px", borderRadius: 8, border: "none", cursor: sendingTpl ? "not-allowed" : "pointer" }}
              >
                {sendingTpl ? "Sending…" : "Send Template"}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && selected && (
        <div style={s.modalOverlay}>
          <div style={{
            background: "#233138",
            borderRadius: 12,
            width: 360,
            overflow: "hidden",
            boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
          }}>
            {/* Header */}
            <div style={{ padding: "20px 24px 0", borderBottom: "1px solid #2a3942" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, paddingBottom: 16 }}>
                <div style={{
                  width: 44, height: 44, borderRadius: "50%", background: "#ef4444",
                  display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                    <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600, color: "#e9edef" }}>Delete conversation?</div>
                  <div style={{ fontSize: 13, color: "#8696a0", marginTop: 2 }}>{convLabel(selected)}</div>
                </div>
              </div>
            </div>

            {/* Body */}
            <div style={{ padding: "16px 24px" }}>
              <p style={{ fontSize: 14, color: "#aebac1", lineHeight: 1.6, margin: 0 }}>
                All messages in this conversation will be permanently deleted.
                This action <strong style={{ color: "#e9edef" }}>cannot be undone</strong>.
              </p>
            </div>

            {/* Actions */}
            <div style={{ display: "flex", borderTop: "1px solid #2a3942" }}>
              <button
                onClick={() => setShowDeleteConfirm(false)}
                style={{
                  flex: 1, padding: "14px", background: "transparent", border: "none",
                  color: "#8696a0", fontSize: 14, fontWeight: 500, cursor: "pointer",
                  borderRight: "1px solid #2a3942",
                }}
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteConversation}
                disabled={deletingConv}
                style={{
                  flex: 1, padding: "14px", background: "transparent", border: "none",
                  color: "#ef4444", fontSize: 14, fontWeight: 600, cursor: "pointer",
                }}
              >
                {deletingConv ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ImageBubble({ src, caption }: { src: string; caption?: string }) {
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  return (
    <div>
      {state === "error" ? (
        <div style={{ padding: "8px 10px", fontSize: 13, color: "#8696a0", display: "flex", alignItems: "center", gap: 6 }}>
          <span>🖼</span><span>Image unavailable</span>
        </div>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={caption || "Image"}
          style={{ maxWidth: 280, maxHeight: 300, borderRadius: 6, display: state === "loading" ? "none" : "block" }}
          onLoad={() => setState("ok")}
          onError={() => setState("error")}
        />
      )}
      {state === "loading" && (
        <div style={{ width: 220, height: 120, borderRadius: 6, background: "#2a3942", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ color: "#8696a0", fontSize: 13 }}>Loading…</span>
        </div>
      )}
      {caption && state !== "loading" && (
        <div style={{ fontSize: 13, color: "#e9edef", padding: "4px 6px 0", wordBreak: "break-word" }}>{caption}</div>
      )}
    </div>
  );
}

function MessageContent({ msg, templateList }: { msg: Message; templateList: Template[] }) {
  const c = msg.content as Record<string, unknown>;
  // Resolve media_id: outbound messages store it as "media_id", inbound as "id"
  const mediaId = (c.media_id ?? c.id) as string | undefined;
  const caption = typeof c.caption === "string" ? c.caption : undefined;
  const filename = typeof c.filename === "string" ? c.filename : "file";

  if (msg.message_type === "image" && mediaId) {
    return (
      <ImageBubble src={mediaProxyUrl(mediaId)} caption={caption} />
    );
  }

  if (msg.message_type === "video" && mediaId) {
    return (
      <div>
        <video
          src={mediaProxyUrl(mediaId)}
          controls
          style={{ maxWidth: 280, maxHeight: 240, borderRadius: 6, display: "block" }}
        />
        {caption && <div style={{ fontSize: 13, color: "#e9edef", padding: "4px 6px 0" }}>{caption}</div>}
      </div>
    );
  }

  if (msg.message_type === "audio" && mediaId) {
    return (
      <div style={{ padding: "2px 0" }}>
        <audio controls src={mediaProxyUrl(mediaId)} style={{ maxWidth: 260, height: 36 }} />
      </div>
    );
  }

  if (msg.message_type === "document" && mediaId) {
    return (
      <a
        href={mediaProxyUrl(mediaId)}
        download={filename}
        target="_blank"
        rel="noreferrer"
        style={{ display: "flex", alignItems: "center", gap: 8, color: "#e9edef", textDecoration: "none" }}
      >
        <span style={{ fontSize: 22 }}>📄</span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500 }}>{filename}</div>
          {caption && <div style={{ fontSize: 12, color: "#8696a0" }}>{caption}</div>}
        </div>
      </a>
    );
  }

  if (msg.message_type === "sticker" && mediaId) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={mediaProxyUrl(mediaId)} alt="Sticker" style={{ maxWidth: 120, maxHeight: 120, display: "block" }} />
    );
  }

  // Text, template, reaction, location, unknown
  return (
    <div style={{ fontSize: 14, color: "#e9edef", lineHeight: 1.5, wordBreak: "break-word" }}>
      {extractText(msg.content, templateList)}
    </div>
  );
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={{ fontSize: 13, fontWeight: 500, color: "#d1d7db" }}>{label}</label>
      {children}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  topBar:        { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12, flexShrink: 0 },
  pageTitle:     { fontSize: 20, fontWeight: 700, color: "#111827", margin: 0 },
  btnGreen:      { padding: "9px 18px", background: "#00a884", color: "#fff", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer" },
  loading:       { color: "#8696a0", fontSize: 14, padding: 20 },
  errorBanner:   { marginBottom: 10, padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, color: "#991b1b", fontSize: 13, display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexShrink: 0 },
  successBanner: { marginBottom: 10, padding: "10px 14px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, color: "#166534", fontSize: 13, flexShrink: 0 },
  closeBtn:      { background: "none", border: "none", cursor: "pointer", color: "#991b1b", fontSize: 16, marginLeft: 8, flexShrink: 0 },

  // Layout
  chatLayout:    { flex: 1, display: "grid", gridTemplateColumns: "360px 1fr", background: "#111b21", borderRadius: 12, overflow: "hidden", minHeight: 0 },

  // Sidebar
  sidebar:       { borderRight: "1px solid #202c33", overflowY: "auto", display: "flex", flexDirection: "column" },
  sidebarSearch: { display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", background: "#202c33", borderBottom: "1px solid #2a3942", flexShrink: 0 },
  searchIcon:    { fontSize: 16 },
  convItem:      { display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", cursor: "pointer", borderBottom: "1px solid #1f2c34" },
  avatar:        { width: 42, height: 42, borderRadius: "50%", background: "#00a884", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 17, flexShrink: 0 },
  convName:      { fontSize: 15, fontWeight: 500, color: "#e9edef", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  convTime:      { fontSize: 11, color: "#8696a0", flexShrink: 0 },
  convPreview:   { fontSize: 13, color: "#8696a0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginTop: 2 },

  // Thread empty
  threadEmpty:   { flex: 1, display: "flex", alignItems: "center", justifyContent: "center", background: "#222e35" },

  // Thread
  thread:        { display: "flex", flexDirection: "column", flex: 1, minHeight: 0, position: "relative" },
  threadHeader:  { display: "flex", alignItems: "center", gap: 12, padding: "10px 20px", background: "#202c33", borderBottom: "1px solid #2a3942", flexShrink: 0 },
  iconBtn:       { background: "none", border: "none", color: "#8696a0", fontSize: 20, cursor: "pointer", padding: "4px 8px" },

  // Messages
  messagesArea:  { flex: 1, overflowY: "auto", position: "relative", minHeight: 0 },
  chatBg:        { position: "absolute", inset: 0, background: "#0b141a", opacity: 0.97, zIndex: 0 },
  messagesInner: { position: "relative", zIndex: 1, padding: "16px 20px", display: "flex", flexDirection: "column" },
  bubble:        { maxWidth: "100%", padding: "6px 10px 4px", borderRadius: 8, wordBreak: "break-word" },
  bubbleMeta:    { display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 2, marginTop: 2 },

  // Reply bar
  replyBar:      { display: "flex", alignItems: "flex-end", gap: 10, padding: "10px 16px", background: "#202c33", borderTop: "1px solid #2a3942", flexShrink: 0 },
  replyIconBtn:  { background: "none", border: "none", color: "#8696a0", fontSize: 22, cursor: "pointer", padding: "6px", flexShrink: 0 },
  replyInput:    {
    flex: 1, background: "#2a3942", border: "none", borderRadius: 8, padding: "10px 14px",
    color: "#e9edef", fontSize: 14, resize: "none", outline: "none",
    lineHeight: 1.5, maxHeight: 120, overflowY: "auto", fontFamily: "inherit",
  },
  sendBtn:       { width: 42, height: 42, borderRadius: "50%", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, transition: "background 0.2s" },

  // Modal
  modalOverlay:  { position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200, padding: 16 },
  modalBox:      { background: "#1f2c33", borderRadius: 12, padding: "24px 28px", width: "100%", maxWidth: 480, maxHeight: "90vh", overflowY: "auto" },
  modalHeader:   { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 },
  modalTitle:    { margin: 0, fontSize: 17, fontWeight: 700, color: "#e9edef" },
  modalClose:    { background: "none", border: "none", color: "#8696a0", fontSize: 20, cursor: "pointer" },
  errorInline:   { marginBottom: 12, padding: "8px 12px", background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 6, color: "#fca5a5", fontSize: 13 },
  input:         { padding: "9px 12px", background: "#2a3942", border: "1px solid #374151", borderRadius: 8, fontSize: 14, color: "#e9edef", outline: "none" },
};
