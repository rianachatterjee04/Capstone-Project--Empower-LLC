"use client";
/**
 * Referral Intelligence — employee networks → open requisitions.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Action, Avatar, EmptyState, PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";
import { IconSparkle, IconCheck } from "@/components/icons";

type Match = {
  employee_id: string;
  employee_name: string;
  job_id: string;
  job_title: string;
  match_score: number;
  skill_overlap: string[];
  network_overlap: string[];
  rationale: string;
  reward_usd: number;
};
type Referral = {
  id: string;
  referrer_employee_id: string;
  referrer_name: string;
  job_id: string;
  job_title: string;
  candidate_name: string;
  candidate_email?: string;
  relationship: string;
  note?: string;
  status: string;
  reward_usd: number;
  reward_status: string;
  created_at: string;
};
type Stats = {
  total_referrals: number;
  hired: number;
  in_progress: number;
  hire_rate: number;
  rewards_earned_usd: number;
  rewards_pending_usd: number;
  active_referrers: number;
};
type Leader = {
  employee_id: string;
  employee_name: string;
  title: string;
  team: string;
  referrals_made: number;
  referrals_hired: number;
  pending_reward_usd: number;
  lifetime_reward_usd: number;
};

const STATUS_TONE: Record<string, "info" | "warn" | "success" | "danger" | "neutral"> = {
  submitted: "info", contacted: "info", interviewing: "warn",
  hired: "success", not_hired: "danger", withdrawn: "neutral",
};

export default function ReferralsPage() {
  const [tab, setTab] = useState<"my-matches" | "open" | "leaderboard">("my-matches");
  const [myId, setMyId] = useState<string>("emp-2"); // demo: pretend you're Atiman
  const [submitting, setSubmitting] = useState<Match | null>(null);

  const statsQ = useQuery({ queryKey: ["referrals-stats"], queryFn: () => apiFetch<Stats>("/referrals/stats") });
  const leaderQ = useQuery({ queryKey: ["referrals-leader"], queryFn: () => apiFetch<{ items: Leader[] }>("/referrals/leaderboard") });
  const refsQ = useQuery({ queryKey: ["referrals-list"], queryFn: () => apiFetch<{ items: Referral[] }>("/referrals") });
  const matchesQ = useQuery({
    queryKey: ["referrals-matches", myId],
    queryFn: () => apiFetch<{ items: Match[] }>(`/referrals/matches-for-employee/${myId}`),
    enabled: Boolean(myId),
  });

  const leaderboard = leaderQ.data?.items ?? [];
  const refs = refsQ.data?.items ?? [];
  const matches = matchesQ.data?.items ?? [];
  const stats = statsQ.data;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Hiring · Referrals"
        title="Referral Intelligence"
        subtitle="AI matches every employee's network and skills against open requisitions. The system surfaces who you should refer — not just where to post a generic 'we're hiring' message."
      />

      {/* Stats strip */}
      <Surface pad="md">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <Stat label="Total" value={stats?.total_referrals ?? "—"} />
          <Stat label="Hired" value={stats?.hired ?? "—"} />
          <Stat label="In progress" value={stats?.in_progress ?? "—"} />
          <Stat label="Hire rate" value={stats ? `${Math.round(stats.hire_rate * 100)}%` : "—"} />
          <Stat label="Rewards earned" value={stats ? `$${stats.rewards_earned_usd.toLocaleString()}` : "—"} />
          <Stat label="Pending rewards" value={stats ? `$${stats.rewards_pending_usd.toLocaleString()}` : "—"} />
        </div>
      </Surface>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        {([
          ["my-matches", "My matches"],
          ["open", "Open referrals"],
          ["leaderboard", "Leaderboard"],
        ] as const).map(([k, lbl]) => (
          <Action key={k} variant={tab === k ? "primary" : "subtle"} size="sm" onClick={() => setTab(k)}>
            {lbl}
          </Action>
        ))}
        {tab === "my-matches" && (
          <select
            value={myId}
            onChange={(e) => setMyId(e.target.value)}
            className="ml-2 rounded-md border border-line bg-canvas px-2 py-1 text-sm text-ink"
          >
            {leaderboard.map((l) => (
              <option key={l.employee_id} value={l.employee_id}>{l.employee_name} · {l.title}</option>
            ))}
          </select>
        )}
      </div>

      {tab === "my-matches" && (
        <Surface>
          <SectionTitle
            eyebrow="My matches"
            title="Open reqs where your network is strongest"
            description="The system blends skill overlap, network signals (ex-employer, alma mater) and title affinity into a match score."
          />
          {matchesQ.isLoading ? (
            <div className="mt-4 text-sm text-muted">Ranking…</div>
          ) : matches.length === 0 ? (
            <div className="mt-4">
              <EmptyState title="No strong matches yet" description="Add networks + skills to your profile to surface opportunities." />
            </div>
          ) : (
            <div className="mt-4 space-y-3">
              {matches.map((m) => (
                <div key={m.job_id} className="rounded-md border border-line bg-canvas p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-ink">{m.job_title}</div>
                      <div className="text-xs text-muted mt-0.5">{m.rationale}</div>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        {(m.skill_overlap ?? []).slice(0, 4).map((s) => (
                          <Pill key={s} tone="success">{s}</Pill>
                        ))}
                        {(m.network_overlap ?? []).slice(0, 3).map((s) => (
                          <Pill key={s} tone="info">network · {s}</Pill>
                        ))}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-2xl font-semibold text-ink tabular-nums">{m.match_score}</div>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted">match</div>
                      <div className="mt-1 text-sm font-medium text-ink">${m.reward_usd.toLocaleString()}</div>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted">reward</div>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <Action variant="primary" size="sm" onClick={() => setSubmitting(m)}>
                      <IconSparkle /> Submit a referral
                    </Action>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Surface>
      )}

      {tab === "open" && (
        <Surface>
          <SectionTitle eyebrow="Open referrals" title="Referrals in flight" description="Track status from submission through hire." />
          {refsQ.isLoading ? (
            <div className="mt-4 text-sm text-muted">Loading…</div>
          ) : refs.length === 0 ? (
            <div className="mt-4">
              <EmptyState title="No referrals yet" description="The first referral lands here." />
            </div>
          ) : (
            <div className="mt-4 divide-y divide-line">
              {refs.map((r) => (
                <div key={r.id} className="py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-ink">{r.candidate_name} <span className="text-muted">· {r.job_title}</span></div>
                    <div className="text-xs text-muted">By {r.referrer_name} · {r.relationship.replace(/_/g, " ")} · {new Date(r.created_at).toLocaleDateString()}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Pill tone={STATUS_TONE[r.status] ?? "neutral"}>{r.status.replace(/_/g, " ")}</Pill>
                    <Pill tone="neutral">${r.reward_usd.toLocaleString()} · {r.reward_status}</Pill>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Surface>
      )}

      {tab === "leaderboard" && (
        <Surface>
          <SectionTitle eyebrow="Leaderboard" title="Top referrers this quarter" />
          {leaderQ.isLoading ? (
            <div className="mt-4 text-sm text-muted">Loading…</div>
          ) : (
            <div className="mt-4 space-y-2">
              {leaderboard.map((l, i) => (
                <div key={l.employee_id} className="rounded-md border border-line bg-canvas px-3 py-2 flex items-center gap-3">
                  <div className="w-7 text-2xs uppercase tracking-eyebrow text-muted tabular-nums">#{i + 1}</div>
                  <Avatar name={l.employee_name} size={32} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-ink">{l.employee_name}</div>
                    <div className="text-xs text-muted">{l.title} · {l.team}</div>
                  </div>
                  <div className="text-right text-xs text-muted">
                    <div><span className="text-ink font-medium">{l.referrals_hired}</span> hired</div>
                    <div>{l.referrals_made} total · ${l.lifetime_reward_usd.toLocaleString()} earned</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Surface>
      )}

      {submitting && (
        <SubmitDrawer match={submitting} onClose={() => setSubmitting(null)} onSubmitted={() => { setSubmitting(null); refsQ.refetch(); statsQ.refetch(); }} />
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-canvas p-3">
      <div className="text-2xs uppercase tracking-eyebrow text-muted">{label}</div>
      <div className="mt-1 text-xl font-semibold text-ink tabular-nums">{value}</div>
    </div>
  );
}

function SubmitDrawer({ match, onClose, onSubmitted }: { match: Match; onClose: () => void; onSubmitted: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [rel, setRel] = useState("former_colleague");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function send() {
    setBusy(true);
    setErr(null);
    try {
      await apiPost("/referrals", {
        referrer_employee_id: match.employee_id,
        job_id: match.job_id,
        candidate_name: name,
        candidate_email: email,
        relationship: rel,
        note,
      });
      onSubmitted();
    } catch (e: any) {
      setErr(e?.message ?? "Submission failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-ink/40 backdrop-blur-sm" onClick={onClose} />
      <div className="w-full max-w-md h-full bg-surface border-l border-line overflow-y-auto">
        <div className="px-5 py-4 border-b border-line">
          <div className="fp-eyebrow">Submit referral</div>
          <div className="text-md font-semibold text-ink">{match.job_title}</div>
          <div className="text-xs text-muted mt-0.5">${match.reward_usd.toLocaleString()} reward · match {match.match_score}</div>
        </div>
        <div className="p-5 space-y-3">
          <Field label="Candidate name">
            <input value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink" />
          </Field>
          <Field label="Candidate email (optional)">
            <input value={email} onChange={(e) => setEmail(e.target.value)} className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink" />
          </Field>
          <Field label="Relationship">
            <select value={rel} onChange={(e) => setRel(e.target.value)} className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink">
              {["former_colleague", "friend", "community", "family"].map((r) => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
            </select>
          </Field>
          <Field label="Note to recruiter (optional)">
            <textarea rows={4} value={note} onChange={(e) => setNote(e.target.value)} className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink" />
          </Field>
          {err && <div className="text-xs text-danger-fg">{err}</div>}
          <Action variant="primary" onClick={send} disabled={!name.trim() || busy}>
            <IconCheck /> {busy ? "Submitting…" : "Submit referral"}
          </Action>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1 text-2xs uppercase tracking-eyebrow text-muted">{label}</div>
      {children}
    </label>
  );
}
