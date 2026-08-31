"use client";

/**
 * Legacy route. The digital twin is now the "Twin" tab of the single unified
 * person page at /app/people/[id]. Redirect there: with an ?id= go straight to
 * that person's Twin tab; without one, fall back to the directory.
 */
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function DigitalTwinRedirect() {
  const router = useRouter();

  useEffect(() => {
    if (typeof window === "undefined") return;
    const id = new URLSearchParams(window.location.search).get("id");
    router.replace(id ? `/app/people/${id}?tab=twin` : "/app/people");
  }, [router]);

  return <div className="p-8 text-sm text-muted">Opening the unified profile…</div>;
}
