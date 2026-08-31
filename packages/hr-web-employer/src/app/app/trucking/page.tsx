"use client";

/**
 * Trucking & 3PL — the operating and financial picture for today.
 *
 * WHY EVERY NUMBER OPENS
 * The board's job is not to be impressive; it is to be checkable. A dispatcher
 * who sees "Delivered, no POD: 4" needs the four load numbers, not a feeling.
 * So every tile carries a `drill_href`, and clicking it fetches the ROWS BEHIND
 * THAT EXACT PREDICATE -- the API runs the same WHERE clause it counted with,
 * and returns its own `tile_value` alongside so this page can tell the operator
 * immediately if what they are looking at has gone stale.
 *
 * WHY THE AUTHORITY LABELS ARE ON THE FACE OF EACH TILE
 * "Open AR" and "Unbilled delivered" are both money and they are not the same
 * kind of fact. One is invoiced, one is earned and not yet billed, and neither
 * is cash. A board that renders them as two numbers in the same typeface is
 * teaching the operator something false. The grade is the minimum authority
 * present, never the average.
 *
 * WHAT IS DELIBERATELY NOT HERE
 * No sparklines, no trend arrows, no "up 12% vs last week". Nothing in this
 * database supports a comparison to last week yet, and a chart that implies one
 * is a claim the data cannot carry.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Action,
  Divider,
  EmptyState,
  PageHeader,
  Pill,
  SectionTitle,
  Stack,
  Surface,
} from "@/components/ds";
import { apiFetch, apiPath } from "@/lib/api";

// ---------------------------------------------------------------------------
// Shapes
// ---------------------------------------------------------------------------

type Tile = {
  label: string;
  value: number;
  authority: string;
  drill: string;
  drill_href: string;
  drill_action: string;
  unit: "count" | "cents";
  hint?: string;
  tone?: "neutral" | "warn" | "danger";
};

type MarginRow = {
  load_number: string;
  revenue_cents: number;
  cost_cents: number;
  contribution_margin_cents: number;
  margin_pct: number | null;
  authority: string;
};

type Board = {
  as_of: string;
  operations: Tile[];
  money: Tile[];
  working_capital: {
    note: string;
    authority: string;
    receivable_cents: number;
    payable_cents: number;
    gap_cents: number;
    bank_connected: boolean;
  };
  margin: {
    basis: string;
    realised_note: string;
    loads: MarginRow[];
    below_floor_count: number;
    floor_pct: number;
    note: string;
  };
  compliance: {
    expiring_credentials: {
      driver: string;
      driver_name?: string;
      credential: string;
      expires_on: string | null;
      days: number | null;
    }[];
    expiring_credentials_drill: string;
    carrier_issues: {
      carrier: string;
      authority_status: string;
      authority_source: string;
      insurance_expires_on: string | null;
    }[];
    carrier_issues_drill: string;
    not_connected: string[];
    fmcsa_live_carriers?: number;
  };
  people: {
    interviews_completed: number;
    interviews_completed_drill: string;
    needs_recruiter_review: number;
    needs_recruiter_review_drill: string;
    note: string;
  };
  disclosure: { not_connected: string[]; note: string };
};

type DrillResult = {
  key: string;
  label: string;
  action: string;
  unit: "count" | "cents";
  tile_value: number;
  returned: number;
  limit: number;
  truncated: boolean;
  rows: Record<string, unknown>[];
  note: string;
};

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

/**
 * Exact dollars and cents. There is deliberately no rounded variant on this
 * page: leaving one beside this invites the next figure to use it, and the
 * whole point of this screen is that its numbers reconcile against each other
 * and against the rows behind them.
 *
 * The working-capital block showed receivable $9,276, payable $5,174 and a gap
 * of -$4,103. Every one of those roundings is correct on its own — the cents
 * are 927625, 517358 and -410267 — but the three sit side by side and
 * 9,276 - 5,174 is 4,102. A CFO reads that as arithmetic we got wrong, and
 * stops trusting the tiles above it. Where numbers are presented as a sum,
 * show the cents.
 */
const moneyExact = (cents: number) =>
  (cents / 100).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

// Money tiles are exact for the same reason the working-capital block is: the
// two payable tiles ($4,377.50 carrier + $796.08 payroll) are what the block's
// payable figure is made of. Rounded to $4,378 and $796 they summed to $5,174
// against a block reading $5,173.58, so the page disagreed with itself one
// level up from where it had just been fixed.
const fmtTile = (t: Pick<Tile, "value" | "unit">) =>
  t.unit === "cents" ? moneyExact(t.value) : String(t.value);

