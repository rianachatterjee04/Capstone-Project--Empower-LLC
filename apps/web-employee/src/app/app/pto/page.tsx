"use client";
import { useState } from "react";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

type PTORequest = {
  id: string;
  start_date: string;
  end_date: string;
  reason: string;
  status: "pending" | "approved" | "denied";
  created_at: string;
};

function Badge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: "bg-amber-50 text-amber-700 border-amber-200",
    approved: "bg-emerald-50 text-emerald-700 border-emerald-200",
    denied: "bg-red-50 text-red-700 border-red-200",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${colors[status] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}>
      {status}
    </span>
  );
}

export default function PTOPage() {
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [reason, setReason] = useState("");
  const [employeeName, setEmployeeName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [requests, setRequests] = useState<PTORequest[]>([]);

  const days = startDate && endDate
    ? Math.max(0, Math.ceil((new Date(endDate).getTime() - new Date(startDate).getTime()) / (1000 * 60 * 60 * 24)) + 1)
    : 0;

  async function submit() {
    if (!startDate || !endDate || !reason || !employeeName) return;
    setSubmitting(true);
    setStatusMsg(null);

    const id = crypto.randomUUID();
    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";
    const wsBase = apiBase.replace(/\/api$/, "");

    try {
      const res = await fetch(`${wsBase}/ws/test-broadcast`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id,
          title: "Approve PTO Request",
          message: `${employeeName} requesting ${days} day${days > 1 ? "s" : ""} off ${startDate} to ${endDate}. Reason: ${reason}`,
          actions: [
            { id: "approve", label: "Approve" },
            { id: "deny", label: "Deny" }
          ]
        }),
      });

      const data = await res.json();
      const newRequest: PTORequest = {
        id,
        start_date: startDate,
        end_date: endDate,
        reason,
        status: "pending",
        created_at: new Date().toISOString(),
      };
      setRequests((prev) => [newRequest, ...prev]);
      setStartDate("");
      setEndDate("");
      setReason("");
      setStatusMsg(data.subscribers > 0
        ? `✓ Request sent to manager for approval (${data.subscribers} reviewer${data.subscribers > 1 ? "s" : ""} notified).`
        : "✓ Request submitted. No managers currently online — they will be notified when they log in."
      );
    } catch (e) {
      setStatusMsg("Failed to submit request. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">PTO Requests</div>
        <div className="mt-1 text-sm text-black/60">Request time off and track approval status</div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm space-y-4">
          <div className="text-sm font-semibold">New request</div>
          <Input label="Your name" value={employeeName} onChange={(e) => setEmployeeName(e.target.value)} placeholder="Jane Smith" />
          <div className="grid grid-cols-2 gap-3">
            <Input label="Start date" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            <Input label="End date" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </div>
          {days > 0 && (
            <div className="rounded-xl bg-black/5 px-3 py-2 text-sm">
              <span className="font-medium">{days} day{days > 1 ? "s" : ""}</span> requested
            </div>
          )}
          <div>
            <div className="mb-1 text-sm font-medium">Reason</div>
            <textarea
              className="w-full rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Vacation, personal, medical, etc."
            />
          </div>
          <Button onClick={submit} disabled={!startDate || !endDate || !reason || !employeeName || submitting}>
            {submitting ? "Submitting…" : "Submit request"}
          </Button>
          {statusMsg && (
            <div className={`text-sm rounded-xl px-3 py-2 ${statusMsg.startsWith("✓") ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
              {statusMsg}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
          <div className="border-b border-black/10 px-5 py-4">
            <div className="text-sm font-semibold">My requests</div>
            <div className="text-xs text-black/50 mt-0.5">{requests.length} total</div>
          </div>
          <div className="divide-y divide-black/5">
            {requests.length === 0 ? (
              <div className="p-5 text-sm text-black/40">No requests yet</div>
            ) : (
              requests.map((r) => (
                <div key={r.id} className="flex items-center justify-between px-5 py-3">
                  <div>
                    <div className="text-sm font-medium">{r.start_date} → {r.end_date}</div>
                    <div className="text-xs text-black/50">{r.reason}</div>
                    <div className="text-xs text-black/40">{new Date(r.created_at).toLocaleString()}</div>
                  </div>
                  <Badge status={r.status} />
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
