"use client";
/**
 * Interview Copilot — list page.
 */
import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Action, EmptyState, PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";
import type { Interview } from "@/components/interviews/types";

const STATUS_TONE: Record<string, "info" | "success" | "warn" | "neutral"> = {
  scheduled: "info", live: "warn", completed: "success", cancelled: "neutral",
};

export default function InterviewsListPage() {
  const [creating, setCreating] = useState(false);
  const q = useQuery({ queryKey: ["interviews-list"], queryFn: () => apiFetch<{ items: Interview[] }>("/interviews") });
  const interviews = q.data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Hiring · AI Interview Copilot"
        title="Interview Copilot"
        subtitle="Real-time AI assistance for human interviewers — consent-based, audit-friendly, integrated end-to-end with the rest of Foundry People. Helps before, during, and after every interview."
        actions={
          <>
            <Link href="/app/interviews/scorecards" className="inline-flex items-center justify-center gap-1.5 rounded-md font-medium h-9 px-3 text-sm bg-surface text-ink border border-line hover:bg-sunken">
              All scorecards
            </Link>
            <Action variant="primary" onClick={() => setCreating(true)}>
              <IconSparkle /> New interview
            </Action>
          </>
        }
      />

      <Surface>
        <SectionTitle eyebrow="Interviews" title="All interviews" description="Click any interview to enter the prep workspace." />
        {q.isLoading ? (
          <div className="mt-4 text-sm text-muted">Loading…</div>
        ) : interviews.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No interviews yet"
              description="Create your first interview to get the AI-drafted plan + question set."
              action={<Action variant="primary" onClick={() => setCreating(true)}>New interview</Action>}
            />
          </div>
        ) : (
          <div className="mt-4 divide-y divide-line">
            {interviews.map((iv) => (
              <div key={iv.id} className="py-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-ink truncate">
                    {iv.candidate_name} <span className="text-muted">· {iv.job_title}</span>
                  </div>
                  <div className="text-xs text-muted mt-0.5">
                    {iv.interview_type} · {iv.duration_minutes}m
                    {iv.scheduled_at ? ` · ${new Date(iv.scheduled_at).toLocaleString()}` : ""}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Pill tone={STATUS_TONE[iv.status]}>{iv.status}</Pill>
                  <Pill tone={iv.consent_status === "granted" ? "success" : "warn"}>consent · {iv.consent_status}</Pill>
                  <Link href={`/app/interviews/${iv.id}`} className="inline-flex items-center gap-1 text-xs text-ink hover:opacity-80">
                    Prep <IconArrowUpRight />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </Surface>

      {creating && <CreateDrawer onClose={() => setCreating(false)} onCreated={() => { setCreating(false); q.refetch(); }} />}
    </div>
  );
}

function CreateDrawer({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [job, setJob] = useState("");
  const [type, setType] = useState<"screen" | "technical" | "onsite" | "culture" | "final">("technical");
  const [dur, setDur] = useState(60);
  const [when, setWhen] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      await apiPost("/interviews", {
        candidate_name: name,
        job_title: job,
        interview_type: type,
        duration_minutes: dur,
        scheduled_at: when || null,
      });
      onCreated();
    } finally { setBusy(false); }
  }
  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-ink/40 backdrop-blur-sm" onClick={onClose} />
      <div className="w-full max-w-md h-full bg-surface border-l border-line overflow-y-auto">
        <div className="px-5 py-4 border-b border-line">
          <div className="fp-eyebrow">New interview</div>
          <div className="text-md font-semibold text-ink">Set up the workspace</div>
        </div>
        <div className="p-5 space-y-3">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Candidate name" className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink" />
          <input value={job} onChange={(e) => setJob(e.target.value)} placeholder="Job title" className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink" />
          <div className="flex flex-wrap gap-1.5">
            {(["screen", "technical", "onsite", "culture", "final"] as const).map((t) => (
              <Action key={t} size="sm" variant={type === t ? "primary" : "subtle"} onClick={() => setType(t)}>{t}</Action>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input type="number" value={dur} onChange={(e) => setDur(Number(e.target.value) || 60)} className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink tabular-nums" />
            <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink" />
          </div>
          <Action variant="primary" onClick={save} disabled={!name.trim() || !job.trim() || busy}>
            <IconSparkle /> {busy ? "Creating…" : "Create + open prep"}
          </Action>
        </div>
      </div>
    </div>
  );
}
