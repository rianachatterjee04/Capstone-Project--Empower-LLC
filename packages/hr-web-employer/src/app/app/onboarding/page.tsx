"use client";

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, StatusPill, Action, LinkAction, EmptyState, Divider } from "@/components/ds";
import { WorkflowTimeline, defaultOnboardingTemplate, stepFromSubtasks, type WorkflowStep, type StepStatus } from "@/components/WorkflowTimeline";
import { IconArrowUpRight } from "@/components/icons";

type Employee = {
  id: string;
  legal_name: string;
  email: string;
  job_title?: string | null;
  department?: string | null;
  status: string;
};

type OnboardingPacket = {
  id: string;
  employee_id: string;
  status: string;
  requested_items: Record<string, any>;
  submitted_items: Record<string, any>;
  created_at: string;
};

type OnboardingPacketRequest = {
  id: string;
  requested_by_user_id: string;
  employee_id?: string | null;
  requester_email?: string | null;
  message?: string | null;
  status: string;
  created_at: string;
};

const REQUESTED_ITEMS_DEFAULT = {
  i9: true,
  w4: true,
  ssn: true,
  direct_deposit: true,
};

const ITEM_LABEL: Record<string, string> = {
  i9: "I-9 employment eligibility",
  w4: "W-4 tax withholding",
  ssn: "SSN on file",
  direct_deposit: "Direct deposit",
  emergency_contact: "Emergency contact",
};

function packetTimeline(pkt: OnboardingPacket, employee?: Employee): WorkflowStep[] {
  const submitted = pkt.submitted_items ?? {};
  const requested = pkt.requested_items ?? {};
  const requestedKeys = Object.keys(requested);
  const documentTasks = requestedKeys.map((k) => ({
    id: `doc-${k}`,
    label: ITEM_LABEL[k] ?? k,
    status: (submitted[k] ? "done" : "pending") as StepStatus,
    owner: "New hire",
  }));

  const status = pkt.status;
  const verifyStatus: StepStatus =
    status === "verified" || status === "activated" ? "done"
    : status === "completed" ? "in_progress"
    : "pending";
  const activateStatus: StepStatus =
    status === "activated" ? "done"
    : status === "verified" ? "in_progress"
    : "pending";

  return [
    stepFromSubtasks(
      {
        id: "documents",
        title: "Required documents",
        owner: "New hire",
        description: "Forms the new hire must submit before Day 1.",
      },
      documentTasks,
    ),
    {
      id: "verify",
      title: "HR verification",
      owner: "HR",
      description: "Confirm submitted items meet I-9 + tax requirements.",
      status: verifyStatus,
    },
    {
      id: "activate",
      title: "Activate employee record",
      owner: "HR + Payroll",
      description: "Move from invited to active. Triggers first payroll cycle.",
      status: activateStatus,
    },
    ...defaultOnboardingTemplate(employee?.legal_name ?? "the new hire", employee?.job_title ?? "the role").slice(1),
  ];
}

