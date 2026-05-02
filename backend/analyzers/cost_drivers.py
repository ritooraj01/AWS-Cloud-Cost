"""
Top 3 Cost Drivers
Ranks the biggest reasons the bill changed using this priority:
  1. Absolute cost increase (₹ impact) — highest priority
  2. Percentage increase                — tiebreaker
  3. New service detection              — always included if found
"""

from collections import defaultdict


def find(records: list[dict], days_count: int) -> list[dict]:
    """
    Returns up to 3 cost driver dicts, each:
      {
        "rank": 1-3,
        "description": "Short label",
        "impact_amount": float,      # absolute ₹ difference (last7 - prev7)
        "impact_percentage": float,  # % change
        "service": str,
        "region": str | None,
        "category": "increase" | "new_service" | "consistent_high",
        "confidence": "HIGH" | "MEDIUM" | "LOW",
      }
    """
    if days_count < 7:
        return []

    # ---- Build per-service daily costs ----------------------------------
    service_daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in records:
        service_daily[r["service"]][r["date"]] += r["cost"]

    all_dates = sorted(
        set(d for daily in service_daily.values() for d in daily.keys())
    )
    last_7 = set(all_dates[-7:])
    prev_7 = set(all_dates[-14:-7]) if len(all_dates) >= 14 else set(all_dates[: max(0, len(all_dates) - 7)])

    drivers = []

    for svc, daily in service_daily.items():
        last_total = sum(v for d, v in daily.items() if d in last_7)
        prev_total = sum(v for d, v in daily.items() if d in prev_7)

        # --- Category: New service (appeared only in last 7 days) --------
        if prev_total == 0 and last_total > 0:
            drivers.append(
                {
                    "service": svc,
                    "impact_amount": round(last_total, 2),
                    "impact_percentage": 100.0,
                    "category": "new_service",
                    "confidence": "MEDIUM",
                    "description": f"New service detected: {svc} (₹{last_total:,.0f} this week)",
                    "region": None,
                }
            )
            continue

        # --- Category: Meaningful increase --------------------------------
        if prev_total > 0 and last_total > prev_total:
            diff = last_total - prev_total
            pct = round((diff / prev_total) * 100, 1)
            if diff > 1.0 or pct >= 10:  # filter trivial noise
                # Confidence: sustained 7-day high → HIGH; short spike → MEDIUM
                days_in_last = sum(1 for d in last_7 if daily.get(d, 0) > 0)
                confidence = "HIGH" if days_in_last >= 6 else "MEDIUM"
                drivers.append(
                    {
                        "service": svc,
                        "impact_amount": round(diff, 2),
                        "impact_percentage": pct,
                        "category": "increase",
                        "confidence": confidence,
                        "description": f"{svc} cost increased ₹{diff:,.0f} ({pct:+.0f}%) this week",
                        "region": None,
                    }
                )

        # --- Category: Consistently high (tops last7, no spike but big) --
        elif prev_total > 0 and last_total >= prev_total * 0.9 and last_total >= prev_total:
            if last_total > 10:  # only flag meaningful amounts
                drivers.append(
                    {
                        "service": svc,
                        "impact_amount": round(last_total, 2),
                        "impact_percentage": 0.0,
                        "category": "consistent_high",
                        "confidence": "HIGH",
                        "description": f"{svc} continues high spend at ₹{last_total:,.0f} this week",
                        "region": None,
                    }
                )

    # ---- Sort by priority: category rank → absolute impact ---------------
    category_rank = {"increase": 0, "new_service": 1, "consistent_high": 2}
    drivers.sort(
        key=lambda d: (
            # Put "increase" first, then sort by absolute impact descending
            category_rank.get(d["category"], 3),
            -d["impact_amount"],
        )
    )

    # ---- Take top 3 and assign ranks ------------------------------------
    top3 = drivers[:3]
    for i, d in enumerate(top3):
        d["rank"] = i + 1

    return top3
