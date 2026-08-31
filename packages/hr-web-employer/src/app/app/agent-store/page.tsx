"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Divider } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type CatalogEntry = {
  key: string;
  name: string;
  headline: string;
  description: string;
  category: string;
  publisher: string;
  capabilities: string[];
  triggers: string[];
  built_in: boolean;
  installable: boolean;
  rating: number;
  installed: boolean;
};

type Catalog = { items: CatalogEntry[]; categories: string[] };

export default function AgentStorePage() {
  const qc = useQueryClient();
  const [busyKey, setBusyKey] = useState<string>("");
  const [activeCategory, setActiveCategory] = useState<string>("");
  const [search, setSearch] = useState("");

  const q = useQuery({
    queryKey: ["agents-catalog"],
    queryFn: () => apiFetch<Catalog>("/agents/catalog"),
    refetchInterval: 90_000,
  });

  const items = q.data?.items ?? [];
  const categories = q.data?.categories ?? [];

  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    return items.filter((c) => {
      if (activeCategory && c.category !== activeCategory) return false;
      if (s && !`${c.name} ${c.headline} ${c.description} ${c.category}`.toLowerCase().includes(s)) return false;
      return true;
    });
  }, [items, activeCategory, search]);

  const installed = items.filter((c) => c.installed).length;
  const available = items.filter((c) => !c.installed && c.installable).length;

  async function install(key: string) {
    setBusyKey(key);
    try {
      await apiPost(`/agents/catalog/${key}/install`, {});
      await qc.invalidateQueries({ queryKey: ["agents-catalog"] });
    } finally {
      setBusyKey("");
    }
  }

  async function uninstall(key: string) {
    setBusyKey(key);
    try {
      await apiPost(`/agents/catalog/${key}/uninstall`, {});
      await qc.invalidateQueries({ queryKey: ["agents-catalog"] });
    } finally {
      setBusyKey("");
    }
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="AI Ops"
        title="Agent store"
        subtitle="Discover and install AI operators. Every agent ships with capabilities, triggers, and an audit trail."
        actions={<Link href="/app/agents" className="h-9 px-3 rounded-md bg-accent text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm flex items-center gap-2 text-sm"><IconSparkle /> Open agents</Link>}
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="In your org" value={installed} tone="success" />
        <Stat label="Available" value={available} tone="info" />
        <Stat label="Categories" value={categories.length} />
        <Stat label="Total catalog" value={items.length} />
      </div>

      <Surface pad="sm">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search agents — by capability, trigger, or name"
            className="flex-1 min-w-[240px] h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface placeholder:text-muted"
          />
          <button
            onClick={() => setActiveCategory("")}
            className={`text-xs rounded-md px-3 py-1.5 border transition-colors duration-150 ease-calm ${
              activeCategory === "" ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"
            }`}
          >
            All
          </button>
          {categories.map((c) => (
            <button
              key={c}
              onClick={() => setActiveCategory(activeCategory === c ? "" : c)}
              className={`text-xs rounded-md px-3 py-1.5 border transition-colors duration-150 ease-calm ${
                activeCategory === c ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      </Surface>

      {q.isLoading ? (
        <Surface><EmptyState title="Loading catalog…" /></Surface>
      ) : filtered.length === 0 ? (
        <Surface><EmptyState title="No agents match" description="Try clearing filters." /></Surface>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((c) => (
            <Surface key={c.key} className="flex flex-col">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="fp-eyebrow">{c.category} · {c.publisher}</div>
                  <div className="text-base font-semibold text-ink tracking-tight">{c.name}</div>
                  <div className="text-sm text-muted mt-0.5">{c.headline}</div>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  {c.installed ? (
                    <Pill tone="success">installed</Pill>
                  ) : c.built_in ? (
                    <Pill tone="neutral">built-in</Pill>
                  ) : (
                    <Pill tone="info">available</Pill>
                  )}
                  <span className="text-2xs uppercase tracking-eyebrow text-muted">★ {c.rating.toFixed(1)}</span>
                </div>
              </div>

              <p className="mt-3 text-sm text-body leading-relaxed">{c.description}</p>

              <Divider className="my-3" />

              <div className="fp-eyebrow mb-1">Capabilities</div>
              <ul className="text-sm text-body space-y-0.5">
                {c.capabilities.map((cap, i) => <li key={i}>• {cap}</li>)}
              </ul>

              <div className="mt-3 fp-eyebrow mb-1">Triggers</div>
              <div className="flex flex-wrap gap-1">
                {c.triggers.map((t, i) => <Pill key={i} tone="neutral">{t}</Pill>)}
              </div>

              <div className="mt-4 flex items-center justify-between gap-2 pt-3 border-t border-rule">
                <div className="text-2xs uppercase tracking-eyebrow text-muted">
                  {c.installed ? "Live in this org" : c.built_in ? "Always available" : c.installable ? "One-click install" : "Not installable yet"}
                </div>
                <div className="flex items-center gap-1.5">
                  {c.installed && c.built_in ? (
                    <Link
                      href={`/app/agents?agent=${c.key}`}
                      className="h-7 px-2.5 rounded-md text-xs text-ink border border-line bg-surface hover:bg-sunken"
                    >
                      Run
                    </Link>
                  ) : c.installed ? (
                    <>
                      <Link
                        href={`/app/agents`}
                        className="h-7 px-2.5 rounded-md text-xs text-ink border border-line bg-surface hover:bg-sunken inline-flex items-center"
                      >
                        Manage
                      </Link>
                      <Action variant="subtle" size="sm" onClick={() => uninstall(c.key)} disabled={busyKey === c.key}>
                        {busyKey === c.key ? "…" : "Uninstall"}
                      </Action>
                    </>
                  ) : c.installable ? (
                    <Action variant="primary" size="sm" onClick={() => install(c.key)} disabled={busyKey === c.key}>
                      {busyKey === c.key ? "Installing…" : "Install"}
                    </Action>
                  ) : (
                    <span className="text-2xs uppercase tracking-eyebrow text-muted">coming soon</span>
                  )}
                </div>
              </div>
            </Surface>
          ))}
        </div>
      )}

      <p className="text-xs text-muted">Every install writes an audit log entry. Uninstall removes the agent from this org but preserves its history.</p>
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "success" | "info" }) {
  const ring: Record<string, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    info: "ring-1 ring-info-line",
  };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
