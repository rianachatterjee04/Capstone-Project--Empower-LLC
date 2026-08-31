"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Textarea } from "@/components/Textarea";

type Triage = {
  summary: string; suggested_category: string; suggested_severity: string;
  confidentiality_reminder: string; ai_disclaimer: string;
};

type ListResponse = { role_view: string; items: { id: string; category: string; severity: string; status: string; is_anonymous: boolean; created_at: string | null }[]; note?: string };

const SEV: Record<string, string> = {
  high: "bg-rose-100 text-rose-800 border-rose-200",
  medium: "bg-amber-100 text-amber-800 border-amber-200",
  low: "bg-slate-100 text-slate-700 border-slate-200",
};

export default function OmbudsmanPage() {
  const qc = useQueryClient();
  const [details, setDetails] = useState("");
  const [anon, setAnon] = useState(true);
  const [triage, setTriage] = useState<Triage | null>(null);
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState<string | null>(null);

  const listQ = useQuery({ queryKey: ["ombudsman-me"], queryFn: () => apiFetch<ListResponse>("/ombudsman") });

  async function runTriage() {
    if (!details.trim()) return;
    setBusy(true);
    try { setTriage(await apiPost<Triage>("/ombudsman/triage", { details })); }
    finally { setBusy(false); }
  }

  async function submit() {
    setBusy(true);
    try {
      const out = await apiPost<{ id: string }>("/cases", {
        is_anonymous: anon,
        category: triage?.suggested_category || "general",
        severity: triage?.suggested_severity || "low",
        details,
        reporter_employee_id: null,
      });
      setSubmitted(out.id);
      setDetails("");
      setTriage(null);
      await qc.invalidateQueries({ queryKey: ["ombudsman-me"] });
    } finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-indigo-200 bg-indigo-50 p-4">
        <div className="text-sm font-semibold text-indigo-900">Confidential. Retaliation-free.</div>
        <div className="text-xs text-indigo-900/80 mt-1">
          Reports go directly to HR/legal. Managers do not have access. Foundry strictly prohibits retaliation.
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <div className="text-sm font-semibold">Submit a report</div>
        <Textarea label="What happened?" rows={6} value={details} onChange={(e) => setDetails(e.target.value)} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={anon} onChange={(e) => setAnon(e.target.checked)} />
          Submit anonymously
        </label>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={runTriage} disabled={!details.trim() || busy}>Preview AI triage</Button>
          <Button onClick={submit} disabled={!details.trim() || busy}>{busy ? "Submitting…" : "Submit"}</Button>
        </div>
        {triage && (
          <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 text-xs">
            Suggested: <span className="font-semibold">{triage.suggested_category}</span> · severity <span className={`rounded-full border px-2 py-0.5 ${SEV[triage.suggested_severity] ?? ""}`}>{triage.suggested_severity}</span>
            <div className="mt-1 text-slate-600">{triage.ai_disclaimer}</div>
          </div>
        )}
        {submitted && (
          <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-900">
            ✓ Submitted. Reference {submitted.slice(0, 8)}. HR will acknowledge within 1 business day.
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold mb-2">Your reports</div>
        {listQ.data?.note && <div className="text-xs text-black/60 mb-2">{listQ.data.note}</div>}
        {(listQ.data?.items ?? []).length === 0 ? (
          <div className="text-sm text-black/40 py-4 text-center">No reports yet.</div>
        ) : (
          <div className="divide-y divide-black/5">
            {listQ.data!.items.map((c) => (
              <div key={c.id} className="py-2 flex items-center justify-between">
                <div>
                  <div className="text-sm capitalize font-medium">{c.category.replace(/_/g, " ")}</div>
                  <div className="text-xs text-black/50">{c.status} · {c.created_at ? new Date(c.created_at).toLocaleDateString() : ""}</div>
                </div>
                <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${SEV[c.severity] ?? "border-black/20"}`}>{c.severity}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
