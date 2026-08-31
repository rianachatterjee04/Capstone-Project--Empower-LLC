"use client";
import { useEffect } from "react";
import { supabase } from "@/lib/supabaseClient";

export default function AuthCallback() {
  useEffect(() => {
    // This page handles the redirect after magic link / OAuth
    // Supabase puts the token in the URL hash — getSession() exchanges it
    supabase.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_IN" && session) {
        window.location.href = "/app";
      }
    });

    // Also check if already signed in (e.g. token in hash fragment)
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) {
        window.location.href = "/app";
      }
    });
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-sm text-black/60">Signing you in…</div>
    </div>
  );
}