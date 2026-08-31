"use client";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, LinkAction, EmptyState, Divider } from "@/components/ds";
import { WorkflowTimeline, defaultOffboardingTemplate } from "@/components/WorkflowTimeline";
import { IconArrowUpRight } from "@/components/icons";

type Employee = {
  id: string;
  legal_name: string;
  email: string;
  job_title?: string | null;
  department?: string | null;
  status: string;
};

/**
 * Offboarding workspace — a calm, workflow-first view backed by the canonical
 * offboarding journey template. The same WorkflowTimeline primitive used for
 * onboarding renders the journey; the page only adds employee selection +
 * journey-level summary stats.
 *
 * No backend offboarding table exists yet, so this page is intentionally
 * read-only for the moment — every step ships with explicit owner + status so
 * the journey is legible. Once an offboarding model lands, this page wires up
 * exactly the same way as onboarding.
 */
export default function OffboardingPage() {
  const router = useRouter();
  const empQ = useQuery({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/employees"),
  });
  const employees = empQ.data ?? [];

  const [selected, setSelected] = useState<string>("");
  const [initErr, setInitErr] = useState<string | null>(null);

  const selectedEmp = useMemo(
    () => employees.find((e) => e.id === selected) ?? employees[0],
    [employees, selected],
  );

  const initiate = useMutation({
    mutationFn: () =>
      apiPost<{ id: string; task_count: number }>("/checklists/instantiate", {
        employee_id: selectedEmp!.id,
        kind: "offboarding",
      }),
    onSuccess: () => router.push("/app/checklists?kind=offboarding"),
    onError: (e) => setInitErr((e as Error).message),
  });

  const steps = useMemo(
    () => defaultOffboardingTemplate(selectedEmp?.legal_name ?? "the employee"),
    [selectedEmp?.legal_name],
  );

  const totalSubtasks = steps.reduce((s, st) => s + (st.subtasks?.length ?? 0), 0);
  const doneSubtasks = steps.reduce(
    (s, st) => s + (st.subtasks?.filter((t) => t.status === "done").length ?? 0),
    0,
  );
  const blocked = steps.some((st) => st.status === "blocked");
  const completion = totalSubtasks ? Math.round((doneSubtasks / totalSubtasks) * 100) : 0;

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Workflow"
        title="Offboarding"
        subtitle="Notice, knowledge transfer, exit interview, access revocation, final payroll, and records retention — orchestrated."
        actions={<LinkAction href="/app/agents?agent=compliance" variant="subtle">Open compliance agent</LinkAction>}
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Summary label="Tasks complete" value={`${doneSubtasks}/${totalSubtasks}`} />
        <Summary label="Journey" value={`${completion}%`} tone={completion === 100 ? "success" : "info"} />
        <Summary label="Status" value={blocked ? "Blocked" : completion === 100 ? "Closed" : "In flight"} tone={blocked ? "danger" : completion === 100 ? "success" : "info"} />
        <Summary label="Owner roles" value="HR · Manager · IT · Payroll · Legal" />
      </div>

      <Surface>
        <SectionTitle eyebrow="Select" title="Offboarding journey" description="Pick an employee to view their journey. Backend persistence lands in the next phase." />
        <div className="mt-3 flex items-end gap-3 flex-wrap">
          <label className="block flex-1 min-w-[260px]">
            <div className="mb-1 text-xs text-muted">Employee</div>
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="w-full h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            >
              {employees.length === 0 && <option value="">No employees yet</option>}
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>{emp.legal_name} · {emp.job_title ?? "—"}</option>
              ))}
            </select>
          </label>
          {selectedEmp && (
            <div className="text-xs text-muted">
              <div className="fp-eyebrow">Subject</div>
              <div className="text-sm text-ink mt-0.5">{selectedEmp.legal_name}</div>
              <div className="text-muted">{selectedEmp.email}</div>
            </div>
          )}
        </div>
      </Surface>

      <Surface>
        <SectionTitle eyebrow="Journey" title="Sequenced steps" description="Every step has an owner and a status. Nothing closes without HR + legal review." />
        <div className="mt-4">
          {employees.length === 0 ? (
            <EmptyState title="No employees yet" description="Seed the directory first to start an offboarding workflow." />
          ) : (
            <WorkflowTimeline steps={steps} />
          )}
        </div>
        <Divider className="my-5" />
        <div className="flex items-center justify-between gap-3">
          <div className="text-xs text-muted">
            {initErr
              ? <span className="text-danger-fg">{initErr}</span>
              : "Initiating creates a live offboarding checklist (access removal, final paycheck trigger, records retention) with owners and due dates."}
          </div>
          <div className="flex items-center gap-2">
            <LinkAction href="/app/checklists?kind=offboarding" variant="subtle">View checklists</LinkAction>
            <Action
              variant="primary"
              disabled={!selectedEmp || initiate.isPending}
              onClick={() => initiate.mutate()}
            >
              {initiate.isPending ? "Starting…" : "Initiate offboarding"}
            </Action>
          </div>
        </div>
      </Surface>

      <Surface inset hairline={false} className="bg-transparent p-0">
        <SectionTitle eyebrow="Related" title="Adjacent workflows" />
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            { label: "Onboarding", href: "/app/onboarding" },
            { label: "Compliance cases", href: "/app/cases" },
            { label: "Documents", href: "/app/documents" },
            { label: "Payroll modeling", href: "/app/cfo" },
          ].map((q) => (
            <a key={q.label} href={q.href} className="group rounded-lg border border-line bg-surface px-3.5 py-3 text-sm text-body hover:text-ink hover:bg-sunken transition-colors duration-150 ease-calm flex items-center justify-between">
              <span>{q.label}</span>
              <span className="text-muted group-hover:text-ink"><IconArrowUpRight /></span>
            </a>
          ))}
        </div>
      </Surface>
    </div>
  );
}

function Summary({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "success" | "warn" | "info" | "danger" }) {
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
      <div className="mt-1 text-lg font-semibold tracking-tight text-ink">{value}</div>
    </div>
  );
}
