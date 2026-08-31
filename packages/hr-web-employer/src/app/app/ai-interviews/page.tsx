"use client";

/**
 * Every AI interview, and what it did or did not establish.
 *
 * NOT THE SAME THING AS /app/interviews.
 * That is the Interview Copilot: assistance for a HUMAN interviewer, backed by
 * the `/interviews` API. This lists the AI-conducted interviews from
 * `/interview-v2` -- the adaptive question engine, the evidence graph and the
 * recording. Two features, two lists, and putting them on one route once cost
 * the Copilot its page.
 *
 * WHY THIS PAGE EXISTS
 * Nothing in the application linked to the review page. The recruiter surface
 * the whole product is built around — the scorecard, the evidence graph, the
 * recording that seeks to the moment a candidate said something — was
 * reachable only by typing a UUID into the address bar.
 *
 * WHAT EACH ROW SAYS THAT A SCORE DOES NOT
 * Whether the interview was COMPLETE, whether there is a recording behind it,
 * and how many questions it took. "2.3/4 on a complete interview with three
 * recorded parts" and "2.3/4 on an incomplete one with no media" are different
 * things to open, and a list that shows only the number hides that.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  EmptyState,
  PageHeader,
  Pill,
  SectionTitle,
  Stack,
  Surface,
} from "@/components/ds";
import { apiFetch } from "@/lib/api";

type Row = {
  id: string;
  candidate: string;
  email: string | null;
  job_title: string;
  status: string;
  mode: string | null;
  questions: number;
  recording_parts: number;
  started_at: string | null;
  ended_at: string | null;
  score: number | null;
  confidence: number | null;
  overall_state: string | null;
  completeness_state: string | null;
  uncovered_required: string[];
  rubric_key: string | null;
  decision_authority: string | null;
};

// The client owns its own routes. The API used to return these paths, which
// put the frontend's routing table in the backend.
const reviewHref = (id: string) => `/app/interview-review/${id}`;
const liveHref = (id: string) => `/app/interview-live/${id}`;

const when = (s: string | null) =>
  s ? new Date(s).toLocaleDateString(undefined, {
        month: "short", day: "numeric", year: "numeric",
      })
    : "—";

export default function AiInterviewsPage() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [onlyScored, setOnlyScored] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  /** The link a recruiter sends the candidate. Copied, never sent from here. */
  const copyLink = async (id: string) => {
    const url = `${window.location.origin}${
      process.env.NEXT_PUBLIC_BASE_PATH ?? "/people"
    }${liveHref(id)}`;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      window.prompt("Copy the candidate's interview link:", url);
    }
    setCopied(id);
    setTimeout(() => setCopied(null), 2500);
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await apiFetch<{ interviews: Row[]; note: string }>(
          "/interview-v2/list",
        );
        if (cancelled) return;
        setRows(r.interviews);
        setNote(r.note);
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "could not load interviews");
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const shown = useMemo(
    () => (rows ?? []).filter((r) => !onlyScored || r.score !== null),
    [rows, onlyScored],
  );

  if (error) {
    return (
      <Surface>
        <EmptyState title="Interviews could not be loaded" description={error} />
      </Surface>
    );
  }
  if (!rows) {
    return <Surface><div className="text-sm text-muted">Loading…</div></Surface>;
  }

  return (
    <Stack gap={5}>
      <PageHeader
        eyebrow="Recruiting · AI Interviewer"
        title="AI interviews"
        subtitle="Open one to hear the recording behind every assessment."
      />

      <Surface>
        <SectionTitle
          title={`${shown.length} interview${shown.length === 1 ? "" : "s"}`}
          description={note}
          trailing={
            <label className="flex items-center gap-1.5 text-xs text-body">
              <input
                type="checkbox"
                checked={onlyScored}
                onChange={(e) => setOnlyScored(e.target.checked)}
              />
              scored only
            </label>
          }
        />

        {shown.length === 0 ? (
          <EmptyState
            title="No interviews yet"
            description="An interview appears here once a candidate has started one."
          />
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left fp-eyebrow border-b border-rule">
                  <th className="py-2 pr-3">Candidate</th>
                  <th className="py-2 pr-3">Role</th>
                  <th className="py-2 pr-3 text-right">Score</th>
                  <th className="py-2 pr-3">Completeness</th>
                  <th className="py-2 pr-3">Recording</th>
                  <th className="py-2 pr-3 text-right">Questions</th>
                  <th className="py-2 pr-3">Finished</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.id} className="border-b border-rule last:border-0">
                    <td className="py-2 pr-3">
                      <div className="font-medium text-ink">{r.candidate}</div>
                      {r.email && (
                        <div className="text-xs text-muted">{r.email}</div>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-body">{r.job_title}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {r.score === null ? (
                        <span className="text-muted">not scored</span>
                      ) : (
                        <>
                          <span className="font-semibold text-ink">
                            {r.score}
                          </span>
                          <span className="text-muted">/4</span>
                        </>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      {r.completeness_state === "COMPLETE" ? (
                        <Pill tone="success">complete</Pill>
                      ) : r.completeness_state ? (
                        <span title={r.uncovered_required.join(", ")}>
                          <Pill tone="warn">
                            {r.uncovered_required.length} not covered
                          </Pill>
                        </span>
                      ) : (
                        <Pill tone="neutral">{r.status.toLowerCase()}</Pill>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      {r.recording_parts > 0 ? (
                        <Pill tone="info">
                          {r.recording_parts} part
                          {r.recording_parts === 1 ? "" : "s"}
                        </Pill>
                      ) : (
                        <span className="text-xs text-muted">none captured</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums text-body">
                      {r.questions}
                    </td>
                    <td className="py-2 pr-3 text-body">{when(r.ended_at)}</td>
                    <td className="py-2 text-right whitespace-nowrap">
                      {r.status === "COMPLETED" ? (
                        <Link
                          href={reviewHref(r.id)}
                          className="text-accent hover:underline"
                        >
                          Review →
                        </Link>
                      ) : (
                        <span className="inline-flex items-center gap-3">
                          {/* THE CANDIDATE COULD NOT REACH THEIR OWN
                              INTERVIEW. Nothing in the product generated a
                              link to /app/interview-live, so the candidate
                              experience existed as a page with no way in. */}
                          <button
                            onClick={() => copyLink(r.id)}
                            className="text-accent hover:underline"
                          >
                            {copied === r.id ? "Copied" : "Copy candidate link"}
                          </button>
                          <Link
                            href={liveHref(r.id)}
                            className="text-muted hover:underline"
                          >
                            Open →
                          </Link>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Surface>
    </Stack>
  );
}
