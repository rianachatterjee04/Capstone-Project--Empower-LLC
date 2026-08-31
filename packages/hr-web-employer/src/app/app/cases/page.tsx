"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";
import { PageHeader, Surface, SectionTitle, StatusPill, EmptyState } from "@/components/ds";

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

  const cases = data ?? [];

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Compliance"
        title="Reports"
        subtitle="Anonymous reporting UX (ombudsman-style)."
      />

      <Surface className="space-y-4">
        <SectionTitle title="Submit a report" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input label="Category" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="harassment / safety / payroll / other" />
          <Input label="Severity" value={severity} onChange={(e) => setSeverity(e.target.value)} placeholder="low / medium / high / critical" />
        </div>
        <Textarea label="Details" rows={6} value={details} onChange={(e) => setDetails(e.target.value)} placeholder="Describe what happened." />
        <label className="flex items-center gap-2 text-sm text-body">
          <input type="checkbox" checked={anonymous} onChange={(e) => setAnonymous(e.target.checked)} />
          Submit anonymously
        </label>
        <div className="flex items-center gap-3">
          <Button onClick={submit} disabled={!details.trim()}>Submit</Button>
          {msg ? <div className="text-sm text-body">{msg}</div> : null}
        </div>
      </Surface>

      <Surface>
        <SectionTitle title="Case list" description={`${cases.length} total`} />
        {isLoading ? <div className="mt-3 text-sm text-muted">Loading…</div> : null}
        {error ? <div className="mt-3 text-sm text-danger-fg">{(error as Error).message}</div> : null}
        {!isLoading && cases.length === 0 ? (
          <EmptyState title="No cases yet" description="Submitted reports will appear here for review and escalation." />
        ) : (
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
            {cases.map((c) => (
              <div key={c.id} className="rounded-md border border-line bg-canvas p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium text-sm text-ink capitalize">{c.category}</div>
                  <StatusPill value={c.severity} />
                </div>
                <div className="text-xs text-muted mt-1">Status: {c.status} · Escalation: {c.escalation_level}</div>
                <div className="mt-2 text-sm text-body">{c.details}</div>
              </div>
            ))}
          </div>
        )}
      </Surface>
    </div>
  );
}
