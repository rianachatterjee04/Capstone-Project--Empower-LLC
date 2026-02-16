"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabaseClient";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"magic"|"password">("magic");
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) window.location.href = "/app";
    });
  }, []);

  async function signInMagic() {
    setStatus(null);
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin + "/app" },
    });
    setStatus(error ? error.message : "Check your email for the login link.");
  }

  async function signInPassword() {
    setStatus(null);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) setStatus(error.message);
    else window.location.href = "/app";
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border border-black/10 p-6 shadow-sm">
        <div className="text-xl font-semibold">Foundry People</div>
        <div className="mt-1 text-sm text-black/60">Employer portal sign-in</div>

        <div className="mt-6 flex gap-2">
          <button
            className={`rounded-xl px-3 py-2 text-sm border ${mode==="magic" ? "bg-black text-white border-black" : "border-black/15 hover:bg-black/5"}`}
            onClick={() => setMode("magic")}
          >
            Magic link
          </button>
          <button
            className={`rounded-xl px-3 py-2 text-sm border ${mode==="password" ? "bg-black text-white border-black" : "border-black/15 hover:bg-black/5"}`}
            onClick={() => setMode("password")}
          >
            Password
          </button>
        </div>

        <div className="mt-4 space-y-3">
          <Input label="Email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
          {mode==="password" ? (
            <Input label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          ) : null}
          {mode==="magic" ? (
            <Button onClick={signInMagic} disabled={!email}>Send magic link</Button>
          ) : (
            <Button onClick={signInPassword} disabled={!email || !password}>Sign in</Button>
          )}
          {status ? <div className="text-sm text-black/70">{status}</div> : null}
        </div>

        <div className="mt-6 text-xs text-black/50">
          Tip: Set Supabase user <code>app_metadata</code> for <code>org_id</code> and <code>role</code>.
        </div>
      </div>
    </div>
  );
}
