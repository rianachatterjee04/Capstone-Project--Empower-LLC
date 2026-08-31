"use client";

/**
 * One load, from the rate that was agreed to the margin it produced.
 *
 * WHY THIS PAGE EXISTS
 * The Today board's drill-through gives an operator a list of load numbers. A
 * list you cannot open is a slightly better version of a number you cannot
 * open. This is where a row goes.
 *
 * WHY THE BLOCKS LOOK DIFFERENT FROM EACH OTHER
 * A load's story is made of facts of different kinds. The shipper's rate is a
 * commitment; the carrier's rate is an agreement with a signature behind it;
 * the tracking is the carrier telling us where they are; the POD is a
 * document; the margin is arithmetic over all of it. Rendering them as one
 * flat field list teaches an operator that they are the same kind of thing,
 * and the entire point of the product is that they are not.
 *
 * WHY THE REFUSALS ARE ON THE PAGE
 * "This cannot be invoiced because the proof of delivery is unrecorded" is
 * more useful than a greyed-out button, and it is the sentence an ops person
 * needs in order to do something about it.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
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

type Detail = {
  load: Row;
  customer: { name: string; payment_terms_days: number };
  carrier: {
    name: string;
    authority_status: string;
    authority_source: string;
    authority_checked_at: string | null;
    insurance_expires_on: string | null;
  } | null;
  driver: { driver_code: string; worker_classification: string } | null;
  rate_confirmation: Row | null;
  rate_confirmation_history: Row[];
  dispatch: { allowed: boolean; refusal_codes: string[]; reasons: string[] };
  events: Row[];
  accessorials: Row[];
  proof_of_delivery: Row | null;
  invoice: Row | null;
  billing_blocked_by: { code: string; detail: string } | null;
  settlements: Row[];
  costs: Row[];
  margin: {
    modeled: Row;
    realised_state: string;
    realised_margin_cents: number | null;
    variance_cents: number | null;
    note: string;
  } | null;
  disclosure: { tracking_authority: string; not_connected: string[] };
};

const money = (c: number | null | undefined) =>
  c === null || c === undefined
    ? "—"
    : (c / 100).toLocaleString(undefined, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 2,
      });

const when = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleString(undefined, {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      })
    : "—";

/** "225 minute" reads as a typo. The unit comes back singular from the DB. */
const plural = (n: number | null | undefined, unit: string) => {
  const u = String(unit ?? "").toLowerCase();
  if (!u) return "";
  return n === 1 ? u : `${u}s`;
};

const AUTH_TONE: Record<string, "neutral" | "warn" | "info" | "success" | "danger"> = {
  MODELED: "warn",
  PLATFORM_REPORTED: "warn",
  CORROBORATED: "info",
  FINANCIAL_ACTUAL: "success",
  CARRIER_REPORTED: "warn",
  DRIVER_APP: "warn",
  TELEMATICS: "info",
  DISPATCHER_ENTRY: "neutral",
  DEMO_SIMULATED: "neutral",
  CUSTOMER_REPORTED: "neutral",
};

