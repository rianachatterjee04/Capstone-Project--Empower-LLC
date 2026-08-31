"use client";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Divider, LinkAction } from "@/components/ds";
import { IconArrowUpRight, IconSearch, IconSparkle } from "@/components/icons";
import { useShellState } from "@/components/ShellState";

type Collection = { id: string; label: string; count: number };
type DocSummary = {
  id: string;
  title: string;
  category: string;
  source: string;
  preview: string;
  body?: string;
  tags: string[];
  updated_at: string | null;
  owner: string | null;
  source_label: string | null;
  read_minutes: number;
  char_count: number;
};
type Summary = {
  total_documents: number;
  collections: number;
  total_words: number;
  char_count: number;
  by_collection: Record<string, number>;
};

export default function MemoryPage() {
  const qc = useQueryClient();
  const { openAssistant } = useShellState();
  const [collection, setCollection] = useState<string>("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string>("");

  const sumQ = useQuery({ queryKey: ["memory-summary"], queryFn: () => apiFetch<Summary>("/memory/summary") });
  const colQ = useQuery({ queryKey: ["memory-collections"], queryFn: () => apiFetch<{ items: Collection[] }>("/memory/collections") });
  const docsQ = useQuery({
    queryKey: ["memory-docs", collection, query],
    queryFn: () =>
      query.trim()
        ? apiPost<{ items: DocSummary[] }>("/memory/browse", { query, collection: collection || null, top_k: 30 })
        : apiFetch<{ items: DocSummary[] }>(`/memory/documents${collection ? `?collection=${encodeURIComponent(collection)}` : ""}`),
  });

  const docs = docsQ.data?.items ?? [];

  // Ensure selection is valid
  useEffect(() => {
    if (docs.length === 0) return;
    if (!docs.some((d) => d.id === selected)) setSelected(docs[0].id);
  }, [docs, selected]);

  const activeDoc = useMemo(() => docs.find((d) => d.id === selected), [docs, selected]);
  const relatedQ = useQuery({
    queryKey: ["memory-related", selected],
    queryFn: () => apiFetch<{ items: DocSummary[] }>(`/memory/documents/${selected}/related`),
    enabled: !!selected,
  });

  // Add doc state
  const [addOpen, setAddOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newBody, setNewBody] = useState("");
  const [newCategory, setNewCategory] = useState("policy");
  const [adding, setAdding] = useState(false);

  async function addDoc() {
    if (!newTitle.trim() || !newBody.trim()) return;
    setAdding(true);
    try {
      await apiPost("/memory/ingest/bulk", {
        items: [{ title: newTitle, body: newBody, category: newCategory, source: "internal" }],
      });
      setNewTitle("");
      setNewBody("");
      setAddOpen(false);
      await qc.invalidateQueries({ queryKey: ["memory-summary"] });
      await qc.invalidateQueries({ queryKey: ["memory-collections"] });
      await qc.invalidateQueries({ queryKey: ["memory-docs"] });
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Knowledge"
        title="Company memory"
        subtitle="The org's living knowledge layer. Policies, SOPs, onboarding, learning, comp philosophy — semantic browse and grounded answers."
        actions={
          <>
            <Action variant="subtle" onClick={() => setAddOpen((v) => !v)}>
              {addOpen ? "Cancel" : "Add document"}
            </Action>
            <Action variant="primary" onClick={openAssistant}>
              <IconSparkle /> Ask the assistant
            </Action>
          </>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Documents"   value={sumQ.data?.total_documents ?? "—"} />
        <Stat label="Collections" value={sumQ.data?.collections ?? "—"} />
        <Stat label="Total words" value={sumQ.data?.total_words ?? "—"} />
        <Stat label="Characters"  value={sumQ.data?.char_count ?? "—"} />
      </div>

      {addOpen && (
        <Surface>
          <SectionTitle eyebrow="Ingest" title="Add a document" />
          <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Title"
              className="md:col-span-2 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <select
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink"
            >
              {["policy","benefits","onboarding","time_off","compensation","performance","learning","manager","ops","security","ethics","career"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
            <textarea
              value={newBody}
              onChange={(e) => setNewBody(e.target.value)}
              placeholder="Body"
              rows={5}
              className="md:col-span-3 rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:bg-surface"
            />
          </div>
          <div className="mt-3 flex items-center gap-2">
            <Action variant="primary" onClick={addDoc} disabled={!newTitle.trim() || !newBody.trim() || adding}>
              {adding ? "Ingesting…" : "Ingest"}
            </Action>
            <span className="text-xs text-muted">The assistant will use this document for grounded answers immediately.</span>
          </div>
        </Surface>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr_360px] gap-5">
        {/* Collections rail */}
        <Surface pad="sm">
          <div className="fp-eyebrow mb-2">Collections</div>
          <div className="space-y-0.5">
            <button
              onClick={() => setCollection("")}
              className={`w-full flex items-center justify-between rounded-md px-2.5 py-1.5 text-sm transition-colors duration-150 ease-calm ${
                collection === "" ? "bg-canvas text-ink" : "text-body hover:bg-sunken hover:text-ink"
              }`}
            >
              <span>All</span>
              <span className="text-2xs tabular-nums text-muted">{sumQ.data?.total_documents ?? "—"}</span>
            </button>
            {(colQ.data?.items ?? []).map((c) => (
              <button
                key={c.id}
                onClick={() => setCollection(c.id === collection ? "" : c.id)}
                className={`w-full flex items-center justify-between rounded-md px-2.5 py-1.5 text-sm transition-colors duration-150 ease-calm ${
                  collection === c.id ? "bg-canvas text-ink" : "text-body hover:bg-sunken hover:text-ink"
                }`}
              >
                <span className="truncate">{c.label}</span>
                <span className="text-2xs tabular-nums text-muted">{c.count}</span>
              </button>
            ))}
          </div>
        </Surface>

        {/* Doc list + search */}
        <div className="space-y-3">
          <Surface pad="sm">
            <div className="flex items-center gap-2">
              <IconSearch className="text-muted" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Semantic search — try 'parental leave' or 'how to request equipment'"
                className="flex-1 h-9 rounded-md bg-canvas border border-line px-3 text-sm text-ink outline-none focus:bg-surface"
              />
              {query && <button onClick={() => setQuery("")} className="text-xs text-muted hover:text-ink">clear</button>}
            </div>
          </Surface>

          {docsQ.isLoading ? (
            <Surface><EmptyState title="Loading…" /></Surface>
          ) : docs.length === 0 ? (
            <Surface>
              <EmptyState title="No documents" description="Try clearing filters or ingesting a doc." />
            </Surface>
          ) : (
            <Surface pad="sm">
              <ul className="divide-y divide-rule">
                {docs.map((d) => {
                  const isActive = d.id === selected;
                  return (
                    <li key={d.id}>
                      <button
                        onClick={() => setSelected(d.id)}
                        className={`w-full text-left -mx-2 px-2 py-3 rounded-md transition-colors duration-150 ease-calm ${
                          isActive ? "bg-canvas" : "hover:bg-sunken/60"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-ink">{d.title}</div>
                            <div className="text-xs text-muted mt-0.5 line-clamp-2">{d.preview}</div>
                          </div>
                          <div className="shrink-0 flex flex-col items-end gap-1">
                            <Pill tone="neutral">{d.category.replace(/_/g, " ")}</Pill>
                            <span className="text-2xs uppercase tracking-eyebrow text-muted">{d.read_minutes}m read</span>
                          </div>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </Surface>
          )}
        </div>

        {/* Detail */}
        <Surface>
          {activeDoc ? (
            <>
              <SectionTitle eyebrow={activeDoc.category.replace(/_/g, " ")} title={activeDoc.title} />
              <div className="mt-3 text-sm text-body leading-relaxed whitespace-pre-line max-h-[400px] overflow-auto">
                {activeDoc.body ?? activeDoc.preview}
              </div>
              <Divider className="my-3" />
              <div className="flex flex-wrap gap-1.5">
                {(activeDoc.tags ?? []).map((t) => <Pill key={t} tone="neutral">{t}</Pill>)}
              </div>
              <Divider className="my-3" />
              <div className="fp-eyebrow mb-2">Related</div>
              <div className="space-y-1.5">
                {(relatedQ.data?.items ?? []).length === 0 ? (
                  <div className="text-xs text-muted">No related documents found.</div>
                ) : (
                  (relatedQ.data?.items ?? []).map((r) => (
                    <button
                      key={r.id}
                      onClick={() => setSelected(r.id)}
                      className="w-full text-left rounded-md border border-line bg-canvas hover:bg-sunken transition-colors duration-150 ease-calm px-3 py-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm text-ink truncate">{r.title}</div>
                        <Pill tone="neutral">{r.category.replace(/_/g, " ")}</Pill>
                      </div>
                      <div className="text-xs text-muted mt-0.5 line-clamp-2">{r.preview}</div>
                    </button>
                  ))
                )}
              </div>
              <Divider className="my-3" />
              <LinkAction href="/app/assistant" variant="primary" className="w-full">
                <IconSparkle /> Ask grounded follow-up
              </LinkAction>
            </>
          ) : (
            <EmptyState title="Select a document" description="Browse the list to read a doc, see related items, and ask grounded follow-ups." />
          )}
        </Surface>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-surface p-4">
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
