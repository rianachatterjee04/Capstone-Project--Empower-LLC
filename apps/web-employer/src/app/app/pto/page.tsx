"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

type Employee = {
  id: string;
  legal_name: string;
  email: string;
};

type PTORequest = {
  id: string;
  employee_id: string;
  start_date: string;
  end_date: string;
  reason: string;
  status: "pending" | "approved" | "denied";
  review_note?: string | null;
  created_at: string;
};

function Badge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: "bg-amber-50 text-amber-700 border-amber-200",
    approved: "bg-emerald-50 text-emerald-700 border-emerald-200",
    denied: "bg-red-50 text-red-700 border-red-200",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${
        colors[status] ?? "bg-gray-50 text-gray-600 border-gray-200"
      }`}
    >
      {status}
    </span>
  );
}

export default function EmployerPTOPage() {
  const qc = useQueryClient();
  const [noteById, setNoteById] = useState<Record<string, string>>({});

  const requestsQ = useQuery({
    queryKey: ["employer-pto-requests"],
    queryFn: () => apiFetch<PTORequest[]>("/pto/requests"),
  });
  const employeesQ = useQuery({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/employees"),
  });

  const employeeMap = useMemo(
    () => Object.fromEntries((employeesQ.data ?? []).map((e) => [e.id, e])),
    [employeesQ.data]
  );

  const reviewMutation = useMutation({
    mutationFn: async ({ id, action }: { id: string; action: "approve" | "deny" }) => {
      const review_note = (noteById[id] ?? "").trim() || undefined;
      return apiPost<PTORequest>(`/pto/requests/${id}/${action}`, { review_note });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["employer-pto-requests"] });
    },
  });

  const all = requestsQ.data ?? [];
  const pending = all.filter((r) => r.status === "pending");
  const reviewed = all.filter((r) => r.status !== "pending");

  return (
    <div className="space-y-8">
      <div>
        <div className="text-2xl font-semibold">PTO Approvals</div>
        <div className="mt-1 text-sm text-black/60">Review employee PTO requests and approve or deny.</div>
      </div>

      <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
        <div className="border-b border-black/10 px-5 py-4">
          <div className="text-sm font-semibold">Pending requests</div>
          <div className="text-xs text-black/50 mt-0.5">{pending.length} pending</div>
        </div>
        {requestsQ.isLoading ? (
          <div className="p-5 text-sm text-black/40">Loading…</div>
        ) : pending.length === 0 ? (
          <div className="p-5 text-sm text-black/40">No pending PTO requests.</div>
        ) : (
          <div className="divide-y divide-black/5">
            {pending.map((r) => {
              const emp = employeeMap[r.employee_id];
              const isBusy = reviewMutation.isPending;
              return (
                <div key={r.id} className="px-5 py-4 space-y-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-sm font-semibold">{emp?.legal_name ?? r.employee_id}</div>
                      <div className="text-xs text-black/55">{emp?.email ?? "Unknown employee"}</div>
                      <div className="text-sm mt-1">
                        {r.start_date} to {r.end_date}
                      </div>
                      <div className="text-xs text-black/60 mt-1">{r.reason}</div>
                    </div>
                    <Badge status={r.status} />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-2">
                    <input
                      className="rounded-lg border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
                      placeholder="Optional note"
                      value={noteById[r.id] ?? ""}
                      onChange={(e) =>
                        setNoteById((prev) => ({ ...prev, [r.id]: e.target.value }))
                      }
                    />
                    <button
                      className="rounded-lg bg-black px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
                      disabled={isBusy}
                      onClick={() => reviewMutation.mutate({ id: r.id, action: "approve" })}
                    >
                      Approve
                    </button>
                    <button
                      className="rounded-lg border border-black/15 px-3 py-2 text-sm font-medium hover:bg-black/5 disabled:opacity-40"
                      disabled={isBusy}
                      onClick={() => reviewMutation.mutate({ id: r.id, action: "deny" })}
                    >
                      Deny
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
        <div className="border-b border-black/10 px-5 py-4">
          <div className="text-sm font-semibold">Reviewed requests</div>
          <div className="text-xs text-black/50 mt-0.5">{reviewed.length} total</div>
        </div>
        {reviewed.length === 0 ? (
          <div className="p-5 text-sm text-black/40">No reviewed requests yet.</div>
        ) : (
          <div className="divide-y divide-black/5">
            {reviewed.map((r) => {
              const emp = employeeMap[r.employee_id];
              return (
                <div key={r.id} className="flex items-center justify-between px-5 py-3 gap-3">
                  <div>
                    <div className="text-sm font-medium">{emp?.legal_name ?? r.employee_id}</div>
                    <div className="text-xs text-black/55">
                      {r.start_date} to {r.end_date}
                      {r.review_note ? ` · Note: ${r.review_note}` : ""}
                    </div>
                  </div>
                  <Badge status={r.status} />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