export default function OnboardingPage() {
  const qc = useQueryClient();
  const [selectedEmployeeId, setSelectedEmployeeId] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const empQ = useQuery({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/employees"),
  });
  const packetsQ = useQuery({
    queryKey: ["onboarding-packets"],
    queryFn: () => apiFetch<OnboardingPacket[]>("/onboarding/packets"),
  });
  const packetRequestsQ = useQuery({
    queryKey: ["onboarding-packet-requests"],
    queryFn: () => apiFetch<OnboardingPacketRequest[]>("/onboarding/packet-requests"),
  });

  const createMutation = useMutation({
    mutationFn: (employeeId: string) =>
      apiPost<OnboardingPacket>("/onboarding/packets", {
        employee_id: employeeId,
        requested_items: REQUESTED_ITEMS_DEFAULT,
      }),
    onSuccess: (data) => {
      setSuccessMsg(`Onboarding packet created · ${data.id.slice(0, 8)}`);
      setErrorMsg(null);
      setSelectedEmployeeId("");
      qc.invalidateQueries({ queryKey: ["onboarding-packets"] });
      qc.invalidateQueries({ queryKey: ["onboarding-packet-requests"] });
    },
    onError: (e: Error) => { setErrorMsg(e.message); setSuccessMsg(null); },
  });

  const verifyMutation = useMutation({
    mutationFn: (packetId: string) => apiPost(`/onboarding/packets/${packetId}/verify`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding-packets"] }),
    onError: (e: Error) => setErrorMsg(e.message),
  });

  const activateMutation = useMutation({
    mutationFn: (packetId: string) => apiPost(`/onboarding/packets/${packetId}/activate`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["onboarding-packets"] });
      qc.invalidateQueries({ queryKey: ["employees"] });
    },
    onError: (e: Error) => setErrorMsg(e.message),
  });

  const employees = empQ.data ?? [];
  const packets = packetsQ.data ?? [];
  const requests = packetRequestsQ.data ?? [];

  const empMap = useMemo(() => Object.fromEntries(employees.map((e) => [e.id, e])), [employees]);
  const packetEmployeeIds = useMemo(() => new Set(packets.map((p) => p.employee_id)), [packets]);
  const eligibleEmployees = employees.filter((e) => !packetEmployeeIds.has(e.id));

  const inFlight = packets.filter((p) => p.status !== "activated").length;
  const activated = packets.filter((p) => p.status === "activated").length;
  const pendingVerify = packets.filter((p) => p.status === "completed").length;

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Workflow"
        title="Onboarding"
        subtitle="Document collection, HR verification, payroll activation — and the first 90 days."
        actions={<LinkAction href="/app/agents?agent=onboarding" variant="subtle">Open onboarding agent</LinkAction>}
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SummaryStat label="Open packets" value={inFlight} />
        <SummaryStat label="Awaiting HR verification" value={pendingVerify} tone={pendingVerify ? "warn" : "neutral"} />
        <SummaryStat label="Activated" value={activated} tone="success" />
        <SummaryStat label="Employee requests" value={requests.length} tone={requests.length ? "info" : "neutral"} />
      </div>

      {requests.length > 0 && (
        <Surface>
          <SectionTitle eyebrow="Inbox" title="Packet requests from employees" description="Resolve by creating a packet for the employee record." />
          <ul className="mt-3 divide-y divide-rule">
            {requests.map((r) => {
              const emp = r.employee_id ? empMap[r.employee_id] : undefined;
              const canCreate = !!(r.employee_id && emp && !packetEmployeeIds.has(r.employee_id));
              const alreadyHas = !!(r.employee_id && packetEmployeeIds.has(r.employee_id));
              return (
                <li key={r.id} className="py-3 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-ink">{emp?.legal_name ?? "Employee record not linked yet"}</div>
                    <div className="text-xs text-muted mt-0.5">
                      {r.requester_email ?? "—"} · {new Date(r.created_at).toLocaleString()}
                    </div>
                    {r.message && <div className="text-xs text-body mt-1.5">{r.message}</div>}
                  </div>
                  <div className="shrink-0 flex items-center gap-2">
                    {alreadyHas && <Pill tone="success">packet exists</Pill>}
                    {!r.employee_id && <Pill tone="warn">no linked employee</Pill>}
                    {canCreate && (
                      <Action
                        size="sm"
                        variant="primary"
                        onClick={() => createMutation.mutate(r.employee_id!)}
                        disabled={createMutation.isPending}
                      >
                        {createMutation.isPending ? "Creating…" : "Create packet"}
                      </Action>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </Surface>
      )}

      <Surface>
        <SectionTitle eyebrow="Create" title="Start a new packet" />
        {empQ.isLoading ? (
          <div className="mt-3 text-sm text-muted">Loading employees…</div>
        ) : eligibleEmployees.length === 0 ? (
          <div className="mt-3 text-sm text-muted">Every active employee already has a packet.</div>
        ) : (
          <div className="mt-3 flex items-end gap-3 flex-wrap">
            <label className="block flex-1 min-w-[260px]">
              <div className="mb-1 text-xs text-muted">Employee</div>
              <select
                value={selectedEmployeeId}
                onChange={(e) => setSelectedEmployeeId(e.target.value)}
                className="w-full h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
              >
                <option value="">— select —</option>
                {eligibleEmployees.map((emp) => (
                  <option key={emp.id} value={emp.id}>{emp.legal_name} ({emp.email})</option>
                ))}
              </select>
            </label>
            <Action variant="primary" onClick={() => selectedEmployeeId && createMutation.mutate(selectedEmployeeId)} disabled={!selectedEmployeeId || createMutation.isPending}>
              {createMutation.isPending ? "Creating…" : "Create packet"}
            </Action>
          </div>
        )}
        {successMsg && <div className="mt-3 text-sm text-success-fg">{successMsg}</div>}
        {errorMsg && <div className="mt-3 text-sm text-danger-fg">{errorMsg}</div>}
      </Surface>

      <Surface>
        <SectionTitle
          eyebrow="Packets"
          title="All onboarding workflows"
          description="Click a packet to expand its journey timeline."
        />
        <div className="mt-3">
          {packetsQ.isLoading ? (
            <div className="text-sm text-muted py-6 text-center">Loading…</div>
          ) : packets.length === 0 ? (
            <EmptyState title="No packets yet" description="Create one above to start an onboarding workflow." />
          ) : (
            <ul className="divide-y divide-rule">
              {packets.map((pkt) => {
                const emp = empMap[pkt.employee_id];
                const submittedCount = Object.keys(pkt.submitted_items ?? {}).length;
                const requestedCount = Object.keys(pkt.requested_items ?? {}).length;
                const isOpen = expanded === pkt.id;
                return (
                  <li key={pkt.id} className="py-3">
                    <button
                      type="button"
                      onClick={() => setExpanded(isOpen ? null : pkt.id)}
                      className="w-full text-left flex items-center justify-between gap-3 hover:bg-sunken/60 rounded-md -mx-2 px-2 py-1.5 transition-colors duration-150 ease-calm"
                    >
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-ink truncate">
                          {emp ? emp.legal_name : pkt.employee_id}
                        </div>
                        <div className="text-xs text-muted mt-0.5 truncate">
                          {emp?.email ?? "—"} · {submittedCount}/{requestedCount} items submitted
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <StatusPill value={pkt.status.replace("_", " ")} />
                        <span className={`text-muted transition-transform duration-150 ease-calm ${isOpen ? "rotate-90" : ""}`}>
                          <IconArrowUpRight />
                        </span>
                      </div>
                    </button>

                    {isOpen && (
                      <div className="mt-3 grid grid-cols-1 lg:grid-cols-3 gap-4">
                        <div className="lg:col-span-2">
                          <div className="fp-eyebrow mb-2">Journey</div>
                          <WorkflowTimeline steps={packetTimeline(pkt, emp)} />
                        </div>
                        <div>
                          <div className="fp-eyebrow mb-2">Actions</div>
                          <div className="rounded-lg border border-line bg-canvas p-3 space-y-2 text-sm">
                            {pkt.status === "completed" && (
                              <Action onClick={() => verifyMutation.mutate(pkt.id)} disabled={verifyMutation.isPending} size="sm" variant="subtle" className="w-full">
                                {verifyMutation.isPending ? "Verifying…" : "Verify documents"}
                              </Action>
                            )}
                            {pkt.status === "verified" && (
                              <Action onClick={() => activateMutation.mutate(pkt.id)} disabled={activateMutation.isPending} size="sm" variant="primary" className="w-full">
                                {activateMutation.isPending ? "Activating…" : "Activate employee"}
                              </Action>
                            )}
                            {pkt.status !== "completed" && pkt.status !== "verified" && (
                              <div className="text-xs text-muted">No actions required at this step. Waiting on the new hire or HR.</div>
                            )}
                            <Divider />
                            <div className="text-2xs uppercase tracking-eyebrow text-muted">Packet id</div>
                            <div className="font-mono text-xs text-ink break-all">{pkt.id}</div>
                          </div>
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </Surface>
    </div>
  );
}

function SummaryStat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "success" | "warn" | "info" | "danger" }) {
  const ring: Record<string, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    warn: "ring-1 ring-warn-line",
    info: "ring-1 ring-info-line",
    danger: "ring-1 ring-danger-line",
  };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
