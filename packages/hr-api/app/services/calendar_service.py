"""Unified people-ops calendar.

Pulls together PTO, anniversaries (work + birth dates if available), comp
cycle key dates, learning deadlines, hiring kick-offs, and onboarding
milestones into one calendar feed.

The frontend treats it as a calm month view; the API returns a flat list
ordered by date so the page can group however it likes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class CalendarEvent:
    id: str
    kind: str               # pto | anniversary | cycle | learning | hiring | onboarding | system
    title: str
    detail: str = ""
    subject: Optional[str] = None
    start: str = ""
    end: Optional[str] = None
    all_day: bool = True
    tone: str = "neutral"   # neutral | info | warn | success | danger
    cta_label: Optional[str] = None
    cta_href: Optional[str] = None
    # True for the illustrative cycle/learning/hiring entries this service
    # ships. Events read from PTO requests, employee start dates and onboarding
    # packets are the organisation's own and leave this False.
    is_sample: bool = False

    def to_dict(self) -> dict:
        return self.__dict__


async def _rows(db: AsyncSession, sql: str, params: dict) -> list[dict]:
    try:
        res = await db.execute(text(sql), params)
        return [dict(r) for r in res.mappings().all()]
    except Exception:
        return []


def _iso(d) -> str:
    if d is None:
        return ""
    if isinstance(d, datetime):
        return d.isoformat()
    if isinstance(d, date):
        return d.isoformat()
    return str(d)


async def upcoming(db: AsyncSession, org_id: str, *, days: int = 30) -> dict:
    out: list[CalendarEvent] = []

    # 1. PTO requests within window
    pto_rows = await _rows(
        db,
        """
        select r.id::text as id, r.start_date, r.end_date, r.status, r.reason,
               e.legal_name as employee
        from public.pto_requests r
        left join public.employees e on e.id = r.employee_id
        where r.org_id=:org and r.start_date >= current_date - interval '7 days'
                          and r.start_date <= current_date + (:days || ' days')::interval
        order by r.start_date
        """,
        {"org": org_id, "days": days},
    )
    for r in pto_rows:
        out.append(CalendarEvent(
            id=f"pto-{r['id']}",
            kind="pto",
            title=f"{r.get('employee') or 'Employee'} · PTO",
            detail=r.get("reason") or "",
            subject=r.get("employee"),
            start=_iso(r["start_date"]),
            end=_iso(r.get("end_date") or r["start_date"]),
            tone="info" if r.get("status") == "approved" else "warn",
            cta_label="Open PTO",
            cta_href="/app/pto",
        ))

    # 2. Work anniversaries from employees.start_date within window
    emp_rows = await _rows(
        db,
        """
        select id::text as id, legal_name, start_date, job_title
        from public.employees
        where org_id=:org and start_date is not null
        """,
        {"org": org_id},
    )
    today = datetime.now(timezone.utc).date()
    for e in emp_rows:
        sd = e.get("start_date")
        if not sd:
            continue
        try:
            sd_date = sd if isinstance(sd, date) else datetime.fromisoformat(str(sd)).date()
        except Exception:
            continue
        # next anniversary date (this year or next)
        try:
            this_year = sd_date.replace(year=today.year)
        except ValueError:
            this_year = sd_date.replace(year=today.year, day=28)
        if this_year < today:
            try:
                this_year = sd_date.replace(year=today.year + 1)
            except ValueError:
                this_year = sd_date.replace(year=today.year + 1, day=28)
        years = this_year.year - sd_date.year
        delta = (this_year - today).days
        if 0 <= delta <= days:
            out.append(CalendarEvent(
                id=f"anniv-{e['id']}",
                kind="anniversary",
                title=f"{e['legal_name']} · {years}-year anniversary",
                detail=e.get("job_title") or "—",
                subject=e["legal_name"],
                start=this_year.isoformat(),
                tone="success",
                cta_label="Open twin",
                cta_href=f"/app/digital-twin?id={e['id']}",
            ))

    # 3. Synthetic cycle + learning deadlines (until backed by tables)
    now = datetime.now(timezone.utc)
    cycle_events = [
        ("cycle-cal-1", "cycle", "Q3 review calibration", "HR + leadership · cross-team rater drift review.", now + timedelta(days=8), "info", "Open cycle", "/app/performance"),
        ("cycle-cal-2", "cycle", "Q3 comp finance approval", "CFO sign-off window.", now + timedelta(days=12), "warn", "Open finance", "/app/finance"),
        ("cycle-cal-3", "cycle", "Q3 review delivery", "Managers deliver reviews to reports.", now + timedelta(days=20), "info", "Open cycle", "/app/performance"),
        ("learn-cal-1", "learning", "SOC 2 training due", "3 employees overdue. Send reminders this week.", now + timedelta(days=4), "warn", "Open compliance", "/app/compliance"),
        ("hire-cal-1", "hiring", "Avery Chen onboarding · Day 1", "Equipment shipped; buddy assigned.", now + timedelta(days=6), "success", "Open onboarding", "/app/onboarding"),
        ("hire-cal-2", "hiring", "Diego Marin · offer expires", "Mid-market AE; needs CFO sign-off.", now + timedelta(days=2), "danger", "Open CRM", "/app/crm"),
        ("onb-cal-1", "onboarding", "Riley Singh · 30-day check-in", "Manager 1:1 + stakeholder map.", now + timedelta(days=15), "info", "Open onboarding", "/app/onboarding"),
        ("sys-cal-1", "system", "Open enrollment opens", "Annual benefits enrollment window.", now + timedelta(days=21), "info", "Open benefits", "/app/benefits"),
    ]
    # SAMPLE EVENTS. Every entry in cycle_events is a literal — "Diego Marin ·
    # offer expires", "SOC 2 training due · 3 employees overdue", "Avery Chen
    # onboarding · Day 1" — and they sit on the same timeline as the PTO,
    # anniversaries and onboarding read from this organisation's own records.
    # "3 employees overdue" is a compliance claim, made for a company with one
    # employee and no such training record.
    #
    # They are marked so the page can label them; deleting them would leave a
    # calendar that demonstrates nothing.
    for eid, kind, title, detail, when, tone, cta_label, cta_href in cycle_events:
        if (when.date() - today).days <= days and (when.date() - today).days >= -2:
            out.append(CalendarEvent(
                id=eid, kind=kind, title=title, detail=detail, is_sample=True,
                start=when.date().isoformat(),
                tone=tone, cta_label=cta_label, cta_href=cta_href,
            ))

    out.sort(key=lambda e: e.start)
    counts: dict[str, int] = {}
    for e in out:
        counts[e.kind] = counts.get(e.kind, 0) + 1

    return {
        "items": [e.to_dict() for e in out],
        "counts": counts,
        "window_days": days,
    }
