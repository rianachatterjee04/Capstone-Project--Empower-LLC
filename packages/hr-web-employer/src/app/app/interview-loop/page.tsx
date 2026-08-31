"use client";
/**
 * Interview Loop Orchestration — panel scheduling + multi-interviewer scorecards.
 *
 * Two views:
 *   - List of all loops (with status pills)
 *   - Active loop drill-in: panel slots, per-slot scorecard, calibration debrief
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Action, Avatar, EmptyState, PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";
import { IconCheck, IconClose, IconSparkle } from "@/components/icons";

type Slot = {
  id: string;
  stage_key: string;
  stage_label: string;
  interviewer_id: string;
  interviewer_name: string;
  interviewer_role: string;
  focus_competency: string;
  scheduled_at: string | null;
  duration_min: number;
  completed_at: string | null;
  rating: number | null;
  rating_label: string;
  signals: Record<string, number>;
  strengths: string[];
  concerns: string[];
  notes: string;
};
type Calibration = {
  n_scorecards: number;
  panel_size: number;
  average_rating?: number;
  median_rating?: number;
  composite: number;
  recommendation: string;
  variance_flags: string[];
  consensus_strengths: string[];
  consensus_concerns: string[];
  dissenters: { interviewer_name: string; rating: number; rating_label: string; delta_from_median: number; concerns: string[] }[];
};
type Loop = {
  id: string;
  candidate_name: string;
  candidate_id?: string;
  job_title: string;
  job_id?: string;
  hiring_manager: string;
  slots: Slot[];
  status: string;
  decision: string | null;
  debrief_notes: string;
  created_at: string;
};

const RATING_LABEL = ["No hire", "Lean no hire", "Lean hire", "Hire", "Strong hire"];
const STATUS_TONE: Record<string, "neutral" | "info" | "warn" | "success"> = {
  draft: "neutral", scheduled: "info", in_progress: "info", debrief: "warn", decided: "success",
};
const REC_TONE: Record<string, "success" | "warn" | "info" | "danger" | "neutral"> = {
  advance: "success", advance_with_caveats: "warn", hold: "info", decline: "danger", pending: "neutral",
};

export default function InterviewLoopPage() {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);

  const loopsQ = useQuery({ queryKey: ["loops"], queryFn: () => apiFetch<{ items: Loop[] }>("/interview-loops") });
  const loops = loopsQ.data?.items ?? [];
  const detailQ = useQuery({
    queryKey: ["loop-detail", activeId],
    queryFn: () => apiFetch<Loop & { calibration: Calibration }>(`/interview-loops/${activeId}`),
    enabled: Boolean(activeId),
  });
  const active = detailQ.data;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Hiring · Interview Loop"
        title="Interview Loop Orchestration"
        subtitle="The AI Interview gives you one calibrated voice. A real hire needs a panel. Build the loop, schedule the slots, collect scorecards, see the calibrated debrief — all in one surface."
        actions={
          <Action variant="primary" onClick={() => setBuilding(true)}>
            <IconSparkle /> New loop
          </Action>
        }
      />

      {/* List */}
      <Surface>
        <SectionTitle eyebrow="Loops" title="All interview loops" />
        {loopsQ.isLoading ? (
          <div className="mt-4 text-sm text-muted">Loading…</div>
        ) : loops.length === 0 ? (
          <div className="mt-4">
            <EmptyState title="No loops yet" description="Build a panel and kick off your first calibrated interview loop." />
          </div>
        ) : (
          <div className="mt-4 divide-y divide-line">
            {loops.map((l) => {
              const completed = l.slots.filter((s) => s.rating !== null).length;
              return (
                <button
                  key={l.id}
                  onClick={() => setActiveId(l.id)}
                  className="w-full py-3 px-2 -mx-2 rounded-md flex items-center justify-between gap-3 hover:bg-sunken text-left"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-ink">{l.candidate_name} <span className="text-muted">· {l.job_title}</span></div>
                    <div className="text-xs text-muted">HM: {l.hiring_manager} · {completed}/{l.slots.length} scorecards · {new Date(l.created_at).toLocaleDateString()}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    {l.decision && <Pill tone={REC_TONE[l.decision] ?? "neutral"}>{l.decision.replace(/_/g, " ")}</Pill>}
                    <Pill tone={STATUS_TONE[l.status] ?? "neutral"}>{l.status.replace(/_/g, " ")}</Pill>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </Surface>

      {/* Detail drawer */}
      {activeId && active && (
        <LoopDrawer
          loop={active}
          calibration={active.calibration}
          onClose={() => setActiveId(null)}
          onChange={() => detailQ.refetch()}
        />
      )}
      {building && <BuildDrawer onClose={() => setBuilding(false)} onCreated={(l) => { setBuilding(false); loopsQ.refetch(); setActiveId(l.id); }} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
function LoopDrawer({ loop, calibration, onClose, onChange }: {
  loop: Loop; calibration: Calibration; onClose: () => void; onChange: () => void;
}) {
  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-ink/40 backdrop-blur-sm" onClick={onClose} />
      <div className="w-full max-w-3xl h-full bg-surface border-l border-line overflow-y-auto">
        <div className="px-5 py-4 border-b border-line flex items-center justify-between sticky top-0 bg-surface z-10">
          <div>
            <div className="fp-eyebrow">Loop</div>
            <div className="text-md font-semibold text-ink">{loop.candidate_name}</div>
            <div className="text-xs text-muted">{loop.job_title} · HM: {loop.hiring_manager}</div>
          </div>
          <Action variant="subtle" onClick={onClose}><IconClose /> Close</Action>
        </div>

        {/* Calibration card */}
        <div className="p-5 space-y-4">
          <Surface pad="md">
            <div className="flex items-end justify-between gap-3">
              <div>
                <div className="fp-eyebrow">Calibrated debrief</div>
                <div className="text-3xl font-bold text-ink tabular-nums">{calibration.composite}</div>
                <div className="text-xs text-muted">{calibration.n_scorecards}/{calibration.panel_size} scorecards in</div>
              </div>
              <Pill tone={REC_TONE[calibration.recommendation] ?? "neutral"}>{calibration.recommendation.replace(/_/g, " ")}</Pill>
            </div>
            {calibration.variance_flags.length > 0 && (
              <div className="mt-3 space-y-1">
                {calibration.variance_flags.map((f, i) => (
                  <div key={i} className="rounded-md border border-warn-line bg-warn-bg text-warn-fg text-xs px-3 py-2">{f}</div>
                ))}
              </div>
            )}
            {(calibration.consensus_strengths.length + calibration.consensus_concerns.length) > 0 && (
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <div className="fp-eyebrow text-success-fg mb-1">Consensus strengths</div>
                  <ul className="text-xs space-y-0.5">{calibration.consensus_strengths.map((s, i) => <li key={i}>• {s}</li>)}</ul>
                </div>
                <div>
                  <div className="fp-eyebrow text-danger-fg mb-1">Consensus concerns</div>
                  <ul className="text-xs space-y-0.5">{calibration.consensus_concerns.map((s, i) => <li key={i}>• {s}</li>)}</ul>
                </div>
              </div>
            )}
            {calibration.dissenters.length > 0 && (
              <div className="mt-3 rounded-md border border-line p-3">
                <div className="fp-eyebrow mb-1">Dissenters</div>
                {calibration.dissenters.map((d, i) => (
                  <div key={i} className="text-xs text-body">
                    <span className="font-medium text-ink">{d.interviewer_name}</span> rated <span className="font-mono">{d.rating_label}</span> ({d.delta_from_median > 0 ? "+" : ""}{d.delta_from_median} vs median)
                  </div>
                ))}
              </div>
            )}
          </Surface>

          {/* Panel slots */}
          <div className="space-y-3">
            {loop.slots.map((slot) => (
              <SlotCard key={slot.id} loopId={loop.id} slot={slot} onChange={onChange} />
            ))}
          </div>

          {/* Decision */}
          {loop.status === "debrief" && !loop.decision && (
            <DecisionForm loopId={loop.id} onDecided={onChange} />
          )}
        </div>
      </div>
    </div>
  );
}

function SlotCard({ loopId, slot, onChange }: { loopId: string; slot: Slot; onChange: () => void }) {
  const [editing, setEditing] = useState(false);
  const [rating, setRating] = useState<number>(slot.rating ?? 2);
  const [strengths, setStrengths] = useState((slot.strengths ?? []).join("\n"));
  const [concerns, setConcerns] = useState((slot.concerns ?? []).join("\n"));
  const [notes, setNotes] = useState(slot.notes ?? "");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await apiPost(`/interview-loops/${loopId}/slots/${slot.id}/scorecard`, {
        rating,
        signals: {},
        strengths: strengths.split("\n").map((s) => s.trim()).filter(Boolean),
        concerns: concerns.split("\n").map((s) => s.trim()).filter(Boolean),
        notes,
      });
      onChange();
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-md border border-line bg-canvas p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Avatar name={slot.interviewer_name} size={32} />
          <div>
            <div className="text-sm font-medium text-ink">{slot.interviewer_name}</div>
            <div className="text-xs text-muted">{slot.stage_label} · {slot.focus_competency || "general"}</div>
            {slot.scheduled_at && <div className="text-2xs uppercase tracking-eyebrow text-muted mt-1">{new Date(slot.scheduled_at).toLocaleString()}</div>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {slot.rating !== null && <Pill tone={slot.rating >= 3 ? "success" : slot.rating >= 2 ? "warn" : "danger"}>{slot.rating_label.replace(/_/g, " ")}</Pill>}
          {!editing && <Action variant="subtle" size="sm" onClick={() => setEditing(true)}>{slot.rating !== null ? "Edit" : "Score"}</Action>}
        </div>
      </div>
      {editing && (
        <div className="mt-3 space-y-2">
          <div>
            <div className="text-2xs uppercase tracking-eyebrow text-muted mb-1">Rating</div>
            <div className="flex gap-1.5">
              {[0, 1, 2, 3, 4].map((r) => (
                <Action key={r} size="sm" variant={rating === r ? "primary" : "subtle"} onClick={() => setRating(r)}>
                  {RATING_LABEL[r]}
                </Action>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <textarea rows={3} value={strengths} onChange={(e) => setStrengths(e.target.value)} placeholder="Strengths (one per line)" className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink" />
            <textarea rows={3} value={concerns} onChange={(e) => setConcerns(e.target.value)} placeholder="Concerns (one per line)" className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink" />
          </div>
          <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes" className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink" />
          <div className="flex items-center gap-2">
            <Action variant="primary" size="sm" onClick={save} disabled={saving}><IconCheck /> Save</Action>
            <Action variant="subtle" size="sm" onClick={() => setEditing(false)}>Cancel</Action>
          </div>
        </div>
      )}
      {!editing && slot.rating !== null && (slot.strengths.length + slot.concerns.length > 0) && (
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div>
            <div className="fp-eyebrow text-success-fg mb-1">Strengths</div>
            <ul className="space-y-0.5">{slot.strengths.map((s, i) => <li key={i}>• {s}</li>)}</ul>
          </div>
          <div>
            <div className="fp-eyebrow text-danger-fg mb-1">Concerns</div>
            <ul className="space-y-0.5">{slot.concerns.map((s, i) => <li key={i}>• {s}</li>)}</ul>
          </div>
        </div>
      )}
    </div>
  );
}

function DecisionForm({ loopId, onDecided }: { loopId: string; onDecided: () => void }) {
  const [decision, setDecision] = useState("advance");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    try {
      await apiPost(`/interview-loops/${loopId}/decide`, { decision, debrief_notes: notes });
      onDecided();
    } finally { setBusy(false); }
  }
  return (
    <Surface pad="md">
      <div className="fp-eyebrow mb-2">Record decision</div>
      <div className="flex flex-wrap gap-2 mb-3">
        {(["advance", "advance_with_caveats", "hold", "decline"] as const).map((d) => (
          <Action key={d} size="sm" variant={decision === d ? "primary" : "subtle"} onClick={() => setDecision(d)}>
            {d.replace(/_/g, " ")}
          </Action>
        ))}
      </div>
      <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Debrief notes" className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink" />
      <div className="mt-2">
        <Action variant="primary" onClick={go} disabled={busy}><IconCheck /> Lock decision</Action>
      </div>
    </Surface>
  );
}

// ---------------------------------------------------------------------------
function BuildDrawer({ onClose, onCreated }: { onClose: () => void; onCreated: (l: Loop) => void }) {
  const [candidate, setCandidate] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [hm, setHm] = useState("");
  const [panel, setPanel] = useState<{ name: string; role: string; competency: string; stage_key: string }[]>([
    { name: "", role: "Recruiter",  competency: "screen",      stage_key: "recruiter_screen" },
    { name: "", role: "Engineer",   competency: "technical",   stage_key: "tech_screen" },
    { name: "", role: "Engineer",   competency: "system design", stage_key: "onsite_1" },
    { name: "", role: "Engineer",   competency: "coding",      stage_key: "onsite_2" },
    { name: "", role: "Hiring mgr", competency: "values + fit", stage_key: "final_round" },
  ]);
  const [busy, setBusy] = useState(false);

  async function build() {
    setBusy(true);
    try {
      const loop = await apiPost<Loop>("/interview-loops", {
        candidate_name: candidate,
        job_title: jobTitle,
        hiring_manager: hm,
        panel: panel.filter((p) => p.name.trim()).map((p, i) => ({
          interviewer_id: `pi-${i}`,
          interviewer_name: p.name,
          interviewer_role: p.role,
          focus_competency: p.competency,
          stage_key: p.stage_key,
        })),
      });
      onCreated(loop);
    } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-ink/40 backdrop-blur-sm" onClick={onClose} />
      <div className="w-full max-w-xl h-full bg-surface border-l border-line overflow-y-auto">
        <div className="px-5 py-4 border-b border-line flex items-center justify-between sticky top-0 bg-surface z-10">
          <div>
            <div className="fp-eyebrow">New loop</div>
            <div className="text-md font-semibold text-ink">Build the panel</div>
          </div>
          <Action variant="subtle" onClick={onClose}><IconClose /> Close</Action>
        </div>
        <div className="p-5 space-y-3">
          <input value={candidate} onChange={(e) => setCandidate(e.target.value)} placeholder="Candidate name" className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink" />
          <input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder="Job title" className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink" />
          <input value={hm} onChange={(e) => setHm(e.target.value)} placeholder="Hiring manager" className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink" />
          <div className="fp-eyebrow mt-2">Panel</div>
          {panel.map((p, i) => (
            <div key={i} className="grid grid-cols-12 gap-1.5">
              <input value={p.name} onChange={(e) => { const cp = [...panel]; cp[i] = { ...cp[i], name: e.target.value }; setPanel(cp); }} placeholder="Name" className="col-span-4 rounded-md border border-line bg-canvas px-2 py-1.5 text-xs text-ink" />
              <input value={p.role} onChange={(e) => { const cp = [...panel]; cp[i] = { ...cp[i], role: e.target.value }; setPanel(cp); }} placeholder="Role" className="col-span-3 rounded-md border border-line bg-canvas px-2 py-1.5 text-xs text-ink" />
              <input value={p.competency} onChange={(e) => { const cp = [...panel]; cp[i] = { ...cp[i], competency: e.target.value }; setPanel(cp); }} placeholder="Focus" className="col-span-3 rounded-md border border-line bg-canvas px-2 py-1.5 text-xs text-ink" />
              <select value={p.stage_key} onChange={(e) => { const cp = [...panel]; cp[i] = { ...cp[i], stage_key: e.target.value }; setPanel(cp); }} className="col-span-2 rounded-md border border-line bg-canvas px-2 py-1.5 text-xs text-ink">
                {["recruiter_screen", "tech_screen", "onsite_1", "onsite_2", "onsite_3", "final_round"].map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
              </select>
            </div>
          ))}
          <Action variant="subtle" size="sm" onClick={() => setPanel([...panel, { name: "", role: "Interviewer", competency: "", stage_key: "onsite_1" }])}>+ Add slot</Action>
          <div className="pt-2">
            <Action variant="primary" onClick={build} disabled={!candidate.trim() || !jobTitle.trim() || busy}>
              <IconSparkle /> {busy ? "Building…" : "Create loop"}
            </Action>
          </div>
        </div>
      </div>
    </div>
  );
}
