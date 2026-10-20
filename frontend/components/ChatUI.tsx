"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Check, Copy, Sparkles, LoaderCircle, FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Brand() {
  return <a className="brand" href="/chat"><span className="brand-mark"><Sparkles size={20} /></span><span>collab<span className="brand-dot">.</span><small>YOUR AI WORKSPACE</small></span></a>;
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!copied && !failed) return;
    const timer = setTimeout(() => { setCopied(false); setFailed(false); }, 2200);
    return () => clearTimeout(timer);
  }, [copied, failed]);
  return <button className="quiet-button copy-button" onClick={async () => {
    try { await navigator.clipboard.writeText(text); setCopied(true); }
    catch { setFailed(true); }
  }} aria-label={copied ? "Copied" : label}>{copied ? <Check size={14} /> : <Copy size={14} />}<span>{failed ? "Could not copy" : copied ? "Copied" : label}</span></button>;
}

export function MessageBody({ content }: { content: string }) {
  return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
    a: ({ children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a>,
    pre: ({ children }) => <div className="code-block"><pre>{children}</pre></div>,
  }}>{content}</ReactMarkdown></div>;
}

export function Thinking() {
  return <span className="thinking" role="status" aria-label="Assistant is thinking"><i /><i /><i /><span>Thinking it through</span></span>;
}

export function Composer({ draft, setDraft, busy, onSubmit, room = false, onDocuments }: {
  draft: string; setDraft: (value: string) => void; busy: boolean;
  onSubmit: (event: React.FormEvent) => void; room?: boolean; onDocuments?: () => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (ref.current) { ref.current.style.height = "auto"; ref.current.style.height = `${Math.min(ref.current.scrollHeight, 180)}px`; }
  }, [draft]);
  return <div className="composer-wrap"><form className={`composer ${busy ? "is-busy" : ""}`} onSubmit={onSubmit}>
    <textarea ref={ref} value={draft} onChange={(e) => setDraft(e.target.value)} rows={1} maxLength={20000}
      aria-label={room ? "Message the room" : "Message your workspace"}
      placeholder={room ? "Message the room… use @ai to ask the assistant" : "Ask a question, explore an idea, or start with your documents…"}
      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (!busy && draft.trim()) e.currentTarget.form?.requestSubmit(); } }} />
    <div className="composer-tools"><div className="composer-hints">{onDocuments && <button type="button" className="quiet-button" onClick={onDocuments}><FileText size={16} /><span>Documents</span></button>}<span className="keyboard-hint">Shift + Enter for a new line</span></div>
      <button className="send-button" type="submit" disabled={busy || !draft.trim()} aria-label={busy ? "Sending message" : "Send message"}>{busy ? <LoaderCircle size={20} className="spin" /> : <ArrowUp size={21} />}</button>
    </div>
  </form><p className="composer-note">A little intelligence. A lot of possibility. Always double-check important answers.</p></div>;
}

export function LoadingState({ label = "Opening your workspace" }: { label?: string }) {
  return <main className="loading-screen"><span className="brand-mark"><Sparkles size={24} /></span><p><LoaderCircle className="spin" size={16} />{label}…</p></main>;
}
