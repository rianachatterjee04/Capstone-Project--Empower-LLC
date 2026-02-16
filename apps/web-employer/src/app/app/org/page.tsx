"use client";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

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

  if (isLoading) return <div>Loading…</div>;
  if (error) return <div className="text-red-600">Failed: {(error as Error).message}</div>;

  const grouped = groupBy(data ?? [], "department");

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Org Tree</div>
        <div className="text-sm text-black/60">Grouped by department (MVP). Next: manager graph + reporting lines.</div>
      </div>

      <div className="space-y-4">
        {grouped.map(([dept, emps]) => (
          <div key={dept} className="rounded-2xl border border-black/10 p-4">
            <div className="font-semibold">{dept}</div>
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
              {emps.map((e) => (
                <div key={e.id} className="rounded-xl border border-black/10 p-3">
                  <div className="font-medium">{e.preferred_name ?? e.legal_name}</div>
                  <div className="text-sm text-black/60">
                    {e.job_title ?? "—"} • {e.location ?? "—"}
                  </div>
                  <div className="mt-1 text-xs text-black/50">{e.email} • {e.status}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
