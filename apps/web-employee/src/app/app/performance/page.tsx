"use client";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

type Review = {
  id: string;
  employee_id: string;
  cycle: string;
  status: string;
  ai_decision?: string | null;
};

function Badge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    draft: "bg-gray-50 text-gray-500 border-gray-200",
    manager_review: "bg-amber-50 text-amber-700 border-amber-200",
    calibration: "bg-blue-50 text-blue-700 border-blue-200",
    finalized: "bg-emerald-50 text-emerald-700 border-emerald-200",
    decision: "bg-purple-50 text-purple-700 border-purple-200",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${colors[status] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

export default function PerformancePage() {
  const reviewsQ = useQuery({
    queryKey: ["performance-reviews"],
    queryFn: () => apiFetch<Review[]>("/performance/reviews"),
  });

  const reviews = reviewsQ.data ?? [];
  const finalized = reviews.filter((r) => r.status === "finalized").length;
  const pending = reviews.filter((r) => r.status !== "finalized").length;

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Performance Reviews</div>
        <div className="mt-1 text-sm text-black/60">Your performance review history and status</div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-widest text-black/40">Total Reviews</div>
          <div className="mt-2 text-3xl font-bold">{reviewsQ.isLoading ? "—" : reviews.length}</div>
        </div>
        <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-widest text-black/40">Finalized</div>
          <div className="mt-2 text-3xl font-bold text-emerald-600">{reviewsQ.isLoading ? "—" : finalized}</div>
        </div>
        <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-widest text-black/40">Pending</div>
          <div className="mt-2 text-3xl font-bold text-amber-600">{reviewsQ.isLoading ? "—" : pending}</div>
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
        <div className="border-b border-black/10 px-5 py-4">
          <div className="text-sm font-semibold">Review History</div>
          <div className="text-xs text-black/50 mt-0.5">{reviews.length} total</div>
        </div>
        <div className="divide-y divide-black/5">
          {reviewsQ.isLoading && <div className="p-5 text-sm text-black/40">Loading reviews…</div>}
          {reviewsQ.error && <div className="p-5 text-sm text-red-500">Failed to load reviews</div>}
          {!reviewsQ.isLoading && reviews.length === 0 && (
            <div className="p-5">
              <div className="text-sm text-black/40">No performance reviews yet</div>
              <div className="mt-1 text-xs text-black/30">Reviews will appear here when your manager initiates a review cycle.</div>
            </div>
          )}
          {reviews.map((r) => (
            <div key={r.id} className="flex items-center justify-between px-5 py-3 hover:bg-black/[0.02]">
              <div>
                <div className="text-sm font-medium">Cycle: {r.cycle}</div>
                <div className="text-xs text-black/50">{r.ai_decision ? `AI Decision: ${r.ai_decision}` : "Pending review"}</div>
              </div>
              <Badge status={r.status} />
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
        <div className="text-sm font-semibold mb-3">Next Review Cycle</div>
        <div className="rounded-xl bg-black/5 p-4 text-sm text-black/60 text-center">
          Your manager will notify you when the next review cycle opens.
        </div>
      </div>
    </div>
  );
}
