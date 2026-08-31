"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, LinkAction, EmptyState, Divider } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";
import { useShellState } from "@/components/ShellState";

type Block = {
  title: string;
  summary: string;
  detail?: string;
  tone: "neutral" | "success" | "warn" | "danger" | "info";
  cta_label?: string;
  cta_href?: string;
};
type Brief = {
  generated_at: string;
  headline: string;
  narrative: string;
  counts: Record<string, number>;
  blocks: Block[];
  suggested_questions: string[];
};

const TONE_RING: Record<string, string> = {
  neutral: "",
  success: "ring-1 ring-success-line",
  warn: "ring-1 ring-warn-line",
  danger: "ring-1 ring-danger-line",
  info: "ring-1 ring-info-line",
};

export default function BriefPage() {
  const q = useQuery({
    queryKey: ["exec-brief"],
    queryFn: () => apiFetch<Brief>("/exec-brief/today"),
    refetchInterval: 5 * 60_000,
  });
  const b = q.data;
  const { openAssistant } = useShellState();

  const today = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow={`${today} · executive brief`}
        title={b?.headline ?? "Loading…"}
        subtitle="One-screen morning briefing for owners and execs. Generated from live workforce, hiring, risk, and execution signal."
        actions={
          <>
            <Action variant="subtle" onClick={() => q.refetch()}>Refresh</Action>
            <button
              onClick={openAssistant}
              className="h-9 px-3 rounded-md bg-accent text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm flex items-center gap-2 text-sm"
            >
              <IconSparkle /> Ask follow-up
            </button>
          </>
        }
      />

      {/* Narrative */}
      <Surface pad="lg">
        <div className="fp-eyebrow mb-2">Morning narrative</div>
        <p className="text-md text-ink leading-relaxed max-w-3xl">
          {b?.narrative ?? "Catching up on signals…"}
        </p>
      </Surface>

      {/* Five blocks */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
        {(b?.blocks ?? []).map((bl) => (
          <div key={bl.title} className={`rounded-lg bg-surface border border-line p-4 ${TONE_RING[bl.tone] ?? ""}`}>
            <div className="fp-eyebrow">{bl.title}</div>
            <div className="mt-1 text-base font-semibold text-ink leading-snug">{bl.summary}</div>
            {bl.detail && <div className="mt-1 text-xs text-muted">{bl.detail}</div>}
            {bl.cta_href && (
              <Link href={bl.cta_href} className="mt-3 inline-flex items-center gap-1 text-xs text-muted hover:text-ink">
                {bl.cta_label ?? "Open"} <IconArrowUpRight />
              </Link>
            )}
          </div>
        ))}
        {(b?.blocks ?? []).length === 0 && (
          <Surface className="md:col-span-2 xl:col-span-5"><EmptyState title="Brief generating…" /></Surface>
        )}
      </div>

      {/* Counts ledger */}
      <Surface>
        <SectionTitle eyebrow="Snapshot" title="Today's numbers" description="Live counts behind the brief." />
        <div className="mt-3 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
          <Mini label="Headcount" value={b?.counts.headcount ?? "—"} />
          <Mini label="Open roles" value={b?.counts.open_jobs ?? "—"} />
          <Mini label="Candidates" value={b?.counts.candidates_total ?? "—"} />
          <Mini label="Candidates at offer" value={b?.counts.candidates_offer ?? "—"} />
          <Mini label="Risk score" value={b?.counts.workforce_risk_score ?? "—"} />
          <Mini label="High-severity cases" value={b?.counts.cases_high_open ?? "—"} />
          <Mini label="New hires pending" value={b?.counts.new_hires_pending ?? "—"} />
          <Mini label="Tasks open" value={b?.counts.tasks_open ?? "—"} />
          <Mini label="Tasks overdue" value={b?.counts.tasks_overdue ?? "—"} />
        </div>
      </Surface>

      {/* Suggested questions */}
      <Surface>
        <SectionTitle eyebrow="Follow-ups" title="Ask the copilot" description="One click opens the assistant with the question pre-loaded." />
        <div className="mt-3 flex flex-wrap gap-2">
          {(b?.suggested_questions ?? []).map((q, i) => (
            <Link
              key={i}
              href={`/app/exec-copilot?q=${encodeURIComponent(q)}`}
              className="rounded-full border border-line bg-canvas px-3.5 py-1.5 text-sm text-body hover:bg-sunken hover:text-ink transition-colors duration-150 ease-calm"
            >
              {q}
            </Link>
          ))}
        </div>
        <Divider className="my-3" />
        <div className="text-xs text-muted">
          The brief refreshes every 5 minutes and is generated from your live HR data + workforce risk signal. The narrative is intended as a starting point for the day, not a decision.
        </div>
      </Surface>

      {b?.generated_at && (
        <p className="text-xs text-muted">Brief generated {new Date(b.generated_at).toLocaleString()}.</p>
      )}
    </div>
  );
}

function Mini({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-canvas p-3">
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
