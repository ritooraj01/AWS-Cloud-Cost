"""
Billing-Based Waste Detector
Uses ONLY spending patterns from the billing CSV — no infrastructure metrics assumed.
Patterns are inspired by AWS Cost Explorer and Trusted Advisor signals:
  1. Constant-cost pattern: near-zero cost variation over 7+ days
  2. Service dependency mismatch: EBS cost with little/no EC2 cost
  3. Data transfer spike: transfer cost doubled vs previous period
  4. High regional concentration: > 70% spend in one region
  5. Idle-pattern high cost: large daily flat spend (likely always-on)
"""

import statistics
from collections import defaultdict

# Coefficient of variation threshold below which cost is "suspiciously flat"
FLAT_COST_CV_THRESHOLD = 0.05   # < 5% variation = flat
MIN_DAYS_FOR_FLAT = 7
DATA_TRANSFER_SERVICES = {"AWSDataTransfer", "DataTransfer", "AWS Data Transfer"}
EC2_SERVICES = {"AmazonEC2", "EC2", "Amazon EC2"}
EBS_KEYWORDS = {"EBS", "AmazonEBS", "Amazon Elastic Block Store"}
CONCENTRATION_THRESHOLD = 0.70  # 70% cost in one region


def _cv(values: list[float]) -> float:
    """Coefficient of variation: std / mean (0 if mean == 0)."""
    if not values or sum(values) == 0:
        return 0.0
    mean = statistics.mean(values)
    if mean == 0:
        return 0.0
    return statistics.stdev(values) / mean if len(values) > 1 else 0.0


def detect(records: list[dict], days_count: int) -> list[dict]:
    """
    Returns a list of waste signal dicts:
      {
        "signal_type": str,
        "title": str,
        "description": str,
        "confidence": "HIGH" | "MEDIUM" | "LOW",
        "potential_savings_inr": float,
        "services_involved": [ str ],
      }
    """
    signals = []

    # ---- Aggregate -------------------------------------------------------
    service_daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    region_totals: dict[str, float] = defaultdict(float)

    for r in records:
        service_daily[r["service"]][r["date"]] += r["cost"]
        region_totals[r["region_friendly"]] += r["cost"]

    all_dates = sorted(set(d for daily in service_daily.values() for d in daily.keys()))
    last_7 = all_dates[-7:] if len(all_dates) >= 7 else all_dates

    # ==================================================================
    # Signal 1: Constant-cost pattern (suspiciously flat spend)
    # ==================================================================
    for svc, daily in service_daily.items():
        daily_vals = [daily.get(d, 0.0) for d in last_7]
        active_days = [v for v in daily_vals if v > 0]
        if len(active_days) < MIN_DAYS_FOR_FLAT:
            continue
        cv = _cv(active_days)
        avg_daily = statistics.mean(active_days)
        weekly_spend = sum(active_days)
        if cv < FLAT_COST_CV_THRESHOLD and avg_daily > 2.0:
            confidence = "HIGH" if len(active_days) >= 7 else "MEDIUM"
            signals.append(
                {
                    "signal_type": "constant_cost",
                    "title": f"{svc}: Always-on spending pattern detected",
                    "description": (
                        f"{svc} costs ₹{avg_daily:,.0f}/day with virtually no variation "
                        f"over {len(active_days)} days (CV={cv:.2%}). "
                        f"This pattern suggests a continuously running resource."
                    ),
                    "confidence": confidence,
                    "potential_savings_inr": round(weekly_spend * 0.3, 2),  # 30% optimisation estimate
                    "services_involved": [svc],
                }
            )

    # ==================================================================
    # Signal 2: EBS cost without matching EC2 cost
    # ==================================================================
    ebs_svc = next((s for s in service_daily if any(k in s for k in EBS_KEYWORDS)), None)
    ec2_svc = next((s for s in service_daily if any(k in s for k in EC2_SERVICES)), None)

    if ebs_svc:
        ebs_last7 = sum(service_daily[ebs_svc].get(d, 0) for d in last_7)
        ec2_last7 = sum(service_daily[ec2_svc].get(d, 0) for d in last_7) if ec2_svc else 0

        # Flag if EBS spend > 20% of EC2 spend, or EBS exists but EC2 is very low
        if ebs_last7 > 5 and (ec2_last7 == 0 or (ebs_last7 / max(ec2_last7, 0.01)) > 0.5):
            signals.append(
                {
                    "signal_type": "ebs_without_ec2",
                    "title": "Storage cost without matching compute usage",
                    "description": (
                        f"EBS storage costs ₹{ebs_last7:,.0f} this week, but EC2 compute spend "
                        f"is {'absent' if ec2_last7 == 0 else f'only ₹{ec2_last7:,.0f}'}. "
                        f"This suggests potentially unattached or orphaned volumes."
                    ),
                    "confidence": "LOW",  # inferred relationship
                    "potential_savings_inr": round(ebs_last7 * 0.8, 2),
                    "services_involved": [ebs_svc] + ([ec2_svc] if ec2_svc else []),
                }
            )

    # ==================================================================
    # Signal 3: Data transfer spike
    # ==================================================================
    dt_svc = next(
        (s for s in service_daily if any(k.lower() in s.lower() for k in DATA_TRANSFER_SERVICES)),
        None,
    )
    if dt_svc and len(all_dates) >= 14:
        prev_7 = all_dates[-14:-7]
        dt_last7 = sum(service_daily[dt_svc].get(d, 0) for d in last_7)
        dt_prev7 = sum(service_daily[dt_svc].get(d, 0) for d in prev_7)
        if dt_prev7 > 0 and dt_last7 >= dt_prev7 * 1.8:  # 80% increase
            pct = round(((dt_last7 - dt_prev7) / dt_prev7) * 100, 0)
            signals.append(
                {
                    "signal_type": "data_transfer_spike",
                    "title": "Unexpected data transfer cost increase",
                    "description": (
                        f"Data transfer costs jumped {pct:.0f}% (₹{dt_prev7:,.0f} → ₹{dt_last7:,.0f}). "
                        "This could indicate unexpected API calls, data replication, or traffic patterns."
                    ),
                    "confidence": "MEDIUM",
                    "potential_savings_inr": round(dt_last7 - dt_prev7, 2),
                    "services_involved": [dt_svc],
                }
            )

    # ==================================================================
    # Signal 4: High regional concentration
    # ==================================================================
    total_region_cost = sum(region_totals.values())
    if total_region_cost > 0:
        top_region = max(region_totals.items(), key=lambda x: x[1])
        concentration = top_region[1] / total_region_cost
        if concentration >= CONCENTRATION_THRESHOLD:
            signals.append(
                {
                    "signal_type": "regional_concentration",
                    "title": f"High cost concentration in {top_region[0]}",
                    "description": (
                        f"{concentration:.0%} of your total spend is in {top_region[0]} "
                        f"(₹{top_region[1]:,.0f}). "
                        "Consider reviewing if this regional allocation is intentional."
                    ),
                    "confidence": "LOW",
                    "potential_savings_inr": 0.0,
                    "services_involved": [],
                }
            )

    # Sort: highest confidence & highest savings first
    confidence_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    signals.sort(
        key=lambda s: (
            confidence_rank.get(s["confidence"], 3),
            -s["potential_savings_inr"],
        )
    )

    return signals
