"use client";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";

export default function AiMemoryPage() {
  const qc = useQueryClient();
  const [namespace, setNamespace] = useState("cases");
  const [content, setContent] = useState("Harassment cases in 2025 were typically resolved in 36 hours with HR+Legal involvement.");
  const [query, setQuery] = useState("What do we usually do for harassment cases?");
  const [out, setOut] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  async function upsert() {
    setError(null);
    try {
      await apiPost("/ai/memory/upsert", { namespace, content, metadata: { source: "manual" } });
      setOut({ ok: true, message: "Saved to tenant memory." });
    } catch (e) {
      setOut(null);
      setError((e as Error).message || "Save failed");
    }
  }

  async function search() {
    setError(null);
    try {
      const res = await apiPost("/ai/memory/search", { namespace, query, k: 5 });
      setOut(res);
    } catch (e) {
      setOut(null);
      setError((e as Error).message || "Search failed");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">AI Memory</div>
        <div className="text-sm text-black/60">Per-tenant vector memory + retrieval (mock embeddings; pgvector storage).</div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-black/10 p-4 space-y-3">
          <div className="text-sm font-semibold">Write memory</div>
          <Input label="Namespace" value={namespace} onChange={(e) => setNamespace(e.target.value)} />
          <Textarea label="Content" rows={6} value={content} onChange={(e) => setContent(e.target.value)} />
          <Button onClick={upsert}>Save memory</Button>
        </div>

        <div className="rounded-2xl border border-black/10 p-4 space-y-3">
          <div className="text-sm font-semibold">Search memory</div>
          <Input label="Namespace" value={namespace} onChange={(e) => setNamespace(e.target.value)} />
          <Input label="Query" value={query} onChange={(e) => setQuery(e.target.value)} />
          <Button onClick={search}>Search</Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
      ) : null}

      {out ? (
        <div className="rounded-2xl border border-black/10 p-4">
          <div className="text-sm font-semibold">Output</div>
          <pre className="mt-2 overflow-auto rounded-xl bg-black/5 p-3 text-xs">{JSON.stringify(out, null, 2)}</pre>
        </div>
      ) : null}
    </div>
  );
}