const POD_TONE: Record<string, "warn" | "info" | "success"> = {
  ASSERTED_BY_DRIVER: "warn",
  RECEIVER_ACKNOWLEDGED: "info",
  SIGNED_DOCUMENT: "success",
  EDI_CONFIRMED: "success",
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

export default function LoadDetailPage({ params }: { params: { id: string } }) {
  const [d, setD] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await apiFetch<Detail>(`/trucking/loads/${params.id}`);
        if (!cancelled) setD(r);
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "could not load this load");
      }
    })();
    return () => { cancelled = true; };
  }, [params.id]);

  if (error) {
    return (
      <Surface>
        <EmptyState title="This load could not be opened" description={error} />
      </Surface>
    );
  }
  if (!d) {
    return <Surface><div className="text-sm text-muted">Loading…</div></Surface>;
  }

  const l = d.load;
  const rc = d.rate_confirmation;

  return (
    <Stack gap={5}>
      <PageHeader
        eyebrow={
          <Link href="/app/trucking" className="hover:underline">
            ← Trucking &amp; 3PL
          </Link> as any
        }
        title={l.load_number}
        subtitle={`${l.origin_city}, ${l.origin_state} → ${l.destination_city}, ${l.destination_state} · ${l.equipment_required ?? "—"} · ${l.commodity ?? "—"}`}
      />

      {/* ---- the shape of the deal ------------------------------------- */}
      <Surface>
        <SectionTitle
          title="The load"
          trailing={<Pill tone="neutral">{l.status}</Pill>}
        />
        <div className="mt-3 grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
          <Field label="Shipper" value={d.customer.name} />
          <Field label="Shipper pays" value={money(l.customer_rate_cents)} />
          <Field
            label="Fulfilment"
            value={l.fulfilment_mode === "BROKERED" ? "Brokered" : "Own fleet"}
          />
          <Field
            label="Miles"
            value={l.miles ? l.miles.toLocaleString() : "—"}
          />
          <Field label="Weight" value={l.weight_lbs ? `${l.weight_lbs.toLocaleString()} lb` : "—"} />
        </div>
      </Surface>

      {/* ---- who is hauling it ----------------------------------------- */}
      {d.carrier && (
        <Surface>
          <SectionTitle
            title="Carrier"
            description="Authority and insurance are checked independently of anything that was agreed on price."
          />
          <div className="mt-3 grid gap-4 grid-cols-2 sm:grid-cols-4">
            <Field label="Carrier" value={d.carrier.name} />
            <Field
              label="Authority"
              value={
                <span className="flex items-center gap-1.5">
                  {d.carrier.authority_status}
                  <Pill tone={d.carrier.authority_source === "FMCSA_LIVE" ? "success" : "warn"}>
                    {d.carrier.authority_source.replace(/_/g, " ").toLowerCase()}
                  </Pill>
                </span>
              }
            />
            <Field label="Checked" value={when(d.carrier.authority_checked_at)} />
            <Field label="Insurance to" value={d.carrier.insurance_expires_on ?? "—"} />
          </div>
        </Surface>
      )}

      {d.driver && (
        <Surface>
          <SectionTitle title="Driver" />
          <div className="mt-3 grid gap-4 grid-cols-2 sm:grid-cols-3">
            <Field label="Driver" value={d.driver.driver_code} />
            <Field
              label="Classification"
              value={d.driver.worker_classification.replace(/_/g, " ")}
            />
            <Field
              label="Pay routes to"
              value={
                d.driver.worker_classification === "W2_EMPLOYEE"
                  ? "Payroll"
                  : "Settlement"
              }
            />
          </div>
        </Surface>
      )}

      {/* ---- what was agreed ------------------------------------------- */}
      {l.fulfilment_mode === "BROKERED" && (
        <Surface>
          <SectionTitle
            title="Rate confirmation"
            trailing={
              rc ? (
                <Pill tone={rc.state === "ACCEPTED" ? "success" : "warn"}>
                  {rc.state.toLowerCase()}
                </Pill>
              ) : (
                <Pill tone="danger">none</Pill>
              )
            }
            description="What the carrier's pay is defensible against. Not a field on the load."
          />
          {rc ? (
            <>
              <div className="mt-3 grid gap-4 grid-cols-2 sm:grid-cols-4">
                <Field label="Number" value={rc.confirmation_number} />
                <Field label="Linehaul" value={money(rc.linehaul_cents)} />
                <Field label="Fuel surcharge" value={money(rc.fuel_surcharge_cents)} />
                <Field label="Agreed total" value={money(rc.agreed_total_cents)} />
                <Field label="Accepted by" value={rc.accepted_by ?? "not yet accepted"} />
                <Field label="Accepted at" value={when(rc.accepted_at)} />
                <Field label="Channel" value={rc.accepted_channel ?? "—"} />
                <Field
                  label="Document"
                  value={
                    rc.document_sha256
                      ? `sha256 ${String(rc.document_sha256).slice(0, 12)}…`
                      : "no hash recorded"
                  }
                />
              </div>

              {Array.isArray(rc.approved_accessorials) &&
                rc.approved_accessorials.length > 0 && (
                  <>
                    <Divider className="my-4" />
                    <div className="fp-eyebrow">Pre-approved accessorials</div>
                    <ul className="mt-1.5 space-y-1 text-sm text-ink">
                      {rc.approved_accessorials.map((t: any, i: number) => (
                        <li key={i}>
                          {t.kind}: {money(t.rate_cents)} per{" "}
                          {String(t.unit ?? "flat").toLowerCase()}
                          {t.free_time_minutes
                            ? `, after ${t.free_time_minutes} minutes free`
                            : ""}
                          {t.cap_cents !== null && t.cap_cents !== undefined
                            ? `, capped at ${money(t.cap_cents)}`
                            : ""}
                        </li>
                      ))}
                    </ul>
                    <p className="mt-2 text-xs text-muted">
                      An accessorial not listed here is not pre-approved. It can
                      still be paid, with a separate human approval, and the
                      settlement note says which of the two it was.
                    </p>
                  </>
                )}
            </>
          ) : (
            <p className="mt-2 text-sm text-danger">
              This brokered load has no rate confirmation, so there is no
              document a carrier payable could be defended against.
            </p>
          )}

          {!d.dispatch.allowed && (
            <div className="mt-3 rounded-md border border-warn-line bg-warn-bg p-3">
              <div className="text-xs font-semibold text-warn">
                Will not dispatch — {d.dispatch.refusal_codes.join(", ")}
              </div>
              {d.dispatch.reasons.map((r, i) => (
                <p key={i} className="mt-1 text-xs text-body">{r}</p>
              ))}
            </div>
          )}

          {d.rate_confirmation_history.length > 1 && (
            <>
              <Divider className="my-4" />
              <div className="fp-eyebrow">History</div>
              <ul className="mt-1.5 space-y-1 text-sm">
                {d.rate_confirmation_history.map((h) => (
                  <li key={h.id} className="flex items-center gap-2">
                    <Pill tone={h.state === "ACCEPTED" ? "success" : "neutral"}>
                      {h.state.toLowerCase()}
                    </Pill>
                    <span className="text-ink">{h.confirmation_number}</span>
                    <span className="text-muted">{money(h.agreed_total_cents)}</span>
                    {h.amendment_reason && (
                      <span className="text-xs text-muted">
                        — {h.amendment_reason}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted">
                A superseded confirmation is kept, because a settlement may
                already cite it.
              </p>
            </>
          )}
        </Surface>
      )}

      {/* ---- what happened --------------------------------------------- */}
      <Surface>
        <SectionTitle
          title="Timeline"
          description={d.disclosure.tracking_authority}
        />
        {d.events.length === 0 ? (
          <div className="mt-2 text-sm text-muted">Nothing recorded yet.</div>
        ) : (
          <ul className="mt-3 space-y-2">
            {d.events.map((e, i) => (
              <li key={i} className="flex items-center gap-3 text-sm">
                <span className="w-28 shrink-0 text-muted tabular-nums">
                  {when(e.occurred_at)}
                </span>
                <span className="w-44 shrink-0 font-medium text-ink">
                  {e.event_type.replace(/_/g, " ")}
                </span>
                <Pill tone={AUTH_TONE[e.source] ?? "neutral"}>
                  {e.source.replace(/_/g, " ").toLowerCase()}
                </Pill>
                {e.note && <span className="text-xs text-muted">{e.note}</span>}
              </li>
            ))}
          </ul>
        )}
      </Surface>

      {/* ---- proof ------------------------------------------------------ */}
      <div className="grid gap-5 lg:grid-cols-2">
        <Surface>
          <SectionTitle
            title="Proof of delivery"
            trailing={
              d.proof_of_delivery ? (
                <Pill tone={POD_TONE[d.proof_of_delivery.evidence_strength] ?? "warn"}>
                  {d.proof_of_delivery.evidence_strength.replace(/_/g, " ").toLowerCase()}
                </Pill>
              ) : (
                <Pill tone="danger">none</Pill>
              )
            }
            description="A driver tapping 'delivered' is an assertion by an interested party."
          />
          {d.proof_of_delivery ? (
            <div className="mt-3 grid gap-4 grid-cols-2">
              <Field label="Received" value={when(d.proof_of_delivery.received_at)} />
              <Field label="Receiver" value={d.proof_of_delivery.receiver_name ?? "—"} />
              <Field
                label="Signature"
                value={(d.proof_of_delivery.signature_kind ?? "—").replace(/_/g, " ")}
              />
              <Field
                label="Exceptions"
                value={d.proof_of_delivery.exceptions_noted || "none noted"}
              />
            </div>
          ) : (
            <p className="mt-2 text-sm text-muted">
              Not received. This load cannot be invoiced.
            </p>
          )}
        </Surface>

        <Surface>
          <SectionTitle
            title="Accessorials"
            description="An accessorial happening and an accessorial being payable are different facts."
          />
          {d.accessorials.length === 0 ? (
            <div className="mt-2 text-sm text-muted">None recorded.</div>
          ) : (
            <ul className="mt-3 space-y-2">
              {d.accessorials.map((a) => (
                <li key={a.id} className="text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-ink">
                      {a.accessorial_type.replace(/_/g, " ")}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Pill tone={a.direction === "CARRIER_PAYABLE" ? "warn" : "info"}>
                        {a.direction === "CARRIER_PAYABLE" ? "we pay" : "we bill"}
                      </Pill>
                      <Pill tone={a.state === "APPROVED" ? "success" : "neutral"}>
                        {a.state.toLowerCase()}
                      </Pill>
                      <span className="tabular-nums text-ink">
                        {money(a.amount_cents)}
                      </span>
                    </span>
                  </div>
                  {a.measured_quantity !== null && (
                    <div className="mt-0.5 text-xs text-muted">
                      measured {a.measured_quantity}{" "}
                      {plural(a.measured_quantity, a.measured_unit)}
                      {a.free_allowance
                        ? `, ${a.free_allowance} free`
                        : ""}
                      {/* NO UNIT NOUN ON THE BILLABLE QUANTITY.
                          `measured_unit` is the unit of the MEASUREMENT
                          (225 minutes at the receiver); `billable_quantity`
                          is in the unit of the RATE (1.75 hours at $50). The
                          row stores only the first, so writing "billable 1.75
                          minutes" states something false. The arithmetic
                          below says the same thing and cannot be wrong. */}
                      {a.billable_quantity !== null && a.rate_cents
                        ? `, billable ${a.billable_quantity} × ${money(a.rate_cents)}`
                        : a.billable_quantity !== null
                          ? `, billable ${a.billable_quantity}`
                          : ""}
                      {a.approved_by ? ` · approved by ${a.approved_by}` : ""}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Surface>
      </div>

      {/* ---- money ------------------------------------------------------ */}
      <div className="grid gap-5 lg:grid-cols-2">
        <Surface>
          <SectionTitle title="Invoice" />
          {d.invoice ? (
            <>
              <div className="mt-3 grid gap-4 grid-cols-2">
                <Field label="Number" value={d.invoice.invoice_number} />
                <Field label="State" value={d.invoice.state} />
                <Field label="Linehaul" value={money(d.invoice.linehaul_cents)} />
                <Field label="Accessorial" value={money(d.invoice.accessorial_cents)} />
                <Field label="Total" value={money(d.invoice.total_cents)} />
                <Field
                  label="Collected"
                  value={money(d.invoice.paid_cents)}
                  tone={d.invoice.paid_cents ? "success" : "warn"}
                />
              </div>
              <p className="mt-2 text-xs text-muted">
                {d.invoice.derivation_note}
              </p>
            </>
          ) : d.billing_blocked_by ? (
            <div className="mt-2 rounded-md border border-warn-line bg-warn-bg p-3">
              <div className="text-xs font-semibold text-warn">
                Cannot be invoiced — {d.billing_blocked_by.code}
              </div>
              <p className="mt-1 text-xs text-body">
                {d.billing_blocked_by.detail}
              </p>
            </div>
          ) : (
            <div className="mt-2 text-sm text-muted">Not yet invoiced.</div>
          )}
        </Surface>

        <Surface>
          <SectionTitle title="What we owe" />
          {d.settlements.length === 0 ? (
            <div className="mt-2 text-sm text-muted">No settlement yet.</div>
          ) : (
            d.settlements.map((s) => (
              <div key={s.id} className="mt-3">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Pill tone={s.payee_kind === "DRIVER_W2" ? "info" : "neutral"}>
                      {s.payee_kind.replace(/_/g, " ").toLowerCase()}
                    </Pill>
                    <Pill tone={s.state === "PAID" ? "success" : "neutral"}>
                      {s.state.replace(/_/g, " ").toLowerCase()}
                    </Pill>
                  </span>
                  <span className="text-sm font-semibold text-ink tabular-nums">
                    {money(s.total_cents)}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted">{s.derivation_note}</p>
                {s.payee_kind === "DRIVER_W2" && (
                  <p className="mt-1 text-xs text-info">
                    Routed to payroll, not paid as an invoice. Withholding and
                    employer contributions are additional to this figure.
                  </p>
                )}
                {s.rate_confirmation_id && (
                  <p className="mt-1 text-xs text-success">
                    Traceable to the accepted rate confirmation.
                  </p>
                )}
              </div>
            ))
          )}
        </Surface>
      </div>

      {/* ---- margin ----------------------------------------------------- */}
      {d.margin && (
        <Surface>
          <SectionTitle
            title="Contribution margin"
            trailing={
              <Pill tone={AUTH_TONE[d.margin.modeled.cost_authority] ?? "warn"}>
                {String(d.margin.modeled.cost_authority).replace(/_/g, " ").toLowerCase()}
              </Pill>
            }
            description={d.margin.modeled.note}
          />
          <div className="mt-3 grid gap-4 grid-cols-2 sm:grid-cols-4">
            <Field label="Revenue" value={money(d.margin.modeled.revenue_cents)} />
            <Field label="Direct cost" value={money(d.margin.modeled.direct_cost_cents)} />
            <Field
              label="Modeled margin"
              value={`${money(d.margin.modeled.contribution_margin_cents)} (${d.margin.modeled.margin_pct}%)`}
            />
            <Field
              label="Realised"
              value={
                d.margin.realised_margin_cents === null
                  ? d.margin.realised_state.replace(/_/g, " ").toLowerCase()
                  : money(d.margin.realised_margin_cents)
              }
              tone={d.margin.realised_state === "REALISED" ? "success" : "warn"}
            />
          </div>
          <p className="mt-2 text-xs text-warn">{d.margin.note}</p>

          {d.costs.length > 0 && (
            <>
              <Divider className="my-4" />
              <div className="fp-eyebrow">Costs, by how strong each figure is</div>
              <ul className="mt-1.5 space-y-1 text-sm">
                {d.costs.map((c, i) => (
                  <li key={i} className="flex items-center justify-between gap-2">
                    <span className="text-ink">
                      {c.cost_type.replace(/_/g, " ")}
                    </span>
                    <span className="flex items-center gap-2">
                      <Pill tone={AUTH_TONE[c.authority] ?? "warn"}>
                        {c.authority.replace(/_/g, " ").toLowerCase()}
                      </Pill>
                      <span className="tabular-nums text-ink">
                        {money(c.amount_cents)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted">
                The grade above is the WEAKEST authority in this list, never the
                average.
              </p>
            </>
          )}
        </Surface>
      )}

      <Surface inset>
        <SectionTitle title="Not connected" />
        <div className="mt-2 flex flex-wrap gap-1.5">
          {d.disclosure.not_connected.map((n) => (
            <Pill key={n} tone="neutral">{n}</Pill>
          ))}
        </div>
      </Surface>
    </Stack>
  );
}
