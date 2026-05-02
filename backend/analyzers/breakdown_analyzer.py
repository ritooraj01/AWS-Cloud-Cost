"""
Cost Breakdown Analyzer
Produces:
  - Top 5 services by total cost
  - Daily cost trend (last 14 days)
  - Region-wise cost distribution
  - Before/After 7-day split totals + averages
"""

from collections import defaultdict
from datetime import date, timedelta


def analyze(records: list[dict]) -> dict:
    """
    Args:
        records: normalised list from aws_parser.parse()["records"]
    Returns a dict with breakdown data.
    """
    # ---- Aggregate by service -------------------------------------------
    service_totals: dict[str, float] = defaultdict(float)
    region_totals: dict[str, float] = defaultdict(float)
    daily_totals: dict[str, float] = defaultdict(float)

    for r in records:
        service_totals[r["service"]] += r["cost"]
        region_totals[r["region_friendly"]] += r["cost"]
        daily_totals[r["date"]] += r["cost"]

    # ---- Top 5 services --------------------------------------------------
    top_services = sorted(service_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    top_services_list = [
        {"service": svc, "total_cost": round(cost, 2)}
        for svc, cost in top_services
    ]

    # ---- Daily trend (last 14 days in data) ------------------------------
    sorted_dates = sorted(daily_totals.keys())
    last_14 = sorted_dates[-14:] if len(sorted_dates) >= 14 else sorted_dates
    daily_trend = [
        {"date": d, "cost": round(daily_totals[d], 2)}
        for d in last_14
    ]

    # ---- Region breakdown ------------------------------------------------
    total_cost = sum(region_totals.values())
    region_breakdown = sorted(
        [
            {
                "region": region,
                "total_cost": round(cost, 2),
                "percentage": round((cost / total_cost * 100) if total_cost else 0, 1),
            }
            for region, cost in region_totals.items()
        ],
        key=lambda x: x["total_cost"],
        reverse=True,
    )

    # ---- Before / After 7-day split -------------------------------------
    all_dates = sorted(daily_totals.keys())
    last_7_dates = all_dates[-7:] if len(all_dates) >= 7 else all_dates
    prev_7_dates = (
        all_dates[-14:-7] if len(all_dates) >= 14 else all_dates[: max(0, len(all_dates) - 7)]
    )

    last_7_total = sum(daily_totals[d] for d in last_7_dates)
    prev_7_total = sum(daily_totals[d] for d in prev_7_dates)
    last_7_avg = last_7_total / len(last_7_dates) if last_7_dates else 0
    prev_7_avg = prev_7_total / len(prev_7_dates) if prev_7_dates else 0

    if prev_7_total > 0:
        change_pct = round(((last_7_total - prev_7_total) / prev_7_total) * 100, 1)
    else:
        change_pct = 0.0

    period_comparison = {
        "last_7_days": {
            "dates": last_7_dates,
            "total": round(last_7_total, 2),
            "daily_avg": round(last_7_avg, 2),
        },
        "previous_7_days": {
            "dates": prev_7_dates,
            "total": round(prev_7_total, 2),
            "daily_avg": round(prev_7_avg, 2),
        },
        "change_percentage": change_pct,
        "change_amount": round(last_7_total - prev_7_total, 2),
    }

    return {
        "total_cost": round(total_cost, 2),
        "top_services": top_services_list,
        "daily_trend": daily_trend,
        "region_breakdown": region_breakdown,
        "period_comparison": period_comparison,
    }
