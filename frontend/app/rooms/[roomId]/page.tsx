"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import {
  Room,
  RoomMember,
  RoomMessage,
  getRoomMembers,
  getRoomMessages,
  listRooms,
  sendRoomMessage,
} from "@/lib/api";

export default function RoomChatPage() {
  const router = useRouter();
  const params = useParams<{ roomId: string }>();
  const roomId = params.roomId;

  const [ready, setReady] = useState(false);
  const [room, setRoom] = useState<Room | null>(null);
  const [members, setMembers] = useState<RoomMember[]>([]);
  const [onlineIds, setOnlineIds] = useState<Set<string>>(new Set());
  const [messages, setMessages] = useState<RoomMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const myId = useRef<string | null>(null);

  useEffect(() => {
    let channel: ReturnType<typeof supabase.channel> | null = null;

    (async () => {
      const { data: sessionData } = await supabase.auth.getSession();
      if (!sessionData.session) {
        router.replace("/");
        return;
      }
      myId.current = sessionData.session.user.id;
      const myName =
        sessionData.session.user.email?.split("@")[0] ?? "Someone";

      const [rooms, memberList, messageList] = await Promise.all([
        listRooms(),
        getRoomMembers(roomId),
        getRoomMessages(roomId),
      ]);
      setRoom(rooms.find((r) => r.id === roomId) ?? null);
      setMembers(memberList);
      setMessages(messageList);
      setReady(true);

      // One Realtime channel per room: live-inserted messages + presence.
      channel = supabase
        .channel(`room:${roomId}`, {
          config: { presence: { key: myId.current! } },
        })
        .on(
          "postgres_changes",
          { event: "INSERT", schema: "public", table: "room_messages", filter: `room_id=eq.${roomId}` },
          (payload) => {
            const row = payload.new as any;
            setMessages((prev) => {
              if (prev.some((m) => m.id === row.id)) return prev;
              return [
                ...prev,
                {
                  id: row.id,
                  sender_type: row.sender_type,
                  user_id: row.user_id,
                  display_name: null, // backfilled from members list in render
                  content: row.content,
                  created_at: row.created_at,
                },
              ];
            });
          }
        )
        .on("presence", { event: "sync" }, () => {
          const state = channel!.presenceState();
          setOnlineIds(new Set(Object.keys(state)));
        })
        .subscribe(async (status) => {
          if (status === "SUBSCRIBED") {
            await channel!.track({ display_name: myName });
          }
        });
    })();

    return () => {
      if (channel) supabase.removeChannel(channel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const nameFor = (userId: string | null) =>
    members.find((m) => m.user_id === userId)?.display_name ?? "Member";

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim() || sending) return;
    setSending(true);
    const text = draft;
    setDraft("");
    try {
      // We don't optimistically append -- the Realtime INSERT event
      // delivers it back to us (and everyone else) a moment later.
      await sendRoomMessage(roomId, text);
    } finally {
      setSending(false);
    }
  }

  if (!ready) {
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <p style={{ color: "var(--text-muted)" }}>Loading room…</p>
      </main>
    );
  }

  return (
    <main style={{ display: "flex", height: "100vh" }}>
      <aside
        style={{
          width: 220,
          borderRight: "1px solid var(--border)",
          background: "var(--panel)",
          padding: 16,
        }}
      >
        <a href="/rooms" style={{ fontSize: 12, color: "var(--text-muted)" }}>
          ← All rooms
        </a>
        <h2 style={{ fontSize: 16, margin: "12px 0 4px" }}>{room?.name}</h2>
        <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 16px" }}>
          Code: {room?.join_code}
        </p>
        <h3 style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 8px" }}>
          Members ({members.length})
        </h3>
        {members.map((m) => (
          <div
            key={m.user_id}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 0", fontSize: 13 }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: onlineIds.has(m.user_id) ? "var(--accent)" : "var(--border)",
              }}
            />
            {m.display_name}
          </div>
        ))}
        <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 16 }}>
          Type <code>@ai</code> at the start of a message to bring the assistant in.
        </p>
      </aside>

      <section style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: "24px 0" }}>
          <div style={{ maxWidth: 720, margin: "0 auto", padding: "0 24px" }}>
            {messages.map((m) => (
              <div key={m.id} style={{ marginBottom: 18 }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>
                  {m.sender_type === "ai" ? "Assistant" : nameFor(m.user_id)}
                </div>
                <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
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
              placeholder="Message the room… (@ai to ask the assistant)"
              style={messageInputStyle}
            />
            <button type="submit" disabled={sending} style={sendButtonStyle}>
              {sending ? "…" : "Send"}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}

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
