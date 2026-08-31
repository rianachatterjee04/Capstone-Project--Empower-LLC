"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";

type CaseReport = {
  id: string;
  category: string;
  severity: string;
  details: string;
  status: string;
  escalation_level: number;
  created_at: string;
};

export default function CasesPage() {
  const qc = useQueryClient();
  const [category, setCategory] = useState("harassment");
  const [severity, setSeverity] = useState("medium");
  const [details, setDetails] = useState("");
  const [anonymous, setAnonymous] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["cases"],
    queryFn: () => apiFetch<CaseReport[]>("/cases"),
  });

  async function submit() {
    setMsg(null);
    try {
      await apiPost("/cases", { category, severity, details, is_anonymous: anonymous, reporter_employee_id: null });
      setDetails("");
      setMsg("Submitted.");
      await qc.invalidateQueries({ queryKey: ["cases"] });
    } catch (e: any) {
      setMsg(e.message);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Reports</div>
        <div className="text-sm text-black/60">Anonymous reporting UX (ombudsman-style).</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-4">
        <div className="text-sm font-semibold">Submit a report</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input label="Category" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="harassment / safety / payroll / other" />
          <Input label="Severity" value={severity} onChange={(e) => setSeverity(e.target.value)} placeholder="low / medium / high / critical" />
        </div>
        <Textarea label="Details" rows={6} value={details} onChange={(e) => setDetails(e.target.value)} placeholder="Describe what happened." />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={anonymous} onChange={(e) => setAnonymous(e.target.checked)} />
          Submit anonymously
        </label>
        <div className="flex items-center gap-2">
          <Button onClick={submit} disabled={!details.trim()}>Submit</Button>
          {msg ? <div className="text-sm text-black/70">{msg}</div> : null}
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Case list</div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          {isLoading ? <div>Loading…</div> : null}
          {error ? <div className="text-red-600">{(error as Error).message}</div> : null}
          {(data ?? []).map((c) => (
            <div key={c.id} className="rounded-xl border border-black/10 p-3">
              <div className="font-medium">{c.category} • {c.severity}</div>
              <div className="text-sm text-black/60">Status: {c.status} • Escalation: {c.escalation_level}</div>
              <div className="mt-2 text-sm">{c.details}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
