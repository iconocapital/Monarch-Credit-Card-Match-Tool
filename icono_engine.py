"""
Icono scoring engine — perk valuation, transaction analysis, and card scoring.

Single source of truth for:
- Category normalization (CATEGORY_MAP)
- Non-expense filters (NON_EXPENSE_*)
- Weighted perk haircuts (Icono philosophy)
- Per-card reward simulation on real transaction data
- Ongoing / Year-1 Icono score computation
- Transaction loading and category normalization
"""

import pandas as pd
from card_models import CardProfile, CARD_DB, get_effective_cpp


# ─────────────────────────────────────────────
#  Monarch Category → Internal Tag Mapping
# ─────────────────────────────────────────────

CATEGORY_MAP: dict[str, str] = {
    # Housing
    "Rent": "housing", "Mortgage": "housing", "Mortgage & Rent": "housing",
    "HOA Dues": "housing",

    # Food & Dining
    "Restaurants": "dining", "Dining": "dining", "Dining Out": "dining",
    "Fast Food": "dining", "Coffee Shops": "dining", "Bars & Alcohol": "dining",
    "Alcohol": "dining", "Restaurants & Bars": "dining", "Takeout": "dining",
    "Groceries": "groceries", "Grocery": "groceries",
    "Food & Supplies": "groceries",

    # Utilities & Fixed Bills
    "Gas & Electric": "utilities", "Electricity": "utilities",
    "Water": "utilities", "Utilities": "utilities", "Sewer": "utilities",
    "Trash": "utilities",
    "Internet & Cable": "internet", "Internet": "internet",
    "Cable/Internet": "internet",
    "Phone": "phone", "Mobile Phone": "phone",

    # Streaming & Subscriptions
    "Streaming Services": "streaming", "Subscriptions": "streaming",
    "Music": "streaming",

    # Transportation
    "Gas": "gas", "Gas & Fuel": "gas", "Fuel": "gas",
    "Public Transit": "transit", "Ride Share": "transit",
    "Taxi & Ride Shares": "transit",
    "Parking": "auto", "Auto Maintenance": "auto",
    "Service & Parts": "auto",
    "Auto Insurance": "insurance", "Auto Payment": "auto",

    # Travel
    "Airlines": "airlines", "Flights": "airlines",
    "Hotels": "hotels", "Lodging": "hotels",
    "Car Rental": "car_rental", "Travel": "travel",

    # Health & Wellness
    "Fitness": "fitness", "Gym": "fitness",
    "Health & Wellness": "self_care", "Personal Care": "self_care",
    "Dentist": "self_care", "Medical": "self_care", "Doctor": "self_care",
    "Health- HSA": "self_care",
    "Pharmacy": "pharmacy",

    # Pets
    "Pets": "pets", "Pet Care": "pets", "Veterinary": "pets",
    "Pet Food & Supplies": "pets",

    # Insurance
    "Insurance": "insurance", "Home Insurance": "insurance",
    "Life Insurance": "insurance", "Health Insurance": "insurance",
    "Renters Insurance": "insurance",

    # Entertainment
    "Entertainment": "entertainment", "Movies": "entertainment",
    "Concerts": "entertainment", "Sports": "entertainment",
    "Amusement": "entertainment",
    "Entertainment & Recreation": "entertainment",

    # Online/Store-specific
    "Amazon": "amazon", "Whole Foods": "whole_foods",
    "Apple": "apple", "Target": "target",

    # Education
    "Education": "general",

    # Gifts
    "Gift": "general", "Gifts": "general",
    "Birthday Gift": "general",

    # Home
    "Home Supplies": "general", "Home Improvement": "general",
    "New Home Build": "general",

    # Business / Personal (Monarch custom categories)
    "Business Expense": "general",
    "Nick Business Expense": "general", "Nick Personal": "general",
    "Matt Personal": "general",

    # Everything else → will hit floor card
    "Shopping": "general", "Electronics": "general", "Clothing": "general",
    "Furniture": "general",
    "Online Shopping": "online_retail",
    "Financial Fees": "general", "Fees & Charges": "general",
    "Charity": "general",
    "Uncategorized": "general",
}

