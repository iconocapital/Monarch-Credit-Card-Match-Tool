"""
Card data models and database for the Icono Credit Card Reward Optimizer.

Extracted from reward_optimizer.py to enable clean imports across
the Streamlit UI, FastAPI backend, and test suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CardProfile:
    """Credit card profile with earn rates, fees, and Icono perk fields."""
    name: str
    annual_fee: float
    currency: str = "Cash Back"
    categories: dict = field(default_factory=dict)
    base_rate: float = 0.01  # 1% default
    cpp_valuation: float = 1.0  # cents-per-point (1.0 = cash, 2.0 = UR, etc.)
    signup_bonus_value: float = 0.0  # SUB dollar value for acquisition planning

    # Icono perk fields — granular credit buckets (all in face-value dollars)
    hotel_credit: float = 0.0
    travel_credit: float = 0.0
    uber_credit: float = 0.0
    dining_credit: float = 0.0
    streaming_credit: float = 0.0
    other_credit: float = 0.0

    # DEPRECATED — display only.  Use the granular *_credit fields above.
    # Not consumed by icono_engine scoring; kept for backwards-compatible display.
    annual_credits: float = 0.0


# ─────────────────────────────────────────────
#  CPP Mode Utility
# ─────────────────────────────────────────────

# Conservative floor CPP values — use when cpp_mode == "floor"
CPP_FLOOR_MAP: dict[str, float] = {
    "Ultimate Rewards": 1.5,
    "Membership Rewards": 0.9,
    "ThankYou Points": 1.5,
    "Capital One Miles": 1.0,
    "Bilt Points": 1.5,
    "Wells Fargo Points": 1.0,
    "Marriott Bonvoy": 0.7,
    "Cash Back": 1.0,
    "Cash Back (Daily Cash)": 1.0,
}


def get_effective_cpp(card: CardProfile, mode: str = "awardwallet") -> float:
    """Return the cents-per-point value for *card* under the chosen mode.

    Parameters
    ----------
    card : CardProfile to evaluate.
    mode : ``"awardwallet"`` returns ``card.cpp_valuation`` (optimistic, live).
           ``"floor"`` returns conservative redemption values per currency.

    Returns
    -------
    float — effective cpp multiplier.
    """
    if mode == "floor":
        return CPP_FLOOR_MAP.get(card.currency, 1.0)
    return card.cpp_valuation


# ─────────────────────────────────────────────
#  AwardWallet Integration Stub
# ─────────────────────────────────────────────

def refresh_cpp_from_awardwallet(cards: dict[str, CardProfile]) -> dict[str, float]:
    """Placeholder for AwardWallet API integration.

    When wired up, this will call the AwardWallet ``/api/cc`` endpoint,
    fetch live cpp valuations and category earn-rate updates, and return
    a dict mapping card name → updated cpp.

    Currently returns each card's existing ``cpp_valuation`` unchanged.
    """
    # TODO: implement actual AwardWallet call:
    #   import requests, os
    #   resp = requests.get(
    #       "https://awardwallet.com/api/cc",
    #       headers={"Authorization": f"Bearer {os.getenv('AWARDWALLET_API_KEY')}"},
    #   )
    #   data = resp.json()
    #   ... map response to cards ...
    return {name: card.cpp_valuation for name, card in cards.items()}


# ─────────────────────────────────────────────
#  Card Database — Feb 2026 Market
# ─────────────────────────────────────────────

CARD_DB: dict[str, CardProfile] = {

    # ═══ PREMIUM TRAVEL ═══
    "Amex Platinum": CardProfile(
        name="Amex Platinum",
        annual_fee=695,
        currency="Membership Rewards",
        base_rate=0.01,
        cpp_valuation=1.99,
        annual_credits=840,
        signup_bonus_value=3000,
        travel_credit=200,
        uber_credit=200,
        streaming_credit=240,
        hotel_credit=200,
        categories={
            "airlines": 0.05,
            "hotels": 0.05,
        },
    ),
    "Chase Sapphire Reserve": CardProfile(
        name="Chase Sapphire Reserve",
        annual_fee=550,
        currency="Ultimate Rewards",
        base_rate=0.01,
        cpp_valuation=2.0,
        annual_credits=300,
        signup_bonus_value=1200,
        travel_credit=300,
        categories={
            "dining": 0.03,
            "travel": 0.03,
            "airlines": 0.03,
            "hotels": 0.03,
            "car_rental": 0.03,
        },
    ),
    "Capital One Venture X": CardProfile(
        name="Capital One Venture X",
        annual_fee=395,
        currency="Capital One Miles",
        base_rate=0.02,
        cpp_valuation=2.04,
        annual_credits=400,
        signup_bonus_value=1530,
        travel_credit=300,
        other_credit=100,
        categories={
            "hotels": 0.10,
            "car_rental": 0.10,
        },
    ),

    # ═══ MID-TIER TRAVEL ═══
    "Chase Sapphire Preferred": CardProfile(
        name="Chase Sapphire Preferred",
        annual_fee=95,
        currency="Ultimate Rewards",
        base_rate=0.01,
        cpp_valuation=2.0,
        annual_credits=50,
        signup_bonus_value=1200,
        hotel_credit=50,
        categories={
            "dining": 0.03,
            "travel": 0.02,
            "airlines": 0.02,
            "hotels": 0.02,
            "streaming": 0.03,
            "groceries": 0.03,
        },
    ),
    "Capital One Venture": CardProfile(
        name="Capital One Venture",
        annual_fee=95,
        currency="Capital One Miles",
        base_rate=0.02,
        cpp_valuation=2.04,
        annual_credits=100,
        signup_bonus_value=1530,
        travel_credit=100,
        categories={
            "hotels": 0.05,
        },
    ),
    "Amex Gold": CardProfile(
        name="Amex Gold",
        annual_fee=325,
        currency="Membership Rewards",
        base_rate=0.01,
        cpp_valuation=1.99,
        annual_credits=424,
        signup_bonus_value=1990,
        dining_credit=304,
        uber_credit=120,
        categories={
            "dining": 0.04,
            "groceries": 0.04,
        },
    ),
    "Citi Strata Premier": CardProfile(
        name="Citi Strata Premier",
        annual_fee=95,
        currency="ThankYou Points",
        base_rate=0.01,
        cpp_valuation=2.29,
        annual_credits=100,
        signup_bonus_value=1374,
        hotel_credit=100,
        categories={
            "hotels": 0.03,
            "airlines": 0.03,
            "dining": 0.03,
            "groceries": 0.03,
            "gas": 0.03,
        },
    ),

    # ═══ NO ANNUAL FEE TRAVEL ═══
    "Capital One VentureOne": CardProfile(
        name="Capital One VentureOne",
        annual_fee=0,
        currency="Capital One Miles",
        base_rate=0.0125,
        cpp_valuation=2.04,
    ),
    "Bilt Mastercard": CardProfile(
        name="Bilt Mastercard",
        annual_fee=0,
        currency="Bilt Points",
        base_rate=0.01,
        cpp_valuation=2.0,
        categories={
            "housing": 0.0125,
            "dining": 0.03,
            "travel": 0.02,
        },
    ),

    # ═══ CASH BACK — FLAT RATE ═══
    "Chase Freedom Unlimited": CardProfile(
        name="Chase Freedom Unlimited",
        annual_fee=0,
        currency="Ultimate Rewards",
        base_rate=0.015,
        cpp_valuation=2.0,
        signup_bonus_value=400,
        categories={
            "dining": 0.03,
            "pharmacy": 0.03,
            "travel": 0.05,
        },
    ),
    "Citi Double Cash": CardProfile(
        name="Citi Double Cash",
        annual_fee=0,
        currency="Cash Back",
        base_rate=0.02,
        signup_bonus_value=200,
    ),
    "PayPal Cashback Mastercard": CardProfile(
        name="PayPal Cashback Mastercard",
        annual_fee=0,
        currency="Cash Back",
        base_rate=0.015,
        categories={
            "paypal": 0.03,
        },
    ),

    # ═══ CASH BACK — CATEGORY ═══
    "Amex Blue Cash Preferred": CardProfile(
        name="Amex Blue Cash Preferred",
        annual_fee=95,
        currency="Cash Back",
        annual_credits=120,
        signup_bonus_value=300,
        streaming_credit=120,
        categories={
            "groceries": 0.06,
            "streaming": 0.06,
            "gas": 0.03,
            "transit": 0.03,
        },
    ),
    "Amex Blue Cash Everyday": CardProfile(
        name="Amex Blue Cash Everyday",
        annual_fee=0,
        currency="Cash Back",
        base_rate=0.01,
        signup_bonus_value=200,
        categories={
            "groceries": 0.03,
            "online_retail": 0.03,
            "gas": 0.03,
        },
    ),
    "Chase Freedom Flex": CardProfile(
        name="Chase Freedom Flex",
        annual_fee=0,
        currency="Ultimate Rewards",
        base_rate=0.01,
        cpp_valuation=2.0,
        categories={
            "dining": 0.03,
            "pharmacy": 0.03,
        },
    ),
    "Capital One SavorOne": CardProfile(
        name="Capital One SavorOne",
        annual_fee=0,
        currency="Cash Back",
        base_rate=0.01,
        signup_bonus_value=200,
        categories={
            "dining": 0.03,
            "groceries": 0.03,
            "entertainment": 0.03,
            "streaming": 0.03,
        },
    ),
    "Citi Custom Cash": CardProfile(
        name="Citi Custom Cash",
        annual_fee=0,
        currency="ThankYou Points",
        base_rate=0.01,
        cpp_valuation=2.29,
        signup_bonus_value=458,
        categories={
            "groceries": 0.05,
            "gas": 0.05,
            "dining": 0.05,
            "travel": 0.05,
            "transit": 0.05,
            "streaming": 0.05,
            "pharmacy": 0.05,
            "fitness": 0.05,
        },
    ),

    # ═══ STORE / CO-BRAND ═══
    "Amazon Prime Visa": CardProfile(
        name="Amazon Prime Visa",
        annual_fee=0,
        currency="Cash Back",
        base_rate=0.01,
        signup_bonus_value=150,
        categories={
            "amazon": 0.05,
            "whole_foods": 0.05,
            "dining": 0.02,
            "gas": 0.02,
            "transit": 0.02,
        },
    ),
    "Apple Card": CardProfile(
        name="Apple Card",
        annual_fee=0,
        currency="Cash Back (Daily Cash)",
        base_rate=0.01,
        categories={
            "apple": 0.03,
            "apple_pay": 0.02,
        },
    ),
    "Chase Marriott Bonvoy Boundless": CardProfile(
        name="Chase Marriott Bonvoy Boundless",
        annual_fee=95,
        currency="Marriott Bonvoy",
        base_rate=0.02,
        cpp_valuation=0.7,
        annual_credits=100,
        signup_bonus_value=525,
        hotel_credit=100,
        categories={
            "hotels": 0.06,
        },
    ),

    # ═══ BUSINESS ═══
    "Blue Business Plus": CardProfile(
        name="Blue Business Plus",
        annual_fee=0,
        currency="Membership Rewards",
        base_rate=0.02,
        cpp_valuation=1.99,
        signup_bonus_value=298.5,
    ),

    # ═══ BANK OF AMERICA ═══
    "Bank of America Atmos Summit": CardProfile(
        name="Bank of America Atmos Summit",
        annual_fee=195,
        currency="Cash Back",
        base_rate=0.02,
        cpp_valuation=1.0,
        annual_credits=150,
        signup_bonus_value=800,
        travel_credit=150,
        categories={
            "dining": 0.04,
            "travel": 0.03,
            "airlines": 0.03,
            "hotels": 0.03,
        },
    ),
    "Bank of America Atmos Ascend": CardProfile(
        name="Bank of America Atmos Ascend",
        annual_fee=95,
        currency="Cash Back",
        base_rate=0.015,
        cpp_valuation=1.0,
        annual_credits=100,
        signup_bonus_value=600,
        travel_credit=100,
        categories={
            "dining": 0.03,
            "travel": 0.02,
            "gas": 0.02,
            "auto": 0.02,
        },
    ),
    "Bank of America Premium Rewards": CardProfile(
        name="Bank of America Premium Rewards",
        annual_fee=95,
        currency="Cash Back",
        base_rate=0.015,
        cpp_valuation=1.0,
        annual_credits=200,
        signup_bonus_value=600,
        travel_credit=100,
        dining_credit=100,
        categories={
            "dining": 0.02,
            "travel": 0.02,
        },
    ),

    # ═══ WELLS FARGO ═══
    "Wells Fargo Autograph Journey": CardProfile(
        name="Wells Fargo Autograph Journey",
        annual_fee=95,
        currency="Wells Fargo Points",
        base_rate=0.01,
        cpp_valuation=1.0,
        signup_bonus_value=500,
        categories={
            "airlines": 0.05,
            "hotels": 0.04,
            "car_rental": 0.03,
            "phone": 0.03,
            "internet": 0.03,
            "travel": 0.03,
        },
    ),
    "Wells Fargo Attune": CardProfile(
        name="Wells Fargo Attune",
        annual_fee=0,
        currency="Cash Back",
        base_rate=0.02,
        cpp_valuation=1.0,
        signup_bonus_value=200,
        categories={
            "transit": 0.04,
            "fitness": 0.04,
            "self_care": 0.04,
            "pets": 0.04,
        },
    ),

    # ═══ US BANK ═══
    "US Bank Cash+": CardProfile(
        name="US Bank Cash+",
        annual_fee=0,
        currency="Cash Back",
        base_rate=0.01,
        cpp_valuation=1.0,
        signup_bonus_value=200,
        categories={
            "utilities": 0.05,
            "internet": 0.05,
            "phone": 0.05,
        },
    ),

    # ═══ STATE FARM ═══
    "State Farm Premier Cash Rewards": CardProfile(
        name="State Farm Premier Cash Rewards",
        annual_fee=0,
        currency="Cash Back",
        base_rate=0.015,
        cpp_valuation=1.0,
        signup_bonus_value=0,
        categories={
            "insurance": 0.03,
        },
    ),

    # ═══ ADDITIONAL CASH BACK ═══
    "Capital One Savor": CardProfile(
        name="Capital One Savor",
        annual_fee=0,
        currency="Cash Back",
        base_rate=0.01,
        cpp_valuation=1.0,
        signup_bonus_value=200,
        categories={
            "dining": 0.04,
            "entertainment": 0.04,
            "groceries": 0.03,
            "streaming": 0.03,
        },
    ),
}
