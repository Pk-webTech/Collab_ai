"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import {
  Conversation,
  Message,
  createConversation,
  getMessages,
  listConversations,
  sendMessageStream,
} from "@/lib/api";
import DocumentsPanel from "@/components/DocumentsPanel";
import MemoryPanel from "@/components/MemoryPanel";
import { Brand, Composer, CopyButton, LoadingState, MessageBody, Thinking } from "@/components/ChatUI";
import { ArrowUpRight, BookOpen, Brain, ChevronRight, FileText, Lightbulb, Menu, MessageSquare, Plus, Search, ShieldCheck, Sparkles, Users, X, LogOut } from "lucide-react";
import SourcesList from "@/components/SourcesList";

export default function ChatPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sendingRef = useRef(false);
  const loadVersion = useRef(0);
  const [view, setView] = useState<"chat" | "documents" | "memory">("chat");
  const [search, setSearch] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [userName, setUserName] = useState("you");
  const scrollRef = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auth guard + initial load.
  useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
      if (!data.session) {
        router.replace("/");
        return;
      }
      setUserName(data.session.user.email?.split("@")[0] || "you");
      const convos = await listConversations();
      setConversations(convos);

      setReady(true);
    }).catch((err) => { setError(err.message); setReady(true); });
  }, [router]);

  // Load messages when the active conversation changes.
  useEffect(() => {
    const version = ++loadVersion.current;
    if (sendingRef.current) return;
    setLoadingMessages(false);
    setMessages([]);
    if (!activeId) {
      setMessages([]);
      return;
    }
    setLoadingMessages(true);
    getMessages(activeId).then((rows) => {
      if (version === loadVersion.current) { setMessages(rows); setLoadingMessages(false); }
    }).catch((err) => { if (version === loadVersion.current) { setError(err.message); setLoadingMessages(false); } });
    return () => { ++loadVersion.current; };
  }, [activeId]);

  useEffect(() => {
    if (nearBottom.current) bottomRef.current?.scrollIntoView({ behavior: streaming ? "auto" : "smooth" });
  }, [messages]);

  function handleNewConversation() {
    if (sendingRef.current) return;
    setActiveId(null); setMessages([]); setDraft(""); setError(null);
    setView("chat"); setSidebarOpen(false); nearBottom.current = true;
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim() || sendingRef.current || loadingMessages) return;
    nearBottom.current = true;
    sendingRef.current = true;
    ++loadVersion.current;
    setStreaming(true);
    setError(null);
    const userText = draft.trim();
    let conversationId = activeId;
    try {
      if (!conversationId) {
        const convo = await createConversation(userText.slice(0, 80));
        setConversations((prev) => [convo, ...prev]);
        conversationId = convo.id;
        setActiveId(convo.id);
      }
      setDraft("");
      setMessages((prev) => [...prev,
        { id: "temp-user", role: "user", content: userText, created_at: new Date().toISOString() },
        { id: "temp-assistant", role: "assistant", content: "", created_at: new Date().toISOString() },
      ]);
      await sendMessageStream(conversationId, userText, (chunk) => {
        setMessages((prev) => prev.map((m) => m.id === "temp-assistant" ? { ...m, content: m.content + chunk } : m));
      });
      setMessages(await getMessages(conversationId));
      setConversations(await listConversations());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
      if (conversationId) {
        try { setMessages(await getMessages(conversationId)); } catch { /* Preserve visible reply if offline. */ }
      }
    } finally {
      sendingRef.current = false;
      setStreaming(false);
    }
  }

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.replace("/");
  }

  if (!ready) return <LoadingState />;
  const active = conversations.find((c) => c.id === activeId);
  const suggestions = [
    { icon: FileText, label: "Make sense of a document", text: "Summarize the key ideas in my uploaded documents.", tag: "UNDERSTAND" },
    { icon: Lightbulb, label: "Find a fresh perspective", text: "Help me brainstorm creative ideas for my next project.", tag: "EXPLORE" },
    { icon: BookOpen, label: "Break down something complex", text: "Explain a complex topic to me step by step. First ask what I want to learn.", tag: "LEARN" },
  ];
  return <main className="workspace">
    {sidebarOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
    <aside className={`workspace-sidebar ${sidebarOpen ? "open" : ""}`}>
      <div className="sidebar-brand"><Brand /><button className="icon-button mobile-only" aria-label="Close navigation" onClick={() => setSidebarOpen(false)}><X size={20} /></button></div>
      <button className="new-chat-button" disabled={streaming} onClick={handleNewConversation}><Plus size={18} />New conversation<span>↗</span></button>
      <div className="sidebar-label">WORKSPACE</div>
      <nav className="sidebar-nav" aria-label="Workspace navigation">
        <button className={view === "chat" ? "active" : ""} onClick={() => { setView("chat"); setSidebarOpen(false); }}><MessageSquare size={18} />Personal chat<span className="nav-dot" /></button>
        <a href="/rooms"><Users size={18} />Group rooms<ArrowUpRight size={15} /></a>
        <button className={view === "documents" ? "active" : ""} onClick={() => { setView("documents"); setSidebarOpen(false); }}><FileText size={18} />Documents</button>
        <button className={view === "memory" ? "active" : ""} onClick={() => { setView("memory"); setSidebarOpen(false); }}><Brain size={18} />Memory</button>
      </nav>
      <div className="history-heading"><span className="sidebar-label">RECENT CONVERSATIONS</span><span>{conversations.length}</span></div>
      <label className="sidebar-search"><Search size={15} /><input aria-label="Search conversations" placeholder="Find a conversation…" value={search} onChange={(e) => setSearch(e.target.value)} /></label>
      <div className="conversation-list">{conversations.filter((c) => c.title.toLowerCase().includes(search.toLowerCase())).map((c) => <button key={c.id} className={activeId === c.id && view === "chat" ? "selected" : ""} disabled={streaming} onClick={() => { setActiveId(c.id); setView("chat"); setSidebarOpen(false); setError(null); nearBottom.current = true; }}><MessageSquare size={14} /><span>{c.title}</span><ChevronRight size={13} /></button>)}
        {!conversations.length && <p className="sidebar-empty">Your ideas will feel at home here.<br />Start your first conversation.</p>}
        {!!conversations.length && !conversations.some((c) => c.title.toLowerCase().includes(search.toLowerCase())) && <p className="sidebar-empty">No matching conversations.</p>}
      </div>
      <div className="sidebar-tip"><Sparkles size={17} /><div><strong>A workspace that knows you</strong><p>Add documents to give your ideas more context.</p><button onClick={() => { setView("documents"); setSidebarOpen(false); }}>Explore your library <ArrowUpRight size={13} /></button></div></div>
      <div className="sidebar-user"><span className="user-avatar">{userName.slice(0, 2).toUpperCase()}</span><div><strong>{userName}</strong><small>Personal workspace</small></div><button className="icon-button" aria-label="Sign out" title="Sign out" onClick={handleSignOut}><LogOut size={17} /></button></div>
    </aside>
    <section className="workspace-main">
      <header className="workspace-header"><div className="breadcrumbs"><button className="icon-button mobile-only" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}><Menu size={21} /></button><span>My workspace</span><ChevronRight size={14} /><strong>{view === "chat" ? "Personal chat" : view === "documents" ? "Documents" : "Memory"}</strong></div><span className="privacy-badge"><ShieldCheck size={14} />Only you</span></header>
      {view !== "chat" ? <div className="resource-page"><div className="eyebrow">YOUR WORKSPACE, WITH CONTEXT</div><h1>{view === "documents" ? "A home for your knowledge." : "Little details. Better conversations."}</h1><p className="page-intro">{view === "documents" ? "Bring your files into the conversation. Your assistant can find, explain, and connect what matters." : "A little context goes a long way. Manage what your assistant remembers about you."}</p>{view === "documents" ? <DocumentsPanel /> : <MemoryPanel />}</div> : <>
      <div className="chat-scroll" ref={scrollRef} onScroll={() => { const el = scrollRef.current; if (el) nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100; }}>
        <div className="chat-content">
          {error && <div className="error-banner" role="alert">{error}<button className="icon-button" aria-label="Dismiss error" onClick={() => setError(null)}><X size={16} /></button></div>}
          {loadingMessages ? <div className="message-loading"><Thinking /></div> : messages.length === 0 ? <div className="welcome">
            <span className="welcome-pill"><span />SPACE FOR YOUR NEXT BIG IDEA</span>
            <div className="welcome-art" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="spark-tile"><Sparkles size={36} strokeWidth={1.4} /></div><span className="orbit-dot" /></div>
            <h1>A little spark.<br /><span>Endless possibilities.</span></h1><p>Your ideas, your documents, your next breakthrough.<br />Think it through with an assistant that works with you.</p>
            <div className="suggestion-grid">{suggestions.map(({ icon: Icon, label, text, tag }) => <button key={tag} onClick={() => { setDraft(text); document.querySelector<HTMLTextAreaElement>(".composer textarea")?.focus(); }}><span className="suggestion-top"><Icon size={21} /><ArrowUpRight size={16} /></span><small>{tag}</small><strong>{label}</strong></button>)}</div>
            <div className="welcome-footnote"><ShieldCheck size={14} />Your personal conversations stay personal.</div>
          </div> : <><div className="conversation-heading"><span className="eyebrow">PERSONAL CONVERSATION</span><h1>{active?.title === "New chat" ? "Let’s think it through." : active?.title || "A new idea takes shape."}</h1></div>{messages.map((m) => <article key={m.id} className={`message message-${m.role}`}><div className={`message-avatar ${m.role === "assistant" ? "assistant-avatar" : ""}`}>{m.role === "assistant" ? <Sparkles size={18} /> : userName.slice(0, 1).toUpperCase()}</div><div className="message-main"><div className="message-meta"><strong>{m.role === "user" ? "You" : "Collab"}</strong>{m.role === "assistant" && <span className="ai-label">AI</span>}<time>{new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></div>{!m.content && streaming ? <Thinking /> : <MessageBody content={m.content} />}{m.role === "assistant" && !!m.content && <><div className="message-actions"><CopyButton text={m.content} /></div>{m.sources && <SourcesList sources={m.sources} />}</>}</div></article>)}</>}
          <div ref={bottomRef} />
        </div>
      </div><Composer draft={draft} setDraft={setDraft} busy={streaming || loadingMessages} onSubmit={handleSend} onDocuments={() => setView("documents")} />
      </>}
    </section>
  </main>;
}
