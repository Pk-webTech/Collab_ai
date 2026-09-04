"use client";

import { useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Document, deleteDocument, listDocuments, uploadDocument } from "@/lib/api";

export default function DocumentsPanel({ roomId }: { roomId?: string }) {
  const [docs, setDocs] = useState<Document[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    setDocs(await listDocuments(roomId));
  }

  // Initial load, plus a live subscription so a document's status flips
  // from "processing" to "ready" (or "failed") on screen the moment the
  // backend's background task finishes -- no polling, no manual refresh.
  // Works for uploads from other room members too.
  useEffect(() => {
    let cancelled = false;
    let channel: ReturnType<typeof supabase.channel> | null = null;

    (async () => {
      let filter: string;
      if (roomId) {
        filter = `room_id=eq.${roomId}`;
      } else {
        const { data } = await supabase.auth.getSession();
        const uid = data.session?.user.id;
        if (!uid) return;
        filter = `owner_id=eq.${uid}`;
      }
      if (cancelled) return;

      setDocs(await listDocuments(roomId));
      if (cancelled) return;

      // Unique topic per mount. supabase.channel() returns the EXISTING
      // channel when the topic is already registered, and postgres_changes
      // handlers cannot be attached after subscribe(). StrictMode mounts
      // effects twice, so a fixed topic hits that on every dev render.
      const topic = `documents:${roomId ?? "personal"}:${crypto.randomUUID()}`;

      const ch = supabase.channel(topic).on(
        "postgres_changes",
        { event: "*", schema: "public", table: "documents", filter },
        (payload) => {
          const row = (payload.new ?? payload.old) as any;
          if (!roomId && row.room_id) return;

          if (payload.eventType === "DELETE") {
            setDocs((prev) => prev.filter((d) => d.id !== row.id));
            return;
          }

          const updated: Document = {
            id: row.id,
            filename: row.filename,
            char_count: row.char_count,
            status: row.status,
            created_at: row.created_at,
          };
          setDocs((prev) =>
            prev.some((d) => d.id === updated.id)
              ? prev.map((d) => (d.id === updated.id ? updated : d))
              : [updated, ...prev]
          );
        }
      );

      // The cleanup may already have run while we were awaiting above.
      if (cancelled) {
        supabase.removeChannel(ch);
        return;
      }
      channel = ch;
      ch.subscribe();
    })();

    return () => {
      cancelled = true;
      if (channel) supabase.removeChannel(channel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId]);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      // The upload call now returns as soon as the file is accepted -- the
      // row starts out "processing" and the Realtime subscription above
      // flips it to "ready" a moment later once chunking/embedding finishes.
      const doc = await uploadDocument(file, roomId);
      setDocs((prev) =>
        prev.some((d) => d.id === doc.id)
          ? prev.map((d) => (d.id === doc.id ? doc : d))
          : [doc, ...prev]
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDelete(id: string) {
    await deleteDocument(id);
    setDocs((prev) => prev.filter((d) => d.id !== id));
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 8px" }}>
          Documents {roomId ? "(shared with room)" : "(personal)"}
        </h3>
      </div>

      <label style={uploadButtonStyle}>
        {uploading ? "Uploading…" : "+ Upload file"}
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.pdf"
          onChange={handleFileChange}
          disabled={uploading}
          style={{ display: "none" }}
        />
      </label>

      {error && (
        <p style={{ color: "var(--danger)", fontSize: 12, margin: "8px 0 0" }}>{error}</p>
      )}

      <div style={{ marginTop: 8 }}>
        {docs.map((d) => (
          <div
            key={d.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "4px 0",
              fontSize: 12,
              color: "var(--text-muted)",
            }}
          >
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {d.status === "processing" ? "⏳" : d.status === "failed" ? "⚠️" : "📄"} {d.filename}
            </span>
            <button onClick={() => handleDelete(d.id)} style={deleteButtonStyle}>
              ✕
            </button>
          </div>
        ))}
        {docs.length === 0 && (
          <p style={{ fontSize: 12, color: "var(--text-muted)" }}>No documents yet.</p>
        )}
      </div>
    </div>
  );
}

const uploadButtonStyle: React.CSSProperties = {
  display: "block",
  textAlign: "center",
  background: "var(--panel-raised)",
  border: "1px dashed var(--border)",
  borderRadius: 8,
  padding: "6px 10px",
  fontSize: 12,
  color: "var(--text)",
  cursor: "pointer",
};

const deleteButtonStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "var(--text-muted)",
  fontSize: 11,
  padding: 2,
};