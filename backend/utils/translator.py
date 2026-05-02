"""
Human Language Translator
Converts raw analysis data into plain English sentences.
Target tone: direct, clear, actionable — "explain like I'm 5."
All amounts in INR (₹). 1 USD ≈ 93 INR conversion applied if costs look USD-scale.
"""

# Rough conversion: if costs look like USD values (< 500 total),
# multiply by this factor for display.  Can be disabled/overridden.
USD_TO_INR = 93.0


def _maybe_inr(amount: float, total_cost: float) -> float:
    """If total_cost looks like USD scale, multiply by USD_TO_INR."""
    if total_cost < 500:
        return amount * USD_TO_INR
    return amount


def translate_summary(period_comparison: dict, total_cost: float) -> dict:
    """
    Produce human-readable summary sentences + formatted display values.
    """
    last7 = _maybe_inr(period_comparison["last_7_days"]["total"], total_cost)
    prev7 = _maybe_inr(period_comparison["previous_7_days"]["total"], total_cost)
    change_pct = period_comparison["change_percentage"]
    change_amt = _maybe_inr(abs(period_comparison["change_amount"]), total_cost)

    if change_pct > 0:
        trend_text = f"Your cloud spend went UP ₹{change_amt:,.0f} compared to last week (+{change_pct:.0f}%)."
        trend_emoji = "🔴"
        trend_label = f"+{change_pct:.0f}%"
    elif change_pct < 0:
        trend_text = f"Your cloud spend went DOWN ₹{change_amt:,.0f} compared to last week ({change_pct:.0f}%)."
        trend_emoji = "🟢"
        trend_label = f"{change_pct:.0f}%"
    else:
        trend_text = "Your cloud spend is stable compared to last week."
        trend_emoji = "🟡"
        trend_label = "~0%"

    return {
        "last_7_days_inr": round(last7, 0),
        "previous_7_days_inr": round(prev7, 0),
        "change_pct": change_pct,
        "change_amount_inr": round(change_amt, 0),
        "trend_emoji": trend_emoji,
        "trend_label": trend_label,
        "narrative": trend_text,
    }


def translate_driver(driver: dict, total_cost: float) -> str:
    """Convert a cost driver dict to a plain English sentence."""
    svc = driver["service"]
    amt = _maybe_inr(driver["impact_amount"], total_cost)
    pct = driver["impact_percentage"]
    cat = driver["category"]

    if cat == "new_service":
        return (
            f"A new AWS service appeared on your bill: {svc} cost ₹{amt:,.0f} "
            f"this week — it wasn't there before."
        )
    elif cat == "increase":
        days_context = "likely due to increased or prolonged usage" if pct < 100 else "a significant change in usage patterns"
        return (
            f"You spent ₹{amt:,.0f} MORE on {svc} this week ({pct:+.0f}% increase), {days_context}."
        )
    elif cat == "consistent_high":
        return (
            f"{svc} has been your biggest spend at ₹{amt:,.0f} this week — "
            f"it's been consistently high with no sign of reduction."
        )
    return driver.get("description", "")


def translate_waste_signal(signal: dict, total_cost: float) -> str:
    """Convert a waste signal to a plain English insight."""
    sig_type = signal["signal_type"]
    savings = _maybe_inr(signal["potential_savings_inr"], total_cost)

    if sig_type == "constant_cost":
        svc = signal["services_involved"][0] if signal["services_involved"] else "A service"
        return (
            f"{svc} is spending the same amount every single day — like a light you forgot to turn off. "
            f"If this resource isn't needed 24/7, you could save up to ₹{savings:,.0f}/week."
        )
    elif sig_type == "ebs_without_ec2":
        return (
            f"You're paying for cloud storage (EBS) but your compute (EC2) usage is low. "
            f"These might be volumes attached to stopped or deleted servers — "
            f"potential savings up to ₹{savings:,.0f}/week."
        )
    elif sig_type == "data_transfer_spike":
        return (
            f"Your data transfer costs jumped unexpectedly. This could be from an API bug, "
            f"accidental data replication, or new traffic. Worth investigating before it compounds."
        )
    elif sig_type == "regional_concentration":
        return (
            f"Almost all your cloud spend is in one region. "
            f"This is fine if intentional — but worth confirming no resources are running elsewhere by mistake."
        )
    return signal.get("description", "")


def translate_suggestion(suggestion: dict, total_cost: float) -> str:
    """Convert a suggestion to a plain English action sentence."""
    savings = _maybe_inr(suggestion.get("savings_inr", 0), total_cost)
    action = suggestion.get("action", "Review this resource")
    confidence = suggestion.get("confidence", "MEDIUM")
    conf_text = {"HIGH": "very likely", "MEDIUM": "possibly", "LOW": "potentially"}.get(confidence, "possibly")

    return (
        f"{action} — this could {conf_text} save you up to ₹{savings:,.0f}/month."
    )
