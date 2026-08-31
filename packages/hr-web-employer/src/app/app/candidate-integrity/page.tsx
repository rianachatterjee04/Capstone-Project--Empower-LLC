"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Divider, MetricStat } from "@/components/ds";

type Signal = {
  category: string;
  weight: number;
  present: boolean;
  severity: number | null;
  points: number;
  detail: Record<string, unknown>;
};

type Assessment = {
  id: string;
  candidate_id: string;
  candidate_name: string;
  interview_id?: string | null;
  fraud_score: number;
  band: "clear" | "review" | "high_risk";
  recommended_action: "proceed" | "verify" | "block";
  confidence: number;
  categories_with_data: number;
  categories_total: number;
  contributing_signals: Signal[];
  top_drivers: { category: string; points: number }[];
  low_confidence: boolean;
};

type Queue = {
  items: Assessment[];
  summary: { total_assessed: number; flagged: number; high_risk: number; review: number; clear: number };
};

const BAND_TONE: Record<string, "success" | "warn" | "danger"> = {
  clear: "success",
  review: "warn",
  high_risk: "danger",
};

const ACTION_LABEL: Record<string, string> = { proceed: "Proceed", verify: "Verify", block: "Block" };
const catLabel = (c: string) => c.replace(/_/g, " ");

export default function CandidateIntegrityPage() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Assessment | null>(null);

  const queue = useQuery({
    queryKey: ["candidate-integrity", "queue"],
    queryFn: () => apiFetch<Queue>(`/candidate-integrity/queue?min_band=review`),
    refetchInterval: 60_000,
  });

  // Demo assess composer — recruiters can run a candidate through the signals.
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [running, setRunning] = useState(false);

  async function runDemoAssess(preset: "clean" | "risky") {
    setRunning(true);
    try {
      const signals = preset === "risky"
        ? {
            name_match: false, email_matches_resume: false, resume_matches_interview: true,
            voice_change_flag: true, face_change_flag: true, multiple_faces_detected: true,
            response_uniformity: 0.8, latency_anomaly: 0.6, paste_burst_count: 5,
            vpn_detected: true, geo_ip_mismatch: true, timezone_mismatch: false,
            reference_mismatches: 1, references_total: 2,
            inflated_titles: true,
          }
        : {
            name_match: true, email_matches_resume: true, resume_matches_interview: true,
            voice_change_flag: false, face_change_flag: false, multiple_faces_detected: false,
            response_uniformity: 0.1, latency_anomaly: 0.1, paste_burst_count: 0,
            vpn_detected: false, geo_ip_mismatch: false, timezone_mismatch: false,
            reference_mismatches: 0, references_total: 3,
          };
      const res = await apiPost<Assessment>(`/candidate-integrity/assess`, {
        candidate_id: `demo-${Date.now()}`,
        candidate_name: name || (preset === "risky" ? "Suspicious Candidate" : "Clean Candidate"),
        signals,
      });
      setSelected(res);
      setName("");
      setOpen(false);
      await qc.invalidateQueries({ queryKey: ["candidate-integrity", "queue"] });
    } finally {
      setRunning(false);
    }
  }

  const s = queue.data?.summary;

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Recruiting · Trust & Security"
        title="Candidate Integrity"
        subtitle="Deterministic fraud, deepfake and proxy-interview detection. Every flag is explainable down to the contributing signal — advisory, never an automatic rejection."
        actions={<Action variant="primary" onClick={() => setOpen((v) => !v)}>{open ? "Cancel" : "Run assessment"}</Action>}
      />

      {open && (
        <Surface pad="sm">
          <SectionTitle eyebrow="Assess" title="Run a candidate through the integrity signals" description="Uses the deterministic signal model. Try a clean vs risky preset." />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Candidate name (optional)"
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" />
            <Action variant="ghost" onClick={() => runDemoAssess("clean")} disabled={running}>Clean preset</Action>
            <Action variant="primary" onClick={() => runDemoAssess("risky")} disabled={running}>Risky preset</Action>
          </div>
        </Surface>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricStat label="Assessed" value={s?.total_assessed ?? "—"} />
        <MetricStat label="Flagged for review" value={s?.flagged ?? "—"} tone={(s?.flagged ?? 0) > 0 ? "warn" : "success"} />
        <MetricStat label="High risk" value={s?.high_risk ?? "—"} tone={(s?.high_risk ?? 0) > 0 ? "danger" : "success"} />
        <MetricStat label="Cleared" value={s?.clear ?? "—"} tone="success" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Review queue */}
        <Surface>
          <SectionTitle eyebrow="Review queue" title="Flagged candidates" description="Sorted by fraud score. Verify before advancing." />
          {queue.isLoading ? (
            <div className="mt-3"><EmptyState title="Loading…" /></div>
          ) : (queue.data?.items.length ?? 0) === 0 ? (
            <div className="mt-3"><EmptyState title="Nothing flagged" description="No candidates are currently in review or high-risk." /></div>
          ) : (
            <ul className="mt-3 space-y-2">
              {queue.data!.items.map((a) => (
                <li key={a.id}>
                  <button onClick={() => setSelected(a)} className={`w-full text-left rounded-md border p-3 hover:bg-sunken transition ${selected?.id === a.id ? "border-accent" : "border-line bg-canvas"}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-ink">{a.candidate_name}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-lg font-bold text-ink tabular-nums">{a.fraud_score}</span>
                        <Pill tone={BAND_TONE[a.band]}>{a.band.replace("_", " ")}</Pill>
                      </div>
                    </div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted mt-1">
                      Action: {ACTION_LABEL[a.recommended_action]} · confidence {(a.confidence * 100).toFixed(0)}%
                      {a.low_confidence && <span className="text-warn-fg"> · low-confidence</span>}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Surface>

        {/* Detail */}
        <Surface>
          <SectionTitle eyebrow="Signal breakdown" title={selected ? selected.candidate_name : "Select a candidate"} description={selected ? `Score ${selected.fraud_score}/100 — ${selected.band.replace("_", " ")} — recommend ${ACTION_LABEL[selected.recommended_action]}.` : "The contributing signals appear here."} />
          {!selected ? (
            <div className="mt-3"><EmptyState title="No candidate selected" /></div>
          ) : (
            <>
              <div className="mt-3 flex items-center gap-3">
                <div className={`text-3xl font-bold tabular-nums ${selected.band === "high_risk" ? "text-danger-fg" : selected.band === "review" ? "text-warn-fg" : "text-ink"}`}>{selected.fraud_score}</div>
                <div>
                  <Pill tone={BAND_TONE[selected.band]}>{selected.band.replace("_", " ")}</Pill>
                  <div className="text-2xs uppercase tracking-eyebrow text-muted mt-1">{selected.categories_with_data}/{selected.categories_total} signal groups · {(selected.confidence * 100).toFixed(0)}% confidence</div>
                </div>
              </div>
              <Divider className="my-3" />
              <div className="fp-eyebrow mb-2">Contributing signals</div>
              <ul className="space-y-1.5">
                {selected.contributing_signals.map((sig) => (
                  <li key={sig.category} className="flex items-center gap-2">
                    <span className="w-40 shrink-0 text-xs text-body capitalize">{catLabel(sig.category)}</span>
                    <div className="flex-1 h-1.5 rounded-full bg-sunken overflow-hidden">
                      <div className={`h-full ${sig.points > 0 ? "bg-danger-fg" : "bg-line"}`} style={{ width: `${(sig.points / sig.weight) * 100}%` }} />
                    </div>
                    <span className="w-20 shrink-0 text-right text-2xs tabular-nums text-muted">
                      {sig.present ? `${sig.points} / ${sig.weight}` : "no data"}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-muted italic">Advisory signal for recruiter review — not an automated rejection. Verify flagged candidates with a human.</p>
            </>
          )}
        </Surface>
      </div>
    </div>
  );
}
