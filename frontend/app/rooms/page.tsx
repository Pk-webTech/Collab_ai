"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { Brand, LoadingState } from "@/components/ChatUI";
import { ArrowLeft, ArrowUpRight, KeyRound, Plus, Users } from "lucide-react";
import { Room, createRoom, joinRoom, listRooms } from "@/lib/api";

export default function RoomsPage() {
  const router = useRouter();
  const [busy, setBusy] = useState<"create" | "join" | null>(null);
  const [ready, setReady] = useState(false);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [newRoomName, setNewRoomName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
      if (!data.session) {
        router.replace("/");
        return;
      }
      setRooms(await listRooms());
      setReady(true);
    }).catch((err) => { setError(err.message); setReady(true); });
  }, [router]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newRoomName.trim() || busy) return;
    setBusy("create");
    setError(null);
    try {
      const room = await createRoom(newRoomName.trim());
      setNewRoomName("");
      router.push(`/rooms/${room.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create room");
    } finally { setBusy(null); }
  }

  async function handleJoin(e: React.FormEvent) {
    e.preventDefault();
    if (!joinCode.trim() || busy) return;
    setBusy("join");
    setError(null);
    try {
      const room = await joinRoom(joinCode.trim());
      router.push(`/rooms/${room.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to join room");
    } finally { setBusy(null); }
  }

  if (!ready) return <LoadingState label="Finding your rooms" />;
  return <main className="rooms-page"><div className="page-topbar"><Brand /><a href="/chat"><ArrowLeft size={14} />Back to personal chat</a></div>
    <div className="page-heading"><div className="eyebrow">BETTER IDEAS, TOGETHER</div><h1>Good company. Great conversations.</h1><p className="page-intro">A shared space for your team, your documents, and an extra spark of intelligence.</p></div>
    {error && <div className="error-banner" role="alert">{error}</div>}
    <div className="room-forms"><form className="room-form" onSubmit={handleCreate}><Users size={26} strokeWidth={1.4} /><h2>Make room for your team</h2><p>Start a space, share the code, and build on each other’s ideas.</p><label className="field-label" htmlFor="room-name">Room name</label><div className="room-form-row"><input id="room-name" className="text-input" value={newRoomName} maxLength={100} onChange={(e) => setNewRoomName(e.target.value)} placeholder="e.g. The brainstorm room" required /><button className="primary-button" disabled={!!busy || !newRoomName.trim()}><Plus size={15} />{busy === "create" ? "Creating…" : "Create"}</button></div></form>
    <form className="room-form" onSubmit={handleJoin}><KeyRound size={26} strokeWidth={1.4} /><h2>Already have an invitation?</h2><p>Enter your six-character room code to join the conversation.</p><label className="field-label" htmlFor="join-code">Invitation code</label><div className="room-form-row"><input id="join-code" className="text-input" value={joinCode} maxLength={6} onChange={(e) => setJoinCode(e.target.value.toUpperCase())} placeholder="e.g. 7F3K9Q" required /><button className="secondary-button" disabled={!!busy || joinCode.trim().length !== 6}>{busy === "join" ? "Joining…" : "Join room"}<ArrowUpRight size={15} /></button></div></form></div>
    <div className="section-heading"><h2>Your spaces</h2><span>{rooms.length} rooms</span></div><div className="room-cards">{rooms.map((r) => <a className="room-card" key={r.id} href={`/rooms/${r.id}`}><div className="room-card-icon"><Users size={23} strokeWidth={1.4} /><ArrowUpRight size={17} /></div><h3>{r.name}</h3><div className="room-card-footer"><span>CODE · {r.join_code}</span><span>Open room →</span></div></a>)}</div>{!rooms.length && <div className="empty-state"><Users size={30} />Your next collaboration starts here. Create or join a room above.</div>}
  </main>;
}
