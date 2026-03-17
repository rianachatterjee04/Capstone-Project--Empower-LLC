"use client";
import { useEffect, useState } from "react";
import { getUserContext } from "@/lib/auth";
import Link from "next/link";

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
    active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${colors[status] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}>
      {status}
    </span>
  );
}

function QuickLink({ href, label, description }: { href: string; label: string; description: string }) {
  return (
    <Link href={href} className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm hover:shadow-md hover:border-black/20 transition-all block">
      <div className="text-sm font-semibold">{label}</div>
      <div className="mt-1 text-xs text-black/50">{description}</div>
    </Link>
  );
}

export default function Dashboard() {
  const [ctx, setCtx] = useState<{ role: string; orgId: string | null; email: string | null } | null>(null);
  const [ptoRequests, setPtoRequests] = useState<PTORequest[]>([]);
  const [greeting, setGreeting] = useState("Good morning");

  useEffect(() => {
    getUserContext().then(setCtx);
    const hour = new Date().getHours();
    if (hour >= 12 && hour < 17) setGreeting("Good afternoon");
    else if (hour >= 17) setGreeting("Good evening");
  }, []);

  const pendingPTO = ptoRequests.filter((r) => r.status === "pending").length;
  const approvedPTO = ptoRequests.filter((r) => r.status === "approved").length;
  const name = ctx?.email?.split("@")[0] ?? "there";

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <div className="text-2xl font-semibold">{greeting}, {name} 👋</div>
        <div className="mt-1 text-sm text-black/50">
          {new Date().toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-widest text-black/40">Role</div>
          <div className="mt-2 text-xl font-bold capitalize">{ctx?.role ?? "—"}</div>
        </div>
        <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-widest text-black/40">PTO Requests</div>
          <div className="mt-2 text-xl font-bold">{ptoRequests.length}</div>
          <div className="mt-1 text-xs text-black/50">{pendingPTO} pending</div>
        </div>
        <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-widest text-black/40">Approved Days</div>
          <div className="mt-2 text-xl font-bold text-emerald-600">{approvedPTO}</div>
          <div className="mt-1 text-xs text-black/50">this year</div>
        </div>
        <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-widest text-black/40">Benefits</div>
          <div className="mt-2 text-xl font-bold"><Badge status="active" /></div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent PTO */}
        <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
          <div className="border-b border-black/10 px-5 py-4 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold">Recent PTO Requests</div>
              <div className="text-xs text-black/50 mt-0.5">{ptoRequests.length} total</div>
            </div>
            <Link href="/app/pto" className="text-xs text-black/50 hover:text-black transition-colors">View all →</Link>
          </div>
          <div className="divide-y divide-black/5">
            {ptoRequests.length === 0 ? (
              <div className="p-5">
                <div className="text-sm text-black/40">No PTO requests yet</div>
                <Link href="/app/pto" className="mt-2 inline-block text-xs font-medium text-black underline underline-offset-2">
                  Submit your first request →
                </Link>
              </div>
            ) : (
              ptoRequests.slice(0, 4).map((r) => (
                <div key={r.id} className="flex items-center justify-between px-5 py-3">
                  <div>
                    <div className="text-sm font-medium">{r.start_date} → {r.end_date}</div>
                    <div className="text-xs text-black/50">{r.reason}</div>
                  </div>
                  <Badge status={r.status} />
                </div>
              ))
            )}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="space-y-3">
          <div className="text-sm font-semibold px-1">Quick Actions</div>
          <QuickLink href="/app/pto" label="Request Time Off" description="Submit a new PTO request for approval" />
          <QuickLink href="/app/benefits" label="View Benefits" description="Check your benefits plans and enrollment status" />
          <QuickLink href="/app/onboarding" label="Complete Onboarding" description="Finish your employee onboarding checklist" />
          <QuickLink href="/app/documents" label="My Documents" description="View and manage your employee documents" />
        </div>
      </div>

      {/* Announcements */}
      <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
        <div className="text-sm font-semibold mb-3">Company Announcements</div>
        <div className="space-y-3">
          <div className="rounded-xl bg-black/[0.02] border border-black/5 p-4">
            <div className="text-sm font-medium">Open Enrollment — Benefits 2026</div>
            <div className="mt-1 text-xs text-black/50">Review and update your benefits elections before November 30, 2026.</div>
          </div>
          <div className="rounded-xl bg-black/[0.02] border border-black/5 p-4">
            <div className="text-sm font-medium">Welcome to Foundry People</div>
            <div className="mt-1 text-xs text-black/50">Your HR portal is live. Submit PTO requests, view benefits, and manage your documents all in one place.</div>
          </div>
        </div>
      </div>
    </div>
  );
}
