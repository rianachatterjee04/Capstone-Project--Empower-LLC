"""Narrative analytics.

Story-first numbers. The page shows a small set of insights — each is a
sentence + a single tiny chart + a "what AI suggests" footer.

EVERY INSIGHT HERE IS COMPUTED. That is a correction, not a description of how
it always was. Two of the four insights this module returned were invented
end to end:

  "Engineering attrition signal is rising, concentrated on senior ICs ...
   Two of three high-risk employees are sub-band on comp and overdue for a
   promotion conversation."   metric "2 of 3 in Eng", delta "up 1 vs. last
   month", trend [0,0,1,1,2,2,3] — no query behind any of it, and the demo org
   has one employee, a CDL driver, and no engineering department.

  "Loaded annual payroll is 17% under the $2.4M comp envelope ... Q3 comp cycle
   adds another 3%."   metric "-17.3%", trend [1.7 ... 1.98] — a financial
   claim, also with no query.

The other two mixed real counts with invented detail ("Sales and Customer
Success have the thinnest funnel", "3 SOC 2 trainings overdue", "No payroll
anomalies this period") and six invented history points followed by one real
value, drawn as a trend.

A page that says "what's changed, why, and what AI suggests next" and then
recommends running a comp review over fabricated attrition is worse than a page
with fewer insights. So:

  * an insight exists only if a query produced it;
  * `evidence` names that query, and the API returns it;
  * a chart is drawn only from real history, never padded to a nicer shape;
  * what cannot be computed is listed as such, with what it would take.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class NarrativeChart:
    series: list[float]
    labels: list[str]
    suffix: str = ""

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class Insight:
    id: str
    headline: str
    narrative: str
    metric_label: str
    metric_value: str
    delta_label: Optional[str] = None
    delta_direction: str = "flat"   # up | down | flat
    delta_tone: str = "neutral"
    chart: Optional[NarrativeChart] = None
    suggested_action: Optional[str] = None
    cta_label: Optional[str] = None
    cta_href: Optional[str] = None
    # What this insight was computed from, in the reader's words. An insight
    # that cannot name its source does not belong on the page.
    evidence: str = ""

    def to_dict(self) -> dict:
        return {**self.__dict__, "chart": self.chart.to_dict() if self.chart else None}


async def _scalar(db: AsyncSession, sql: str, params: dict) -> int:
    try:
        row = (await db.execute(text(sql), params)).first()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


async def _monthly(db: AsyncSession, table: str, column: str, org_id: str,
                   months: int = 6) -> tuple[list[float], list[str]]:
    """Real counts per calendar month, oldest first, from `table`.`column`.

    Returns ([], []) when the query fails or the table is empty. The caller
    must then draw NO chart — six invented points and one real one is how the
    old version made a straight line look like a trend.
    """
    try:
        rows = (await db.execute(text(f"""
            SELECT to_char(date_trunc('month', {column}), 'Mon') AS label,
                   date_trunc('month', {column}) AS bucket,
                   count(*) AS n
              FROM public.{table}
             WHERE org_id = :org
               AND {column} >= date_trunc('month', current_date)
                             - make_interval(months => :m)
             GROUP BY 1, 2
             ORDER BY 2
        """), {"org": org_id, "m": months - 1})).mappings().all()
    except Exception:
        return [], []
    return [float(r["n"]) for r in rows], [r["label"] for r in rows]


async def build(db: AsyncSession, org_id: str) -> dict:
    employees = await _scalar(db, "select count(*) from public.employees where org_id=:org", {"org": org_id})
    open_jobs = await _scalar(db, "select count(*) from public.job_postings where org_id=:org and status<>'closed'", {"org": org_id})
    candidates = await _scalar(db, "select count(*) from public.candidates where org_id=:org", {"org": org_id})
    cases_high = await _scalar(db, "select count(*) from public.cases where org_id=:org and severity='high' and status<>'closed'", {"org": org_id})

    insights: list[Insight] = []
    unavailable: list[dict] = []

    # ── headcount, from employees.status ────────────────────────────────────
    active = await _scalar(db, "select count(*) from public.employees "
                               "where org_id=:org and status='active'", {"org": org_id})
    departed = employees - active
    starts, start_labels = await _monthly(db, "employees", "start_date", org_id)
    if employees:
        insights.append(Insight(
            id="ins-headcount",
            headline=(f"{active} active employee{'s' if active != 1 else ''} on record"
                      + (f", {departed} no longer active" if departed else "")),
            narrative=(
                f"{employees} employee record{'s' if employees != 1 else ''} in this "
                f"organisation, {active} with status active"
                + (f" and {departed} not." if departed else ".")
                + (" Start dates are recorded, so the trend below is actual starts per month."
                   if starts else
                   " No start dates are recorded, so there is no trend to draw.")
            ),
            metric_label="Active employees",
            metric_value=str(active),
            delta_label=(f"{departed} inactive" if departed else "all active"),
            delta_direction="down" if departed else "flat",
            delta_tone="warn" if departed else "success",
            chart=(NarrativeChart(series=starts, labels=start_labels) if len(starts) > 1 else None),
            suggested_action=None,
            cta_label="Open people",
            cta_href="/app/people",
            evidence="count of public.employees by status; trend is starts per month from employees.start_date",
        ))

    # ── pipeline coverage, from candidates and open requisitions ────────────
    if open_jobs or candidates:
        coverage = (candidates / open_jobs) if open_jobs else 0.0
        cand_series, cand_labels = await _monthly(db, "candidates", "created_at", org_id)
        insights.append(Insight(
            id="ins-pipeline",
            headline=("Pipeline coverage is thin for current open requisitions"
                      if open_jobs and coverage < 5 else
                      "Pipeline coverage against open requisitions"),
            narrative=(
                f"{candidates} candidate{'s' if candidates != 1 else ''} across "
                f"{open_jobs} open requisition{'s' if open_jobs != 1 else ''}"
                + (f" ({coverage:.1f}x coverage)." if open_jobs else
                   " — no requisitions are open, so coverage is undefined.")
                + " A commonly cited healthy ratio is around 5x per role; that is a"
                  " rule of thumb, not a measurement of this company."
            ),
            metric_label="Pipeline coverage",
            metric_value=(f"{coverage:.1f}x" if open_jobs else "n/a"),
            delta_label="Rule of thumb: 5x",
            delta_direction="down" if open_jobs and coverage < 5 else "flat",
            delta_tone="warn" if open_jobs and coverage < 5 else "neutral",
            chart=(NarrativeChart(series=cand_series, labels=cand_labels)
                   if len(cand_series) > 1 else None),
            suggested_action=None,
            cta_label="Open talent",
            cta_href="/app/talent",
            evidence="count of public.candidates over public.job_postings where status<>'closed'; "
                     "trend is candidates created per month",
        ))

    # ── screening backlog, from candidates.ai_score ─────────────────────────
    unscreened = await _scalar(db, "select count(*) from public.candidates "
                                   "where org_id=:org and ai_score is null", {"org": org_id})
    if candidates:
        insights.append(Insight(
            id="ins-screening",
            headline=(f"{unscreened} of {candidates} candidates have not been screened"
                      if unscreened else "Every candidate on file has been screened"),
            narrative=(
                f"{unscreened} candidate record{'s' if unscreened != 1 else ''} "
                f"ha{'ve' if unscreened != 1 else 's'} no AI score. "
                "Not screened is not a low score — these carry no assessment at all, "
                "and any ranking that silently treats them as zero is wrong."
                if unscreened else
                "Every candidate on file carries an AI score."
            ),
            metric_label="Unscreened candidates",
            metric_value=f"{unscreened} of {candidates}",
            delta_label=None,
            delta_direction="flat",
            delta_tone="warn" if unscreened else "success",
            chart=None,
            suggested_action=("Run screening on the unscreened records before comparing candidates."
                              if unscreened else None),
            cta_label="Open recruiting",
            cta_href="/app/recruiting",
            evidence="count of public.candidates where ai_score is null",
        ))

    # ── open high-severity cases ────────────────────────────────────────────
    if cases_high:
        insights.append(Insight(
            id="ins-cases",
            headline=f"{cases_high} high-severity case{'s' if cases_high != 1 else ''} open",
            narrative="Open cases at high severity, from the employee-relations record.",
            metric_label="High-severity cases",
            metric_value=str(cases_high),
            delta_label=None,
            delta_direction="flat",
            delta_tone="danger",
            chart=None,
            suggested_action=None,
            cta_label="Open compliance",
            cta_href="/app/compliance",
            evidence="count of public.cases where severity='high' and status<>'closed'",
        ))

    # ── what this page cannot tell you, and why ─────────────────────────────
    #
    # These two USED to be the most confident insights on the screen. Naming
    # them as gaps is the honest version of what they were.
    unavailable.append({
        "topic": "Attrition risk",
        "reason": "no termination dates or attrition signals are recorded against "
                  "employees, so leaver rates and at-risk cohorts cannot be computed.",
        "needs": "employee termination dates, or a connected HRIS feed.",
    })
    unavailable.append({
        "topic": "Payroll against budget",
        "reason": "payroll runs live in a separate service and no compensation "
                  "envelope is configured for this organisation.",
        "needs": "a payroll connection and a comp budget.",
    })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "insights": [i.to_dict() for i in insights],
        "unavailable": unavailable,
        "note": ("Every insight above is computed from this organisation's own "
                 "records and names the query it came from. Topics with no "
                 "evidence are listed as unavailable rather than estimated."),
    }