/** Snake_case column names read badly as headers. */
const humanise = (k: string) =>
  k
    .replace(/_cents$/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

const cell = (key: string, v: unknown): string => {
  if (v === null || v === undefined || v === "") return "—";
  if (key.endsWith("_cents") && typeof v === "number") return moneyExact(v);
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v)) {
    return v.slice(0, 10);
  }
  if (typeof v === "boolean") return v ? "yes" : "no";
  return String(v);
};

/** Ids are for linking, not for reading. */
const VISIBLE = (rows: Record<string, unknown>[]): string[] => {
  if (!rows.length) return [];
  return Object.keys(rows[0]).filter(
    (k) => k !== "id" && !k.endsWith("_id"),
  );
};

const AUTHORITY_TONE: Record<string, "neutral" | "warn" | "info" | "success"> = {
  OPERATING_TRUTH: "info",
  INVOICED: "neutral",
  APPROVED_PAYABLE: "neutral",
  PAYROLL_INPUT: "warn",
  MODELED: "warn",
  PLATFORM_REPORTED: "warn",
  CORROBORATED: "info",
  FINANCIAL_ACTUAL: "success",
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function TruckingTodayPage() {
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<DrillResult | null>(null);
  const [drilling, setDrilling] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const b = await apiFetch<Board>("/trucking/today");
        if (!cancelled) setBoard(b);
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "could not load the board");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const drill = useCallback(async (href: string, fallbackLabel: string) => {
    setDrilling(href);
    setOpen(null);
    try {
      const r = await apiFetch<DrillResult>(apiPath(href));
      setOpen(r);
    } catch (e: any) {
      setOpen({
        key: "error",
        label: fallbackLabel,
        action: e?.message ?? "the drill-through could not be loaded",
        unit: "count",
        tile_value: 0,
        returned: 0,
        limit: 0,
        truncated: false,
        rows: [],
        note: "",
      });
    } finally {
      setDrilling(null);
    }
  }, []);

  if (error) {
    return (
      <Surface>
        <EmptyState
          title="The trucking board could not be loaded"
          description={error}
        />
      </Surface>
    );
  }

  if (!board) {
    return (
      <Surface>
        <div className="text-sm text-muted">Loading the board…</div>
      </Surface>
    );
  }

  const tile = (t: Tile) => (
    <button
      key={t.label}
      onClick={() => drill(t.drill_href, t.label)}
      className={[
        "text-left bg-surface border rounded-lg p-4 transition-colors duration-150",
        "hover:bg-sunken focus:outline-none focus:ring-2 focus:ring-accent",
        t.tone === "warn" ? "border-warn-line" : "border-line",
        drilling === t.drill_href ? "opacity-60" : "",
      ].join(" ")}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="fp-eyebrow">{t.label}</div>
        <Pill tone={AUTHORITY_TONE[t.authority] ?? "neutral"}>
          {t.authority.replace(/_/g, " ").toLowerCase()}
        </Pill>
      </div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink">
        {fmtTile(t)}
      </div>
      {t.hint && <div className="mt-0.5 text-xs text-muted">{t.hint}</div>}
      <div className="mt-2 text-[11px] text-accent">Open the rows →</div>
    </button>
  );

  return (
    <Stack gap={5}>
      <PageHeader
        eyebrow="Trucking & 3PL"
        title="Today"
        subtitle={`Operating and financial picture as of ${board.as_of}. Every number opens.`}
      />

      {/* ---- operations ------------------------------------------------ */}
      <Surface>
        <SectionTitle
          title="Operations"
          description="What is moving, and what is stuck."
        />
        <div className="mt-3 grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          {board.operations.map(tile)}
        </div>
      </Surface>

      {/* ---- money ----------------------------------------------------- */}
      <Surface>
        <SectionTitle
          title="Money"
          description="Three different kinds of fact. The label on each tile says which."
        />
        <div className="mt-3 grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {board.money.map(tile)}
        </div>

        <Divider className="my-4" />

        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <div className="fp-eyebrow">Receivable</div>
            <div className="text-lg font-semibold text-ink">
              {moneyExact(board.working_capital.receivable_cents)}
            </div>
          </div>
          <div>
            <div className="fp-eyebrow">Payable</div>
            <div className="text-lg font-semibold text-ink">
              {moneyExact(board.working_capital.payable_cents)}
            </div>
          </div>
          <div>
            <div className="fp-eyebrow">Gap</div>
            <div className="text-lg font-semibold text-ink">
              {moneyExact(board.working_capital.gap_cents)}
            </div>
          </div>
        </div>
        <p className="mt-2 text-xs text-muted">
          {board.working_capital.note}{" "}
          {board.working_capital.bank_connected
            ? null
            : "No bank feed is connected."}
        </p>
      </Surface>

      {/* ---- margin ---------------------------------------------------- */}
      <Surface>
        <SectionTitle
          title="Contribution margin"
          trailing={<Pill tone="warn">{board.margin.basis}</Pill>}
          description={board.margin.note}
        />
        <p className="mt-1 mb-3 text-xs text-warn">
          {board.margin.realised_note}
        </p>
        {board.margin.loads.length === 0 ? (
          <EmptyState
            title="No invoiced loads yet"
            description="Margin appears once a load has been invoiced."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left fp-eyebrow border-b border-rule">
                  <th className="py-2 pr-3">Load</th>
                  <th className="py-2 pr-3 text-right">Revenue</th>
                  <th className="py-2 pr-3 text-right">Direct cost</th>
                  <th className="py-2 pr-3 text-right">Margin</th>
                  <th className="py-2 pr-3 text-right">%</th>
                  <th className="py-2">Weakest authority</th>
                </tr>
              </thead>
              <tbody>
                {board.margin.loads.map((m) => {
                  const below =
                    m.margin_pct !== null && m.margin_pct < board.margin.floor_pct;
                  return (
                    <tr
                      key={m.load_number}
                      className="border-b border-rule last:border-0"
                    >
                      <td className="py-2 pr-3 font-medium text-ink">
                        {m.load_number}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {moneyExact(m.revenue_cents)}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {moneyExact(m.cost_cents)}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {moneyExact(m.contribution_margin_cents)}
                      </td>
                      <td
                        className={[
                          "py-2 pr-3 text-right tabular-nums",
                          below ? "text-danger font-semibold" : "",
                        ].join(" ")}
                      >
                        {m.margin_pct === null ? "—" : `${m.margin_pct}%`}
                      </td>
                      <td className="py-2">
                        <Pill tone={AUTHORITY_TONE[m.authority] ?? "warn"}>
                          {m.authority.replace(/_/g, " ").toLowerCase()}
                        </Pill>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {board.margin.below_floor_count > 0 && (
          <p className="mt-2 text-xs text-danger">
            {board.margin.below_floor_count} load
            {board.margin.below_floor_count === 1 ? "" : "s"} below the{" "}
            {board.margin.floor_pct}% floor.
          </p>
        )}
      </Surface>

      {/* ---- compliance ------------------------------------------------ */}
      <div className="grid gap-5 lg:grid-cols-2">
        <Surface>
          <SectionTitle
            title="Credentials expiring"
            trailing={
              <Action
                size="sm"
                onClick={() =>
                  drill(
                    board.compliance.expiring_credentials_drill,
                    "Credentials expiring",
                  )
                }
              >
                Open
              </Action>
            }
            description="A credential that expires mid-load makes the driver ineligible before the freight is delivered."
          />
          {board.compliance.expiring_credentials.length === 0 ? (
            <div className="mt-2 text-sm text-muted">
              Nothing expiring in the next 30 days.
            </div>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {board.compliance.expiring_credentials.map((c, i) => (
                <li key={i} className="flex items-center justify-between text-sm">
                  <span className="text-ink">
                    {c.driver_name ?? c.driver} · {c.credential.replace(/_/g, " ")}
                  </span>
                  <Pill tone={(c.days ?? 99) <= 14 ? "danger" : "warn"}>
                    {c.days === null ? "no date" : `${c.days} days`}
                  </Pill>
                </li>
              ))}
            </ul>
          )}
        </Surface>

        <Surface>
          <SectionTitle
            title="Carriers that cannot be used"
            trailing={
              <Action
                size="sm"
                onClick={() =>
                  drill(board.compliance.carrier_issues_drill, "Carrier issues")
                }
              >
                Open
              </Action>
            }
            description="Authority not ACTIVE, insurance missing or expired, or the authority check is more than 30 days old."
          />
          {board.compliance.carrier_issues.length === 0 ? (
            <div className="mt-2 text-sm text-muted">
              Every carrier on file is currently usable.
            </div>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {board.compliance.carrier_issues.map((c, i) => (
                <li key={i} className="flex items-center justify-between text-sm">
                  <span className="text-ink">{c.carrier}</span>
                  <span className="flex items-center gap-1.5">
                    <Pill
                      tone={c.authority_status === "ACTIVE" ? "warn" : "danger"}
                    >
                      {c.authority_status.toLowerCase()}
                    </Pill>
                    <Pill tone="neutral">
                      {c.authority_source.replace(/_/g, " ").toLowerCase()}
                    </Pill>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Surface>
      </div>

      {/* ---- hiring ---------------------------------------------------- */}
      <Surface>
        <SectionTitle title="Hiring" description={board.people.note} />
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <button
            onClick={() =>
              drill(
                board.people.interviews_completed_drill,
                "Interviews completed",
              )
            }
            className="text-left bg-surface border border-line rounded-lg p-4 hover:bg-sunken focus:outline-none focus:ring-2 focus:ring-accent"
          >
            <div className="fp-eyebrow">Interviews completed</div>
            <div className="mt-1 text-2xl font-semibold text-ink">
              {board.people.interviews_completed}
            </div>
            <div className="mt-2 text-[11px] text-accent">Open the rows →</div>
          </button>
          <button
            onClick={() =>
              drill(
                board.people.needs_recruiter_review_drill,
                "Needs a recruiter",
              )
            }
            className="text-left bg-surface border border-warn-line rounded-lg p-4 hover:bg-sunken focus:outline-none focus:ring-2 focus:ring-accent"
          >
            <div className="fp-eyebrow">Needs a recruiter</div>
            <div className="mt-1 text-2xl font-semibold text-ink">
              {board.people.needs_recruiter_review}
            </div>
            <div className="mt-2 text-[11px] text-accent">Open the rows →</div>
          </button>
        </div>
      </Surface>

      {/* ---- what is not connected ------------------------------------- */}
      <Surface inset>
        <SectionTitle title="Not connected" />
        <div className="mt-2 flex flex-wrap gap-1.5">
          {board.disclosure.not_connected.map((n) => (
            <Pill key={n} tone="neutral">
              {n}
            </Pill>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted">{board.disclosure.note}</p>
        {typeof board.compliance.fmcsa_live_carriers === "number" && (
          <p className="mt-1 text-xs text-muted">
            {board.compliance.fmcsa_live_carriers === 0
              ? "No carrier on file has a live FMCSA authority check inside the 30-day window, so FMCSA is reported as not connected."
              : `${board.compliance.fmcsa_live_carriers} carrier(s) have a live FMCSA authority check inside the 30-day window.`}
          </p>
        )}
      </Surface>

      {/* ---- drill-through --------------------------------------------- */}
      {open && (
        <DrillPanel result={open} onClose={() => setOpen(null)} />
      )}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Drill-through panel
// ---------------------------------------------------------------------------

function DrillPanel({
  result,
  onClose,
}: {
  result: DrillResult;
  onClose: () => void;
}) {
  // Escape closes it, and the page behind it stops scrolling while it is open.
  // Without the scroll lock the board moves under the panel, so closing it
  // leaves the operator somewhere they did not choose to be.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  const cols = VISIBLE(result.rows);
  const summed =
    result.unit === "cents"
      ? result.rows.reduce(
          (n, r) => n + Number((r as any).amount_cents ?? 0),
          0,
        )
      : result.returned;
  // THE RECONCILIATION, SHOWN.
  // The API returns the tile's own number recomputed from the same predicate.
  // If what we listed does not add up to it, the operator is told, rather than
  // being left to notice.
  const reconciles = result.truncated || summed === result.tile_value;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/30 p-0 sm:p-6"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={result.label}
        className="w-full sm:max-w-4xl max-h-[85vh] overflow-y-auto bg-surface border border-line rounded-t-xl sm:rounded-xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-base font-semibold text-ink">{result.label}</div>
            <p className="mt-0.5 text-xs text-muted max-w-xl">{result.action}</p>
          </div>
          <Action size="sm" onClick={onClose}>
            Close
          </Action>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <Pill tone="neutral">
            {result.unit === "cents"
              ? moneyExact(result.tile_value)
              : `${result.tile_value} rows`}
          </Pill>
          <span className="text-muted">
            showing {result.returned}
            {result.truncated ? ` of ${result.tile_value} (capped at ${result.limit})` : ""}
          </span>
          {!reconciles && (
            <Pill tone="danger">
              These rows do not add up to the tile — reload the board
            </Pill>
          )}
        </div>

        {result.rows.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="Nothing here right now"
              description="That is the honest answer, not an error."
            />
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left fp-eyebrow border-b border-rule">
                  {cols.map((c) => (
                    <th key={c} className="py-2 pr-3 whitespace-nowrap">
                      {humanise(c)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r, i) => {
                  // A row you cannot open is a slightly better version of a
                  // number you cannot open. Load rows go to the load.
                  const href =
                    (r as any).load_number && (r as any).id
                      ? `/app/trucking/loads/${(r as any).id}`
                      : null;
                  return (
                  <tr
                    key={i}
                    className={[
                      "border-b border-rule last:border-0",
                      href ? "cursor-pointer hover:bg-sunken" : "",
                    ].join(" ")}
                    onClick={href ? () => { window.location.href = href; } : undefined}
                  >
                    {cols.map((c) => (
                      <td
                        key={c}
                        className={[
                          "py-2 pr-3 whitespace-nowrap",
                          c.endsWith("_cents") ? "text-right tabular-nums" : "",
                        ].join(" ")}
                      >
                        {cell(c, (r as any)[c])}
                      </td>
                    ))}
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {result.note && (
          <p className="mt-3 text-xs text-muted">{result.note}</p>
        )}
      </div>
    </div>
  );
}