# Categories typically paid via ACH/bank transfer (reward leakage risk)
ACH_CATEGORIES = {"housing", "utilities", "insurance"}


# ─────────────────────────────────────────────
#  Non-Expense Filters
# ─────────────────────────────────────────────

NON_EXPENSE_CATEGORIES = {
    "transfer", "credit card payment", "credit card payments",
    "transfer to savings", "internal transfer", "account transfer",
    "paychecks", "paycheck", "income", "salary", "wages",
    "interest income", "interest", "dividend", "dividends",
    "investment income", "capital gains",
    "reimbursement", "refund",
    "loan payment", "loan", "student loan", "auto loan",
    "investments", "investment", "investing",
}

NON_EXPENSE_PATTERNS = [
    "transfer to ", "transfer from ",
    "payment to ", "payment from ",
]

NON_EXPENSE_MERCHANTS = {
    "atm withdrawal", "atm", "wire", "wire transfer",
}

NON_EXPENSE_MERCHANT_PATTERNS = [
    "to ", "from ",
]


# ─────────────────────────────────────────────
#  Icono Perk Valuation (Weighted Haircuts)
# ─────────────────────────────────────────────

ICONO_WEIGHTS = {
    "travel": 1.0,
    "uber": 0.7,
    "dining": 0.7,
    "streaming": 0.5,
    "other": 0.7,
    "hotel_util": 0.7,
    "hotel_difficulty": 0.5,
}


def icono_perk_value(card: CardProfile) -> float:
    """Iconoclastic-adjusted annual perks value (dollars).

    Applies differentiated weights to each perk bucket instead of
    counting raw face-value credits.  Hotel credits are double-discounted
    (utilization x difficulty).  Niche perks excluded at the profile level.
    """
    w = ICONO_WEIGHTS
    hotel_val = card.hotel_credit * w["hotel_util"] * w["hotel_difficulty"]
    travel_val = card.travel_credit * w["travel"]
    uber_val = card.uber_credit * w["uber"]
    dining_val = card.dining_credit * w["dining"]
    streaming_val = card.streaming_credit * w["streaming"]
    other_val = card.other_credit * w["other"]
    return hotel_val + travel_val + uber_val + dining_val + streaming_val + other_val


def icono_score_ongoing(card: CardProfile, annual_rewards: float) -> float:
    """Ongoing Icono score: real annual rewards + haircut perks - fee."""
    return annual_rewards + icono_perk_value(card) - card.annual_fee


def icono_score_year1(card: CardProfile, annual_rewards: float) -> float:
    """Year 1 Icono score: ongoing value + sign-up bonus."""
    return annual_rewards + card.signup_bonus_value + icono_perk_value(card) - card.annual_fee


# ─────────────────────────────────────────────
#  Conservative CPP Floor Values
# ─────────────────────────────────────────────
# Canonical map lives in card_models.CPP_FLOOR_MAP.
# Re-exported here for backwards compatibility.

from card_models import CPP_FLOOR_MAP

CPP_FLOOR_VALUES = CPP_FLOOR_MAP


# ─────────────────────────────────────────────
#  Transaction Loading & Category Mapping
# ─────────────────────────────────────────────

def map_earn_category(category_str: str) -> str:
    """Map a raw Monarch category string to a normalized internal tag.

    Returns ``"other"`` for anything not explicitly mapped.
    """
    return CATEGORY_MAP.get(category_str, CATEGORY_MAP.get(category_str.strip(), "other"))


