"use client";

/**
 * Unified employee profile — ONE page for a person.
 *
 * Previously a person was fragmented across three routes: /app/people/[id]
 * (records), /app/profile/[id] (culture card + total comp) and
 * /app/digital-twin (skills / attrition / marketplace). Those are now tabs on
 * this single page, mirroring the already-unified employee-side /twin:
 *
 *   Overview · Records · Total comp · Performance · Twin
 *
 * /app/profile/[id] and /app/digital-twin redirect here. The directory,
 * org-chart and manager links all point at this one URL.
 */
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState, Avatar, Divider, LinkAction } from "@/components/ds";
import { TotalCompPanel } from "@/components/TotalCompPanel";
import { IconSparkle } from "@/components/icons";

type Employee = {
  id: string;
  legal_name: string;
  preferred_name?: string | null;
  email: string;
  status: string;
  job_title?: string | null;
  department?: string | null;
  location?: string | null;
  manager_employee_id?: string | null;
  start_date?: string | null;
};

type CompRecord = {
  id: string; amount: number; currency: string; basis: "salary" | "hourly";
  effective_date: string; end_date: string | null; reason: string | null; review_id: string | null;
};
type JobRecord = {
  id: string; job_title: string | null; department: string | null; manager_employee_id: string | null;
  effective_date: string; end_date: string | null; reason: string | null;
};
type Contact = { id: string; full_name: string; relationship: string | null; phone: string; email: string | null; is_primary: boolean };
type Doc = { id: string; category: string; storage_path: string; status: string; created_at: string; employee_id?: string | null };

type Profile = {
  employee_id: string; name: string; bio: string;
  interests: string[]; skills: string[]; currently_working_on: string[];
  favourite_collab: string; asks: string; languages: string[];
  pronouns?: string | null; pronouns_visible: boolean;
};

type Review = {
  id: string; employee_id: string; cycle: string; status: string; ai_decision?: string | null;
  self_submitted_at?: string | null; manager_submitted_at?: string | null; finalized_at?: string | null;
};

type Twin = {
  employee_id: string; name: string; job_title: string | null; department: string | null;
  tenure_years: number; skills: string[]; performance_rating: number;
  growth_signals: string[];
  attrition: { risk_score: number; band: string; drivers: string[]; suggested_actions: string[] };
  marketplace_matches: { role: any; score: number; matched_skills: string[]; missing_skills: string[]; learning_hint: string }[];
  skill_gap_to_next: { target_role: string; gap: string[]; coverage_percent: number };
};

const money = (n: number, currency: string) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(n);

const BAND_TONE: Record<string, "danger" | "warn" | "success" | "neutral"> = { high: "danger", medium: "warn", low: "success" };

