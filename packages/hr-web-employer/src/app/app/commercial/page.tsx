"use client";

/**
 * The commercial loop: what we did, who it produced, and whether it made money.
 *
 * WHY THIS PAGE IS THE POINT
 * Every tool in this category can draw a funnel. A funnel counts stages, which
 * is a measure of activity. This counts dollars, and says which of them
 * actually moved — spend against contribution margin against cash collected,
 * with the grade of each figure on its face.
 *
 * THE TWO THINGS IT REFUSES TO DO
 * It will not show a prospect nobody saved as a lead: a scan surfaces names,
 * a person decides. And it will not let a source that does not licence
 * outreach be marketed to, however public the data is — the refusal is on the
 * page, with what the source IS good for, because a refusal that only says no
 * teaches people to route around it.
 *
 * AND THE ONE IT REFUSES TO CLAIM
 * Causation. One customer arriving after one campaign is a sequence. The
 * caveats are rendered, not tucked into a tooltip.
 */

import { useEffect, useState } from "react";
import {
  Divider,
  EmptyState,
  PageHeader,
  Pill,
  SectionTitle,
  Stack,
  Surface,
} from "@/components/ds";
import { apiFetch } from "@/lib/api";

type Row = Record<string, any>;

type IndexRow = {
  id: string;
  name: string;
  stage: string;
  city: string | null;
  state: string | null;
  saved_by: string | null;
  source_name: string;
  permits_direct_marketing: boolean;
  customer_name: string | null;
  spend_cents: number;
  loads_count: number;
  href: string;
};

type Attribution = {
  verdict: string;
  grade: string;
  basis: string;
  spend_cents: number;
  revenue_cents: number;
  direct_cost_cents: number;
  contribution_margin_cents: number;
  cash_collected_cents: number;
  loads_count: number;
  net_cents: number;
  margin_per_dollar: number | null;
  note: string;
  limiting_input: string | null;
  caveats: string[];
};

type Detail = {
  prospect: Row;
  source: Row;
  marketing_rights: {
    allowed: boolean;
    refusal_code: string | null;
    reason: string;
    alternative: string;
  };
  actions: Row[];
  loads: Row[];
  invoices: Row[];
  costs: Row[];
  attribution: Attribution;
};

const money = (c: number | null | undefined) =>
  c === null || c === undefined
    ? "—"
    : (c / 100).toLocaleString(undefined, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      });

const VERDICT_TONE: Record<string, "success" | "danger" | "warn" | "neutral"> = {
  WORKED: "success",
  DID_NOT_WORK: "danger",
  TOO_EARLY: "warn",
  INSUFFICIENT_EVIDENCE: "neutral",
};

const GRADE_TONE: Record<string, "warn" | "info" | "success" | "neutral"> = {
  MODELED: "warn",
  PLATFORM_REPORTED: "warn",
  CORROBORATED: "info",
  FINANCIAL_ACTUAL: "success",
};

const STAGE_TONE: Record<string, "neutral" | "info" | "success" | "danger"> = {
  OBSERVED: "neutral",
  SAVED: "info",
  CONTACTED: "info",
  QUALIFIED: "info",
  CUSTOMER: "success",
  DISQUALIFIED: "danger",
};

function Field({ label, value, tone }: {
  label: string;
  value: React.ReactNode;
  tone?: "neutral" | "warn" | "danger" | "success";
}) {
  return (
    <div>
      <div className="fp-eyebrow">{label}</div>
      <div
        className={[
          "mt-0.5 text-sm font-medium",
          tone === "danger" ? "text-danger"
            : tone === "warn" ? "text-warn"
            : tone === "success" ? "text-success"
            : "text-ink",
        ].join(" ")}
      >
        {value}
      </div>
    </div>
  );
}

