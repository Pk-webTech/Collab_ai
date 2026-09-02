"use client";

import { useState } from "react";
import { Source } from "@/lib/api";

export default function SourcesList({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);
  if (!sources || sources.length === 0) return null;

  const uniqueFilenames = Array.from(new Set(sources.map((s) => s.filename)));

  return (
    <div style={{ marginTop: 6 }}>
      <button onClick={() => setOpen(!open)} style={toggleStyle}>
        {open ? "▾" : "▸"} Sources: {uniqueFilenames.join(", ")}
      </button>
      {open && (
        <div style={{ marginTop: 4, display: "flex", flexDirection: "column", gap: 6 }}>
          {sources.map((s, i) => (
            <div key={i} style={snippetStyle}>
              <div style={{ color: "var(--accent)", marginBottom: 2 }}>
                {s.filename} · chunk {s.chunk_index}
              </div>
              <div>{s.snippet}…</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const toggleStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "var(--text-muted)",
  fontSize: 12,
  padding: 0,
};

const snippetStyle: React.CSSProperties = {
  background: "var(--panel-raised)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "6px 8px",
  fontSize: 12,
  color: "var(--text-muted)",
};
