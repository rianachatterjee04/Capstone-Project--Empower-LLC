"use client";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Textarea } from "@/components/Textarea";

type CaseItem = {
  id: string;
  category: string;
  severity: string;
  is_anonymous: boolean;
  status: string;
  escalation_level?: number;
  summary?: string;
  created_at: string | null;
};

type ListResponse = { role_view: string; items: CaseItem[]; note?: string };
type Triage = {
  summary: string;
  suggested_category: string;
  suggested_severity: string;
  confidentiality_reminder: string;
  ai_disclaimer: string;
};

type Risk = {
  totals: { all_cases: number };
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
  open_high_severity: { id: string; category: string; summary: string; created_at: string | null }[];
  retaliation_reminder: string;
};

const SEV_COLOR: Record<string, string> = {
  high: "bg-rose-100 text-rose-800 border-rose-200",
  medium: "bg-amber-100 text-amber-800 border-amber-200",
  low: "bg-slate-100 text-slate-700 border-slate-200",
};

export default function OmbudsmanPage() {
  const qc = useQueryClient();
  const [details, setDetails] = useState("");
  const [anonymous, setAnonymous] = useState(true);
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState("");
  const [triage, setTriage] = useState<Triage | null>(null);
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const listQ = useQuery({ queryKey: ["ombudsman-list"], queryFn: () => apiFetch<ListResponse>("/ombudsman") });
  const riskQ = useQuery({ queryKey: ["ombudsman-risk"], queryFn: () => apiFetch<Risk>("/ombudsman/risk-dashboard").catch(() => null) });

  const privileged = listQ.data?.role_view === "privileged";

  async function runTriage() {
    if (!details.trim()) return;
    setBusy(true);
    try {
      const t = await apiPost<Triage>("/ombudsman/triage", { details });
      setTriage(t);
      if (!category) setCategory(t.suggested_category);
      if (!severity) setSeverity(t.suggested_severity);
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!details.trim()) return;
    setBusy(true);
    try {
      const created = await apiPost<{ id: string }>("/cases", {
        is_anonymous: anonymous,
        category: category || triage?.suggested_category || "general",
        severity: severity || triage?.suggested_severity || "low",
        details,
        reporter_employee_id: null,
      });
      setSubmitted(created.id);
      setDetails("");
      setTriage(null);
      setCategory("");
      setSeverity("");
      await qc.invalidateQueries({ queryKey: ["ombudsman-list"] });
      await qc.invalidateQueries({ queryKey: ["ombudsman-risk"] });
    } catch (e) {
      // err handled inline
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-indigo-200 bg-indigo-50 p-4">
        <div className="text-sm font-semibold text-indigo-900">Confidential & retaliation-free</div>
        <div className="text-xs text-indigo-900/80 mt-1">
          Reports go to HR / legal only. Managers do not have direct access. Foundry strictly prohibits retaliation
          against good-faith reporters. AI suggestions are starting points — HR reviews every submission.
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-black/10 p-5 space-y-3">
          <div className="text-sm font-semibold">Submit a report</div>
          <Textarea
            label="What happened?"
            rows={6}
            value={details}
            onChange={(e) => setDetails(e.target.value)}
            placeholder="Describe the situation in as much detail as you're comfortable sharing. Times, places, people involved if you want to share them."
          />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={anonymous} onChange={(e) => setAnonymous(e.target.checked)} />
            Submit anonymously
          </label>
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={runTriage} disabled={!details.trim() || busy}>
              Run AI triage (preview)
            </Button>
            <Button onClick={submit} disabled={!details.trim() || busy}>
              {busy ? "Submitting…" : "Submit report"}
            </Button>
          </div>
          {submitted && (
            <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-900">
              ✓ Report submitted. Reference: <span className="font-mono">{submitted.slice(0, 8)}</span>. HR will acknowledge within 1 business day.
            </div>
          )}

          {triage && (
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 space-y-2">
              <div className="text-xs uppercase tracking-wide text-slate-600">AI triage preview</div>
              <div className="text-sm">
                Suggested category: <span className="font-semibold capitalize">{triage.suggested_category.replace(/_/g, " ")}</span>
                <span className="mx-2 text-black/40">·</span>
                Suggested severity: <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${SEV_COLOR[triage.suggested_severity] ?? "border-black/20"}`}>{triage.suggested_severity}</span>
              </div>
              <div className="text-xs text-slate-600">{triage.ai_disclaimer}</div>
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-black/10 p-5 space-y-3">
          <div className="text-sm font-semibold">{privileged ? "All cases" : "Your reports"}</div>
          {listQ.data?.note && <div className="text-xs text-black/60">{listQ.data.note}</div>}
          {(listQ.data?.items ?? []).length === 0 ? (
            <div className="text-sm text-black/40 py-6 text-center">No cases yet</div>
          ) : (
            <div className="divide-y divide-black/5">
              {(listQ.data?.items ?? []).map((c) => (
                <div key={c.id} className="py-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium capitalize">{c.category.replace(/_/g, " ")}</div>
                    <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${SEV_COLOR[c.severity] ?? "border-black/20"}`}>
                      {c.severity}
                    </span>
                  </div>
                  <div className="text-xs text-black/50">
                    {c.is_anonymous ? "Anonymous" : "Named"} · {c.status} · {c.created_at ? new Date(c.created_at).toLocaleString() : ""}
                  </div>
                  {c.summary && <div className="text-sm text-black/70">{c.summary}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {privileged && riskQ.data && (
        <div className="rounded-2xl border border-black/10 p-5 space-y-3">
          <div className="text-sm font-semibold">Risk dashboard</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-xl border border-black/10 p-3">
              <div className="text-xs text-black/40 uppercase">Total cases</div>
              <div className="text-2xl font-bold">{riskQ.data.totals.all_cases}</div>
            </div>
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3">
              <div className="text-xs text-rose-800 uppercase">High severity</div>
              <div className="text-2xl font-bold text-rose-900">{riskQ.data.by_severity.high ?? 0}</div>
            </div>
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
              <div className="text-xs text-amber-800 uppercase">Medium</div>
              <div className="text-2xl font-bold text-amber-900">{riskQ.data.by_severity.medium ?? 0}</div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <div className="text-xs text-slate-700 uppercase">Low</div>
              <div className="text-2xl font-bold text-slate-900">{riskQ.data.by_severity.low ?? 0}</div>
            </div>
          </div>

          {riskQ.data.open_high_severity.length > 0 && (
            <div>
              <div className="text-sm font-semibold text-rose-900 mb-2">Open high-severity cases</div>
              <div className="divide-y divide-black/5">
                {riskQ.data.open_high_severity.map((c) => (
                  <div key={c.id} className="py-2">
                    <div className="text-sm capitalize font-medium">{c.category.replace(/_/g, " ")}</div>
                    <div className="text-xs text-black/60">{c.summary}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="text-xs text-black/50 italic">{riskQ.data.retaliation_reminder}</div>
        </div>
      )}
    </div>
  );
}
