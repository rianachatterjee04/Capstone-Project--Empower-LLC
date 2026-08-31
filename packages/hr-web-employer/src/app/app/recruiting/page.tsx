"use client";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { PIPELINE_STAGES, toStage } from "@/lib/pipelineStages";
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
    // THREE OF FOUR CANDIDATES WERE INVISIBLE HERE.
    //
    // The columns were the five names this page happened to know, and the
    // bucket key was the raw stored status. Three seeded candidates are stored
    // as "interviewing", which is not one of them, so `by.set("interviewing",
    // ...)` created a bucket nothing renders and they vanished from the board
    // entirely — present in the database, absent from the recruiter's screen.
    // "offer" had no column at all, so anyone at offer stage disappeared too.
    //
    // src/lib/pipelineStages.ts already holds the vocabulary and the synonyms,
    // agreed with the API. It just was not used here.
    //
    // A status we cannot place is listed separately rather than dropped or
    // quietly counted as "new" — a full top of funnel reads as a healthy
    // pipeline, which is the most misleading place to put an unknown.
    const cols = PIPELINE_STAGES;
    const by = new Map<string, Candidate[]>();
    cols.forEach((c) => by.set(c, []));
    const unplaced: Candidate[] = [];
    for (const cand of candidates) {
      const stage = toStage(cand.status ?? "");
      if (!stage) {
        unplaced.push(cand);
        continue;
      }
      by.set(stage, [...(by.get(stage) ?? []), cand]);
    }
    return { cols, by, unplaced };
  }, [candidates]);

  const [jobCreated, setJobCreated] = useState(false);
  const [candidateAdded, setCandidateAdded] = useState(false);

  async function createJob() {
    await apiPost<Job>("/recruiting/jobs", { title, description, location, status });
    await qc.invalidateQueries({ queryKey: ["jobs"] });
    setJobCreated(true);
    setTimeout(() => setJobCreated(false), 3000);
  }

  async function createCandidate() {
    await apiPost<Candidate>("/recruiting/candidates", { job_posting_id: candJobId, full_name: fullName, email, resume_text: resumeText });
    setFullName(""); setEmail(""); setResumeText("");
    await qc.invalidateQueries({ queryKey: ["candidates"] });
    setCandidateAdded(true);
    setTimeout(() => setCandidateAdded(false), 3000);
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Recruiting</div>
        <div className="text-sm text-black/60">
          Candidates by stage. Screening reads the resume; a person moves anyone
          between stages.
        </div>
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
          <div className="flex items-center gap-3">
            <Button onClick={createJob}>Create job</Button>
            {jobCreated && <span className="text-sm text-green-600 font-medium">✓ Job created</span>}
          </div>
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
          <Textarea label="Resume text" rows={6} value={resumeText} onChange={(e) => setResumeText(e.target.value)} placeholder="Paste resume text here." />
          <div className="flex items-center gap-3">
            <Button onClick={createCandidate} disabled={!candJobId || !fullName || !email}>Add candidate</Button>
            {candidateAdded && <span className="text-sm text-green-600 font-medium">✓ Candidate added</span>}
          </div>
          {candsQ.error ? <div className="text-sm text-red-600">{(candsQ.error as Error).message}</div> : null}
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Pipeline</div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {pipeline.cols.map((col) => (
            <div key={col} className="rounded-xl border border-black/10 p-3 min-h-[180px]">
              <div className="text-sm font-semibold capitalize">{col}</div>
              <div className="mt-3 space-y-2">
                {(pipeline.by.get(col) ?? []).map((c) => (
                  <div key={c.id} className="rounded-lg border border-black/10 p-2">
                    <div className="text-sm font-medium">{c.full_name}</div>
                    <div className="text-xs text-black/60">{c.email}</div>
                    {/* A bare em-dash reads as a broken number. "Not screened yet" and
                        "screened and scored 0" are different facts and a buyer should
                        not have to guess which one a dash means. */}
                    <div className="mt-1 text-xs text-black/60">
                      {c.ai_score === null || c.ai_score === undefined ? (
                        <span>Not screened yet</span>
                      ) : (
                        <>Screening score: <span className="font-medium">{c.ai_score}</span></>
                      )}
                    </div>
                    {c.ai_summary ? <div className="mt-1 text-xs">{c.ai_summary}</div> : null}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Not a column. These candidates are in the pipeline but their stored
            stage is not one we recognise, and putting them in "new" would say
            something false about where they are. */}
        {pipeline.unplaced.length > 0 && (
          <div className="mt-4 rounded-xl border border-amber-500/40 bg-amber-50/60 p-3">
            <div className="text-sm font-semibold">
              {pipeline.unplaced.length} candidate
              {pipeline.unplaced.length === 1 ? "" : "s"} not shown in a column
            </div>
            <p className="mt-1 text-xs text-black/70">
              Their recorded stage is not one this board knows, so we cannot say
              where they are without guessing. Move them to a stage to place them.
            </p>
            <div className="mt-2 space-y-1">
              {pipeline.unplaced.map((c) => (
                <div key={c.id} className="text-xs">
                  <span className="font-medium">{c.full_name}</span>
                  <span className="text-black/60"> — stage recorded as “{c.status}”</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}