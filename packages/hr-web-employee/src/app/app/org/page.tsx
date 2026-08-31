"use client";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { PageHeader, Surface, StatusPill } from "@/components/ds";

type Employee = {
  id: string;
  employee_number: string;
  legal_name: string;
  preferred_name?: string | null;
  email: string;
  status: string;
  job_title?: string | null;
  department?: string | null;
  location?: string | null;
};

function groupBy<T extends Record<string, any>>(items: T[], key: keyof T) {
  const map = new Map<string, T[]>();
  for (const i of items) {
    const k = (i[key] ?? "Unassigned") as string;
    map.set(k, [...(map.get(k) ?? []), i]);
  }
  return [...map.entries()];
}

export default function OrgTreePage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/employees"),
  });

  if (isLoading) return <div className="text-sm text-muted">Loading…</div>;
  if (error) return <div className="text-sm text-danger-fg">Failed: {(error as Error).message}</div>;

  const grouped = groupBy(data ?? [], "department");

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Today"
        title="Company directory"
        subtitle="Grouped by department. Next: manager graph + reporting lines."
      />

      <div className="space-y-4">
        {grouped.map(([dept, emps]) => (
          <Surface key={dept}>
            <div className="font-semibold text-ink">{dept}</div>
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
              {emps.map((e) => (
                <div key={e.id} className="rounded-md border border-line bg-canvas p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-sm text-ink">{e.preferred_name ?? e.legal_name}</div>
                    <StatusPill value={e.status} />
                  </div>
                  <div className="text-sm text-muted">
                    {e.job_title ?? "—"} · {e.location ?? "—"}
                  </div>
                  <div className="mt-1 text-xs text-faint">{e.email}</div>
                </div>
              ))}
            </div>
          </Surface>
        ))}
      </div>
    </div>
  );
}
