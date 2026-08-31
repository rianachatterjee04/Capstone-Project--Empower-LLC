"use client";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPatch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Divider } from "@/components/ds";
import { WorkflowTimeline, stepFromSubtasks, type WorkflowStep, type WorkflowSubtask, type StepStatus } from "@/components/WorkflowTimeline";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";

type Packet = {
  id: string;
  employee_id: string;
  status: string;
  requested_items: Record<string, boolean>;
  submitted_items: Record<string, any>;
  created_at: string;
};
type PacketRequest = {
  id: string;
  status: string;
  created_at: string;
  message?: string | null;
  requester_email?: string | null;
};

type ChecklistTaskT = {
  id: string;
  title: string;
  category: string;
  assignee_role: string;
  due_date: string | null;
  link: string | null;
  status: "open" | "done" | "skipped";
};

type ChecklistT = {
  id: string;
  kind: string;
  name: string;
  status: string;
  progress: { done: number; total: number };
  tasks: ChecklistTaskT[];
};

const STEPS = [
  { key: "i9", title: "I-9 verification", fields: ["citizenship_status", "documents"] as string[] },
  { key: "w4", title: "W-4 withholding", fields: ["filing_status", "dependents", "additional_withholding"] as string[] },
  { key: "ssn", title: "Social Security", fields: ["ssn_last4"] as string[] },
  { key: "direct_deposit", title: "Direct deposit", fields: ["bank_name", "routing_number", "account_number"] as string[] },
];

const FIELD_LABEL: Record<string, string> = {
  ssn_last4: "SSN (last 4)",
  bank_name: "Bank name",
  routing_number: "Routing number",
  account_number: "Account number",
  filing_status: "Filing status",
  dependents: "Dependents",
  additional_withholding: "Additional withholding",
  citizenship_status: "Work authorization status",
  documents: "I-9 documents",
};

function packetJourney(packet: Packet, activeKey: string): WorkflowStep[] {
  const submitted = packet.submitted_items ?? {};
  const myStepsCompleted = STEPS.filter((s) => packet.requested_items?.[s.key] !== false).map<WorkflowSubtask>((s) => ({
    label: s.title,
    status: submitted[s.key] ? "done" : s.key === activeKey ? "in_progress" : "pending",
  }));

  const hrStatus: StepStatus =
    packet.status === "verified" || packet.status === "activated" ? "done"
    : packet.status === "completed" ? "in_progress"
    : "pending";
  const activateStatus: StepStatus =
    packet.status === "activated" ? "done"
    : packet.status === "verified" ? "in_progress"
    : "pending";

  return [
    stepFromSubtasks(
      { id: "my-tasks", title: "Your tasks", owner: "You", description: "Submit the required information." },
      myStepsCompleted,
    ),
    { id: "hr-verify", title: "HR verification", owner: "HR", description: "HR confirms your information.", status: hrStatus },
    { id: "activate", title: "Account activated", owner: "HR + Payroll", description: "Your account is activated and payroll begins.", status: activateStatus },
  ];
}

