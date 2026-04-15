"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

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

function Badge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: "bg-amber-50 text-amber-700 border-amber-200",
    in_progress: "bg-blue-50 text-blue-700 border-blue-200",
    completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
    verified: "bg-purple-50 text-purple-700 border-purple-200",
    activated: "bg-green-50 text-green-700 border-green-200",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${
        colors[status] ?? "bg-gray-50 text-gray-600 border-gray-200"
      }`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

export default function OnboardingPage() {
  const qc = useQueryClient();
  const [selectedEmployeeId, setSelectedEmployeeId] = useState("");
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
      setSuccessMsg(`Onboarding packet created (ID: ${data.id})`);
      setErrorMsg(null);
      setSelectedEmployeeId("");
      qc.invalidateQueries({ queryKey: ["onboarding-packets"] });
      qc.invalidateQueries({ queryKey: ["onboarding-packet-requests"] });
    },
    onError: (e: Error) => {
      setErrorMsg(e.message);
      setSuccessMsg(null);
    },
  });

  const verifyMutation = useMutation({
    mutationFn: (packetId: string) =>
      apiPost(`/onboarding/packets/${packetId}/verify`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["onboarding-packets"] });
    },
    onError: (e: Error) => setErrorMsg(e.message),
  });

  const activateMutation = useMutation({
    mutationFn: (packetId: string) =>
      apiPost(`/onboarding/packets/${packetId}/activate`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["onboarding-packets"] });
      qc.invalidateQueries({ queryKey: ["employees"] });
    },
    onError: (e: Error) => setErrorMsg(e.message),
  });

  const employees = empQ.data ?? [];
  const packets = packetsQ.data ?? [];

  const empMap = Object.fromEntries(employees.map((e) => [e.id, e]));
  const packetEmployeeIds = new Set(packets.map((p) => p.employee_id));
  const eligibleEmployees = employees.filter(
    (e) => !packetEmployeeIds.has(e.id)
  );

  function handleCreate() {
    if (!selectedEmployeeId) return;
    createMutation.mutate(selectedEmployeeId);
  }

  function handleCreateForRequest(employeeId?: string | null) {
    if (!employeeId) return;
    createMutation.mutate(employeeId);
  }

  return (
    <div className="space-y-8">
      <div>
        <div className="text-2xl font-semibold">Onboarding</div>
        <div className="mt-1 text-sm text-black/50">
          Create and manage employee onboarding packets.
        </div>
      </div>

      {/* Employee requests */}
      <div className="rounded-2xl border border-amber-200/80 bg-amber-50/40 p-6 shadow-sm space-y-3">
        <div className="text-sm font-semibold text-amber-950">Packet requests from employees</div>
        <p className="text-xs text-amber-900/70">
          Employees without a packet can ask HR to create one from their portal. Resolve by creating a packet for
          their employee record below.
        </p>
        {packetRequestsQ.isLoading && (
          <div className="text-sm text-black/40">Loading requests…</div>
        )}
        {!packetRequestsQ.isLoading && (packetRequestsQ.data ?? []).length === 0 && (
          <div className="text-sm text-black/45">No pending requests.</div>
        )}
        <ul className="space-y-2">
          {(packetRequestsQ.data ?? []).map((r) => {
            const emp = r.employee_id ? empMap[r.employee_id] : undefined;
            const canCreateForRequest = !!(
              r.employee_id &&
              emp &&
              !packetEmployeeIds.has(r.employee_id)
            );
            const alreadyHasPacket = !!(r.employee_id && packetEmployeeIds.has(r.employee_id));
            return (
              <li
                key={r.id}
                className="rounded-xl border border-amber-200/60 bg-white/90 px-4 py-3 text-sm"
              >
                <div className="font-medium text-black/90">
                  {emp?.legal_name ?? "Employee record not linked yet"}
                </div>
                <div className="text-xs text-black/55 mt-1">
                  {r.requester_email ?? "—"} · user {r.requested_by_user_id.slice(0, 8)}… ·{" "}
                  {new Date(r.created_at).toLocaleString()}
                </div>
                {r.message && (
                  <div className="text-xs text-black/70 mt-2 border-t border-black/5 pt-2">{r.message}</div>
                )}
                <div className="mt-3 flex items-center gap-2">
                  <button
                    onClick={() => handleCreateForRequest(r.employee_id)}
                    disabled={!canCreateForRequest || createMutation.isPending}
                    className="rounded-lg bg-black px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
                  >
                    {createMutation.isPending ? "Creating..." : "Create packet for this request"}
                  </button>
                  {!r.employee_id && (
                    <span className="text-xs text-black/50">
                      No linked employee record yet.
                    </span>
                  )}
                  {alreadyHasPacket && (
                    <span className="text-xs text-emerald-700">
                      Packet already exists for this employee.
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      {/* Create packet */}
      <div className="rounded-2xl border border-black/10 bg-white p-6 shadow-sm space-y-4">
        <div className="text-sm font-semibold">Create onboarding packet</div>

        {empQ.isLoading && (
          <div className="text-sm text-black/40">Loading employees…</div>
        )}
        {!empQ.isLoading && eligibleEmployees.length === 0 && (
          <div className="text-sm text-black/40">
            All employees already have onboarding packets.
          </div>
        )}

        {eligibleEmployees.length > 0 && (
          <div className="flex items-end gap-3">
            <label className="flex-1 block">
              <div className="mb-1 text-xs font-medium text-black/60">
                Select employee
              </div>
              <select
                value={selectedEmployeeId}
                onChange={(e) => setSelectedEmployeeId(e.target.value)}
                className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none transition focus:border-black/30"
              >
                <option value="">— choose employee —</option>
                {eligibleEmployees.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.legal_name} ({emp.email})
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={handleCreate}
              disabled={!selectedEmployeeId || createMutation.isPending}
              className="rounded-xl bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {createMutation.isPending ? "Creating…" : "Create packet"}
            </button>
          </div>
        )}

        {successMsg && (
          <div className="text-sm text-emerald-600">{successMsg}</div>
        )}
        {errorMsg && <div className="text-sm text-red-500">{errorMsg}</div>}
      </div>

      {/* Packets list */}
      <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
        <div className="border-b border-black/10 px-5 py-4">
          <div className="text-sm font-semibold">All onboarding packets</div>
          <div className="text-xs text-black/50 mt-0.5">
            {packets.length} total
          </div>
        </div>

        {packetsQ.isLoading && (
          <div className="p-5 text-sm text-black/40">Loading…</div>
        )}
        {!packetsQ.isLoading && packets.length === 0 && (
          <div className="p-5 text-sm text-black/40">
            No packets yet. Create one above.
          </div>
        )}

        <div className="divide-y divide-black/5">
          {packets.map((pkt) => {
            const emp = empMap[pkt.employee_id];
            const submittedCount = Object.keys(pkt.submitted_items ?? {}).length;
            const requestedCount = Object.keys(pkt.requested_items ?? {}).length;

            return (
              <div
                key={pkt.id}
                className="flex items-center justify-between px-5 py-4 gap-4"
              >
                <div className="min-w-0">
                  <div className="font-medium text-sm truncate">
                    {emp ? emp.legal_name : pkt.employee_id}
                  </div>
                  <div className="text-xs text-black/50 mt-0.5">
                    {emp?.email} &middot; {submittedCount}/{requestedCount} items submitted
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <Badge status={pkt.status} />

                  {pkt.status === "completed" && (
                    <button
                      onClick={() => verifyMutation.mutate(pkt.id)}
                      disabled={verifyMutation.isPending}
                      className="rounded-lg border border-black/10 px-3 py-1 text-xs font-medium hover:bg-black/5 disabled:opacity-40"
                    >
                      Verify
                    </button>
                  )}

                  {pkt.status === "verified" && (
                    <button
                      onClick={() => activateMutation.mutate(pkt.id)}
                      disabled={activateMutation.isPending}
                      className="rounded-lg bg-black px-3 py-1 text-xs font-medium text-white disabled:opacity-40"
                    >
                      Activate employee
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}