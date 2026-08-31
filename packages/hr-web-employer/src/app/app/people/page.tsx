"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState, Avatar } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type Employee = {
  id: string;
  legal_name: string;
  email: string;
  job_title?: string | null;
  department?: string | null;
  location?: string | null;
  status: string;
};

const STATUS_TONE: Record<string, "success" | "warn" | "neutral" | "danger"> = {
  active: "success",
  activated: "success",
  invited: "warn",
  onboarding: "warn",
  pending: "warn",
  terminated: "danger",
  inactive: "neutral",
};

/**
 * People overview — calm directory + workflow shortcuts.
 *
 * The People section spans org tree, org design, digital twins, marketplace,
 * onboarding, offboarding, time off, and documents. This hub gives a single
 * scannable starting point that respects the design language: PageHeader +
 * SectionTitle rhythm, hairline surfaces, no widget spam.
 */
export default function PeoplePage() {
  const empQ = useQuery({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/employees"),
  });

  const employees = empQ.data ?? [];

  const total = employees.length;
  const active = employees.filter((e) => /(active|activated)/i.test(e.status)).length;
  const onboarding = employees.filter((e) => /(invited|onboard|pending)/i.test(e.status)).length;
  const byDept = employees.reduce<Record<string, number>>((acc, e) => {
    const k = e.department || "Unassigned";
    acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {});
  const deptTotal = Object.values(byDept).reduce((s, n) => s + n, 0) || 1;

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="People"
        title="People overview"
        subtitle="Directory · workflows · org intelligence. One scannable hub for every people-shaped task."
        actions={
          <>
            <Link href="/app/org-graph" className="h-9 px-3 rounded-md border border-line bg-surface text-ink hover:bg-sunken transition-colors duration-150 ease-calm flex items-center gap-2 text-sm">
              <IconSparkle /> Org graph
            </Link>
            <Link href="/app/org-design" className="h-9 px-3 rounded-md bg-accent text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm flex items-center gap-2 text-sm">
              Org design
            </Link>
          </>
        }
      />

      {/* Headline */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Summary label="Headcount" value={total} />
        <Summary label="Active" value={active} tone="success" />
        <Summary label="Onboarding in flight" value={onboarding} tone={onboarding ? "warn" : "neutral"} />
        <Summary label="Departments" value={Object.keys(byDept).length} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Directory */}
        <Surface className="lg:col-span-2">
          <SectionTitle
            eyebrow="Directory"
            title="Everyone"
            trailing={<Link href="/app/org" className="text-xs underline text-muted hover:text-ink">Org tree →</Link>}
          />
          {empQ.isLoading ? (
            <div className="mt-3 text-sm text-muted">Loading…</div>
          ) : employees.length === 0 ? (
            <EmptyState title="No employees yet" description="Add your first hire to populate the directory." />
          ) : (
            <ul className="mt-3 divide-y divide-rule max-h-[440px] overflow-auto -mx-2 px-2">
              {employees.map((e) => (
                <li key={e.id} className="py-2.5 flex items-center justify-between gap-3">
                  <Link href={`/app/people/${e.id}`} className="flex items-center gap-3 min-w-0 flex-1 group">
                    <Avatar name={e.legal_name} size={30} />
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-ink truncate group-hover:underline">{e.legal_name}</div>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted truncate">
                        {e.job_title ?? "—"} · {e.department ?? "—"}{e.location ? ` · ${e.location}` : ""}
                      </div>
                    </div>
                  </Link>
                  <div className="flex items-center gap-2 shrink-0">
                    <Pill tone={STATUS_TONE[e.status?.toLowerCase()] ?? "neutral"}>{e.status}</Pill>
                    <Link href={`/app/people/${e.id}`} className="text-muted hover:text-ink"><IconArrowUpRight /></Link>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Surface>

        {/* Dept mix */}
        <Surface>
          <SectionTitle eyebrow="Distribution" title="By department" />
          <div className="mt-3 space-y-2.5">
            {Object.entries(byDept)
              .sort((a, b) => b[1] - a[1])
              .map(([dept, n]) => (
                <div key={dept}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-ink truncate">{dept}</span>
                    <span className="font-mono text-xs text-muted tabular-nums">{n}</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-sunken overflow-hidden">
                    <div className="h-full bg-accent" style={{ width: `${Math.min(100, (n / deptTotal) * 100)}%` }} />
                  </div>
                </div>
              ))}
            {Object.keys(byDept).length === 0 && <div className="text-sm text-muted">—</div>}
          </div>
        </Surface>
      </div>

      {/* Workflow shortcuts */}
      <div>
        <SectionTitle eyebrow="Workflows" title="Common moves" description="Every people workflow, one click away." />
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            { label: "Onboarding", href: "/app/onboarding" },
            { label: "Offboarding", href: "/app/offboarding" },
            { label: "Time off", href: "/app/pto" },
            { label: "Documents", href: "/app/documents" },
            { label: "Org design", href: "/app/org-design", aiHinted: true },
            { label: "Workforce graph", href: "/app/workforce-graph", aiHinted: true },
            { label: "Marketplace", href: "/app/marketplace", aiHinted: true },
            { label: "Compensation", href: "/app/comp", aiHinted: true },
          ].map((q) => (
            <Link key={q.label} href={q.href} className="group rounded-lg border border-line bg-surface px-3.5 py-3 text-sm text-body hover:text-ink hover:bg-sunken transition-colors duration-150 ease-calm flex items-center justify-between">
              <span className="flex items-center gap-2">
                {q.label}
                {q.aiHinted && <span className="text-2xs uppercase tracking-eyebrow text-muted group-hover:text-ink">AI</span>}
              </span>
              <span className="text-muted group-hover:text-ink"><IconArrowUpRight /></span>
            </Link>
          ))}
        </div>
      </div>
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
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
