"use client";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { PageHeader, Surface, SectionTitle, Pill, EmptyState } from "@/components/ds";

// These must match the server (skills_management_service.py). A test compares them.
const MIN_LEVEL = 1;
const MAX_LEVEL = 4;
const LEVEL_NAMES: Record<number, string> = { 1: "Beginner", 2: "Working", 3: "Advanced", 4: "Expert" };

type Employee = { id: string; legal_name: string; preferred_name?: string | null; job_title?: string | null };
type EmployeeSkill = { skill: string; level: number; level_name: string; source: string };
type Requirement = { skill: string; required_level: number };
type RoleRow = { role: string; skill_count: number; is_default: boolean };
type RoleRequirements = { role: string; items: Requirement[]; is_default: boolean };
type Notice = { tone: "ok" | "error"; text: string };

const LEVELS = Array.from({ length: MAX_LEVEL - MIN_LEVEL + 1 }, (_, i) => MIN_LEVEL + i);

function LevelSelect({ value, onChange, label }: { value: number; onChange: (n: number) => void; label: string }) {
  return (
    <label className="block">
      <div className="mb-1 text-sm font-medium text-ink">{label}</div>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-md border border-line bg-surface text-ink px-3 py-2 text-sm"
      >
        {LEVELS.map((n) => (
          <option key={n} value={n}>
            {n} · {LEVEL_NAMES[n]}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function EmployeeSkillsPage() {
  const qc = useQueryClient();
  const [employeeId, setEmployeeId] = useState("");
  const [skill, setSkill] = useState("");
  const [level, setLevel] = useState(2);
  const [role, setRole] = useState("");
  const [reqSkill, setReqSkill] = useState("");
  const [reqLevel, setReqLevel] = useState(2);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);

  const employeesQ = useQuery({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/employees"),
  });
  const employees = employeesQ.data ?? [];
  const employee = employees.find((e) => e.id === employeeId);

  // Start on the first person in the list.
  useEffect(() => {
    if (!employeeId && employees.length > 0) setEmployeeId(employees[0].id);
  }, [employees, employeeId]);

  const skillsQ = useQuery({
    queryKey: ["employee-skills", employeeId],
    enabled: !!employeeId,
    queryFn: () => apiFetch<{ items: EmployeeSkill[] }>(`/skills-management/employees/${employeeId}/skills`),
  });
  const skills = skillsQ.data?.items ?? [];

  const rolesQ = useQuery({
    queryKey: ["skill-roles"],
    queryFn: () => apiFetch<{ items: RoleRow[] }>("/skills-management/roles"),
  });
  const roles = rolesQ.data?.items ?? [];

  useEffect(() => {
    if (!role && roles.length > 0) setRole(roles[0].role);
  }, [roles, role]);

  const reqQ = useQuery({
    queryKey: ["role-requirements", role],
    enabled: !!role,
    queryFn: () => apiFetch<RoleRequirements>(`/skills-management/roles/requirements?role=${encodeURIComponent(role)}`),
  });
  const requirements = reqQ.data?.items ?? [];

  async function act(work: () => Promise<unknown>, done: string, refresh: string[][]) {
    setBusy(true);
    setNotice(null);
    try {
      await work();
      setNotice({ tone: "ok", text: done });
      await Promise.all(refresh.map((queryKey) => qc.invalidateQueries({ queryKey })));
    } catch (e) {
      setNotice({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function addSkill() {
    if (!skill.trim()) {
      setNotice({ tone: "error", text: "Type a skill first." });
      return;
    }
    await act(
      () => apiPost(`/skills-management/employees/${employeeId}/skills`, { skill: skill.trim(), level }),
      `Saved ${skill.trim().toLowerCase()} at level ${level}.`,
      [["employee-skills", employeeId]],
    );
    setSkill("");
  }

  async function removeSkill(name: string) {
    await act(
      () => apiFetch(`/skills-management/employees/${employeeId}/skills?skill=${encodeURIComponent(name)}`, { method: "DELETE" }),
      `Removed ${name}.`,
      [["employee-skills", employeeId]],
    );
  }

  async function saveRequirements(items: Requirement[], done: string) {
    await act(
      () => apiFetch("/skills-management/roles/requirements", { method: "PUT", body: JSON.stringify({ role, items }) }),
      done,
      [["role-requirements", role], ["skill-roles"]],
    );
  }

  async function addRequirement() {
    if (!reqSkill.trim()) {
      setNotice({ tone: "error", text: "Type a skill first." });
      return;
    }
    const name = reqSkill.trim().toLowerCase();
    const next = [...requirements.filter((r) => r.skill !== name), { skill: name, required_level: reqLevel }];
    await saveRequirements(next, `${role} now needs ${name} at level ${reqLevel}.`);
    setReqSkill("");
  }

  // How this person lines up with the role being shown.
  const have = new Map(skills.map((s) => [s.skill, s.level]));
  const comparison = requirements.map((r) => {
    const current = have.get(r.skill);
    const status = current === undefined ? "missing" : current < r.required_level ? "below" : "met";
    return { ...r, current, status };
  });
  const metCount = comparison.filter((c) => c.status === "met").length;

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="People · Skills"
        title="Employee skills"
        subtitle="Record what each person can do and how well, and set what each role needs. Levels run from 1 (beginner) to 4 (expert)."
      />

      {notice ? (
        <div className={notice.tone === "error" ? "text-sm text-danger-fg" : "text-sm text-body"} role="status">
          {notice.text}
        </div>
      ) : null}

      <Surface className="space-y-3">
        <SectionTitle title="Employee" description="Pick a person to see and edit their skills." />
        <label className="block">
          <div className="mb-1 text-sm font-medium text-ink">Employee</div>
          <select
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
            className="w-full rounded-md border border-line bg-surface text-ink px-3 py-2 text-sm"
          >
            {employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.preferred_name || e.legal_name}
                {e.job_title ? `, ${e.job_title}` : ""}
              </option>
            ))}
          </select>
        </label>
        {employeesQ.error ? <div className="text-sm text-danger-fg">{(employeesQ.error as Error).message}</div> : null}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
          <Input label="Skill" placeholder="for example python" value={skill} onChange={(e) => setSkill(e.target.value)} />
          <LevelSelect label="Level" value={level} onChange={setLevel} />
          <Button onClick={addSkill} disabled={busy || !employeeId}>
            Add or update skill
          </Button>
        </div>
      </Surface>

      <Surface>
        <SectionTitle
          title={employee ? `${employee.preferred_name || employee.legal_name}'s skills` : "Skills"}
          description={`${skills.length} recorded`}
        />
        {skillsQ.isLoading ? <div className="mt-3 text-sm text-muted">Loading…</div> : null}
        {skillsQ.error ? <div className="mt-3 text-sm text-danger-fg">{(skillsQ.error as Error).message}</div> : null}
        {!skillsQ.isLoading && !skillsQ.error && skills.length === 0 ? (
          <EmptyState title="No skills yet" description="Add the first skill above." />
        ) : (
          <ul className="mt-3 divide-y divide-line">
            {skills.map((s) => (
              <li key={s.skill} className="py-2 flex items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-ink">{s.skill}</span>
                  <Pill tone="info">
                    {s.level} · {s.level_name}
                  </Pill>
                  <Pill tone="neutral">{s.source === "hr" ? "Set by HR" : "Self reported"}</Pill>
                </div>
                <Button variant="secondary" disabled={busy} onClick={() => removeSkill(s.skill)}>
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Surface>

      <Surface className="space-y-3">
        <SectionTitle
          title="Role requirements"
          description="What a role needs. The list for a role you have not edited is the built in starting list."
        />
        <label className="block">
          <div className="mb-1 text-sm font-medium text-ink">Role</div>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="w-full rounded-md border border-line bg-surface text-ink px-3 py-2 text-sm"
          >
            {roles.map((r) => (
              <option key={r.role} value={r.role}>
                {r.role} ({r.skill_count} skills{r.is_default ? ", built in" : ""})
              </option>
            ))}
          </select>
        </label>

        {reqQ.isLoading ? <div className="text-sm text-muted">Loading…</div> : null}
        {reqQ.error ? <div className="text-sm text-danger-fg">{(reqQ.error as Error).message}</div> : null}
        {employee && comparison.length > 0 ? (
          <div className="text-sm text-body">
            {employee.preferred_name || employee.legal_name} meets {metCount} of {comparison.length} requirements for {role}.
          </div>
        ) : null}

        <ul className="divide-y divide-line">
          {comparison.map((c) => (
            <li key={c.skill} className="py-2 flex items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-ink">{c.skill}</span>
                <Pill tone="neutral">
                  needs {c.required_level} · {LEVEL_NAMES[c.required_level]}
                </Pill>
                {employee ? (
                  <Pill tone={c.status === "met" ? "success" : c.status === "below" ? "warn" : "danger"}>
                    {c.status === "met" ? "Met" : c.status === "below" ? `Below (has ${c.current})` : "Missing"}
                  </Pill>
                ) : null}
              </div>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() =>
                  saveRequirements(
                    requirements.filter((r) => r.skill !== c.skill),
                    `Removed ${c.skill} from ${role}.`,
                  )
                }
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
          <Input label="Add a required skill" value={reqSkill} onChange={(e) => setReqSkill(e.target.value)} />
          <LevelSelect label="Level needed" value={reqLevel} onChange={setReqLevel} />
          <Button onClick={addRequirement} disabled={busy || !role}>
            Add requirement
          </Button>
        </div>
        <div className="text-xs text-muted">Only HR and admins can change what a role requires.</div>
      </Surface>
    </div>
  );
}