export default function CommercialLoopPage() {
  const [rows, setRows] = useState<IndexRow[] | null>(null);
  const [note, setNote] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await apiFetch<{ prospects: IndexRow[]; note: string }>(
          "/commercial/loop",
        );
        if (cancelled) return;
        setRows(r.prospects);
        setNote(r.note);
        const first = r.prospects.find((p) => p.customer_name) ?? r.prospects[0];
        if (first) setSelected(first.id);
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "could not load the loop");
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    (async () => {
      try {
        const d = await apiFetch<Detail>(`/commercial/loop/${selected}`);
        if (!cancelled) setDetail(d);
      } catch {
        if (!cancelled) setDetail(null);
      }
    })();
    return () => { cancelled = true; };
  }, [selected]);

  if (error) {
    return (
      <Surface>
        <EmptyState title="The commercial loop could not be loaded" description={error} />
      </Surface>
    );
  }
  if (!rows) {
    return <Surface><div className="text-sm text-muted">Loading…</div></Surface>;
  }

  const a = detail?.attribution;

  return (
    <Stack gap={5}>
      <PageHeader
        eyebrow="Growth"
        title="The commercial loop"
        subtitle="From a name on a list to a dollar of margin — and whether it was worth doing."
      />

      <Surface>
        <SectionTitle title="Prospects" description={note} />
        {rows.length === 0 ? (
          <EmptyState
            title="Nobody has saved a prospect yet"
            description="A market scan can surface names. Someone has to decide one is worth pursuing."
          />
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left fp-eyebrow border-b border-rule">
                  <th className="py-2 pr-3">Prospect</th>
                  <th className="py-2 pr-3">Stage</th>
                  <th className="py-2 pr-3">Source</th>
                  <th className="py-2 pr-3">Saved by</th>
                  <th className="py-2 pr-3 text-right">Spend</th>
                  <th className="py-2 pr-3 text-right">Loads</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => setSelected(p.id)}
                    className={[
                      "border-b border-rule last:border-0 cursor-pointer",
                      selected === p.id ? "bg-sunken" : "hover:bg-sunken",
                    ].join(" ")}
                  >
                    <td className="py-2 pr-3 font-medium text-ink">
                      {p.name}
                      {p.customer_name && (
                        <span className="ml-2 text-xs text-success">
                          now {p.customer_name}
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      <Pill tone={STAGE_TONE[p.stage] ?? "neutral"}>
                        {p.stage.toLowerCase()}
                      </Pill>
                    </td>
                    <td className="py-2 pr-3">
                      <span className="flex items-center gap-1.5">
                        <span className="text-body">{p.source_name}</span>
                        {!p.permits_direct_marketing && (
                          <Pill tone="warn">no outreach licence</Pill>
                        )}
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-body">
                      {p.saved_by ?? (
                        <span className="text-muted">nobody — observed only</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {money(p.spend_cents)}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {p.loads_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Surface>

      {detail && (
        <>
          {/* ---- rights ------------------------------------------------- */}
          <Surface>
            <SectionTitle
              title="Where this name came from"
              trailing={
                <Pill tone={detail.marketing_rights.allowed ? "success" : "warn"}>
                  {detail.marketing_rights.allowed
                    ? "outreach permitted"
                    : "outreach refused"}
                </Pill>
              }
            />
            <div className="mt-3 grid gap-4 sm:grid-cols-3">
              <Field label="Source" value={detail.source.name} />
              <Field
                label="Kind"
                value={String(detail.source.kind).replace(/_/g, " ").toLowerCase()}
              />
              <Field
                label="Identity"
                value={String(detail.prospect.identity_strength)
                  .replace(/_/g, " ")
                  .toLowerCase()}
              />
            </div>
            {detail.marketing_rights.allowed ? (
              <p className="mt-2 text-xs text-muted">
                {detail.source.licence_note}
              </p>
            ) : (
              <div className="mt-3 rounded-md border border-warn-line bg-warn-bg p-3">
                <div className="text-xs font-semibold text-warn">
                  {detail.marketing_rights.refusal_code}
                </div>
                <p className="mt-1 text-xs text-body">
                  {detail.marketing_rights.reason}
                </p>
                <p className="mt-1 text-xs text-body">
                  {detail.marketing_rights.alternative}
                </p>
              </div>
            )}
          </Surface>

          {/* ---- what we did -------------------------------------------- */}
          <Surface>
            <SectionTitle
              title="What we did"
              description="Each action carries what it cost and how strong that figure is."
            />
            {detail.actions.length === 0 ? (
              <div className="mt-2 text-sm text-muted">
                Nothing has been spent against this prospect.
              </div>
            ) : (
              <ul className="mt-3 space-y-3">
                {detail.actions.map((act) => (
                  <li key={act.id}>
                    <div className="flex items-center justify-between gap-3">
                      <span className="flex items-center gap-2">
                        <Pill tone="neutral">
                          {String(act.action_kind).replace(/_/g, " ").toLowerCase()}
                        </Pill>
                        <span className="text-sm text-ink">{act.description}</span>
                      </span>
                      <span className="flex items-center gap-2">
                        <Pill tone={GRADE_TONE[act.spend_authority] ?? "warn"}>
                          {String(act.spend_authority).replace(/_/g, " ").toLowerCase()}
                        </Pill>
                        <span className="text-sm font-semibold tabular-nums text-ink">
                          {money(act.spend_cents)}
                        </span>
                      </span>
                    </div>
                    {act.hypothesis && (
                      <p className="mt-1 text-xs text-muted">
                        hypothesis: {act.hypothesis}
                      </p>
                    )}
                    {act.spend_source_ref && (
                      <p className="mt-0.5 text-xs text-muted">
                        cited: {act.spend_source_ref}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Surface>

          {/* ---- what it produced --------------------------------------- */}
          {detail.loads.length > 0 && (
            <Surface>
              <SectionTitle
                title="What they shipped"
                description="The freight this account actually moved."
              />
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left fp-eyebrow border-b border-rule">
                      <th className="py-2 pr-3">Load</th>
                      <th className="py-2 pr-3">Lane</th>
                      <th className="py-2 pr-3">Status</th>
                      <th className="py-2 pr-3 text-right">Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.loads.map((l) => (
                      <tr
                        key={l.id}
                        className="border-b border-rule last:border-0 cursor-pointer hover:bg-sunken"
                        onClick={() => {
                          window.location.href = `/app/trucking/loads/${l.id}`;
                        }}
                      >
                        <td className="py-2 pr-3 font-medium text-ink">
                          {l.load_number}
                        </td>
                        <td className="py-2 pr-3 text-body">
                          {l.origin_city}, {l.origin_state} → {l.destination_city},{" "}
                          {l.destination_state}
                        </td>
                        <td className="py-2 pr-3 text-body">{l.status}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {money(l.customer_rate_cents)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Surface>
          )}

          {/* ---- did it work -------------------------------------------- */}
          {a && (
            <Surface>
              <SectionTitle
                title="Did it work?"
                trailing={
                  <span className="flex items-center gap-1.5">
                    <Pill tone={VERDICT_TONE[a.verdict] ?? "neutral"}>
                      {a.verdict.replace(/_/g, " ").toLowerCase()}
                    </Pill>
                    <Pill tone={GRADE_TONE[a.grade] ?? "warn"}>
                      {a.grade.replace(/_/g, " ").toLowerCase()}
                    </Pill>
                    <Pill tone={a.basis === "REALISED" ? "success" : "warn"}>
                      {a.basis.toLowerCase()}
                    </Pill>
                  </span>
                }
                description="The question most tools skip."
              />
              <div className="mt-3 grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
                <Field label="Spend" value={money(a.spend_cents)} />
                <Field label="Revenue" value={money(a.revenue_cents)} />
                <Field label="Direct cost" value={money(a.direct_cost_cents)} />
                <Field
                  label="Contribution margin"
                  value={money(a.contribution_margin_cents)}
                />
                <Field
                  label="Net of the action"
                  value={money(a.net_cents)}
                  tone={a.net_cents >= 0 ? "success" : "danger"}
                />
                <Field
                  label="Cash collected"
                  value={money(a.cash_collected_cents)}
                  tone={a.cash_collected_cents > 0 ? "success" : "warn"}
                />
              </div>

              <p className="mt-3 text-sm text-ink">{a.note}</p>

              <Divider className="my-4" />
              <div className="fp-eyebrow">What this is not</div>
              <ul className="mt-1.5 space-y-1">
                {a.caveats.map((c, i) => (
                  <li key={i} className="text-xs text-muted">
                    · {c}
                  </li>
                ))}
              </ul>
            </Surface>
          )}
        </>
      )}
    </Stack>
  );
}
