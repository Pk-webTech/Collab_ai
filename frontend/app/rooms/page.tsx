"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { Room, createRoom, joinRoom, listRooms } from "@/lib/api";

export default function RoomsPage() {
  const router = useRouter();
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
    });
  }, [router]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newRoomName.trim()) return;
    setError(null);
    try {
      const room = await createRoom(newRoomName.trim());
      setNewRoomName("");
      router.push(`/rooms/${room.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create room");
    }
  }

  async function handleJoin(e: React.FormEvent) {
    e.preventDefault();
    if (!joinCode.trim()) return;
    setError(null);
    try {
      const room = await joinRoom(joinCode.trim());
      router.push(`/rooms/${room.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to join room");
    }
  }

  if (!ready) {
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <p style={{ color: "var(--text-muted)" }}>Loading rooms…</p>
      </main>
    );
  }

  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: 32 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: 20 }}>Group rooms</h1>
        <a href="/chat" style={{ fontSize: 13 }}>
          ← Back to personal chat
        </a>
      </div>

      <div style={{ display: "flex", gap: 16, margin: "24px 0" }}>
        <form onSubmit={handleCreate} style={{ ...cardStyle, flex: 1 }}>
          <h2 style={cardTitleStyle}>Create a room</h2>
          <input
            value={newRoomName}
            onChange={(e) => setNewRoomName(e.target.value)}
            placeholder="Room name"
            style={inputStyle}
          />
          <button type="submit" style={buttonStyle}>
            Create
          </button>
        </form>

        <form onSubmit={handleJoin} style={{ ...cardStyle, flex: 1 }}>
          <h2 style={cardTitleStyle}>Join with a code</h2>
          <input
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
            placeholder="e.g. 7F3K9Q"
            style={inputStyle}
          />
          <button type="submit" style={buttonStyle}>
            Join
          </button>
        </form>
      </div>

      {error && <p style={{ color: "var(--danger)", fontSize: 13 }}>{error}</p>}

      <h2 style={{ fontSize: 14, color: "var(--text-muted)", margin: "24px 0 8px" }}>
        Your rooms
      </h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {rooms.map((r) => (
          <a
            key={r.id}
            href={`/rooms/${r.id}`}
            style={{
              display: "flex",
              justifyContent: "space-between",
              padding: "12px 16px",
              background: "var(--panel)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              textDecoration: "none",
              color: "var(--text)",
            }}
          >
            <span>{r.name}</span>
            <span style={{ color: "var(--text-muted)", fontSize: 13 }}>{r.join_code}</span>
          </a>
        ))}
        {rooms.length === 0 && (
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            No rooms yet — create one or join with a code.
          </p>
        )}
      </div>
    </main>
  );
}

const cardStyle: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  padding: 16,
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

const cardTitleStyle: React.CSSProperties = { fontSize: 14, margin: 0 };

const inputStyle: React.CSSProperties = {
  background: "var(--panel-raised)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "8px 10px",
  color: "var(--text)",
  fontSize: 14,
  outline: "none",
};

const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  border: "none",
  borderRadius: 8,
  padding: "8px 12px",
  color: "#0d1310",
  fontWeight: 600,
  fontSize: 13,
};
