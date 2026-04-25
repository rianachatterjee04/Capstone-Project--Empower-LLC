"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getUserContext } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import Link from "next/link";

type Job = { id: string; title: string; status: string; created_at: string };
type Candidate = { id: string; full_name: string; status: string; ai_score?: number | null };
type PTORequest = { id: string; status: string };

function StatCard({ label, value, sub, href, color }: { label: string; value: string | number; sub?: string; href?: string; color?: string }) {
  const inner = (
    <div className={`rounded-2xl border border-black/10 p-5 space-y-1 hover:border-black/20 transition-colors ${href ? "cursor-pointer" : ""}`}>
      <div className="text-xs font-medium text-black/50 uppercase tracking-wide">{label}</div>
      <div className={`text-3xl font-bold ${color ?? "text-black"}`}>{value}</div>
      {sub && <div className="text-xs text-black/40">{sub}</div>}
    </div>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

function PipelineBar({ candidates }: { candidates: Candidate[] }) {
  const stages = ["new", "screened", "interview", "hired", "rejected"] as const;
  const colors: Record<string, string> = {
    new: "bg-blue-400",
    screened: "bg-yellow-400",
    interview: "bg-purple-400",
    hired: "bg-green-500",
    rejected: "bg-red-400",
  };
  const counts = Object.fromEntries(stages.map((s) => [s, candidates.filter((c) => c.status === s).length]));
  const total = candidates.length || 1;

  return (
    <div className="space-y-2">
      <div className="flex h-3 rounded-full overflow-hidden gap-0.5">
        {stages.map((s) =>
          counts[s] > 0 ? (
            <div key={s} className={`${colors[s]} transition-all`} style={{ width: `${(counts[s] / total) * 100}%` }} title={`${s}: ${counts[s]}`} />
          ) : null
        )}
      </div>
      <div className="flex flex-wrap gap-3">
        {stages.map((s) => (
          <div key={s} className="flex items-center gap-1.5 text-xs text-black/60">
            <span className={`w-2 h-2 rounded-full ${colors[s]}`} />
            <span className="capitalize">{s}</span>
            <span className="font-semibold text-black">{counts[s]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [ctx, setCtx] = useState<{ role: string; orgId: string | null; email: string | null } | null>(null);
  useEffect(() => { getUserContext().then(setCtx); }, []);

  const jobsQ = useQuery({ queryKey: ["jobs"], queryFn: () => apiFetch<Job[]>("/recruiting/jobs") });
  const candsQ = useQuery({ queryKey: ["candidates"], queryFn: () => apiFetch<Candidate[]>("/recruiting/candidates") });
  const ptoQ = useQuery({ queryKey: ["pto"], queryFn: () => apiFetch<PTORequest[]>("/pto/requests") });

  const jobs = jobsQ.data ?? [];
  const candidates = candsQ.data ?? [];
  const ptoRequests = ptoQ.data ?? [];

  const openJobs = jobs.filter((j) => j.status !== "closed").length;
  const pendingPTO = ptoRequests.filter((p) => p.status === "pending").length;
  const hired = candidates.filter((c) => c.status === "hired").length;
  const scoredCands = candidates.filter((c) => c.ai_score != null);
  const avgScore = scoredCands.length
    ? Math.round(scoredCands.reduce((a, c) => a + (c.ai_score ?? 0), 0) / scoredCands.length * 10) / 10
    : null;

  const recentJobs = [...jobs].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 3);

  function timeAgo(dateStr: string) {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  }

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-2xl font-semibold">Dashboard</div>
          <div className="text-sm text-black/50 mt-0.5">
            {ctx?.email ?? "—"} · <span className="capitalize">{ctx?.role ?? "—"}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-black/40">Org ID</div>
          <div className="text-xs font-mono text-black/50">{ctx?.orgId?.slice(0, 8)}…</div>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Open Jobs" value={openJobs} sub={`${jobs.length} total postings`} href="/app/recruiting" />
        <StatCard label="Candidates" value={candidates.length} sub={`${hired} hired`} href="/app/recruiting" />
        <StatCard label="Pending PTO" value={pendingPTO} sub="awaiting approval" href="/app/pto" color={pendingPTO > 0 ? "text-amber-600" : "text-black"} />
        <StatCard label="Avg AI Score" value={avgScore != null ? avgScore : "—"} sub="from AI screening" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-black/10 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold">Candidate Pipeline</div>
            <Link href="/app/recruiting" className="text-xs text-black/40 hover:text-black transition-colors">View all →</Link>
          </div>
          {candidates.length === 0 ? (
            <div className="text-sm text-black/40 py-4 text-center">No candidates yet</div>
          ) : (
            <PipelineBar candidates={candidates} />
          )}
        </div>

        <div className="rounded-2xl border border-black/10 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold">Recent Job Postings</div>
            <Link href="/app/recruiting" className="text-xs text-black/40 hover:text-black transition-colors">View all →</Link>
          </div>
          {recentJobs.length === 0 ? (
            <div className="text-sm text-black/40 py-4 text-center">No jobs posted yet</div>
          ) : (
            <div>
              {recentJobs.map((j) => (
                <div key={j.id} className="flex items-center justify-between py-3 border-b border-black/5 last:border-0">
                  <div>
                    <div className="text-sm font-medium">{j.title}</div>
                    <div className="text-xs text-black/40">{timeAgo(j.created_at)}</div>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    j.status === "open" ? "bg-green-100 text-green-700" :
                    j.status === "closed" ? "bg-black/10 text-black/50" :
                    "bg-yellow-100 text-yellow-700"
                  }`}>
                    {j.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-5">
        <div className="text-sm font-semibold mb-4">Quick Actions</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Post a Job", icon: "📋", href: "/app/recruiting" },
            { label: "PTO Requests", icon: "🗓️", href: "/app/pto" },
            { label: "Onboarding", icon: "👤", href: "/app/onboarding" },
            { label: "Reports", icon: "📊", href: "/app/hr" },
          ].map((a) => (
            <Link key={a.label} href={a.href} className="flex items-center gap-2.5 rounded-xl border border-black/10 px-4 py-3 hover:border-black/20 hover:bg-black/[0.02] transition-all">
              <span className="text-xl">{a.icon}</span>
              <span className="text-sm font-medium">{a.label}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}