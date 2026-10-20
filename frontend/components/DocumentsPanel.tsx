"use client";
import { useEffect, useRef, useState } from "react";
import { Check, FileText, FolderOpen, LoaderCircle, Trash2, UploadCloud, AlertCircle } from "lucide-react";
import { supabase } from "@/lib/supabase";
import { Document, deleteDocument, listDocuments, uploadDocument } from "@/lib/api";

export default function DocumentsPanel({ roomId }: { roomId?: string }) {
  const [docs, setDocs] = useState<Document[]>([]);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadLock = useRef(false);
  useEffect(() => {
    let cancelled = false;
    let fetching = false;
    let channel: ReturnType<typeof supabase.channel> | null = null;
    async function refresh() {
      if (fetching) return;
      fetching = true;
      try { const rows = await listDocuments(roomId); if (!cancelled) setDocs(rows); }
      catch (err) { if (!cancelled) setError(err instanceof Error ? err.message : "Could not load documents"); }
      finally { fetching = false; }
    }
    void refresh();
    void (async () => {
      const { data } = await supabase.auth.getSession();
      if (cancelled || !data.session) return;
      channel = supabase.channel(`docs:${crypto.randomUUID()}`).on("postgres_changes", {
        event: "*", schema: "public", table: "documents",
        filter: roomId ? `room_id=eq.${roomId}` : `owner_id=eq.${data.session.user.id}`,
      }, () => { void refresh(); }).subscribe();
    })().catch(() => {});
    const timer = setInterval(() => { if (!document.hidden) void refresh(); }, 10000);
    return () => { cancelled = true; clearInterval(timer); if (channel) void supabase.removeChannel(channel); };
  }, [roomId]);
  async function handleUpload(file?: File) {
    if (!file || uploadLock.current) return;
    if (file.size > 5 * 1024 * 1024) { setError("Choose a file smaller than 5 MB."); return; }
    if (!/\.(txt|md|pdf)$/i.test(file.name)) { setError("Please choose a PDF, text, or Markdown file."); return; }
    uploadLock.current = true; setUploading(true); setError(null);
    try { const doc = await uploadDocument(file, roomId); setDocs((prev) => [doc, ...prev.filter((d) => d.id !== doc.id)]); }
    catch (err) { setError(err instanceof Error ? err.message : "Upload failed"); }
    finally { uploadLock.current = false; setUploading(false); if (fileInputRef.current) fileInputRef.current.value = ""; }
  }
  async function handleDelete(id: string) {
    if (!confirm("Remove this document? Its saved chunks will also be deleted.")) return;
    setDeleting(id); setError(null);
    try { await deleteDocument(id); setDocs((prev) => prev.filter((d) => d.id !== id)); }
    catch (err) { setError(err instanceof Error ? err.message : "Delete failed"); }
    finally { setDeleting(null); }
  }
  return <section className="panel-card" aria-label="Document library">
    <div className="section-heading"><h2>{roomId ? "Room library" : "Your library"}</h2><span>{docs.length} {docs.length === 1 ? "document" : "documents"}</span></div>
    <label className={`dropzone ${dragging ? "dragging" : ""}`} onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(e) => { e.preventDefault(); setDragging(false); void handleUpload(e.dataTransfer.files[0]); }}>
      {uploading ? <LoaderCircle size={30} className="spin" /> : <UploadCloud size={30} strokeWidth={1.3} />}
      <strong>{uploading ? "Uploading your document…" : "Drop a file here, or click to browse"}</strong><small>PDF, Markdown, or text · Up to 5 MB</small>
      <input ref={fileInputRef} type="file" accept=".txt,.md,.pdf" aria-label="Upload document" onChange={(e) => void handleUpload(e.target.files?.[0])} disabled={uploading} className="upload-input" />
    </label>
    {error && <div className="error-banner" role="alert" style={{ marginTop: 16 }}>{error}</div>}
    <div className="document-list">{docs.map((d) => <div className="document-row" key={d.id}><span className="file-icon"><FileText size={20} strokeWidth={1.5} /></span><div className="document-info"><strong title={d.filename}>{d.filename}</strong><small>{d.char_count.toLocaleString()} characters · {new Date(d.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</small></div><span className={`status-tag ${d.status}`}>{d.status === "processing" ? <LoaderCircle size={11} className="spin" /> : d.status === "failed" ? <AlertCircle size={11} /> : <Check size={11} />}{d.status === "processing" ? "Indexing" : d.status === "failed" ? "Failed" : "Ready"}</span><button className="icon-button" title={`Delete ${d.filename}`} aria-label={`Delete ${d.filename}`} disabled={deleting === d.id} onClick={() => handleDelete(d.id)}>{deleting === d.id ? <LoaderCircle size={14} className="spin" /> : <Trash2 size={14} />}</button></div>)}</div>
    {!docs.length && <div className="empty-state"><FolderOpen size={28} strokeWidth={1.2} />A little knowledge goes a long way.<br />Upload a document to get started.</div>}
  </section>;
}
