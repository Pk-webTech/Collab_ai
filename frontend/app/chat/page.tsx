"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import {
  Conversation,
  Message,
  createConversation,
  getMessages,
  listConversations,
  sendMessageStream,
} from "@/lib/api";
import DocumentsPanel from "@/components/DocumentsPanel";
import MemoryPanel from "@/components/MemoryPanel";
import SourcesList from "@/components/SourcesList";

export default function ChatPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auth guard + initial load.
  useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
      if (!data.session) {
        router.replace("/");
        return;
      }
      const convos = await listConversations();
      setConversations(convos);
      if (convos.length > 0) {
        setActiveId(convos[0].id);
      }
      setReady(true);
    });
  }, [router]);

  // Load messages when the active conversation changes.
  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    getMessages(activeId).then(setMessages);
  }, [activeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleNewConversation() {
    const convo = await createConversation();
    setConversations((prev) => [convo, ...prev]);
    setActiveId(convo.id);
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim() || streaming) return;

    let conversationId = activeId;
    if (!conversationId) {
      const convo = await createConversation();
      setConversations((prev) => [convo, ...prev]);
      conversationId = convo.id;
      setActiveId(convo.id);
    }

    const userText = draft;
    setDraft("");
    setMessages((prev) => [
      ...prev,
      { id: "temp-user", role: "user", content: userText, created_at: new Date().toISOString() },
      { id: "temp-assistant", role: "assistant", content: "", created_at: new Date().toISOString() },
    ]);
    setStreaming(true);

    try {
      await sendMessageStream(conversationId, userText, (chunk) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.id === "temp-assistant") {
            next[next.length - 1] = { ...last, content: last.content + chunk };
          }
          return next;
        });
      });
      // Re-fetch so temp ids get replaced with real ones and the assistant
      // message picks up its persisted citation sources (if any).
      setMessages(await getMessages(conversationId));
    } finally {
      setStreaming(false);
    }
  }

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.replace("/");
  }

  if (!ready) {
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <p style={{ color: "var(--text-muted)" }}>Loading workspace…</p>
      </main>
    );
  }

  return (
    <main style={{ display: "flex", height: "100vh" }}>
      <aside
        style={{
          width: 260,
          borderRight: "1px solid var(--border)",
          background: "var(--panel)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ padding: 16, borderBottom: "1px solid var(--border)" }}>
          <button onClick={handleNewConversation} style={newChatButtonStyle}>
            + New chat
          </button>
          <a
            href="/rooms"
            style={{ display: "block", marginTop: 8, fontSize: 12, color: "var(--text-muted)" }}
          >
            Group rooms →
          </a>
        </div>
        <div style={{ flex: 1, overflowY: "auto" }}>
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveId(c.id)}
              style={{
                ...convoItemStyle,
                background: c.id === activeId ? "var(--panel-raised)" : "transparent",
              }}
            >
              {c.title}
            </button>
          ))}
          {conversations.length === 0 && (
            <p style={{ color: "var(--text-muted)", fontSize: 13, padding: 16 }}>
              No conversations yet.
            </p>
          )}
        </div>
        <div style={{ padding: 16, borderTop: "1px solid var(--border)" }}>
          <DocumentsPanel />
        </div>
        <div style={{ padding: 16, borderTop: "1px solid var(--border)", maxHeight: 220, overflowY: "auto" }}>
          <MemoryPanel />
        </div>
        <div style={{ padding: 16, borderTop: "1px solid var(--border)" }}>
          <button onClick={handleSignOut} style={signOutButtonStyle}>
            Sign out
          </button>
        </div>
      </aside>

      <section style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: "24px 0" }}>
          <div style={{ maxWidth: 720, margin: "0 auto", padding: "0 24px" }}>
            {messages.length === 0 && (
              <p style={{ color: "var(--text-muted)" }}>Ask anything to start.</p>
            )}
            {messages.map((m) => (
              <div key={m.id} style={{ marginBottom: 20 }}>
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--text-muted)",
                    marginBottom: 4,
                  }}
                >
                  {m.role === "user" ? "You" : "Assistant"}
                </div>
                <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
                {m.role === "assistant" && m.sources && <SourcesList sources={m.sources} />}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </div>

        <form
          onSubmit={handleSend}
          style={{
            borderTop: "1px solid var(--border)",
            padding: 16,
            display: "flex",
            justifyContent: "center",
          }}
        >
          <div style={{ display: "flex", gap: 8, width: "100%", maxWidth: 720 }}>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Message your workspace…"
              style={messageInputStyle}
            />
            <button type="submit" disabled={streaming} style={sendButtonStyle}>
              {streaming ? "…" : "Send"}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}

const newChatButtonStyle: React.CSSProperties = {
  width: "100%",
  background: "var(--accent)",
  border: "none",
  borderRadius: 8,
  padding: "8px 12px",
  color: "#0d1310",
  fontWeight: 600,
  fontSize: 13,
};

const convoItemStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  textAlign: "left",
  background: "transparent",
  border: "none",
  color: "var(--text)",
  padding: "10px 16px",
  fontSize: 13,
  borderBottom: "1px solid var(--border)",
};

const signOutButtonStyle: React.CSSProperties = {
  width: "100%",
  background: "transparent",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "8px 12px",
  color: "var(--text-muted)",
  fontSize: 13,
};

const messageInputStyle: React.CSSProperties = {
  flex: 1,
  background: "var(--panel-raised)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "10px 12px",
  color: "var(--text)",
  fontSize: 14,
  outline: "none",
};

const sendButtonStyle: React.CSSProperties = {
  background: "var(--accent)",
  border: "none",
  borderRadius: 8,
  padding: "10px 18px",
  color: "#0d1310",
  fontWeight: 600,
  fontSize: 14,
};