const TABS = ["overview", "records", "total-comp", "performance", "twin"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABEL: Record<Tab, string> = {
  overview: "Overview", records: "Records", "total-comp": "Total comp", performance: "Performance", twin: "Twin",
};

export default function EmployeeProfilePage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [tab, setTab] = useState<Tab>("overview");
  useEffect(() => {
    if (typeof window === "undefined") return;
    const t = new URLSearchParams(window.location.search).get("tab");
    if (t && (TABS as readonly string[]).includes(t)) setTab(t as Tab);
  }, []);

  const employeesQ = useQuery({ queryKey: ["employees"], queryFn: () => apiFetch<Employee[]>("/employees") });
  const employees = employeesQ.data ?? [];
  const emp = useMemo(() => employees.find((e) => e.id === id) ?? null, [employees, id]);
  const manager = useMemo(() => employees.find((e) => e.id === emp?.manager_employee_id) ?? null, [employees, emp]);

  if (employeesQ.isLoading) return <div className="p-8 text-sm text-muted">Loading…</div>;
  if (!emp) {
    return (
      <div className="p-8">
        <EmptyState title="Employee not found" description="They may have been removed, or the link is stale." />
        <Link className="text-sm underline text-muted hover:text-ink" href="/app/people">← Back to directory</Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 fp-fade-in">
      <PageHeader
        eyebrow="People / Profile"
        title={emp.preferred_name || emp.legal_name}
        subtitle={`${emp.job_title ?? "—"} · ${emp.department ?? "—"}${emp.location ? ` · ${emp.location}` : ""}`}
        actions={
          <>
            <LinkAction href={`/app/checklists?employee=${emp.id}`} variant="subtle">Checklists</LinkAction>
            <LinkAction href={`/app/recognition?to_name=${encodeURIComponent(emp.preferred_name || emp.legal_name)}`} variant="primary">
              <IconSparkle /> Recognise
            </LinkAction>
          </>
        }
      />

      {/* Snapshot — always visible */}
      <Surface>
        <div className="flex items-center gap-4">
          <Avatar name={emp.legal_name} size={44} />
          <div className="grid grid-cols-2 md:grid-cols-5 gap-x-8 gap-y-1 text-sm flex-1">
            <div><span className="text-muted text-xs block">Email</span>{emp.email}</div>
            <div><span className="text-muted text-xs block">Status</span><Pill tone={emp.status === "active" ? "success" : "neutral"}>{emp.status}</Pill></div>
            <div><span className="text-muted text-xs block">Start date</span>{emp.start_date ?? "—"}</div>
            <div><span className="text-muted text-xs block">Manager</span>{manager ? <Link href={`/app/people/${manager.id}`} className="text-ink hover:underline">{manager.preferred_name || manager.legal_name}</Link> : "—"}</div>
            <div><span className="text-muted text-xs block">Employee ID</span><span className="font-mono text-xs">{emp.id}</span></div>
          </div>
        </div>
      </Surface>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px px-4 py-2 text-sm font-medium border-b-2 transition-colors duration-150 ease-calm ${
              tab === t ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab id={id} emp={emp} />}
      {tab === "records" && <RecordsTab id={id} emp={emp} employees={employees} />}
      {tab === "total-comp" && (
        <div className="space-y-4">
          <TotalCompPanel employeeId={id} />
        </div>
      )}
      {tab === "performance" && <PerformanceTab id={id} name={emp.preferred_name || emp.legal_name} />}
      {tab === "twin" && <TwinTab id={id} />}
    </div>
  );
}

// ---------------------------------------------------------------- OVERVIEW
function OverviewTab({ id, emp }: { id: string; emp: Employee }) {
  const profQ = useQuery({
    queryKey: ["public-profile", id],
    queryFn: () => apiFetch<Profile>(`/public-profile/${id}`),
    retry: false,
  });
  const p = profQ.data;

  return (
    <div className="space-y-5">
      <Surface>
        <SectionTitle eyebrow="Now" title="About" />
        {profQ.isLoading ? (
          <p className="mt-3 text-sm text-muted">Loading profile…</p>
        ) : !p ? (
          <p className="mt-3 text-sm text-muted">No self-profile captured yet. Records, comp and the digital twin are still available on the other tabs.</p>
        ) : (
          <>
            <p className="mt-3 text-base text-body leading-relaxed">{p.bio || "—"}</p>
            {p.currently_working_on?.length > 0 && (
              <>
                <Divider className="my-4" />
                <div className="fp-eyebrow mb-1">Currently working on</div>
                <ul className="space-y-1 text-sm text-body">
                  {p.currently_working_on.map((w, i) => <li key={i}>• {w}</li>)}
                </ul>
              </>
            )}
          </>
        )}
      </Surface>

      {p && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <Surface>
            <SectionTitle eyebrow="Skills" title="Captured competencies" />
            <div className="mt-3 flex flex-wrap gap-1.5">
              {(p.skills ?? []).length === 0 ? <span className="text-sm text-muted">No skills documented yet.</span>
                : p.skills.map((s) => <Pill key={s} tone="neutral">{s}</Pill>)}
            </div>
          </Surface>
          <Surface>
            <SectionTitle eyebrow="Interests" title="Outside of work" />
            <div className="mt-3 flex flex-wrap gap-1.5">
              {(p.interests ?? []).length === 0 ? <span className="text-sm text-muted">—</span>
                : p.interests.map((s) => <Pill key={s} tone="neutral">{s}</Pill>)}
            </div>
          </Surface>
          <Surface>
            <SectionTitle eyebrow="Languages" title="Speaks" />
            <div className="mt-3 flex flex-wrap gap-1.5">
              {(p.languages ?? []).length === 0 ? <span className="text-sm text-muted">—</span>
                : p.languages.map((s) => <Pill key={s} tone="neutral">{s}</Pill>)}
            </div>
          </Surface>
          <Surface>
            <SectionTitle eyebrow="Working with me" title="How collaboration feels" />
            <p className="mt-3 text-sm text-body leading-relaxed">{p.favourite_collab || "—"}</p>
            {p.asks && (
              <>
                <Divider className="my-3" />
                <div className="fp-eyebrow mb-1 flex items-center gap-1.5"><IconSparkle size={12} /> Ask me about</div>
                <p className="text-sm text-body">{p.asks}</p>
              </>
            )}
          </Surface>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- RECORDS
function RecordsTab({ id, emp, employees }: { id: string; emp: Employee; employees: Employee[] }) {
  const qc = useQueryClient();

  const compQ = useQuery({ queryKey: ["comp-history", id], queryFn: () => apiFetch<CompRecord[]>(`/employee-records/${id}/comp-history`), enabled: !!id });
  const jobQ = useQuery({ queryKey: ["job-history", id], queryFn: () => apiFetch<JobRecord[]>(`/employee-records/${id}/job-history`), enabled: !!id });
  const contactsQ = useQuery({ queryKey: ["emergency-contacts", id], queryFn: () => apiFetch<Contact[]>(`/employee-records/${id}/emergency-contacts`), enabled: !!id });
  const docsQ = useQuery({ queryKey: ["documents"], queryFn: () => apiFetch<Doc[]>("/documents") });
  const myDocs = (docsQ.data ?? []).filter((d) => d.employee_id === id);

  const [compForm, setCompForm] = useState({ amount: "", basis: "salary", effective_date: "", reason: "merit" });
  const [compMsg, setCompMsg] = useState<string | null>(null);
  const addComp = useMutation({
    mutationFn: () => apiPost(`/employee-records/${id}/comp-history`, {
      amount: Number(compForm.amount), basis: compForm.basis, effective_date: compForm.effective_date, reason: compForm.reason,
    }),
    onSuccess: async () => { setCompMsg("Compensation record added."); setCompForm({ ...compForm, amount: "" }); await qc.invalidateQueries({ queryKey: ["comp-history", id] }); },
    onError: (e) => setCompMsg((e as Error).message),
  });

  const [jobForm, setJobForm] = useState({ job_title: "", department: "", manager_employee_id: "", effective_date: "", reason: "promotion" });
  const [jobMsg, setJobMsg] = useState<string | null>(null);
  const addJob = useMutation({
    mutationFn: () => apiPost(`/employee-records/${id}/job-change`, {
      job_title: jobForm.job_title.trim() || null, department: jobForm.department.trim() || null,
      manager_employee_id: jobForm.manager_employee_id || null, effective_date: jobForm.effective_date, reason: jobForm.reason,
    }),
    onSuccess: async () => {
      setJobMsg("Job change recorded and applied.");
      setJobForm({ ...jobForm, job_title: "", department: "", manager_employee_id: "" });
      await qc.invalidateQueries({ queryKey: ["job-history", id] });
      await qc.invalidateQueries({ queryKey: ["employees"] });
    },
    onError: (e) => setJobMsg((e as Error).message),
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      {/* Comp history */}
      <Surface>
        <SectionTitle eyebrow="Effective-dated" title="Compensation history" description="One open record at a time; new records close the previous one." />
        <div className="mt-3">
          {compQ.isLoading ? <div className="text-sm text-muted">Loading…</div>
            : (compQ.data ?? []).length === 0 ? <div className="text-sm text-muted">No compensation records yet.</div>
            : (
              <ul className="divide-y divide-rule">
                {(compQ.data ?? []).map((c) => (
                  <li key={c.id} className="py-2.5 flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-ink tabular-nums">{money(c.amount, c.currency)} {c.basis === "hourly" ? "/hr" : "/yr"}</div>
                      <div className="text-xs text-muted">{c.effective_date} → {c.end_date ?? "present"}{c.reason ? ` · ${c.reason}` : ""}{c.review_id ? " · from review" : ""}</div>
                    </div>
                    {c.end_date === null && <Pill tone="success">current</Pill>}
                  </li>
                ))}
              </ul>
            )}
        </div>
        <div className="mt-4 border-t border-line pt-3 space-y-2">
          <div className="fp-eyebrow">Add record (HR)</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <input className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" placeholder="Amount" value={compForm.amount} onChange={(e) => setCompForm({ ...compForm, amount: e.target.value })} />
            <select className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" value={compForm.basis} onChange={(e) => setCompForm({ ...compForm, basis: e.target.value })}>
              <option value="salary">Salary /yr</option>
              <option value="hourly">Hourly</option>
            </select>
            <input type="date" className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" value={compForm.effective_date} onChange={(e) => setCompForm({ ...compForm, effective_date: e.target.value })} />
            <select className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" value={compForm.reason} onChange={(e) => setCompForm({ ...compForm, reason: e.target.value })}>
              <option value="hire">Hire</option><option value="merit">Merit</option><option value="promotion">Promotion</option><option value="market">Market</option><option value="review">Review outcome</option>
            </select>
          </div>
          <button className="h-9 px-4 rounded-md bg-accent text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm text-sm disabled:opacity-40" disabled={addComp.isPending || !Number(compForm.amount) || !compForm.effective_date} onClick={() => addComp.mutate()}>
            {addComp.isPending ? "Saving…" : "Add comp record"}
          </button>
          {compMsg && <div className="text-xs text-muted">{compMsg}</div>}
        </div>
      </Surface>

      {/* Job history */}
      <Surface>
        <SectionTitle eyebrow="Effective-dated" title="Job history" description="Title, department and manager changes — recorded and applied together." />
        <div className="mt-3">
          {jobQ.isLoading ? <div className="text-sm text-muted">Loading…</div>
            : (jobQ.data ?? []).length === 0 ? <div className="text-sm text-muted">No job history yet.</div>
            : (
              <ul className="divide-y divide-rule">
                {(jobQ.data ?? []).map((j) => (
                  <li key={j.id} className="py-2.5 flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-ink">{j.job_title ?? "—"} · {j.department ?? "—"}</div>
                      <div className="text-xs text-muted">{j.effective_date} → {j.end_date ?? "present"}{j.reason ? ` · ${j.reason}` : ""}</div>
                    </div>
                    {j.end_date === null && <Pill tone="success">current</Pill>}
                  </li>
                ))}
              </ul>
            )}
        </div>
        <div className="mt-4 border-t border-line pt-3 space-y-2">
          <div className="fp-eyebrow">Record job change (HR)</div>
          <div className="grid grid-cols-2 gap-2">
            <input className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" placeholder={`Title (now: ${emp.job_title ?? "—"})`} value={jobForm.job_title} onChange={(e) => setJobForm({ ...jobForm, job_title: e.target.value })} />
            <input className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" placeholder={`Department (now: ${emp.department ?? "—"})`} value={jobForm.department} onChange={(e) => setJobForm({ ...jobForm, department: e.target.value })} />
            <select className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" value={jobForm.manager_employee_id} onChange={(e) => setJobForm({ ...jobForm, manager_employee_id: e.target.value })}>
              <option value="">Manager unchanged</option>
              {employees.filter((e) => e.id !== emp.id).map((e) => <option key={e.id} value={e.id}>{e.legal_name}</option>)}
            </select>
            <input type="date" className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" value={jobForm.effective_date} onChange={(e) => setJobForm({ ...jobForm, effective_date: e.target.value })} />
            <select className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" value={jobForm.reason} onChange={(e) => setJobForm({ ...jobForm, reason: e.target.value })}>
              <option value="hire">Hire</option><option value="promotion">Promotion</option><option value="transfer">Transfer</option><option value="reorg">Reorg</option>
            </select>
          </div>
          <button className="h-9 px-4 rounded-md bg-accent text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm text-sm disabled:opacity-40"
            disabled={addJob.isPending || !jobForm.effective_date || (!jobForm.job_title.trim() && !jobForm.department.trim() && !jobForm.manager_employee_id)}
            onClick={() => addJob.mutate()}>
            {addJob.isPending ? "Saving…" : "Record change"}
          </button>
          {jobMsg && <div className="text-xs text-muted">{jobMsg}</div>}
        </div>
      </Surface>

      {/* Emergency contacts */}
      <Surface>
        <SectionTitle eyebrow="Safety" title="Emergency contacts" />
        <div className="mt-3">
          {(contactsQ.data ?? []).length === 0 ? <div className="text-sm text-muted">None on file. Employees can add their own from the portal.</div>
            : (
              <ul className="divide-y divide-rule">
                {(contactsQ.data ?? []).map((c) => (
                  <li key={c.id} className="py-2.5 flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-ink">{c.full_name}</div>
                      <div className="text-xs text-muted">{c.relationship ?? "—"} · {c.phone}{c.email ? ` · ${c.email}` : ""}</div>
                    </div>
                    {c.is_primary && <Pill tone="info">primary</Pill>}
                  </li>
                ))}
              </ul>
            )}
        </div>
      </Surface>

      {/* Documents */}
      <Surface>
        <SectionTitle eyebrow="Records" title="Documents" trailing={<Link href="/app/documents" className="text-xs underline text-muted hover:text-ink">All documents →</Link>} />
        <div className="mt-3">
          {myDocs.length === 0 ? <div className="text-sm text-muted">No documents linked to this employee yet.</div>
            : (
              <ul className="divide-y divide-rule">
                {myDocs.map((d) => (
                  <li key={d.id} className="py-2.5 flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-ink truncate">{d.storage_path.split("/").pop()}</div>
                      <div className="text-xs text-muted">{d.category} · {new Date(d.created_at).toLocaleDateString()}</div>
                    </div>
                    <Pill tone={d.status === "verified" ? "success" : "neutral"}>{d.status}</Pill>
                  </li>
                ))}
              </ul>
            )}
        </div>
      </Surface>
    </div>
  );
}

// ---------------------------------------------------------------- PERFORMANCE
function PerformanceTab({ id, name }: { id: string; name: string }) {
  const reviewsQ = useQuery({
    queryKey: ["reviews"],
    queryFn: () => apiFetch<{ reviews: Review[] }>("/reviews"),
    retry: false,
  });
  const mine = (reviewsQ.data?.reviews ?? []).filter((r) => r.employee_id === id);

  function statusTone(s: string): "success" | "info" | "warn" | "neutral" {
    if (s === "finalized") return "success";
    if (s === "calibration" || s === "decision") return "info";
    if (s.includes("manager") || s === "self_submitted") return "warn";
    return "neutral";
  }

  return (
    <div className="space-y-5">
      <Surface pad="none">
        <div className="border-b border-line px-5 py-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-md font-semibold text-ink">Review history</div>
            <div className="text-xs text-muted mt-0.5">{name}'s performance reviews</div>
          </div>
          <LinkAction href="/app/calibration" variant="subtle" size="sm">Open 9-box calibration →</LinkAction>
        </div>
        <div className="divide-y divide-rule">
          {reviewsQ.isLoading ? <div className="p-5 text-sm text-muted">Loading reviews…</div>
            : reviewsQ.error ? <div className="p-5 text-sm text-muted">Review history is not available for your role.</div>
            : mine.length === 0 ? (
              <div className="p-5"><EmptyState title="No reviews yet" description="Reviews appear here once a cycle is opened for this employee." /></div>
            ) : (
              mine.map((r) => (
                <div key={r.id} className="flex items-center justify-between px-5 py-3">
                  <div>
                    <div className="text-sm font-medium text-ink">Cycle: {r.cycle}</div>
                    <div className="text-xs text-muted">
                      {r.ai_decision ? `AI decision: ${r.ai_decision}` : "In progress"}
                      {r.finalized_at ? ` · finalized ${new Date(r.finalized_at).toLocaleDateString()}` : ""}
                    </div>
                  </div>
                  <Pill tone={statusTone(r.status)}>{r.status.replace(/_/g, " ")}</Pill>
                </div>
              ))
            )}
        </div>
      </Surface>
      <div className="flex flex-wrap gap-2">
        <LinkAction href="/app/performance" variant="subtle" size="sm">Performance cycles</LinkAction>
        <LinkAction href="/app/goals" variant="subtle" size="sm">Goals & OKRs</LinkAction>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- TWIN
function TwinTab({ id }: { id: string }) {
  const twinQ = useQuery({ queryKey: ["twin", id], queryFn: () => apiFetch<Twin>(`/digital-twin/${id}`), retry: false });
  const t = twinQ.data;

  if (twinQ.isLoading) return <Surface><EmptyState title="Loading digital twin…" /></Surface>;
  if (!t) return <Surface><EmptyState title="No digital twin yet" description="The twin builds from skills, performance and marketplace signals." /></Surface>;

  return (
    <div className="space-y-5">
      <Surface>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="fp-eyebrow">Digital twin</div>
            <div className="text-sm text-muted">{t.job_title ?? "—"} · {t.department ?? "—"} · {t.tenure_years}y tenure</div>
          </div>
          <div className="flex items-center gap-2">
            <Pill tone={BAND_TONE[t.attrition?.band] ?? "neutral"}>Attrition · {t.attrition?.risk_score ?? "—"} · {t.attrition?.band ?? "—"}</Pill>
            <Pill tone="neutral">Perf {(t.performance_rating ?? 0).toFixed(1)} / 5</Pill>
          </div>
        </div>
        {(t.growth_signals ?? []).length > 0 && (
          <>
            <Divider className="my-4" />
            <div className="fp-eyebrow mb-1">Growth signals</div>
            <ul className="text-sm text-body space-y-1">{(t.growth_signals ?? []).map((g, i) => <li key={i}>• {g}</li>)}</ul>
          </>
        )}
      </Surface>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Surface>
          <SectionTitle eyebrow="Skills" title="Captured competencies" />
          <div className="mt-3">
            {(t.skills ?? []).length === 0 ? <EmptyState title="No skills captured" description="Invite to self-document." />
              : <div className="flex flex-wrap gap-1.5">{(t.skills ?? []).map((s) => <Pill key={s} tone="neutral">{s}</Pill>)}</div>}
          </div>
        </Surface>

        <Surface>
          <SectionTitle eyebrow="Risk" title="Attrition drivers" />
          <div className="mt-3 space-y-2">
            {(t.attrition?.drivers ?? []).length === 0 ? <div className="text-sm text-muted">No specific drivers flagged.</div>
              : <ul className="text-sm text-body space-y-1">{(t.attrition?.drivers ?? []).map((d, i) => <li key={i}>• {d}</li>)}</ul>}
            {(t.attrition?.suggested_actions ?? []).length > 0 && (
              <>
                <Divider className="my-3" />
                <div className="fp-eyebrow mb-1">Suggested actions</div>
                <ul className="text-sm text-muted space-y-1">{(t.attrition?.suggested_actions ?? []).map((a, i) => <li key={i}>→ {a}</li>)}</ul>
              </>
            )}
          </div>
        </Surface>

        <Surface className="lg:col-span-2">
          <SectionTitle eyebrow="Marketplace" title="Internal roles that fit" trailing={<Link href="/app/marketplace" className="text-xs underline text-muted hover:text-ink">Open marketplace →</Link>} />
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {(t.marketplace_matches ?? []).length === 0 ? <div className="md:col-span-2 lg:col-span-3"><EmptyState title="No internal fits yet" /></div>
              : (t.marketplace_matches ?? []).map((m, i) => (
                <div key={i} className="rounded-lg border border-line bg-canvas p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-semibold text-ink">{m.role?.title}</div>
                    <span className="text-sm tabular-nums">{m.score}</span>
                  </div>
                  <div className="text-2xs uppercase tracking-eyebrow text-muted">{m.role?.department}</div>
                  <div className="mt-2 flex flex-wrap gap-1">{m.matched_skills.slice(0, 5).map((s) => <Pill key={s} tone="success">{s}</Pill>)}</div>
                  {m.missing_skills.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{m.missing_skills.slice(0, 5).map((s) => <Pill key={s} tone="danger">{s}</Pill>)}</div>}
                  <div className="mt-2 text-xs text-muted">{m.learning_hint}</div>
                </div>
              ))}
          </div>
        </Surface>

        <Surface className="lg:col-span-2">
          <SectionTitle eyebrow="Next role" title={`Skill gap → ${t.skill_gap_to_next?.target_role || "—"}`} />
          <div className="mt-3">
            <div className="flex items-center justify-between text-xs text-muted">
              <span>Coverage</span><span className="tabular-nums">{t.skill_gap_to_next?.coverage_percent ?? 0}%</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-sunken overflow-hidden">
              <div className="h-full bg-accent" style={{ width: `${t.skill_gap_to_next?.coverage_percent ?? 0}%` }} />
            </div>
            <div className="mt-3 flex flex-wrap gap-1">
              {(t.skill_gap_to_next?.gap || []).length === 0 ? <span className="text-sm text-success-fg">Meets the next-role skill profile.</span>
                : (t.skill_gap_to_next?.gap || []).map((g) => <Pill key={g} tone="danger">{g}</Pill>)}
            </div>
          </div>
        </Surface>
      </div>
    </div>
  );
}
