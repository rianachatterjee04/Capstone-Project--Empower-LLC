from __future__ import annotations
from statistics import mean


# ---------------------------------------------------------
# PAY COMPRESSION DETECTION
# ---------------------------------------------------------

def detect_pay_compression(employees: list[dict]) -> dict:
    """
    Detects salary compression within same title/level groups.

    employees = [
        { "id": "...", "title": "Software Engineer", "level": 2, "salary": 110000 }
    ]
    """

    groups: dict[tuple, list[dict]] = {}

    for e in employees:
        if not e.get("salary"):
            continue
        key = (e.get("title"), e.get("level"))
        groups.setdefault(key, []).append(e)

    issues = []

    for (title, level), members in groups.items():

        if len(members) < 2:
            continue

        salaries = [m["salary"] for m in members]
        avg = mean(salaries)
        highest = max(salaries)

        for m in members:
            compression_ratio = m["salary"] / highest

            # compression: employee paid too close to top performer
            if compression_ratio > 0.90 and m["salary"] < avg:
                issues.append({
                    "employee_id": m["id"],
                    "title": title,
                    "level": level,
                    "salary": m["salary"],
                    "group_average": round(avg, 2),
                    "compression_ratio": round(compression_ratio, 3),
                    "explanation": "Employee pay is near top of band but below peer average — indicates pay compression risk"
                })

    return {
        "issues": issues,
        "groups_analyzed": len(groups)
    }


# ---------------------------------------------------------
# RAISE SIMULATION
# ---------------------------------------------------------

def simulate_raise(employee: dict, percent: float) -> dict:
    """
    Predict impact of salary increase
    """

    current = float(employee["salary"])
    new_salary = round(current * (1 + percent / 100), 2)
    delta = round(new_salary - current, 2)

    band_mid = estimate_band_mid(employee.get("title"), employee.get("level"))

    positioning = "below_mid"
    if new_salary > band_mid * 1.10:
        positioning = "above_band"
    elif new_salary >= band_mid * 0.95:
        positioning = "at_market"

    return {
        "employee_id": employee["id"],
        "old_salary": current,
        "new_salary": new_salary,
        "change": delta,
        "percent": percent,
        "market_midpoint": band_mid,
        "market_positioning": positioning,
        "explainability": f"Raise moves employee to {positioning} relative to estimated market band midpoint"
    }


# ---------------------------------------------------------
# BAND ESTIMATION (placeholder — replace with real market data later)
# ---------------------------------------------------------

def estimate_band_mid(title: str | None, level: int | None) -> float:
    """
    Simple heuristic band model until real benchmarking plugged in
    """

    if not title:
        return 100000

    base = {
        "engineer": 120000,
        "manager": 150000,
        "director": 190000,
        "hr": 90000,
        "sales": 100000
    }

    key = title.lower()

    for k in base:
        if k in key:
            midpoint = base[k] + (level or 1) * 8000
            return midpoint

    return 100000 + (level or 1) * 7000