def load_transactions(
    df: pd.DataFrame,
    category_col: str = "Category",
    amount_col: str = "Amount",
) -> pd.DataFrame:
    """Filter a Monarch CSV DataFrame to only earnable expense rows.

    Removes income, transfers, credit card payments, and other
    non-card-optimizable rows.  Converts amounts to positive spend values.
    """
    work = df.copy()
    work[amount_col] = pd.to_numeric(work[amount_col], errors="coerce").fillna(0)

    # Keep only expenses (negative amounts in Monarch)
    work = work[work[amount_col] < 0].copy()

    # Remove non-expense categories
    cat_lower = work[category_col].str.lower().str.strip()
    mask_exact = cat_lower.isin(NON_EXPENSE_CATEGORIES)
    mask_partial = pd.Series(False, index=work.index)
    for pat in NON_EXPENSE_PATTERNS:
        mask_partial = mask_partial | cat_lower.str.startswith(pat, na=False)
    work = work[~(mask_exact | mask_partial)].copy()

    # Convert to positive spend
    work["_spend"] = work[amount_col].abs()
    work["_earn_category"] = work[category_col].apply(map_earn_category)

    return work


# ─────────────────────────────────────────────
#  Per-Card Reward Simulation
# ─────────────────────────────────────────────

def card_base_rewards(
    card: CardProfile,
    df: pd.DataFrame,
    cpp_mode: str = "awardwallet",
) -> float:
    """Compute total annual dollar rewards a card would earn on transactions.

    Parameters
    ----------
    card : CardProfile to simulate.
    df : DataFrame already processed by ``load_transactions``
         (must have ``_spend`` and ``_earn_category`` columns).
    cpp_mode : ``"awardwallet"`` uses ``card.cpp_valuation``;
               ``"floor"`` uses conservative CPP_FLOOR_VALUES.
    """
    cpp = get_effective_cpp(card, mode=cpp_mode)

    total = 0.0
    for _, row in df.iterrows():
        spend = row["_spend"]
        earn_cat = row["_earn_category"]
        rate = card.categories.get(earn_cat, card.base_rate)
        total += spend * rate * cpp
    return total


def analyze_cards(
    df: pd.DataFrame,
    cards: list[CardProfile] | None = None,
    cpp_mode: str = "awardwallet",
) -> dict:
    """Run Icono analysis across all cards on the given transaction data.

    Parameters
    ----------
    df : Raw Monarch DataFrame (will be run through ``load_transactions``).
    cards : List of CardProfile objects to evaluate.
            Defaults to all cards in CARD_DB.
    cpp_mode : ``"awardwallet"`` or ``"floor"``.

    Returns
    -------
    dict with:
      ``cards`` — list of dicts sorted by ``icono_year1`` descending.
      ``total_spend`` — sum of earnable transaction amounts.
      ``meta`` — dict with ``cpp_mode``, ``cards_evaluated``, ``txn_count``.
    """
    if cards is None:
        cards = list(CARD_DB.values())

    clean_df = load_transactions(df)
    total_spend = float(clean_df["_spend"].sum()) if not clean_df.empty else 0.0

    card_results = []
    for card in cards:
        base_val = card_base_rewards(card, clean_df, cpp_mode)
        perks_val = icono_perk_value(card)
        ongoing = icono_score_ongoing(card, base_val)
        year1 = icono_score_year1(card, base_val)

        card_results.append({
            "name": card.name,
            "base_rewards_value": round(base_val, 2),
            "perks_value": round(perks_val, 2),
            "icono_ongoing": round(ongoing, 2),
            "icono_year1": round(year1, 2),
            "annual_fee": card.annual_fee,
            "signup_bonus": card.signup_bonus_value,
        })

    card_results.sort(key=lambda r: r["icono_year1"], reverse=True)

    return {
        "cards": card_results,
        "total_spend": round(total_spend, 2),
        "meta": {
            "cpp_mode": cpp_mode,
            "cards_evaluated": len(card_results),
            "txn_count": len(clean_df),
        },
    }
