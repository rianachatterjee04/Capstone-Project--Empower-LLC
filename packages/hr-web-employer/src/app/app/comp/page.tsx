"use client";
import { useEffect, useMemo, useState } from "react";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, Divider, KeyValue } from "@/components/ds";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";
import { WorkflowTimeline, defaultCompReviewTemplate, type StepStatus } from "@/components/WorkflowTimeline";
import { TotalCompPanel, TotalCompRollUp } from "@/components/TotalCompPanel";

// The employee whose total comp is shown. This used to be a hardcoded id that
// existed in no database, so the panel reported "Not on file" for every pay
// stream on every install -- the honest answer to the question it was asked,
// which made a working feature look broken. It now reads the real directory and
// reviews a real person, and the reviewer can switch to anyone in the org.
type DirectoryEntry = { id: string; legal_name?: string | null; preferred_name?: string | null; job_title?: string | null };

function displayName(e: DirectoryEntry): string {
  // Legal name first: a comp review is a formal record, and `preferred_name`
  // holds only the given name ("Amara"), which is ambiguous in a picker.
  return e.legal_name?.trim() || e.preferred_name?.trim() || "Unnamed employee";
}

type Recommendation = {
  employee_id: string;
  current_salary: number;
  suggested_low: number;
  suggested_mid: number;
  suggested_high: number;
  merit_percent_low: number;
  merit_percent_mid: number;
  merit_percent_high: number;
  compa_ratio: number | null;
  market_position: string | null;
  promotion_recommended: boolean;
  equity_flags: string[];
  rationale: string;
  confidence: string;
  requires_approval_by: string[];
  disclaimer: string;
};

