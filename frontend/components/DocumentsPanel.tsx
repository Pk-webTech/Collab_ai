"use client";

import { useEffect, useRef, useState } from "react";
import { Document, deleteDocument, listDocuments, uploadDocument } from "@/lib/api";

export default function DocumentsPanel({ roomId }: { roomId?: string }) {
  const [docs, setDocs] = useState<Document[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    setDocs(await listDocuments(roomId));
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId]);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await uploadDocument(file, roomId);
      await refresh();
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
              📄 {d.filename}
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
