"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import {
  Room,
  RoomMember,
  RoomMessage,
  deleteRoom,
  getRoomMembers,
  getRoomMessages,
  listRooms,
  removeOrLeaveRoom,
  renameRoom,
  sendRoomMessage,
} from "@/lib/api";
import DocumentsPanel from "@/components/DocumentsPanel";
import SourcesList from "@/components/SourcesList";

export default function RoomChatPage() {
  const router = useRouter();
  const params = useParams<{ roomId: string }>();
  const roomId = params.roomId;

  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [room, setRoom] = useState<Room | null>(null);
  const [members, setMembers] = useState<RoomMember[]>([]);
  const [onlineIds, setOnlineIds] = useState<Set<string>>(new Set());
  const [messages, setMessages] = useState<RoomMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const myId = useRef<string | null>(null);

  const isOwner = room && myId.current && room.owner_id === myId.current;

  async function refreshMembers() {
    setMembers(await getRoomMembers(roomId));
  }

  useEffect(() => {
    setReady(false);
    setError(null);
    let cancelled = false;
    let channel: ReturnType<typeof supabase.channel> | null = null;

    (async () => {
      const { data: sessionData } = await supabase.auth.getSession();
      if (cancelled) return;

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
      if (cancelled) return;

      const found = rooms.find((r) => r.id === roomId) ?? null;
      setRoom(found);
      setNameDraft(found?.name ?? "");
      setMembers(memberList);
      setMessages(messageList);
      setReady(true);

      // Unique per mount: supabase.channel() returns the EXISTING channel for
      // a repeated topic, and postgres_changes handlers can't be attached
      // after subscribe(). StrictMode mounts effects twice.
      const ch = supabase
        .channel(`room:${roomId}:${crypto.randomUUID()}`, {
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
                  sources: row.sources ?? null,
                },
              ];
            });
          }
        )
        .on("presence", { event: "sync" }, () => {
          setOnlineIds(new Set(Object.keys(ch.presenceState())));
        });

      if (cancelled) {
        supabase.removeChannel(ch);
        return;
      }
      
      channel = ch;
      ch.subscribe(async (status) => {
        if (status === "SUBSCRIBED") {
          await ch.track({ display_name: myName });
        }
      });
    })().catch((err) => { if (!cancelled) { setError(err.message); setReady(true); } });

    const poll = setInterval(() => {
      Promise.all([getRoomMessages(roomId), getRoomMembers(roomId)]).then(([rows, people]) => {
        if (!cancelled) { setMessages(rows); setMembers(people); }
      }).catch((err) => { if (!cancelled) setError(err.message); });
    }, 5000);
    return () => {
      clearInterval(poll);
      cancelled = true;
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
      const sent = await sendRoomMessage(roomId, text);
      setMessages((prev) => prev.some((m) => m.id === sent.id) ? prev : [...prev, sent]);
    } catch (err) {
      setDraft(text);
      setError(err instanceof Error ? err.message : "Message failed");
    } finally {
      setSending(false);
    }
  }

  async function handleRename(e: React.FormEvent) {
    e.preventDefault();
    if (!nameDraft.trim() || !room) return;
    try {
      const updated = await renameRoom(roomId, nameDraft.trim());
      setRoom(updated);
      setRenaming(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Rename failed"); }
  }

  async function handleDeleteRoom() {
    if (!confirm("Delete this room for everyone? This can't be undone.")) return;
    try { await deleteRoom(roomId); router.push("/rooms"); }
    catch (err) { setError(err instanceof Error ? err.message : "Delete failed"); }
  }

  async function handleLeaveRoom() {
    if (!myId.current) return;
    if (!confirm("Leave this room?")) return;
    try { await removeOrLeaveRoom(roomId, myId.current); router.push("/rooms"); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not leave room"); }
  }

  async function handleRemoveMember(memberId: string) {
    if (!confirm("Remove this member from the room?")) return;
    try { await removeOrLeaveRoom(roomId, memberId); await refreshMembers(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not remove member"); }
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
          width: 240,
          borderRight: "1px solid var(--border)",
          background: "var(--panel)",
          padding: 16,
          overflowY: "auto",
        }}
      >
        <a href="/rooms" style={{ fontSize: 12, color: "var(--text-muted)" }}>
          ← All rooms
        </a>

        {renaming ? (
          <form onSubmit={handleRename} style={{ margin: "12px 0 4px" }}>
            <input
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              autoFocus
              onBlur={handleRename}
              style={renameInputStyle}
            />
          </form>
        ) : (
          <h2
            style={{ fontSize: 16, margin: "12px 0 4px", cursor: isOwner ? "pointer" : "default" }}
            onClick={() => isOwner && setRenaming(true)}
            title={isOwner ? "Click to rename" : undefined}
          >
            {room?.name}
          </h2>
        )}
        <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 16px" }}>
          Code: {room?.join_code}
        </p>

        <h3 style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 8px" }}>
          Members ({members.length})
        </h3>
        {members.map((m) => (
          <div
            key={m.user_id}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 6,
              padding: "4px 0",
              fontSize: 13,
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: onlineIds.has(m.user_id) ? "var(--accent)" : "var(--border)",
                }}
              />
              {m.display_name}
              {m.role === "owner" && (
                <span style={{ fontSize: 10, color: "var(--text-muted)" }}>owner</span>
              )}
            </span>
            {isOwner && m.role !== "owner" && (
              <button onClick={() => handleRemoveMember(m.user_id)} style={smallActionStyle}>
                remove
              </button>
            )}
          </div>
        ))}

        <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 16 }}>
          Type <code>@ai</code> at the start of a message to bring the assistant in.
        </p>

        <div style={{ marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
          <DocumentsPanel roomId={roomId} />
        </div>

        <div style={{ marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
          {isOwner ? (
            <button onClick={handleDeleteRoom} style={dangerButtonStyle}>
              Delete room
            </button>
          ) : (
            <button onClick={handleLeaveRoom} style={dangerButtonStyle}>
              Leave room
            </button>
          )}
        </div>
      </aside>

      <section style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: "24px 0" }}>
          <div style={{ maxWidth: 720, margin: "0 auto", padding: "0 24px" }}>
            {error && <p role="alert" style={{ color: "var(--danger)" }}>{error}</p>}
            {messages.map((m) => (
              <div key={m.id} style={{ marginBottom: 18 }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>
                  {m.sender_type === "ai" ? "Assistant" : nameFor(m.user_id)}
                </div>
                <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
                {m.sender_type === "ai" && m.sources && <SourcesList sources={m.sources} />}
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

const renameInputStyle: React.CSSProperties = {
  width: "100%",
  background: "var(--panel-raised)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "6px 8px",
  color: "var(--text)",
  fontSize: 15,
  fontWeight: 600,
  outline: "none",
};

const smallActionStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "var(--danger)",
  fontSize: 11,
  padding: 0,
};

const dangerButtonStyle: React.CSSProperties = {
  width: "100%",
  background: "transparent",
  border: "1px solid var(--danger)",
  borderRadius: 8,
  padding: "8px 12px",
  color: "var(--danger)",
  fontSize: 13,
};