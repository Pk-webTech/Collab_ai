"use client";
import { useEffect, useState, useRef } from "react";
import { Brain, Check, Pencil, Plus, Trash2, X, LoaderCircle } from "lucide-react";
import { Memory, createMemory, deleteMemory, listMemories, updateMemory } from "@/lib/api";
export default function MemoryPanel() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const lock = useRef(false);
  useEffect(() => { let cancelled = false; listMemories().then((rows) => { if (!cancelled) setMemories(rows); }).catch((err) => { if (!cancelled) setError(err.message); }); return () => { cancelled = true; }; }, []);
  async function action(id: string, fn: () => Promise<void>) {
    if (lock.current) return; lock.current = true; setBusy(id); setError(null);
    try { await fn(); } catch (err) { setError(err instanceof Error ? err.message : "Could not save changes"); }
    finally { lock.current = false; setBusy(null); }
  }
  return <section className="panel-card"><div className="section-heading"><h2>Your remembered details</h2><span>{memories.length} saved</span></div>
    {error && <div className="error-banner" role="alert">{error}</div>}
    <form className="memory-form" onSubmit={(e) => { e.preventDefault(); if (draft.trim()) void action("add", async () => { const m = await createMemory(draft.trim()); setMemories((prev) => [m, ...prev]); setDraft(""); }); }}>
      <input className="text-input" aria-label="New memory" placeholder="A preference, a project, something worth remembering…" maxLength={500} value={draft} onChange={(e) => setDraft(e.target.value)} />
      <button className="primary-button" disabled={!!busy || !draft.trim()}>{busy === "add" ? <LoaderCircle size={16} className="spin" /> : <Plus size={16} />}Add</button>
    </form><div className="memory-list">{memories.map((m) => <div key={m.id} className="memory-card">{editingId === m.id ? <textarea autoFocus className="text-input" aria-label="Edit memory" maxLength={500} value={editDraft} onChange={(e) => setEditDraft(e.target.value)} /> : <p>{m.content}</p>}<div className="memory-card-footer"><Brain size={16} /><div>{editingId === m.id ? <><button className="icon-button" aria-label="Save memory" disabled={!!busy || !editDraft.trim()} onClick={() => action(m.id, async () => { const updated = await updateMemory(m.id, editDraft.trim()); setMemories((prev) => prev.map((item) => item.id === m.id ? updated : item)); setEditingId(null); })}><Check size={16} /></button><button className="icon-button" aria-label="Cancel editing" onClick={() => setEditingId(null)}><X size={16} /></button></> : <button className="icon-button" aria-label="Edit memory" onClick={() => { setEditingId(m.id); setEditDraft(m.content); }}><Pencil size={14} /></button>}<button className="icon-button" aria-label="Delete memory" disabled={!!busy} onClick={() => { if (confirm("Delete this remembered detail?")) void action(m.id, async () => { await deleteMemory(m.id); setMemories((prev) => prev.filter((item) => item.id !== m.id)); }); }}><Trash2 size={14} /></button></div></div></div>)}</div>
    {!memories.length && <div className="empty-state"><Brain size={30} strokeWidth={1.2} />A fresh start. Add a detail above, or let your conversations fill this space.</div>}
  </section>;
}
