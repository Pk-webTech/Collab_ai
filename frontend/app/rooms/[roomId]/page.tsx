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
import { Brand, Composer, CopyButton, LoadingState, MessageBody } from "@/components/ChatUI";
import { ArrowLeft, Check, ChevronRight, FileText, LogOut, Menu, MessageSquare, Pencil, Sparkles, Trash2, Users, X } from "lucide-react";
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
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showDocuments, setShowDocuments] = useState(false);
  const nearBottom = useRef(true);
  const sendLock = useRef(false);
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
      if (document.hidden) return;
      Promise.all([getRoomMessages(roomId), getRoomMembers(roomId)]).then(([rows, people]) => {
        if (!cancelled) { setMessages(rows); setMembers(people); }
      }).catch((err) => { if (!cancelled) setError(err.message); });
    }, 10000);
    return () => {
      clearInterval(poll);
      cancelled = true;
      if (channel) supabase.removeChannel(channel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId]);

  useEffect(() => {
    if (nearBottom.current) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const nameFor = (userId: string | null) =>
    members.find((m) => m.user_id === userId)?.display_name ?? "Member";

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim() || sendLock.current) return;
    sendLock.current = true;
    nearBottom.current = true;
    setError(null);
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
      sendLock.current = false;
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

  if (!ready) return <LoadingState label="Opening your room" />;
  return <main className="workspace">
    {sidebarOpen && <button className="sidebar-scrim" aria-label="Close room details" onClick={() => setSidebarOpen(false)} />}
    <aside className={`workspace-sidebar ${sidebarOpen ? "open" : ""}`}><div className="sidebar-brand"><Brand /><button className="icon-button mobile-only" aria-label="Close room details" onClick={() => setSidebarOpen(false)}><X size={20} /></button></div>
    <nav className="sidebar-nav"><a href="/rooms"><ArrowLeft size={16} />All rooms</a><a href="/chat"><MessageSquare size={16} />Personal workspace</a></nav>
    <div className="room-sidebar-content"><div className="sidebar-label">SHARED SPACE</div>{renaming ? <form onSubmit={handleRename}><input aria-label="Room name" className="text-input" value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} autoFocus maxLength={100} /><div style={{ display: "flex", gap: 8, marginTop: 8 }}><button className="secondary-button" disabled={!nameDraft.trim()}><Check size={14} />Save</button><button type="button" className="quiet-button" onClick={() => setRenaming(false)}>Cancel</button></div></form> : <h2>{room?.name || "Room unavailable"}{isOwner && <button className="icon-button" aria-label="Rename room" onClick={() => { setNameDraft(room?.name || ""); setRenaming(true); }}><Pencil size={13} /></button>}</h2>}
      {room && <div className="room-code"><div><small>INVITE YOUR TEAM</small><strong>{room.join_code}</strong></div><CopyButton text={room.join_code} label="Copy code" /></div>}
      <div className="sidebar-label">MEMBERS · {members.length}</div>{members.map((m) => <div className="member-row" key={m.user_id}><span className={`presence-dot ${onlineIds.has(m.user_id) ? "online" : ""}`} title={onlineIds.has(m.user_id) ? "Online" : "Offline"} /><span>{m.display_name || "Member"}</span>{m.role === "owner" && <small>OWNER</small>}{isOwner && m.role !== "owner" && <button className="icon-button" aria-label={`Remove ${m.display_name || "member"}`} onClick={() => handleRemoveMember(m.user_id)}><X size={13} /></button>}</div>)}
      <p className="room-help">An extra mind at the table.<br />Start a message with <code>@ai</code> to bring your assistant into the conversation.</p>
    </div>{room && <button className="room-danger" onClick={isOwner ? handleDeleteRoom : handleLeaveRoom}>{isOwner ? <Trash2 size={14} /> : <LogOut size={14} />}{isOwner ? "Delete room" : "Leave room"}</button>}
    </aside><section className="workspace-main"><header className="workspace-header"><div className="breadcrumbs"><button className="icon-button mobile-only" aria-label="Open room details" onClick={() => setSidebarOpen(true)}><Menu size={20} /></button><a href="/rooms">Rooms</a><ChevronRight size={14} /><strong>{showDocuments ? "Shared library" : "Conversation"}</strong></div><div className="room-header-actions"><span className="privacy-badge"><Users size={14} />{onlineIds.size} online</span><button className="quiet-button" onClick={() => setShowDocuments(!showDocuments)}>{showDocuments ? <MessageSquare size={15} /> : <FileText size={15} />}{showDocuments ? "Back to chat" : "Shared files"}</button></div></header>
    {showDocuments ? <div className="resource-page"><div className="eyebrow">A SHARED SOURCE OF KNOWLEDGE</div><h1>Keep everyone on the same page.</h1><p className="page-intro">Files in this library are available to every member of this room.</p><DocumentsPanel roomId={roomId} /></div> : <><div className="chat-scroll" onScroll={(e) => { const el = e.currentTarget; nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100; }}><div className="chat-content">{error && <div className="error-banner" role="alert">{error}<button className="icon-button" aria-label="Dismiss error" onClick={() => setError(null)}><X size={15} /></button></div>}<div className="conversation-heading"><span className="eyebrow">COLLABORATE & CREATE</span><h1>{room?.name || "Room unavailable"}</h1></div>
    {!messages.length && <div className="room-empty"><Users size={40} strokeWidth={1.2} /><h2>Ideas are better together.</h2><p>Say hello, share a thought, or ask @ai to get things started.</p><button className="secondary-button" onClick={() => setDraft("@ai Help us brainstorm a plan for our project.")}><Sparkles size={15} />Start with a spark</button></div>}
    {messages.map((m) => <article className={`message message-${m.sender_type === "ai" ? "assistant" : "user"}`} key={m.id}><div className={`message-avatar ${m.sender_type === "ai" ? "assistant-avatar" : ""}`}>{m.sender_type === "ai" ? <Sparkles size={18} /> : nameFor(m.user_id).slice(0, 1).toUpperCase()}</div><div className="message-main"><div className="message-meta"><strong>{m.sender_type === "ai" ? "Collab" : m.user_id === myId.current ? "You" : nameFor(m.user_id)}</strong>{m.sender_type === "ai" && <span className="ai-label">AI</span>}<time>{new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></div><MessageBody content={m.content} />{m.sender_type === "ai" && <><CopyButton text={m.content} />{m.sources && <SourcesList sources={m.sources} />}</>}</div></article>)}<div ref={bottomRef} /></div></div><Composer room draft={draft} setDraft={setDraft} busy={sending || !room} onSubmit={handleSend} onDocuments={() => setShowDocuments(true)} /></>}
    </section>
  </main>;
}
