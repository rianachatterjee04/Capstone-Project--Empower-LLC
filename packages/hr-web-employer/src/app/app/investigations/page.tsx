"use client";

/**
 * Investigations console — the first UI over the workplace-investigations
 * backend (app/api/routers/investigations.py, prefix /investigations).
 *
 * The backend is intentionally write-only (report → witness → evidence →
 * findings → action → close) with no list endpoint, so this console is an
 * intake + case-management surface: open a case, then run the case through its
 * lifecycle. Cases opened in this session are tracked client-side so an
 * investigator can keep working them; an existing case id can also be pasted
 * in to resume. Every action calls a real endpoint.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import {
  PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Divider, KeyValue,
} from "@/components/ds";

type Employee = { id: string; legal_name: string; preferred_name?: string | null; department?: string | null };

type LogEntry = { at: string; label: string; detail?: string };
type Case = {
  id: string;
  category: string;
  status: string;
  opened_at: string;
  accused_name?: string | null;
  log: LogEntry[];
};

const CATEGORIES = [
  "Harassment",
  "Discrimination",
  "Retaliation",
  "Safety",
  "Policy violation",
  "Financial / fraud",
  "Other",
];

const STATUS_TONE: Record<string, "neutral" | "warn" | "success" | "danger"> = {
  open: "warn",
  decision_pending: "warn",
  closed: "success",
};

function now() {
  return new Date().toISOString();
}

export default function InvestigationsPage() {
  const empQ = useQuery({ queryKey: ["employees"], queryFn: () => apiFetch<Employee[]>("/employees") });
  const employees = empQ.data ?? [];
  const nameOf = (id?: string | null) =>
    id ? (employees.find((e) => e.id === id)?.preferred_name || employees.find((e) => e.id === id)?.legal_name || id) : null;

  // Session-local case register. The backend has no list endpoint, so we hold
  // the cases opened / resumed this session here.
  const [cases, setCases] = useState<Case[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const active = cases.find((c) => c.id === activeId) ?? null;

  function upsert(next: Case) {
    setCases((prev) => {
      const i = prev.findIndex((c) => c.id === next.id);
      if (i === -1) return [next, ...prev];
      const copy = [...prev];
      copy[i] = next;
      return copy;
    });
  }
  function appendLog(caseId: string, entry: LogEntry, patch?: Partial<Case>) {
    setCases((prev) =>
      prev.map((c) => (c.id === caseId ? { ...c, ...patch, log: [entry, ...c.log] } : c)),
    );
  }

  // ---- open a case ---------------------------------------------------------
  const [form, setForm] = useState({ category: CATEGORIES[0], accused: "", description: "" });
  const [openMsg, setOpenMsg] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);

  async function openCase() {
    if (!form.description.trim()) return;
    setOpening(true);
    setOpenMsg(null);
    try {
      const res = await apiPost<{ case_id: string }>("/investigations/report", {
        category: form.category,
        accused_employee_id: form.accused || null,
        description: form.description.trim(),
      });
      const c: Case = {
        id: res.case_id,
        category: form.category,
        status: "open",
        opened_at: now(),
        accused_name: nameOf(form.accused),
        log: [{ at: now(), label: "Case opened", detail: form.category }],
      };
      upsert(c);
      setActiveId(c.id);
      setForm({ category: CATEGORIES[0], accused: "", description: "" });
      setOpenMsg(`Case opened · ${c.id}`);
    } catch (e) {
      setOpenMsg((e as Error).message);
    } finally {
      setOpening(false);
    }
  }

  // ---- resume an existing case --------------------------------------------
  const [resumeId, setResumeId] = useState("");
  function resume() {
    const id = resumeId.trim();
    if (!id) return;
    if (!cases.find((c) => c.id === id)) {
      upsert({ id, category: "—", status: "open", opened_at: now(), log: [{ at: now(), label: "Case resumed", detail: id }] });
    }
    setActiveId(id);
    setResumeId("");
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Compliance"
        title="Investigations"
        subtitle="Open and run workplace investigations — witnesses, evidence, findings, disciplinary action and closure. Every step is written to the audited investigations record."
      />

      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-5">
        {/* Left rail: open + register */}
        <div className="space-y-5">
          <Surface>
            <SectionTitle eyebrow="Intake" title="Open an investigation" />
            <div className="mt-3 space-y-3">
              <label className="block">
                <div className="mb-1 text-xs text-muted">Category</div>
                <select
                  className="h-9 w-full rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                >
                  {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-muted">Subject (optional)</div>
                <select
                  className="h-9 w-full rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
                  value={form.accused}
                  onChange={(e) => setForm({ ...form, accused: e.target.value })}
                >
                  <option value="">Not specified</option>
                  {employees.map((e) => (
                    <option key={e.id} value={e.id}>{e.preferred_name || e.legal_name}{e.department ? ` · ${e.department}` : ""}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-muted">What happened?</div>
                <textarea
                  className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:bg-surface"
                  rows={4}
                  placeholder="Summarise the allegation. Keep it factual."
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                />
              </label>
              <Action variant="primary" onClick={openCase} disabled={opening || !form.description.trim()}>
                {opening ? "Opening…" : "Open case"}
              </Action>
              {openMsg && <div className="text-xs text-muted break-all">{openMsg}</div>}
            </div>
          </Surface>

          <Surface>
            <SectionTitle eyebrow="Register" title="Cases this session" />
            <div className="mt-3 space-y-1.5">
              {cases.length === 0 ? (
                <div className="text-sm text-muted">No cases yet. Open one above, or resume by id.</div>
              ) : (
                cases.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setActiveId(c.id)}
                    className={`w-full text-left rounded-md px-3 py-2 border text-sm ${
                      activeId === c.id ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium truncate">{c.category}</span>
                      <Pill tone={activeId === c.id ? "neutral" : (STATUS_TONE[c.status] ?? "neutral")}>{c.status.replace(/_/g, " ")}</Pill>
                    </div>
                    <div className="text-2xs uppercase tracking-eyebrow opacity-80 truncate mt-0.5">{c.id}</div>
                  </button>
                ))
              )}
            </div>
            <Divider className="my-3" />
            <div className="flex items-center gap-2">
              <input
                value={resumeId}
                onChange={(e) => setResumeId(e.target.value)}
                placeholder="Resume by case id…"
                className="flex-1 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
              />
              <Action onClick={resume} disabled={!resumeId.trim()}>Resume</Action>
            </div>
          </Surface>
        </div>

        {/* Right: case management */}
        <div>
          {!active ? (
            <Surface><EmptyState title="No case selected" description="Open a new case or select one from the register to manage witnesses, evidence, findings and closure." /></Surface>
          ) : (
            <CaseWorkspace
              key={active.id}
              c={active}
              employees={employees}
              onLog={appendLog}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function CaseWorkspace({
  c,
  employees,
  onLog,
}: {
  c: Case;
  employees: Employee[];
  onLog: (caseId: string, entry: LogEntry, patch?: Partial<Case>) => void;
}) {
  return (
    <div className="space-y-5">
      <Surface>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <div className="fp-eyebrow">Active case</div>
            <div className="text-lg font-semibold text-ink">{c.category}</div>
            <div className="text-2xs uppercase tracking-eyebrow text-muted break-all mt-0.5">{c.id}</div>
          </div>
          <Pill tone={STATUS_TONE[c.status] ?? "neutral"}>{c.status.replace(/_/g, " ")}</Pill>
        </div>
        <Divider className="my-3" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
          <KeyValue label="Subject" value={c.accused_name ?? "Not specified"} />
          <KeyValue label="Opened" value={new Date(c.opened_at).toLocaleString()} />
        </div>
      </Surface>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <WitnessPanel c={c} employees={employees} onLog={onLog} />
        <EvidencePanel c={c} onLog={onLog} />
        <FindingsPanel c={c} onLog={onLog} />
        <ActionPanel c={c} onLog={onLog} />
      </div>

      <ClosePanel c={c} onLog={onLog} />

      <Surface>
        <SectionTitle eyebrow="Trail" title="Case activity (this session)" />
        <ul className="mt-3 space-y-2">
          {c.log.length === 0 ? (
            <li className="text-sm text-muted">No activity yet.</li>
          ) : (
            c.log.map((l, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className="text-2xs uppercase tracking-eyebrow text-muted shrink-0 w-16 text-right mt-0.5">
                  {new Date(l.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
                <span className="text-body"><span className="font-medium text-ink">{l.label}</span>{l.detail ? ` — ${l.detail}` : ""}</span>
              </li>
            ))
          )}
        </ul>
      </Surface>
    </div>
  );
}

function usePost(caseId: string, path: string) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  async function run(body: any): Promise<boolean> {
    setBusy(true);
    setMsg(null);
    try {
      await apiPost(`/investigations/${caseId}${path}`, body);
      return true;
    } catch (e) {
      setMsg((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { busy, msg, run };
}

function WitnessPanel({ c, employees, onLog }: { c: Case; employees: Employee[]; onLog: (id: string, e: LogEntry, p?: Partial<Case>) => void }) {
  const [emp, setEmp] = useState("");
  const [notes, setNotes] = useState("");
  const { busy, msg, run } = usePost(c.id, "/witness");
  return (
    <Surface>
      <SectionTitle eyebrow="Statements" title="Add witness" />
      <div className="mt-3 space-y-2">
        <select className="h-9 w-full rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" value={emp} onChange={(e) => setEmp(e.target.value)}>
          <option value="">Select witness…</option>
          {employees.map((e) => <option key={e.id} value={e.id}>{e.preferred_name || e.legal_name}</option>)}
        </select>
        <textarea className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:bg-surface" rows={2} placeholder="Statement notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        <Action
          onClick={async () => {
            if (await run({ employee_id: emp || null, notes })) {
              onLog(c.id, { at: now(), label: "Witness added", detail: employees.find((e) => e.id === emp)?.legal_name });
              setEmp(""); setNotes("");
            }
          }}
          disabled={busy || (!emp && !notes.trim())}
        >
          {busy ? "Saving…" : "Add witness"}
        </Action>
        {msg && <div className="text-xs text-danger-fg">{msg}</div>}
      </div>
    </Surface>
  );
}

function EvidencePanel({ c, onLog }: { c: Case; onLog: (id: string, e: LogEntry, p?: Partial<Case>) => void }) {
  const [url, setUrl] = useState("");
  const [desc, setDesc] = useState("");
  const { busy, msg, run } = usePost(c.id, "/evidence");
  return (
    <Surface>
      <SectionTitle eyebrow="Exhibits" title="Add evidence" />
      <div className="mt-3 space-y-2">
        <input className="h-9 w-full rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" placeholder="Evidence link / file URL" value={url} onChange={(e) => setUrl(e.target.value)} />
        <textarea className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:bg-surface" rows={2} placeholder="Description" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <Action
          onClick={async () => {
            if (await run({ file_url: url || null, description: desc })) {
              onLog(c.id, { at: now(), label: "Evidence added", detail: desc || url });
              setUrl(""); setDesc("");
            }
          }}
          disabled={busy || (!url.trim() && !desc.trim())}
        >
          {busy ? "Saving…" : "Add evidence"}
        </Action>
        {msg && <div className="text-xs text-danger-fg">{msg}</div>}
      </div>
    </Surface>
  );
}

function FindingsPanel({ c, onLog }: { c: Case; onLog: (id: string, e: LogEntry, p?: Partial<Case>) => void }) {
  const [findings, setFindings] = useState("");
  const [outcome, setOutcome] = useState("substantiated");
  const { busy, msg, run } = usePost(c.id, "/findings");
  return (
    <Surface>
      <SectionTitle eyebrow="Investigator" title="Record findings" description="Moves the case to decision-pending. Investigators only." />
      <div className="mt-3 space-y-2">
        <textarea className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:bg-surface" rows={3} placeholder="Findings summary" value={findings} onChange={(e) => setFindings(e.target.value)} />
        <select className="h-9 w-full rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          <option value="substantiated">Substantiated</option>
          <option value="partially_substantiated">Partially substantiated</option>
          <option value="unsubstantiated">Unsubstantiated</option>
          <option value="inconclusive">Inconclusive</option>
        </select>
        <Action
          variant="primary"
          onClick={async () => {
            if (await run({ findings, outcome })) {
              onLog(c.id, { at: now(), label: "Findings recorded", detail: outcome.replace(/_/g, " ") }, { status: "decision_pending" });
              setFindings("");
            }
          }}
          disabled={busy || !findings.trim()}
        >
          {busy ? "Saving…" : "Submit findings"}
        </Action>
        {msg && <div className="text-xs text-danger-fg">{msg}</div>}
      </div>
    </Surface>
  );
}

function ActionPanel({ c, onLog }: { c: Case; onLog: (id: string, e: LogEntry, p?: Partial<Case>) => void }) {
  const [type, setType] = useState("verbal_warning");
  const [notes, setNotes] = useState("");
  const { busy, msg, run } = usePost(c.id, "/action");
  return (
    <Surface>
      <SectionTitle eyebrow="Outcome" title="Disciplinary action" description="Restricted to HR / legal / owner." />
      <div className="mt-3 space-y-2">
        <select className="h-9 w-full rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="coaching">Coaching</option>
          <option value="verbal_warning">Verbal warning</option>
          <option value="written_warning">Written warning</option>
          <option value="final_warning">Final warning</option>
          <option value="suspension">Suspension</option>
          <option value="termination">Termination</option>
          <option value="no_action">No action</option>
        </select>
        <textarea className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:bg-surface" rows={2} placeholder="Action notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        <Action
          onClick={async () => {
            if (await run({ action_type: type, notes })) {
              onLog(c.id, { at: now(), label: "Action taken", detail: type.replace(/_/g, " ") });
              setNotes("");
            }
          }}
          disabled={busy}
        >
          {busy ? "Saving…" : "Record action"}
        </Action>
        {msg && <div className="text-xs text-danger-fg">{msg}</div>}
      </div>
    </Surface>
  );
}

function ClosePanel({ c, onLog }: { c: Case; onLog: (id: string, e: LogEntry, p?: Partial<Case>) => void }) {
  const [notes, setNotes] = useState("");
  const { busy, msg, run } = usePost(c.id, "/close");
  const closed = c.status === "closed";
  return (
    <Surface>
      <SectionTitle eyebrow="Resolution" title="Close case" description="Restricted to HR / legal / owner." trailing={closed ? <Pill tone="success">closed</Pill> : undefined} />
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-start">
        <textarea className="flex-1 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:bg-surface disabled:opacity-50" rows={2} placeholder="Closure notes" value={notes} onChange={(e) => setNotes(e.target.value)} disabled={closed} />
        <Action
          variant="primary"
          onClick={async () => {
            if (await run({ closure_notes: notes })) {
              onLog(c.id, { at: now(), label: "Case closed", detail: notes || undefined }, { status: "closed" });
              setNotes("");
            }
          }}
          disabled={busy || closed}
        >
          {busy ? "Closing…" : "Close case"}
        </Action>
      </div>
      {msg && <div className="mt-2 text-xs text-danger-fg">{msg}</div>}
    </Surface>
  );
}
