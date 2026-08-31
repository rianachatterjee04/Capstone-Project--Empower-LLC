"use client";
import { useState } from "react";
import { supabase } from "@/lib/supabaseClient";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

const IS_DEV = process.env.NODE_ENV === "development";

type AuthMode = "magic" | "password" | "signup";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [mode, setMode] = useState<AuthMode>("magic");
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  function enterPortalDev() {
    window.location.href = "/app";
  }

  async function signInMagic() {
    setStatus(null);
    setIsLoading(true);
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin + "/auth/callback" },
    });
    setStatus(error ? error.message : "Check your email for the login link.");
    setIsLoading(false);
  }

  async function signInPassword() {
    setStatus(null);
    setIsLoading(true);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setStatus(error.message);
      setIsLoading(false);
    } else {
      window.location.href = "/app";
    }
  }

  async function signUp() {
    setStatus(null);
    if (password !== confirmPassword) {
      setStatus("Passwords do not match.");
      return;
    }
    if (password.length < 6) {
      setStatus("Password must be at least 6 characters.");
      return;
    }
    setIsLoading(true);
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: window.location.origin + "/auth/callback" },
    });
    if (error) {
      setStatus(error.message);
    } else {
      setStatus("Account created! Check your email to confirm, or sign in if confirmation is disabled.");
    }
    setIsLoading(false);
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border border-black/10 p-6 shadow-sm">
        <div className="text-xl font-semibold">Fintra</div>
        <div className="mt-1 text-sm text-black/60">Employee portal sign-in</div>

        {IS_DEV && (
          <div className="mt-6 space-y-3">
            <Button onClick={enterPortalDev}>Enter employee portal</Button>
            <div className="text-xs text-black/50">
              Authentication is temporarily disabled for local development.
            </div>
            <div className="relative flex items-center py-2">
              <div className="flex-grow border-t border-black/10" />
              <span className="mx-3 text-xs text-black/30">or sign in with Supabase</span>
              <div className="flex-grow border-t border-black/10" />
            </div>
          </div>
        )}

        {/* Mode tabs */}
        <div className="mt-4 flex gap-2">
          {(["magic", "password", "signup"] as AuthMode[]).map((m) => (
            <button
              key={m}
              className={`rounded-xl px-3 py-2 text-sm border ${
                mode === m ? "bg-black text-white border-black" : "border-black/15 hover:bg-black/5"
              }`}
              onClick={() => { setMode(m); setStatus(null); }}
            >
              {m === "magic" ? "Magic link" : m === "password" ? "Sign in" : "Sign up"}
            </button>
          ))}
        </div>

        <div className="mt-4 space-y-3">
          <Input
            label="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
          />

          {(mode === "password" || mode === "signup") && (
            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}

          {mode === "signup" && (
            <Input
              label="Confirm password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          )}

          {mode === "magic" && (
            <Button variant="secondary" onClick={signInMagic} disabled={!email || isLoading}>
              {isLoading ? "Sending…" : "Send magic link"}
            </Button>
          )}
          {mode === "password" && (
            <Button variant="secondary" onClick={signInPassword} disabled={!email || !password || isLoading}>
              {isLoading ? "Signing in…" : "Sign in"}
            </Button>
          )}
          {mode === "signup" && (
            <Button onClick={signUp} disabled={!email || !password || !confirmPassword || isLoading}>
              {isLoading ? "Creating account…" : "Create account"}
            </Button>
          )}

          {status && (
            <div className={`text-sm ${status.includes("error") || status.includes("match") || status.includes("least") ? "text-red-500" : "text-black/70"}`}>
              {status}
            </div>
          )}
        </div>

        <div className="mt-6 text-xs text-black/50">
          Tip: Set Supabase user <code>app_metadata</code> for <code>org_id</code> and <code>role</code>.
        </div>
      </div>
    </div>
  );
}