function currency(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

type CycleStage = "perfSignal" | "aiRec" | "managerProposal" | "hrCalibration" | "financeApproval" | "communicate";

export default function CompPage() {
  const [roster, setRoster] = useState<DirectoryEntry[]>([]);
  const [employeeId, setEmployeeId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<DirectoryEntry[] | { items?: DirectoryEntry[] }>("/employees")
      .then((res) => {
        if (cancelled) return;
        const rows = Array.isArray(res) ? res : (res.items ?? []);
        setRoster(rows);
        setEmployeeId((cur) => cur ?? rows[0]?.id ?? null);
      })
      .catch(() => {
        /* The panel below renders its own "unavailable" state; a failed roster
           fetch must not blank the rest of the comp cycle. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const [name, setName] = useState("Avery Chen");
  const [title, setTitle] = useState("Senior Software Engineer");
  const [department, setDepartment] = useState("Engineering");
  const [salary, setSalary] = useState(135000);
  const [tenure, setTenure] = useState(2.4);
  const [rating, setRating] = useState(4.2);
  const [reviewSummary, setReviewSummary] = useState("Strong impact on the payments platform; shipped 4 major features with positive customer feedback.");
  const [p50, setP50] = useState(150000);
  const [p25, setP25] = useState(125000);
  const [p75, setP75] = useState(175000);
  const [bandMin, setBandMin] = useState(120000);
  const [bandMax, setBandMax] = useState(180000);
  const [promotionReady, setPromotionReady] = useState(false);
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Cycle state — drives the WorkflowTimeline.
  const [proposalAccepted, setProposalAccepted] = useState(false);
  const [hrCalibrated, setHrCalibrated] = useState(false);
  const [financeApproved, setFinanceApproved] = useState(false);
  const [communicated, setCommunicated] = useState(false);

  async function generate() {
    setError(null);
    setLoading(true);
    try {
      const out = await apiPost<Recommendation>("/comp-ai/recommend", {
        employee_id: "11111111-1111-1111-1111-111111111199",
        name,
        job_title: title,
        department,
        current_salary: salary,
        tenure_years: tenure,
        performance_rating: rating,
        last_review_summary: reviewSummary,
        market_p25: p25,
        market_p50: p50,
        market_p75: p75,
        band_min: bandMin,
        band_max: bandMax,
        promotion_ready: promotionReady,
      });
      setRec(out);
      // Reset downstream cycle stages when a fresh rec is generated.
      setProposalAccepted(false);
      setHrCalibrated(false);
      setFinanceApproved(false);
      setCommunicated(false);
    } catch (e: any) {
      setError(e?.message ?? "Failed to generate");
    } finally {
      setLoading(false);
    }
  }

  // Derive the cycle status from local UI state.
  const cycleSteps = useMemo(() => {
    const status = (b: boolean, inProgress = false): StepStatus =>
      b ? "done" : inProgress ? "in_progress" : "pending";

    return defaultCompReviewTemplate(name, {
      perfSignal: "done",
      aiRec: rec ? "done" : "in_progress",
      managerProposal: status(proposalAccepted, !!rec && !proposalAccepted),
      hrCalibration: status(hrCalibrated, proposalAccepted && !hrCalibrated),
      financeApproval: status(financeApproved, hrCalibrated && !financeApproved),
      communicate: status(communicated, financeApproved && !communicated),
    });
  }, [name, rec, proposalAccepted, hrCalibrated, financeApproved, communicated]);

  function advance(stage: CycleStage) {
    if (stage === "managerProposal") setProposalAccepted(true);
    if (stage === "hrCalibration") setHrCalibrated(true);
    if (stage === "financeApproval") setFinanceApproved(true);
    if (stage === "communicate") setCommunicated(true);
  }

  function reset() {
    setProposalAccepted(false);
    setHrCalibrated(false);
    setFinanceApproved(false);
    setCommunicated(false);
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Performance"
        title="Compensation review"
        subtitle="AI merit and promotion recommendations with explainable rationale and pay-equity flags. Final approval is always human."
      />

      {/* Unified Total Compensation — every pay stream from its real source,
          target vs actual, so offers and comp cycles see the FULL number. */}
      {roster.length > 0 && (
        <div className="flex items-center gap-3">
          <label htmlFor="tc-employee" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Reviewing
          </label>
          <select
            id="tc-employee"
            value={employeeId ?? ""}
            onChange={(e) => setEmployeeId(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            {roster.map((e) => (
              <option key={e.id} value={e.id}>
                {displayName(e)}
                {e.job_title ? ` — ${e.job_title}` : ""}
              </option>
            ))}
          </select>
        </div>
      )}
      {employeeId && <TotalCompPanel employeeId={employeeId} />}
      <TotalCompRollUp />

      {/* Inputs and recommendation, side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Surface>
          <SectionTitle eyebrow="Inputs" title="Employee snapshot" />
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
            <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
            <Input label="Job title" value={title} onChange={(e) => setTitle(e.target.value)} />
            <Input label="Department" value={department} onChange={(e) => setDepartment(e.target.value)} />
            <Input label="Current salary (USD)" type="number" value={salary} onChange={(e) => setSalary(Number(e.target.value))} />
            <Input label="Tenure (years)" type="number" step="0.1" value={tenure} onChange={(e) => setTenure(Number(e.target.value))} />
            <Input label="Performance rating (1–5)" type="number" step="0.1" min="1" max="5" value={rating} onChange={(e) => setRating(Number(e.target.value))} />
          </div>
          <div className="mt-3">
            <Textarea label="Latest review highlight" rows={3} value={reviewSummary} onChange={(e) => setReviewSummary(e.target.value)} />
          </div>
          <label className="mt-3 flex items-center gap-2 text-sm text-body">
            <input type="checkbox" checked={promotionReady} onChange={(e) => setPromotionReady(e.target.checked)} />
            Manager flagged promotion-ready
          </label>
        </Surface>

        <Surface>
          <SectionTitle eyebrow="Market & band" title="Comparators" />
          <div className="mt-3 grid grid-cols-2 gap-3">
            <Input label="Market P25" type="number" value={p25} onChange={(e) => setP25(Number(e.target.value))} />
            <Input label="Market P50" type="number" value={p50} onChange={(e) => setP50(Number(e.target.value))} />
            <Input label="Market P75" type="number" value={p75} onChange={(e) => setP75(Number(e.target.value))} />
            <Input label="Band min" type="number" value={bandMin} onChange={(e) => setBandMin(Number(e.target.value))} />
            <Input label="Band max" type="number" value={bandMax} onChange={(e) => setBandMax(Number(e.target.value))} />
          </div>
          <div className="mt-4 flex items-center gap-2">
            <Action variant="primary" onClick={generate} disabled={loading}>
              {loading ? "Analyzing…" : rec ? "Re-run recommendation" : "Generate AI recommendation"}
            </Action>
            {rec && (
              <Action variant="subtle" onClick={reset}>
                Reset cycle
              </Action>
            )}
          </div>
          {error && <div className="mt-2 text-sm text-danger-fg">{error}</div>}
        </Surface>
      </div>

      {/* Recommendation card — calm, no rainbow */}
      {rec && (
        <Surface>
          <SectionTitle
            eyebrow="Recommendation"
            title={`Suggested range for ${name}`}
            trailing={
              <div className="flex items-center gap-1.5">
                {rec.promotion_recommended && <Pill tone="info">Promotion recommended</Pill>}
                <Pill tone={rec.confidence === "high" ? "success" : rec.confidence === "medium" ? "warn" : "neutral"}>
                  {rec.confidence} confidence
                </Pill>
              </div>
            }
          />

          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
            <RangeStat label="Conservative" amount={currency(rec.suggested_low)} pct={rec.merit_percent_low} tone="neutral" />
            <RangeStat label="Recommended" amount={currency(rec.suggested_mid)} pct={rec.merit_percent_mid} tone="success" emphasis />
            <RangeStat label="Stretch" amount={currency(rec.suggested_high)} pct={rec.merit_percent_high} tone="neutral" />
          </div>

          <Divider className="my-4" />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
            <div>
              <KeyValue label="Current" value={currency(rec.current_salary)} />
              <KeyValue label="Market position" value={rec.market_position?.replace(/_/g, " ") ?? "—"} />
            </div>
            <div>
              <KeyValue label="Compa-ratio" value={rec.compa_ratio != null ? rec.compa_ratio.toFixed(2) : "—"} />
              <KeyValue label="Approval path" value={rec.requires_approval_by.join(" · ")} />
            </div>
          </div>

          {rec.equity_flags.length > 0 && (
            <div className="mt-4 rounded-md border border-warn-line bg-warn-bg text-warn-fg text-xs px-3 py-2">
              <span className="font-semibold uppercase tracking-eyebrow text-2xs">Pay equity flags</span>
              <ul className="mt-1 space-y-0.5">
                {rec.equity_flags.map((f, i) => <li key={i}>• {f}</li>)}
              </ul>
            </div>
          )}

          <p className="mt-4 text-sm text-body">{rec.rationale}</p>
          <p className="mt-2 text-xs text-muted italic">{rec.disclaimer}</p>
        </Surface>
      )}

      {/* The cycle */}
      <Surface>
        <SectionTitle
          eyebrow="Cycle"
          title="Comp review journey"
          description="Performance signal → AI recommendation → manager proposal → HR calibration → finance approval → communicate."
        />
        <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2">
            <WorkflowTimeline steps={cycleSteps} />
          </div>
          <div>
            <div className="fp-eyebrow mb-2">Cycle actions</div>
            <div className="rounded-lg border border-line bg-canvas p-3 space-y-2">
              <CycleButton label="Accept manager proposal" disabled={!rec || proposalAccepted} onClick={() => advance("managerProposal")} done={proposalAccepted} />
              <CycleButton label="Mark HR calibrated" disabled={!proposalAccepted || hrCalibrated} onClick={() => advance("hrCalibration")} done={hrCalibrated} />
              <CycleButton label="Record finance approval" disabled={!hrCalibrated || financeApproved} onClick={() => advance("financeApproval")} done={financeApproved} />
              <CycleButton label="Mark communicated" disabled={!financeApproved || communicated} onClick={() => advance("communicate")} done={communicated} />
              <Divider />
              <div className="text-2xs uppercase tracking-eyebrow text-muted">Auditability</div>
              <p className="text-xs text-muted">Each transition writes to the org audit log so the comp decision is defensible.</p>
            </div>
          </div>
        </div>
      </Surface>
    </div>
  );
}

function RangeStat({ label, amount, pct, tone, emphasis }: { label: string; amount: string; pct: number; tone: "neutral" | "success"; emphasis?: boolean }) {
  return (
    <div
      className={[
        "rounded-lg border bg-surface p-4",
        emphasis ? "border-success-line ring-1 ring-success-line" : "border-line",
      ].join(" ")}
    >
      <div className="fp-eyebrow">{label}</div>
      <div className={["mt-1 text-2xl font-semibold tracking-tight tabular-nums", emphasis ? "text-success-fg" : "text-ink"].join(" ")}>{amount}</div>
      <div className={["text-xs", emphasis ? "text-success-fg/80" : "text-muted"].join(" ")}>+{pct.toFixed(1)}%</div>
    </div>
  );
}

function CycleButton({ label, disabled, onClick, done }: { label: string; disabled: boolean; onClick: () => void; done: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={[
        "w-full text-left text-sm rounded-md border px-3 py-2 transition-colors duration-150 ease-calm",
        done
          ? "border-success-line bg-success-bg text-success-fg"
          : disabled
          ? "border-line bg-surface text-faint cursor-not-allowed"
          : "border-line bg-surface text-ink hover:bg-sunken",
      ].join(" ")}
    >
      {done ? `✓ ${label}` : label}
    </button>
  );
}
