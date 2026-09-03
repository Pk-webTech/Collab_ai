"use client";

import { useEffect, useState } from "react";
import { Memory, createMemory, deleteMemory, listMemories, updateMemory } from "@/lib/api";

export default function MemoryPanel() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");

  async function refresh() {
    setMemories(await listMemories());
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    const m = await createMemory(draft.trim());
    setMemories((prev) => [m, ...prev]);
    setDraft("");
  }

  async function handleSaveEdit(id: string) {
    if (!editDraft.trim()) {
      setEditingId(null);
      return;
    }
    const updated = await updateMemory(id, editDraft.trim());
    setMemories((prev) => prev.map((m) => (m.id === id ? updated : m)));
    setEditingId(null);
  }

  async function handleDelete(id: string) {
    await deleteMemory(id);
    setMemories((prev) => prev.filter((m) => m.id !== id));
  }

  return (
    <div>
      <h3 style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 8px" }}>
        Memory
      </h3>

      <form onSubmit={handleAdd} style={{ display: "flex", gap: 4, marginBottom: 8 }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add something to remember…"
          style={inputStyle}
        />
        <button type="submit" style={addButtonStyle}>
          +
        </button>
      </form>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {memories.map((m) => (
          <div key={m.id} style={rowStyle}>
            {editingId === m.id ? (
              <input
                value={editDraft}
                onChange={(e) => setEditDraft(e.target.value)}
                onBlur={() => handleSaveEdit(m.id)}
                onKeyDown={(e) => e.key === "Enter" && handleSaveEdit(m.id)}
                autoFocus
                style={inputStyle}
              />
            ) : (
              <span
                onClick={() => {
                  setEditingId(m.id);
                  setEditDraft(m.content);
                }}
                title="Click to edit"
                style={{ flex: 1, cursor: "pointer" }}
              >
                {m.content}
              </span>
            )}
            <button onClick={() => handleDelete(m.id)} style={deleteButtonStyle}>
              ✕
            </button>
          </div>
        ))}
        {memories.length === 0 && (
          <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Nothing remembered yet — it fills in automatically as you chat, or add your own.
          </p>
        )}
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  flex: 1,
  background: "var(--panel-raised)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "4px 6px",
  color: "var(--text)",
  fontSize: 12,
  outline: "none",
};

const addButtonStyle: React.CSSProperties = {
  background: "var(--accent)",
  border: "none",
  borderRadius: 6,
  width: 24,
  color: "#0d1310",
  fontWeight: 700,
  fontSize: 13,
};

const rowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  fontSize: 12,
  color: "var(--text-muted)",
};

const deleteButtonStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "var(--text-muted)",
  fontSize: 11,
  padding: 2,
};
