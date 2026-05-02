"""
Smart Suggestions Engine
Maps waste signals and spike data → actionable recommendations.
Each suggestion includes: action, impact (₹/month), confidence, signal_type.
Language is conservative: "potential savings UP TO" — never overpromise.
"""


# Approximate monthly multiplier from weekly costs (4.33 weeks/month)
WEEKLY_TO_MONTHLY = 4.33


def build(waste_signals: list[dict], spike_data: dict, total_cost: float) -> list[dict]:
    """
    Returns a list of suggestion dicts:
      {
        "action": str,
        "detail": str,
        "savings_inr": float,          # ₹/month estimate
        "confidence": "HIGH" | "MEDIUM" | "LOW",
        "signal_type": str,
        "copyable_text": str,           # human-readable for copy button
      }
    """
    suggestions = []
    MIN_SAVINGS_INR = 500  # only include if potential monthly savings > ₹500

    # USD→INR scaling (same heuristic as translator.py)
    scale = 83.0 if total_cost < 500 else 1.0

    for signal in waste_signals:
        raw_savings_weekly = signal.get("potential_savings_inr", 0) * scale
        monthly_est = round(raw_savings_weekly * WEEKLY_TO_MONTHLY, 0)

        if monthly_est < MIN_SAVINGS_INR and signal["signal_type"] not in (
            "data_transfer_spike",
        ):
            continue

        confidence = signal["confidence"]
        sig_type = signal["signal_type"]
        services = signal.get("services_involved", [])
        svc_label = services[0] if services else "resource"

        if sig_type == "constant_cost":
            action = f"Review always-on {svc_label} usage and schedule downtime or right-size"
            detail = (
                f"{svc_label} shows a flat daily cost pattern — indicative of a resource "
                f"running continuously. Consider stopping during off-hours or switching to a "
                f"smaller instance/tier."
            )
            copyable = (
                f"Action: Review {svc_label} usage — potential savings up to "
                f"₹{monthly_est:,.0f}/month ({confidence.title()} confidence)"
            )

        elif sig_type == "ebs_without_ec2":
            action = "Audit EBS volumes for unattached or orphaned storage"
            detail = (
                "Storage billing without matching compute suggests volumes may be unattached. "
                "Go to EC2 → Volumes in AWS Console and check for 'available' state volumes."
            )
            copyable = (
                f"Action: Audit EBS volumes — potential savings up to "
                f"₹{monthly_est:,.0f}/month ({confidence.title()} confidence)"
            )

        elif sig_type == "data_transfer_spike":
            action = "Investigate unexpected data transfer usage"
            detail = (
                "A sudden jump in data transfer costs can signal API misconfiguration, "
                "accidental cross-region replication, or unexpected traffic. Check CloudWatch "
                "for network metrics."
            )
            monthly_est = max(monthly_est, MIN_SAVINGS_INR)
            copyable = (
                f"Action: Investigate data transfer spike — potential savings vary "
                f"({confidence.title()} confidence)"
            )

        elif sig_type == "regional_concentration":
            action = "Confirm all regional resources are intentionally active"
            detail = (
                "High cost concentration in one region is fine if intentional, but verify "
                "no test or dev resources are running in unexpected regions."
            )
            copyable = (
                f"Action: Audit regional spend allocation ({confidence.title()} confidence)"
            )
        else:
            continue

        suggestions.append(
            {
                "action": action,
                "detail": detail,
                "savings_inr": monthly_est,
                "confidence": confidence,
                "signal_type": sig_type,
                "copyable_text": copyable,
            }
        )

    # ---- If spike detected, add a generic investigate suggestion ---------
    if spike_data.get("spike_detected") and spike_data.get("affected_services"):
        top_svc = spike_data["affected_services"][0]
        svc_name = top_svc["service"]
        change_amt = round(top_svc.get("change_amount", 0) * scale * WEEKLY_TO_MONTHLY, 0)
        if change_amt >= MIN_SAVINGS_INR:
            suggestions.append(
                {
                    "action": f"Investigate {svc_name} usage spike and consider scaling down",
                    "detail": (
                        f"{svc_name} shows a {top_svc['change_pct']:+.0f}% cost increase. "
                        "If this is unexpected, review running resources in the AWS console."
                    ),
                    "savings_inr": change_amt,
                    "confidence": "MEDIUM",
                    "signal_type": "spike",
                    "copyable_text": (
                        f"Action: Investigate {svc_name} spike — potential savings up to "
                        f"₹{change_amt:,.0f}/month (Medium confidence)"
                    ),
                }
            )

    # Sort by savings descending
    suggestions.sort(key=lambda s: s["savings_inr"], reverse=True)
    return suggestions
