"""
JVN-style guide — sassy, supportive commentary on card optimization results.

Modeled on Jonathan Van Ness (Queer Eye): celebratory when things are good,
gently snarky about suboptimal choices, always encouraging.
"""


def generate_guide(results: list[dict], total_spend: float = 0) -> dict:
    """Generate JVN-style commentary based on Icono card analysis results.

    Parameters
    ----------
    results : list of card dicts from ``analyze_cards()``, sorted by
              ``icono_year1`` descending.
    total_spend : optional total annual spend for context.

    Returns
    -------
    dict with ``headline`` (str), ``bullets`` (list[str]), ``tone`` (str).
    """
    if not results:
        return {
            "headline": "Honey, we need some transactions to work with!",
            "bullets": ["Upload your Monarch export and let's find your glow-up."],
            "tone": "sassy-supportive",
        }

    top = results[0]
    second = results[1] if len(results) > 1 else None
    bottom = results[-1] if len(results) > 2 else None

    headline = _build_headline(top, second)
    bullets = _build_bullets(results, total_spend)

    return {
        "headline": headline,
        "bullets": bullets,
        "tone": "sassy-supportive",
    }


def _build_headline(top: dict, second: dict | None) -> str:
    """Pick a headline based on the top card and the gap to second."""
    name = top["name"]
    year1 = top["icono_year1"]

    if year1 > 3000:
        return f"Gorgeous, {name} is SERVING — ${year1:,.0f} in Year 1 value. We love to see it."
    if year1 > 1500:
        return f"OK {name}, main character energy! ${year1:,.0f} Year-1 value? Yes please."

    if second:
        gap = top["icono_year1"] - second["icono_year1"]
        if gap > 500:
            return (
                f"{name} is running away with it — ${gap:,.0f} ahead of "
                f"{second['name']}. That's not even close, bestie."
            )
        if gap < 100:
            return (
                f"It's giving neck-and-neck between {name} and "
                f"{second['name']}. Either way, you're winning."
            )

    return f"{name} is quietly the main character here. Let's talk about it."


def _build_bullets(results: list[dict], total_spend: float) -> list[str]:
    """Build 2-4 actionable insight bullets."""
    bullets: list[str] = []
    top = results[0]

    # 1. Celebrate the winner
    if top["perks_value"] > 200:
        bullets.append(
            f"{top['name']} brings ${top['perks_value']:,.0f} in Icono-adjusted perks "
            f"alone. That's not nothing, honey."
        )

    # 2. Call out big gaps
    if len(results) >= 2:
        worst_ongoing = min(results, key=lambda r: r["icono_ongoing"])
        if worst_ongoing["icono_ongoing"] < 0:
            bullets.append(
                f"We need to talk about {worst_ongoing['name']}. "
                f"It's costing you ${abs(worst_ongoing['icono_ongoing']):,.0f}/yr more "
                f"than it's earning. That card is not pulling its weight."
            )

    # 3. Rent/Bilt callout
    bilt_results = [r for r in results if r["name"] == "Bilt Mastercard"]
    if bilt_results and bilt_results[0]["base_rewards_value"] > 0:
        bilt = bilt_results[0]
        bullets.append(
            f"Bilt is earning ${bilt['base_rewards_value']:,.0f} on rent — "
            f"if you're still paying via ACH, we are NOT doing that anymore."
        )

    # 4. Travel energy
    travel_cards = [r for r in results if r["name"] in (
        "Chase Sapphire Reserve", "Capital One Venture X", "Amex Platinum",
        "Chase Sapphire Preferred", "Citi Strata Premier",
    )]
    if travel_cards:
        best_travel = max(travel_cards, key=lambda r: r["icono_year1"])
        if best_travel["icono_year1"] > 1000:
            bullets.append(
                f"{best_travel['name']} is serving global upgrade energy — "
                f"${best_travel['icono_year1']:,.0f} in Year-1 value for the "
                f"wanderlust crowd."
            )

    # 5. Floor card roast
    low_earners = [r for r in results if r["base_rewards_value"] > 0 and r["base_rewards_value"] < 100]
    if low_earners:
        weakest = min(low_earners, key=lambda r: r["base_rewards_value"])
        bullets.append(
            f"We are not putting that spend on {weakest['name']} at "
            f"${weakest['base_rewards_value']:,.0f}/yr, honey. You deserve better."
        )

    # Always end with encouragement
    if not bullets:
        bullets.append("Your card game is solid. Keep that energy going!")

    return bullets[:4]  # cap at 4 bullets
