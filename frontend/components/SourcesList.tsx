"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import { Source } from "@/lib/api";
export default function SourcesList({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);
  if (!sources?.length) return null;
  const names = [...new Set(sources.map((s) => s.filename))];
  return <div><button className="sources-toggle" aria-expanded={open} onClick={() => setOpen(!open)}><FileText size={12} /><span>{names.length} {names.length === 1 ? "source" : "sources"} · {names.join(", ")}</span>{open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</button>{open && <div className="sources-grid">{sources.map((s, i) => <div className="source-card" key={`${s.document_id}-${s.chunk_index}-${i}`}><strong>{s.filename} · Excerpt {s.chunk_index + 1}</strong><p>{s.snippet}</p></div>)}</div>}</div>;
}
