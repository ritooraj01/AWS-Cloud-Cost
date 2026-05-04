"""
Human Language Translator
Converts raw analysis data into plain English sentences.
Target tone: direct, clear, actionable — "explain like I'm 5."
All amounts displayed in INR (₹). USD is converted at 1 USD = 83 INR.
"""

USD_TO_INR = 83.0


def _to_inr(amount: float, currency: str = "USD") -> float:
    """Convert an amount to INR. Always converts USD at fixed rate."""
    if currency == "USD":
        return amount * USD_TO_INR
    return amount


def translate_summary(
    period_comparison: dict,
    total_cost: float,
    currency: str = "USD",
    period_label: str = "Last 7 Days",
    prev_period_label: str = "Previous 7 Days",
) -> dict:
    """
    Produce human-readable summary sentences + formatted display values.
    """
    last7_raw = period_comparison["last_7_days"]["total"]
    prev7_raw = period_comparison["previous_7_days"]["total"]
    change_pct = period_comparison["change_percentage"]

    last7 = _to_inr(last7_raw, currency)
    prev7 = _to_inr(prev7_raw, currency)
    change_amt = _to_inr(abs(period_comparison["change_amount"]), currency)

    no_prev_data = prev7_raw == 0 and last7_raw > 0

    if no_prev_data:
        # Single period — no comparison available
        usd_note = f" (~${last7_raw:,.2f})" if currency == "USD" else ""
        trend_text = (
            f"Your AWS bill for this period is ₹{last7:,.0f}{usd_note}. "
            f"No previous period data is available for comparison."
        )
        trend_emoji = "🟡"
        trend_label = "N/A"
        change_pct = 0.0
        change_amt = 0.0
    elif change_pct > 0:
        trend_text = f"Your cloud spend went UP ₹{change_amt:,.0f} compared to the previous period (+{change_pct:.0f}%)."
        trend_emoji = "🔴"
        trend_label = f"+{change_pct:.0f}%"
    elif change_pct < 0:
        trend_text = f"Your cloud spend went DOWN ₹{change_amt:,.0f} compared to the previous period ({change_pct:.0f}%)."
        trend_emoji = "🟢"
        trend_label = f"{change_pct:.0f}%"
    else:
        trend_text = "Your cloud spend is stable compared to the previous period."
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
        "period_label": period_label,
        "prev_period_label": prev_period_label,
    }


def translate_driver(driver: dict, total_cost: float, currency: str = "USD") -> str:
    """Convert a cost driver dict to a plain English sentence."""
    svc = driver["service"]
    amt = _to_inr(driver["impact_amount"], currency)
    pct = driver["impact_percentage"]
    cat = driver["category"]

    if cat == "high_spender":
        return (
            f"{svc} is your #{driver.get('rank', '')} biggest cost at ₹{amt:,.0f} "
            f"({pct:.0f}% of your total bill)."
        )
    elif cat == "new_service":
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


def translate_waste_signal(signal: dict, total_cost: float, currency: str = "USD") -> str:
    """Convert a waste signal to a plain English insight."""
    sig_type = signal["signal_type"]
    savings = _to_inr(signal["potential_savings_inr"], currency)

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


def translate_suggestion(suggestion: dict, total_cost: float, currency: str = "USD") -> str:
    """Convert a suggestion to a plain English action sentence."""
    savings = _to_inr(suggestion.get("savings_inr", 0), currency)
    action = suggestion.get("action", "Review this resource")
    confidence = suggestion.get("confidence", "MEDIUM")
    conf_text = {"HIGH": "very likely", "MEDIUM": "possibly", "LOW": "potentially"}.get(confidence, "possibly")

    return (
        f"{action} — this could {conf_text} save you up to ₹{savings:,.0f}/month."
    )
