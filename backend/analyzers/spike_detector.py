"""
Spike Detector
Compares last 7 days vs previous 7 days.
Requires minimum 7 days of data; gracefully degrades with fewer days.
"""

from collections import defaultdict


SPIKE_THRESHOLD_PCT = 15.0  # % increase needed to flag a spike


def detect(records: list[dict], days_count: int) -> dict:
    """
    Returns:
      {
        "spike_detected": bool,
        "insufficient_data": bool,
        "reason": str,          # human-readable note
        "overall_change_pct": float,
        "spike_magnitude": str, # "low" | "medium" | "high"
        "affected_services": [ {service, prev_avg, last_avg, change_pct}, ... ],
        "affected_regions":  [ {region, prev_avg, last_avg, change_pct}, ... ],
      }
    """
    # ---- Edge case: not enough days ------------------------------------
    if days_count < 7:
        return {
            "spike_detected": False,
            "insufficient_data": True,
            "reason": f"Spike detection requires at least 7 days of data. Your CSV contains {days_count} day(s).",
            "overall_change_pct": 0.0,
            "spike_magnitude": None,
            "affected_services": [],
            "affected_regions": [],
        }

    # ---- Aggregate daily totals per service / region ------------------
    daily_total: dict[str, float] = defaultdict(float)
    service_daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    region_daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for r in records:
        d = r["date"]
        daily_total[d] += r["cost"]
        service_daily[r["service"]][d] += r["cost"]
        region_daily[r["region_friendly"]][d] += r["cost"]

    all_dates = sorted(daily_total.keys())
    last_7 = all_dates[-7:]
    prev_7 = all_dates[-14:-7] if len(all_dates) >= 14 else all_dates[: max(0, len(all_dates) - 7)]

    def period_avg(daily_dict: dict[str, float], dates: list[str]) -> float:
        vals = [daily_dict.get(d, 0.0) for d in dates]
        return sum(vals) / len(vals) if vals else 0.0

    def pct_change(prev: float, last: float) -> float:
        if prev == 0:
            return 100.0 if last > 0 else 0.0
        return round(((last - prev) / prev) * 100, 1)

    # ---- Overall spike --------------------------------------------------
    overall_prev = period_avg(daily_total, prev_7)
    overall_last = period_avg(daily_total, last_7)
    overall_pct = pct_change(overall_prev, overall_last)
    spike_detected = overall_pct >= SPIKE_THRESHOLD_PCT

    # ---- Magnitude label -----------------------------------------------
    if overall_pct >= 50:
        magnitude = "high"
    elif overall_pct >= 25:
        magnitude = "medium"
    elif overall_pct >= SPIKE_THRESHOLD_PCT:
        magnitude = "low"
    else:
        magnitude = None

    # ---- Per-service breakdown -----------------------------------------
    affected_services = []
    for svc, daily in service_daily.items():
        prev_avg = period_avg(daily, prev_7)
        last_avg = period_avg(daily, last_7)
        pct = pct_change(prev_avg, last_avg)
        if pct >= SPIKE_THRESHOLD_PCT and last_avg > 0:
            affected_services.append(
                {
                    "service": svc,
                    "prev_7day_avg": round(prev_avg, 2),
                    "last_7day_avg": round(last_avg, 2),
                    "change_pct": pct,
                    "change_amount": round((last_avg - prev_avg) * 7, 2),
                }
            )
    affected_services.sort(key=lambda x: x["change_amount"], reverse=True)

    # ---- Per-region breakdown ------------------------------------------
    affected_regions = []
    for region, daily in region_daily.items():
        prev_avg = period_avg(daily, prev_7)
        last_avg = period_avg(daily, last_7)
        pct = pct_change(prev_avg, last_avg)
        if pct >= SPIKE_THRESHOLD_PCT and last_avg > 0:
            affected_regions.append(
                {
                    "region": region,
                    "prev_7day_avg": round(prev_avg, 2),
                    "last_7day_avg": round(last_avg, 2),
                    "change_pct": pct,
                }
            )
    affected_regions.sort(key=lambda x: x["change_pct"], reverse=True)

    reason = (
        "No unusual spending detected 👍"
        if not spike_detected
        else f"Overall spend increased {overall_pct:+.1f}% compared to previous 7 days."
    )

    return {
        "spike_detected": spike_detected,
        "insufficient_data": False,
        "reason": reason,
        "overall_change_pct": overall_pct,
        "spike_magnitude": magnitude,
        "affected_services": affected_services,
        "affected_regions": affected_regions,
    }