export default function OnboardingPage() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["packets"],
    queryFn: () => apiFetch<Packet[]>("/onboarding/packets"),
  });

  const { data: myRequest, isLoading: reqLoading } = useQuery({
    queryKey: ["onboarding-packet-request-me"],
    queryFn: () => apiFetch<PacketRequest | null>("/onboarding/packet-requests/me"),
    enabled: !isLoading && (data ?? []).length === 0,
  });

  const packet = useMemo(() => (data ?? [])[0] ?? null, [data]);
  const requested = packet?.requested_items ?? {};
  const availableSteps = STEPS.filter((s) => requested[s.key] !== false);

  const [stepIdx, setStepIdx] = useState(0);
  const step = availableSteps[stepIdx];
  const [form, setForm] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [requestNote, setRequestNote] = useState("");
  const [requestBusy, setRequestBusy] = useState(false);
  const [requestErr, setRequestErr] = useState<string | null>(null);

  const isLastStep = stepIdx === availableSteps.length - 1;

  async function saveStep() {
    if (!packet) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const submitted_items = { ...(packet.submitted_items ?? {}), [step.key]: { ...form, saved_at: new Date().toISOString() } };
      await apiPatch<Packet>(`/onboarding/packets/${packet.id}`, { submitted_items });
      await qc.invalidateQueries({ queryKey: ["packets"] });
      setSaveMsg("Saved.");
    } catch (e) {
      setSaveMsg("Error saving: " + (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function saveAndNext() {
    await saveStep();
    setStepIdx((i) => Math.min(i + 1, availableSteps.length - 1));
    setForm({});
    setSaveMsg(null);
  }

  async function finish() {
    if (!packet) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const submitted_items = { ...(packet.submitted_items ?? {}), [step.key]: { ...form, saved_at: new Date().toISOString() } };
      await apiPatch<Packet>(`/onboarding/packets/${packet.id}`, { submitted_items });
      await apiPatch<Packet>(`/onboarding/packets/${packet.id}`, { status: "completed" });
      await qc.invalidateQueries({ queryKey: ["packets"] });
    } catch (e) {
      setSaveMsg("Error: " + (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function sendHrRequest() {
    setRequestBusy(true);
    setRequestErr(null);
    try {
      await apiPost<PacketRequest>("/onboarding/packet-requests", { message: requestNote.trim() || undefined });
      await qc.invalidateQueries({ queryKey: ["onboarding-packet-request-me"] });
      setRequestNote("");
    } catch (e) {
      setRequestErr((e as Error).message);
    } finally {
      setRequestBusy(false);
    }
  }

  if (isLoading) return <div className="p-8 text-sm text-muted">Loading…</div>;
  if (error) return <div className="p-8 text-sm text-danger-fg">Failed: {(error as Error).message}</div>;

  // No packet yet — request flow
  if (!packet) {
    const sent = myRequest?.status === "pending";
    return (
      <div className="space-y-6 fp-fade-in">
        <PageHeader eyebrow="Workflow" title="Onboarding" subtitle="No packet on file yet. Let HR know to create one." />
        <Surface>
          <SectionTitle eyebrow="Request" title="Notify HR" description="Adds your name to the HR inbox so they can set up your packet." />
          <div className="mt-3 space-y-3">
            {reqLoading ? (
              <div className="text-sm text-muted">Checking request status…</div>
            ) : sent ? (
              <div className="rounded-md border border-success-line bg-success-bg text-success-fg px-4 py-3 text-sm">
                <div className="font-semibold">Request sent</div>
                <div className="text-xs mt-1 opacity-80">
                  Submitted {new Date(myRequest!.created_at).toLocaleString()}
                  {myRequest?.message ? ` · Note: ${myRequest.message}` : ""}
                </div>
              </div>
            ) : (
              <>
                <Textarea
                  label="Optional message to HR"
                  hint="e.g. start date, role, or anything that helps them match your record."
                  rows={3}
                  value={requestNote}
                  onChange={(e) => setRequestNote(e.target.value)}
                  placeholder="Optional"
                />
                {requestErr && <div className="text-sm text-danger-fg">{requestErr}</div>}
                <Action onClick={sendHrRequest} variant="primary" disabled={requestBusy}>
                  {requestBusy ? "Sending…" : "Request packet from HR"}
                </Action>
              </>
            )}
          </div>
        </Surface>
        <MyChecklistSection />
      </div>
    );
  }

  // Completed / verified / activated — calm done state with timeline
  if (["completed", "verified", "activated"].includes(packet.status)) {
    return (
      <div className="space-y-6 fp-fade-in">
        <PageHeader
          eyebrow="Workflow"
          title="Onboarding"
          subtitle={
            packet.status === "activated"
              ? "All set. Welcome to the team."
              : packet.status === "verified"
              ? "Verified. Activation coming up."
              : "Submitted. HR will review next."
          }
        />
        <Surface>
          <SectionTitle eyebrow="Journey" title="Where you are" />
          <div className="mt-4">
            <WorkflowTimeline steps={packetJourney(packet, "")} />
          </div>
        </Surface>
        <MyChecklistSection />
      </div>
    );
  }

  return (
    <div className="space-y-6 fp-fade-in">
      <PageHeader
        eyebrow="Workflow"
        title="Onboarding"
        subtitle="Submit the required information so HR can verify and activate your account."
        actions={<Pill tone="info">{packet.status.replace("_", " ")}</Pill>}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Journey */}
        <Surface className="lg:col-span-1">
          <SectionTitle eyebrow="Journey" title="Where you are" />
          <div className="mt-4">
            <WorkflowTimeline steps={packetJourney(packet, step?.key ?? "")} />
          </div>
        </Surface>

        {/* Step form */}
        <Surface className="lg:col-span-2">
          <SectionTitle
            eyebrow={`Step ${stepIdx + 1} of ${availableSteps.length}`}
            title={step.title}
            trailing={
              <div className="flex flex-wrap gap-1.5">
                {availableSteps.map((s, i) => {
                  const done = !!(packet.submitted_items ?? {})[s.key];
                  return (
                    <button
                      key={s.key}
                      onClick={() => { setStepIdx(i); setForm({}); setSaveMsg(null); }}
                      className={`text-2xs uppercase tracking-eyebrow px-2 py-1 rounded-md border transition-colors duration-150 ease-calm ${
                        i === stepIdx
                          ? "bg-accent text-accent-fg border-accent"
                          : done
                          ? "bg-success-bg text-success-fg border-success-line"
                          : "bg-canvas text-muted border-line hover:bg-sunken"
                      }`}
                      title={s.title}
                    >
                      {i + 1}
                    </button>
                  );
                })}
              </div>
            }
          />

          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
            {step.fields.map((f) => {
              if (f === "documents") return null;
              const type = f === "ssn_last4" || f === "dependents" || f === "additional_withholding" || f === "routing_number" || f === "account_number" ? "text" : "text";
              return (
                <Input
                  key={f}
                  label={FIELD_LABEL[f] ?? f}
                  type={type}
                  value={form[f] ?? ""}
                  onChange={(e) => setForm({ ...form, [f]: e.target.value })}
                />
              );
            })}
          </div>

          {step.fields.includes("documents") && (
            <div className="mt-3">
              <Textarea
                label="I-9 documents"
                hint="Next: upload images directly. For now, list what you'll provide."
                rows={3}
                value={form.documents ?? ""}
                onChange={(e) => setForm({ ...form, documents: e.target.value })}
                placeholder="e.g. Passport, Driver's license + SS card"
              />
            </div>
          )}

          {saveMsg && (
            <div className={`mt-3 text-sm ${saveMsg.startsWith("Error") ? "text-danger-fg" : "text-success-fg"}`}>
              {saveMsg}
            </div>
          )}

          <Divider className="my-4" />

          <div className="flex items-center justify-between">
            <Action variant="subtle" onClick={() => { setStepIdx(Math.max(0, stepIdx - 1)); setForm({}); setSaveMsg(null); }} disabled={stepIdx === 0}>
              Back
            </Action>
            <div className="flex gap-2">
              <Action variant="subtle" onClick={saveStep} disabled={saving}>{saving ? "Saving…" : "Save"}</Action>
              {isLastStep ? (
                <Action variant="primary" onClick={finish} disabled={saving}>{saving ? "Submitting…" : "Finish & submit"}</Action>
              ) : (
                <Action variant="primary" onClick={saveAndNext} disabled={saving}>Save & next</Action>
              )}
            </div>
          </div>
        </Surface>
      </div>

      <MyChecklistSection />
    </div>
  );
}

/** Tasks assigned to me from my onboarding/offboarding checklists
 * (equipment, intros, handbook…). Complements the document packet above. */
function MyChecklistSection() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["my-checklists"],
    queryFn: () => apiFetch<ChecklistT[]>("/checklists/me"),
  });
  const toggle = async (t: ChecklistTaskT) => {
    await apiPost(`/checklists/tasks/${t.id}/${t.status === "done" ? "reopen" : "complete"}`, {});
    await qc.invalidateQueries({ queryKey: ["my-checklists"] });
  };
  const lists = q.data ?? [];
  if (q.isLoading || lists.length === 0) return null;

  return (
    <>
      {lists.map((cl) => (
        <Surface key={cl.id}>
          <SectionTitle
            eyebrow={cl.kind === "offboarding" ? "Offboarding" : "Checklist"}
            title={cl.name}
            description={`${cl.progress.done}/${cl.progress.total} tasks done`}
            trailing={<Pill tone={cl.status === "completed" ? "success" : "info"}>{cl.status}</Pill>}
          />
          <ul className="mt-3 divide-y divide-rule">
            {cl.tasks.map((t) => {
              const mine = t.assignee_role === "employee";
              return (
                <li key={t.id} className="py-2.5 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className={`text-sm ${t.status === "done" ? "line-through text-muted" : "text-ink"}`}>
                      {t.title}
                    </div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">
                      {t.assignee_role}
                      {t.due_date ? ` · due ${t.due_date}` : ""}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {t.link && (
                      <a href={t.link} className="text-xs underline text-muted hover:text-ink">Open</a>
                    )}
                    {mine ? (
                      <Action variant={t.status === "done" ? "subtle" : "primary"} onClick={() => toggle(t)}>
                        {t.status === "done" ? "Undo" : "Mark done"}
                      </Action>
                    ) : (
                      <Pill tone={t.status === "done" ? "success" : "neutral"}>{t.status}</Pill>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </Surface>
      ))}
    </>
  );
}
