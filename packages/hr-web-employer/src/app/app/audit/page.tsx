"use client";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { EmptyState, PageHeader, Skeleton, Surface } from "@/components/ds";

type ViewEvent = {
  id: string;
  route: string;
  actor_role?: string | null;
  actor_user_id?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  created_at: string;
};

export default function AuditViewsPage() {
  const q = useQuery({
    queryKey: ["audit_views"],
    queryFn: () => apiFetch<ViewEvent[]>("/audit/views?limit=200"),
  });
  const rows = q.data ?? [];

  return (
    <div className="space-y-6 fp-fade-in">
      <PageHeader
        eyebrow="Compliance"
        title="View audit"
        // "Who viewed what when (GET requests logged by middleware)." The
        // parenthesis is our implementation, on the screen an auditor reads.
        subtitle="Who opened which record, and when. Read access is logged separately from changes, because knowing who looked is a different question from knowing who edited."
      />

      <Surface>
        {q.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : q.isError ? (
          // An audit screen that renders an empty box on failure is the worst
          // possible failure mode: "nobody looked at anything" and "we could
          // not tell you" render identically.
          <EmptyState
            title="The view log could not be read"
            description={(q.error as Error)?.message || "The request failed."}
          />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No view events recorded yet"
            description="View auditing records authenticated sessions. Local development sessions are deliberately not recorded, so this stays empty until someone signs in properly."
          />
        ) : (
          <ul className="divide-y divide-rule">
            {rows.map((e) => (
              <li key={e.id} className="py-3">
                <div className="font-medium text-ink">{e.route}</div>
                <div className="mt-0.5 text-xs text-muted">
                  {e.actor_role ?? "unknown role"} · {e.actor_user_id ?? "unknown user"}
                </div>
                <div className="text-xs text-muted">
                  {e.entity_type ? `${e.entity_type}${e.entity_id ? ` · ${e.entity_id}` : ""}` : "no entity resolved from the route"}
                </div>
                <div className="text-xs text-faint">{new Date(e.created_at).toLocaleString()}</div>
              </li>
            ))}
          </ul>
        )}
      </Surface>
    </div>
  );
}
