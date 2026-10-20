"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Brand } from "@/components/ChatUI";
import { ArrowRight, Eye, EyeOff, FileText, ShieldCheck, Sparkles, Users } from "lucide-react";
import { supabase } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [showPassword, setShowPassword] = useState(false);
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) router.replace("/chat");
    });
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      if (mode === "signin") {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      } else {
        const { data, error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        if (!data.session) {
          setNotice("Check your email to confirm your account, then sign in.");
          return;
        }
      }
      router.replace("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-page"><section className="auth-story"><Brand /><div className="auth-story-copy"><div className="eyebrow">THINK CLEARER. CREATE TOGETHER.</div><h1>Every great idea<br />starts with<br /><span>a conversation.</span></h1><p>A thoughtful space for your questions, your knowledge, and the people you build with.</p><div className="auth-features"><span><Sparkles size={15} />Personal AI</span><span><FileText size={15} />Your knowledge</span><span><Users size={15} />Shared ideas</span></div></div><div className="auth-story-footer">A little spark. Endless possibilities.</div></section>
    <section className="auth-form-side"><div className="auth-form-card"><h2>{mode === "signin" ? "Good to see you." : "Make space for your ideas."}</h2><p>{mode === "signin" ? "Your next idea is waiting. Let’s pick up where you left off." : "Create an account and start a conversation worth having."}</p>
    <form onSubmit={handleSubmit}><div><label className="field-label" htmlFor="email">Email address</label><input id="email" className="text-input" type="email" autoComplete="email" required placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} /></div><div><label className="field-label" htmlFor="password">Password</label><div className="auth-password"><input id="password" className="text-input" type={showPassword ? "text" : "password"} required minLength={6} autoComplete={mode === "signin" ? "current-password" : "new-password"} placeholder="At least 6 characters" value={password} onChange={(e) => setPassword(e.target.value)} /><button type="button" className="icon-button" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></div>
      {error && <div className="error-banner" role="alert">{error}</div>}{notice && <div className="auth-notice" role="status">{notice}</div>}<button className="primary-button" disabled={busy}>{busy ? "One moment…" : mode === "signin" ? "Step into your workspace" : "Create your workspace"}<ArrowRight size={17} /></button>
    </form><div className="auth-switch">{mode === "signin" ? "New around here?" : "Already have a space?"}<button disabled={busy} onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(null); setNotice(null); }}>{mode === "signin" ? "Create an account" : "Sign in"}</button></div><div className="auth-trust"><ShieldCheck size={14} />Your personal space stays personal.</div></div></section>
  </main>;
}
