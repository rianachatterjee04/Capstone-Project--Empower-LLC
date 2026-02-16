"use client";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";

type Job = { id: string; title: string; location?: string | null; status: string; description: string; created_at: string };
type Candidate = { id: string; full_name: string; email: string; status: string; ai_score?: number | null; ai_summary?: string | null; resume_text?: string | null; job_posting_id: string; created_at: string };

export default function RecruitingPage() {
  const qc = useQueryClient();
  const [title, setTitle] = useState("Software Engineer");
  const [location, setLocation] = useState("Remote");
  const [status, setStatus] = useState("draft");
  const [description, setDescription] = useState("We are looking for ...");

  const [candJobId, setCandJobId] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [resumeText, setResumeText] = useState("");

  const jobsQ = useQuery({ queryKey: ["jobs"], queryFn: () => apiFetch<Job[]>("/recruiting/jobs") });
  const candsQ = useQuery({ queryKey: ["candidates"], queryFn: () => apiFetch<Candidate[]>("/recruiting/candidates") });

  const jobs = jobsQ.data ?? [];
  const candidates = candsQ.data ?? [];

  const pipeline = useMemo(() => {
    const cols = ["new", "screened", "interview", "rejected", "hired"] as const;
    const by = new Map<string, Candidate[]>();
    cols.forEach((c) => by.set(c, []));
    for (const cand of candidates) {
      const k = (cand.status as any) ?? "new";
      by.set(k, [...(by.get(k) ?? []), cand]);
    }
    return { cols, by };
  }, [candidates]);

  async function createJob() {
    await apiPost<Job>("/recruiting/jobs", { title, description, location, status });
    await qc.invalidateQueries({ queryKey: ["jobs"] });
  }

  async function createCandidate() {
    await apiPost<Candidate>("/recruiting/candidates", { job_posting_id: candJobId, full_name: fullName, email, resume_text: resumeText });
    setFullName(""); setEmail(""); setResumeText("");
    await qc.invalidateQueries({ queryKey: ["candidates"] });
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Recruiting</div>
        <div className="text-sm text-black/60">Pipeline + AI screening controls (MVP).</div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-black/10 p-4 space-y-3">
          <div className="text-sm font-semibold">Create job posting</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
            <Input label="Location" value={location} onChange={(e) => setLocation(e.target.value)} />
            <Input label="Status" value={status} onChange={(e) => setStatus(e.target.value)} />
          </div>
          <Textarea label="Description" rows={6} value={description} onChange={(e) => setDescription(e.target.value)} />
          <Button onClick={createJob}>Create job</Button>
          {jobsQ.error ? <div className="text-sm text-red-600">{(jobsQ.error as Error).message}</div> : null}
        </div>

        <div className="rounded-2xl border border-black/10 p-4 space-y-3">
          <div className="text-sm font-semibold">Add candidate (runs AI screening)</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="block">
              <div className="mb-1 text-sm font-medium">Job</div>
              <select className="w-full rounded-xl border border-black/15 px-3 py-2 text-sm" value={candJobId} onChange={(e) => setCandJobId(e.target.value)}>
                <option value="">Select job</option>
                {jobs.map((j) => (
                  <option key={j.id} value={j.id}>{j.title} ({j.status})</option>
                ))}
              </select>
            </label>
            <Input label="Candidate name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            <Input label="Candidate email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <Textarea label="Resume text (MVP)" rows={6} value={resumeText} onChange={(e) => setResumeText(e.target.value)} placeholder="Paste resume text here." />
          <Button onClick={createCandidate} disabled={!candJobId || !fullName || !email}>Add candidate</Button>
          {candsQ.error ? <div className="text-sm text-red-600">{(candsQ.error as Error).message}</div> : null}
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Pipeline</div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-5 gap-3">
          {pipeline.cols.map((col) => (
            <div key={col} className="rounded-xl border border-black/10 p-3 min-h-[180px]">
              <div className="text-sm font-semibold capitalize">{col}</div>
              <div className="mt-3 space-y-2">
                {(pipeline.by.get(col) ?? []).map((c) => (
                  <div key={c.id} className="rounded-lg border border-black/10 p-2">
                    <div className="text-sm font-medium">{c.full_name}</div>
                    <div className="text-xs text-black/60">{c.email}</div>
                    <div className="mt-1 text-xs text-black/60">AI score: <span className="font-medium">{c.ai_score ?? "—"}</span></div>
                    {c.ai_summary ? <div className="mt-1 text-xs">{c.ai_summary}</div> : null}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
