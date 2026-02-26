"""
Credit Card Reward Optimizer — Q1 2026 Edition
================================================
Ingests Monarch Money CSV exports and maps spending to the highest-yielding
credit card for each category, flagging ACH/bank-pay leakage and insurance
optimization opportunities.

Designed for: Chris @ Icono / personal use
Last updated:  2025-02-25
"""

import pandas as pd
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# ─────────────────────────────────────────────
#  Data Models
# ─────────────────────────────────────────────

class SpendFlag(Enum):
    """Flags for actionable optimization opportunities."""
    ACH_LEAKAGE = "ACH/Bank Pay → Move to credit card for rewards"
    INSURANCE_OPP = "Insurance spend earning 0% → card opportunity exists"
    BELOW_FLOOR = "Earning below 2% floor — use flat-rate fallback"
    BILT_FIRST = "Bilt 1st-of-month double points opportunity"
    CITI_NIGHT = "Citi Nights 6x multiplier window (Fri/Sat 6pm–6am ET)"
    ROTATING_Q = "Quarterly rotating bonus category active"


@dataclass
class CardRecommendation:
    card: str
    rate_pct: float
    note: str
    annual_reward: float = 0.0
    flags: list = field(default_factory=list)


@dataclass
class CardProfile:
    name: str
    annual_fee: float
    currency: str = "Cash Back"
    categories: dict = field(default_factory=dict)
    base_rate: float = 0.01  # 1% default
    cpp_valuation: float = 1.0  # cents-per-point (1.0 = cash, 2.2 = Bilt, 1.8 = ThankYou, etc.)


# ─────────────────────────────────────────────
#  Quarterly Rotation Definitions
# ─────────────────────────────────────────────

QUARTERLY_ROTATIONS = {
    2026: {
        1: {  # Q1: Jan 1 – Mar 31
            "Chase Freedom Flex": {
                "categories": ["Dining", "Restaurants", "Fast Food", "Coffee Shops"],
                "rate": 0.05,
                "note": "Q1 2026 rotating: Dining 5%",
            },
            "Discover it": {
                "categories": ["Groceries", "Grocery"],
                "rate": 0.05,
                "note": "Q1 2026 rotating: Groceries 5% (matched 1st year → 10%)",
            },
        },
        # Placeholders — update as announced
        2: {},  # Q2: Apr 1 – Jun 30
        3: {},  # Q3: Jul 1 – Sep 30
        4: {},  # Q4: Oct 1 – Dec 31
    }
}


def get_quarter(dt: datetime) -> int:
    return (dt.month - 1) // 3 + 1


# ─────────────────────────────────────────────
#  Card Database — Feb 2026 Market
# ─────────────────────────────────────────────

CARD_DB: dict[str, CardProfile] = {
    # --- Premium / Housing ---
    "Bilt Palladium": CardProfile(
        name="Bilt Palladium",
        annual_fee=495,
        currency="Bilt Points",
        base_rate=0.02,
        cpp_valuation=2.2,  # Bilt Points valued at ~2.2 cpp for transfers
        categories={
            "housing": {"rate": 0.01, "tiered_max": 0.0125},
            "dining": 0.03,
            "travel": 0.02,
        },
    ),
    "Citi Strata Elite": CardProfile(
        name="Citi Strata Elite",
        annual_fee=595,
        currency="ThankYou Points",
        base_rate=0.015,
        cpp_valuation=1.8,  # ThankYou Points ~1.8 cpp via transfer partners
        categories={
            "dining": 0.03,
            "dining_night": 0.06,  # Citi Nights: Fri/Sat 6pm-6am ET
            "hotels": 0.05,
            "airlines": 0.03,
        },
    ),

    # --- Category Specialists ---
    "Amex Blue Cash Preferred": CardProfile(
        name="Amex Blue Cash Preferred",
        annual_fee=95,
        currency="Cash Back",
        categories={
            "groceries": 0.06,   # up to $6k/yr
            "streaming": 0.06,
            "gas": 0.03,
            "transit": 0.03,
        },
    ),
    "Wells Fargo Attune": CardProfile(
        name="Wells Fargo Attune",
        annual_fee=0,
        currency="Cash Back",
        categories={
            "self_care": 0.04,
            "fitness": 0.04,
            "transit": 0.04,
            "pets": 0.04,
            "sustainable": 0.04,  # planet-friendly merchants
        },
    ),
    "US Bank Cash+": CardProfile(
        name="US Bank Cash+",
        annual_fee=0,
        currency="Cash Back",
        categories={
            "utilities": 0.05,   # user-selected
            "internet": 0.05,
        },
    ),
    "Wells Fargo Autograph Journey": CardProfile(
        name="Wells Fargo Autograph Journey",
        annual_fee=95,
        currency="Rewards Points",
        base_rate=0.01,
        cpp_valuation=1.5,  # WF points ~1.5 cpp via transfer partners
        categories={
            "airlines": 0.05,
            "hotels": 0.04,
            "car_rental": 0.03,
            "dining": 0.03,
            "phone": 0.03,
            "internet": 0.03,
        },
    ),
    "State Farm Premier Cash Rewards": CardProfile(
        name="State Farm Premier Cash Rewards",
        annual_fee=0,
        currency="Cash Back",
        base_rate=0.015,
        categories={
            "insurance": 0.03,
        },
    ),
    "Atmos Ascent": CardProfile(
        name="Atmos Ascent",
        annual_fee=0,
        currency="Atmos Points",
        base_rate=0.02,
        categories={
            "gas": 0.02,
            "transit": 0.02,
            "auto": 0.02,
        },
    ),

    # --- Flat-Rate Floor Cards ---
    "Wells Fargo Active Cash": CardProfile(
        name="Wells Fargo Active Cash",
        annual_fee=0,
        currency="Cash Back",
        base_rate=0.02,
    ),
    "Citi Double Cash": CardProfile(
        name="Citi Double Cash",
        annual_fee=0,
        currency="Cash Back",
        base_rate=0.02,
    ),
}


# ─────────────────────────────────────────────
#  Monarch Category → Internal Tag Mapping
# ─────────────────────────────────────────────

CATEGORY_MAP: dict[str, str] = {
    # Housing
    "Rent": "housing", "Mortgage": "housing", "Mortgage & Rent": "housing",
    "HOA Dues": "housing",

    # Food & Dining
    "Restaurants": "dining", "Dining": "dining", "Fast Food": "dining",
    "Coffee Shops": "dining", "Bars & Alcohol": "dining",
    "Groceries": "groceries", "Grocery": "groceries",

    # Utilities & Fixed Bills
    "Gas & Electric": "utilities", "Water": "utilities",
    "Utilities": "utilities", "Sewer": "utilities", "Trash": "utilities",
    "Internet & Cable": "internet", "Internet": "internet",
    "Phone": "phone", "Mobile Phone": "phone",

    # Streaming & Subscriptions
    "Streaming Services": "streaming", "Subscriptions": "streaming",
    "Music": "streaming",

    # Transportation
    "Gas": "gas", "Fuel": "gas",
    "Public Transit": "transit", "Ride Share": "transit",
    "Parking": "auto", "Auto Maintenance": "auto",
    "Auto Insurance": "insurance", "Auto Payment": "auto",

    # Travel
    "Airlines": "airlines", "Flights": "airlines",
    "Hotels": "hotels", "Lodging": "hotels",
    "Car Rental": "car_rental", "Travel": "travel",

    # Health & Wellness
    "Fitness": "fitness", "Gym": "fitness",
    "Health & Wellness": "self_care", "Personal Care": "self_care",
    "Dentist": "self_care", "Medical": "self_care", "Doctor": "self_care",
    "Pharmacy": "self_care",

    # Pets
    "Pets": "pets", "Pet Care": "pets", "Veterinary": "pets",

    # Insurance
    "Insurance": "insurance", "Home Insurance": "insurance",
    "Life Insurance": "insurance", "Health Insurance": "insurance",
    "Renters Insurance": "insurance",

    # Everything else → will hit floor card
    "Shopping": "general", "Electronics": "general", "Clothing": "general",
    "Furniture": "general", "Home Improvement": "general",
    "Financial Fees": "general", "Fees & Charges": "general",
    "Education": "general", "Gifts": "general", "Charity": "general",
}

# Categories typically paid via ACH/bank transfer (reward leakage risk)
ACH_CATEGORIES = {"housing", "utilities", "insurance"}


# ─────────────────────────────────────────────
#  Core Engine
# ─────────────────────────────────────────────

class RewardOptimizer:
    """
    Maps spending data to optimal credit cards based on the Feb 2026 card market.

    Usage:
        optimizer = RewardOptimizer()
        df = pd.read_csv("monarch_export.csv")
        results, summary = optimizer.analyze(df)
    """

    def __init__(self, cards: dict[str, CardProfile] | None = None):
        self.cards = cards or CARD_DB
        self.floor_rate = 0.02
        self.floor_card = "Wells Fargo Active Cash"

    # --- Time-based checks ---

    @staticmethod
    def is_citi_night(timestamp) -> bool:
        """Fri/Sat between 6 pm and 6 am ET → Citi Nights multiplier."""
        try:
            dt = pd.to_datetime(timestamp)
            is_fri_or_sat = dt.weekday() in [4, 5]  # 4=Friday, 5=Saturday
            is_night_hours = dt.hour >= 18 or dt.hour < 6
            return is_fri_or_sat and is_night_hours
        except (ValueError, TypeError):
            return False

    @staticmethod
    def is_bilt_first(timestamp) -> bool:
        """1st of the month → Bilt double points day."""
        try:
            dt = pd.to_datetime(timestamp)
            return dt.day == 1
        except (ValueError, TypeError):
            return False

    def _get_active_rotation(self, txn_date: datetime) -> dict:
        """Return the rotating category bonuses active for a given date."""
        year = txn_date.year
        quarter = get_quarter(txn_date)
        return QUARTERLY_ROTATIONS.get(year, {}).get(quarter, {})

    # --- Bilt tiered housing logic ---

    @staticmethod
    def calc_bilt_housing_rate(monthly_housing: float, monthly_nonhousing_on_bilt: float) -> float:
        """
        Bilt Palladium tiered housing multiplier:
        Spend ≥ 100% of housing amount on non-housing → 1.25x
        Spend ≥ 50%  → 1.0x
        Spend ≥ 25%  → 0.75x
        Below 25%    → 0.50x
        """
        if monthly_housing == 0:
            return 0.01
        ratio = monthly_nonhousing_on_bilt / monthly_housing
        if ratio >= 1.0:
            return 0.0125
        elif ratio >= 0.5:
            return 0.01
        elif ratio >= 0.25:
            return 0.0075
        else:
            return 0.005

    # --- Core matching ---

    def get_optimal_card(
        self,
        category: str,
        amount: float,
        timestamp=None,
        bilt_housing_rate: float = 0.0125,  # assume max tier unless calculated
    ) -> CardRecommendation:
        """Determine the highest-yielding card for a single transaction."""

        internal_tag = CATEGORY_MAP.get(category, "general")
        flags: list[SpendFlag] = []
        txn_date = pd.to_datetime(timestamp) if timestamp else datetime.now()

        # --- Check rotating categories first ---
        rotations = self._get_active_rotation(txn_date)
        best_rotating_card = None
        best_rotating_rate = 0.0
        best_rotating_note = ""

        for card_name, rot in rotations.items():
            if category in rot.get("categories", []):
                if rot["rate"] > best_rotating_rate:
                    best_rotating_card = card_name
                    best_rotating_rate = rot["rate"]
                    best_rotating_note = rot["note"]
                    flags.append(SpendFlag.ROTATING_Q)

        # --- Category-specific matching ---
        candidates: list[tuple[str, float, str]] = []

        # Housing
        if internal_tag == "housing":
            flags.append(SpendFlag.ACH_LEAKAGE)
            candidates.append((
                "Bilt Palladium",
                bilt_housing_rate * 100,
                f"Bilt tiered housing multiplier ({bilt_housing_rate*100:.2f}%). Move from ACH to Bilt.",
            ))

        # Dining — check Citi Nights
        elif internal_tag == "dining":
            if self.is_citi_night(timestamp):
                flags.append(SpendFlag.CITI_NIGHT)
                candidates.append(("Citi Strata Elite", 6.0, "Citi Nights 6x (Fri/Sat 6pm–6am ET)."))

            # Bilt 1st of month double points on dining
            if self.is_bilt_first(timestamp):
                flags.append(SpendFlag.BILT_FIRST)
                candidates.append(("Bilt Palladium", 6.0, "Bilt 1st-of-month: dining doubled to 6x."))

            candidates.append(("Citi Strata Elite", 3.0, "Standard 3x dining."))
            candidates.append(("Bilt Palladium", 3.0, "Bilt 3x dining."))

            # Add rotating if applicable
            if best_rotating_card:
                candidates.append((best_rotating_card, best_rotating_rate * 100, best_rotating_note))

        # Groceries
        elif internal_tag == "groceries":
            candidates.append(("Amex Blue Cash Preferred", 6.0, "6% groceries (up to $6k/yr)."))
            if best_rotating_card:
                candidates.append((best_rotating_card, best_rotating_rate * 100, best_rotating_note))

        # Utilities
        elif internal_tag == "utilities":
            flags.append(SpendFlag.ACH_LEAKAGE)
            candidates.append(("US Bank Cash+", 5.0, "5% on utilities (user-selected). Move from ACH."))

        # Internet / Phone
        elif internal_tag in ("internet", "phone"):
            candidates.append(("US Bank Cash+", 5.0, "5% internet/telecom (if selected)."))
            candidates.append(("Wells Fargo Autograph Journey", 3.0, "3x phone/internet."))

        # Streaming
        elif internal_tag == "streaming":
            candidates.append(("Amex Blue Cash Preferred", 6.0, "6% streaming services."))

        # Gas
        elif internal_tag == "gas":
            candidates.append(("Amex Blue Cash Preferred", 3.0, "3% gas stations."))
            candidates.append(("Atmos Ascent", 2.0, "2x gas + Atmos status points."))

        # Transit
        elif internal_tag == "transit":
            candidates.append(("Wells Fargo Attune", 4.0, "4% transit."))
            candidates.append(("Amex Blue Cash Preferred", 3.0, "3% transit."))

        # Airlines
        elif internal_tag == "airlines":
            candidates.append(("Wells Fargo Autograph Journey", 5.0, "5x airlines."))
            candidates.append(("Citi Strata Elite", 3.0, "3x airlines."))

        # Hotels
        elif internal_tag == "hotels":
            candidates.append(("Citi Strata Elite", 5.0, "5x hotels."))
            candidates.append(("Wells Fargo Autograph Journey", 4.0, "4x hotels."))

        # Car Rental
        elif internal_tag == "car_rental":
            candidates.append(("Wells Fargo Autograph Journey", 3.0, "3x car rental."))

        # Travel (general)
        elif internal_tag == "travel":
            candidates.append(("Bilt Palladium", 2.0, "2x travel."))
            candidates.append(("Wells Fargo Autograph Journey", 3.0, "3x travel (if classified)."))

        # Health & Wellness / Self-Care
        elif internal_tag in ("self_care", "fitness"):
            candidates.append(("Wells Fargo Attune", 4.0, "4% wellness / fitness / self-care."))

        # Pets
        elif internal_tag == "pets":
            candidates.append(("Wells Fargo Attune", 4.0, "4% pet care & vet."))

        # Insurance
        elif internal_tag == "insurance":
            flags.append(SpendFlag.INSURANCE_OPP)
            candidates.append(("State Farm Premier Cash Rewards", 3.0, "3% on insurance premiums."))
            if self.is_bilt_first(timestamp):
                flags.append(SpendFlag.BILT_FIRST)
                candidates.append(("Bilt Palladium", 4.0, "Bilt 1st-of-month: 2x base → 4x on insurance."))

        # Auto (general)
        elif internal_tag == "auto":
            candidates.append(("Atmos Ascent", 2.0, "2x auto / transport for Atmos status."))

        # --- Pick the winner ---
        # Add the floor card as a baseline
        candidates.append((self.floor_card, self.floor_rate * 100, "2% flat-rate floor."))

        # Compare by effective value: rate * cents-per-point valuation
        def effective_value(candidate):
            card_name, rate, _ = candidate
            cpp = self.cards[card_name].cpp_valuation if card_name in self.cards else 1.0
            return rate * cpp

        candidates.sort(key=effective_value, reverse=True)
        best_card, best_rate, best_note = candidates[0]

        # Compare effective value for floor check (cpp-aware)
        best_cpp = self.cards[best_card].cpp_valuation if best_card in self.cards else 1.0
        effective_pct = best_rate * best_cpp
        floor_effective = self.floor_rate * 100  # cash = 1.0 cpp

        if effective_pct < floor_effective:
            flags.append(SpendFlag.BELOW_FLOOR)
            best_card = self.floor_card
            best_rate = self.floor_rate * 100
            best_note = "Below 2% effective floor — defaulting to flat-rate card."
            best_cpp = 1.0

        # Annotate points cards with effective value
        if best_cpp > 1.0:
            eff_display = best_rate * best_cpp
            best_note += f" (Effective value: {eff_display:.1f}% at {best_cpp:.1f}x cpp)"

        return CardRecommendation(
            card=best_card,
            rate_pct=best_rate,
            note=best_note,
            annual_reward=amount * (best_rate / 100),
            flags=flags,
        )

    # --- Batch analysis ---

    def analyze(
        self,
        df: pd.DataFrame,
        category_col: str = "Category",
        amount_col: str = "Amount",
        timestamp_col: str = "Date",
        monthly_housing: float = 0,
        monthly_nonhousing_bilt: float = 0,
    ) -> tuple[pd.DataFrame, dict]:
        """
        Process a Monarch Money export and return optimized card assignments.

        Parameters
        ----------
        df : DataFrame with at minimum a category and amount column.
        category_col / amount_col / timestamp_col : column name overrides.
        monthly_housing : for Bilt tiered housing calc.
        monthly_nonhousing_bilt : non-housing spend on Bilt for tier calc.

        Returns
        -------
        results_df : DataFrame with card recommendations per row.
        summary : dict with totals and key metrics.
        """
        bilt_housing_rate = self.calc_bilt_housing_rate(monthly_housing, monthly_nonhousing_bilt)

        rows = []
        totals = {
            "total_spend": 0.0,
            "total_rewards": 0.0,
            "ach_leakage_potential": 0.0,
            "insurance_opportunity": 0.0,
            "below_floor_spend": 0.0,
            "card_breakdown": {},
            "flag_counts": {f.name: 0 for f in SpendFlag},
        }

        for _, row in df.iterrows():
            cat = row.get(category_col, "")
            amt = abs(float(row.get(amount_col, 0)))
            ts = row.get(timestamp_col)

            rec = self.get_optimal_card(cat, amt, ts, bilt_housing_rate)
            totals["total_spend"] += amt
            totals["total_rewards"] += rec.annual_reward

            # Track ACH leakage
            internal_tag = CATEGORY_MAP.get(cat, "general")
            if internal_tag in ACH_CATEGORIES:
                totals["ach_leakage_potential"] += rec.annual_reward

            if internal_tag == "insurance":
                totals["insurance_opportunity"] += rec.annual_reward

            # Card breakdown
            totals["card_breakdown"].setdefault(rec.card, {"spend": 0, "rewards": 0})
            totals["card_breakdown"][rec.card]["spend"] += amt
            totals["card_breakdown"][rec.card]["rewards"] += rec.annual_reward

            # Flag counts
            for f in rec.flags:
                totals["flag_counts"][f.name] += 1

            rows.append({
                "Category": cat,
                "Amount": amt,
                "Best Card": rec.card,
                "Rate": f"{rec.rate_pct:.1f}%",
                "Reward Value": round(rec.annual_reward, 2),
                "Note": rec.note,
                "Flags": ", ".join(f.value for f in rec.flags) if rec.flags else "",
            })

        results_df = pd.DataFrame(rows)

        # Effective blended rate
        if totals["total_spend"] > 0:
            totals["blended_rate_pct"] = round(
                (totals["total_rewards"] / totals["total_spend"]) * 100, 2
            )
        else:
            totals["blended_rate_pct"] = 0.0

        # Annual fee ROI
        total_fees = sum(
            self.cards[name].annual_fee
            for name in totals["card_breakdown"]
            if name in self.cards
        )
        totals["total_annual_fees"] = total_fees
        totals["net_rewards_after_fees"] = round(totals["total_rewards"] - total_fees, 2)

        return results_df, totals

    # --- Reporting ---

    @staticmethod
    def print_summary(summary: dict) -> None:
        """Print a human-readable summary of the optimization analysis."""
        print("\n" + "=" * 60)
        print("  REWARD OPTIMIZATION SUMMARY")
        print("=" * 60)
        print(f"  Total Spend Analyzed:    ${summary['total_spend']:>12,.2f}")
        print(f"  Total Reward Value:      ${summary['total_rewards']:>12,.2f}")
        print(f"  Blended Reward Rate:      {summary['blended_rate_pct']:>11.2f}%")
        print(f"  Total Annual Fees:       ${summary['total_annual_fees']:>12,.2f}")
        print(f"  Net Rewards (after fees):${summary['net_rewards_after_fees']:>12,.2f}")
        print("-" * 60)

        if summary["ach_leakage_potential"] > 0:
            print(f"  ⚡ ACH Leakage Recovery:  ${summary['ach_leakage_potential']:>12,.2f}")
            print(f"     (Rewards lost by paying housing/utilities/insurance via bank)")

        if summary["insurance_opportunity"] > 0:
            print(f"  🛡️  Insurance Card Opp:    ${summary['insurance_opportunity']:>12,.2f}")

        print("\n  Card-by-Card Breakdown:")
        print("  " + "-" * 56)
        for card, data in sorted(
            summary["card_breakdown"].items(),
            key=lambda x: x[1]["rewards"],
            reverse=True,
        ):
            print(f"    {card:<35} ${data['spend']:>10,.2f}  →  ${data['rewards']:>8,.2f}")

        active_flags = {k: v for k, v in summary["flag_counts"].items() if v > 0}
        if active_flags:
            print("\n  Optimization Flags:")
            print("  " + "-" * 56)
            for flag_name, count in active_flags.items():
                print(f"    {flag_name:<40} {count:>3} txns")

        print("=" * 60 + "\n")


# ─────────────────────────────────────────────
#  Card Acquisition Planner
# ─────────────────────────────────────────────

@dataclass
class CardAcquisitionStep:
    """One step in the recommended card acquisition timeline."""
    priority: int
    card: str
    apply_date: date
    annual_fee: float
    projected_monthly_rewards: float
    projected_annual_rewards: float
    spend_captured: float
    categories_unlocked: list[str]
    rationale: str
    signup_bonus: str = ""  # user fills in or we estimate
    hard_inquiry_note: str = ""
    cumulative_blended_rate: float = 0.0


# Known SUBs as of Feb 2026 — conservative estimates, update as offers change
SIGNUP_BONUSES: dict[str, str] = {
    "Bilt Palladium":                "None (invite-only, but housing rewards start immediately)",
    "Citi Strata Elite":             "75,000 ThankYou pts ($4k/3mo) ≈ $1,350 at 1.8 cpp",
    "Amex Blue Cash Preferred":      "$350 back ($3k/6mo)",
    "Wells Fargo Attune":            "$200 back ($500/3mo)",
    "US Bank Cash+":                 "$200 back ($1k/120 days)",
    "Wells Fargo Autograph Journey":  "30,000 pts ($1.5k/3mo) ≈ $450 at 1.5 cpp",
    "State Farm Premier Cash Rewards":"$200 back (State Farm customer, $500/3mo)",
    "Atmos Ascent":                  "5,000 Atmos pts ($1k/3mo) ≈ $50",
    "Wells Fargo Active Cash":       "$200 back ($500/3mo)",
    "Citi Double Cash":              "$200 back ($1.5k/6mo)",
    "Chase Freedom Flex":            "$200 back ($500/3mo)",
    "Discover it":                   "Cashback Match (all CB doubled year 1)",
}

# Hard inquiry constraints per bureau (5/24 for Chase, 6/24 for Amex, etc.)
ISSUER_VELOCITY_NOTES: dict[str, str] = {
    "Chase":        "5/24 rule — denied if 5+ new cards across all issuers in 24 months",
    "Amex":         "1 credit card + 1 charge card per 5 days; limited to ~4-5 Amex cards",
    "Citi":         "8/65 rule (1 app/8 days, 2/65 days); 24-month SUB restriction on same card",
    "Wells Fargo":  "Generally 1 per product family at a time; cell phone restriction",
    "US Bank":      "Sensitive to recent inquiries; prefer low inquiry count",
    "Discover":     "Only 1 Discover card at a time",
    "Bilt":         "Invite-only; no traditional hard pull for existing renters in network",
    "State Farm":   "Must be State Farm customer; lower approval bar",
    "Atmos":        "Neobank; soft pull for most applicants",
}


class CardAcquisitionPlanner:
    """
    Given spending analysis results, builds a prioritized 90-day-cadence
    acquisition plan for cards the client doesn't already own.

    Strategy:
    1. Rank missing cards by incremental monthly reward value
    2. Factor in SUB value amortized over year 1
    3. Respect issuer velocity rules (Chase 5/24, etc.)
    4. Space applications 90 days apart to minimize inquiry damage
    """

    CADENCE_DAYS = 90

    def __init__(self, existing_cards: list[str] | None = None, start_date: date | None = None):
        """
        Parameters
        ----------
        existing_cards : list of card names the client already has (matched to CARD_DB keys)
        start_date : when to begin the acquisition timeline (default: today)
        """
        self.existing_cards = set(existing_cards or [])
        self.start_date = start_date or date.today()

    def _get_issuer(self, card_name: str) -> str:
        """Infer issuer from card name for velocity rule lookups."""
        issuer_map = {
            "Chase": ["Chase Freedom Flex"],
            "Amex": ["Amex Blue Cash Preferred"],
            "Citi": ["Citi Strata Elite", "Citi Double Cash"],
            "Wells Fargo": ["Wells Fargo Active Cash", "Wells Fargo Attune", "Wells Fargo Autograph Journey"],
            "US Bank": ["US Bank Cash+"],
            "Discover": ["Discover it"],
            "Bilt": ["Bilt Palladium"],
            "State Farm": ["State Farm Premier Cash Rewards"],
            "Atmos": ["Atmos Ascent"],
        }
        for issuer, cards in issuer_map.items():
            if card_name in cards:
                return issuer
        return "Unknown"

    def plan(
        self,
        summary: dict,
        cards_db: dict[str, CardProfile] | None = None,
    ) -> list[CardAcquisitionStep]:
        """
        Build an acquisition roadmap from the spend analysis summary.

        Parameters
        ----------
        summary : the summary dict from RewardOptimizer.analyze()
        cards_db : the card database (defaults to CARD_DB)

        Returns
        -------
        list of CardAcquisitionStep ordered by priority
        """
        cards_db = cards_db or CARD_DB
        breakdown = summary.get("card_breakdown", {})

        # Identify cards the optimizer recommends but client doesn't own
        missing_cards: list[dict] = []
        for card_name, data in breakdown.items():
            if card_name in self.existing_cards:
                continue
            profile = cards_db.get(card_name)
            if not profile:
                continue

            monthly_rewards = data["rewards"]
            annual_rewards = monthly_rewards * 12
            annual_fee = profile.annual_fee
            net_year1 = annual_rewards - annual_fee
            spend = data["spend"]

            # Estimate SUB value for year-1 priority weighting
            sub_text = SIGNUP_BONUSES.get(card_name, "Unknown")
            # Extract rough dollar value from SUB text for sorting
            sub_value = 0.0
            if "≈ $" in sub_text:
                try:
                    sub_value = float(sub_text.split("≈ $")[1].split()[0].replace(",", ""))
                except (ValueError, IndexError):
                    pass
            elif sub_text.startswith("$"):
                try:
                    sub_value = float(sub_text.split("$")[1].split()[0].replace(",", ""))
                except (ValueError, IndexError):
                    pass

            # Year-1 total value = SUB + net annual rewards
            year1_value = sub_value + net_year1

            # Build category list this card unlocks
            cats_unlocked = []
            if profile.categories:
                cats_unlocked = list(profile.categories.keys())
            elif profile.base_rate >= 0.02:
                cats_unlocked = ["general (2% floor)"]

            missing_cards.append({
                "card": card_name,
                "monthly_rewards": monthly_rewards,
                "annual_rewards": annual_rewards,
                "annual_fee": annual_fee,
                "spend": spend,
                "year1_value": year1_value,
                "sub_text": sub_text,
                "cats_unlocked": cats_unlocked,
                "issuer": self._get_issuer(card_name),
            })

        # Sort by year-1 total value descending
        missing_cards.sort(key=lambda x: x["year1_value"], reverse=True)

        # Build the cadence timeline
        steps: list[CardAcquisitionStep] = []
        apply_date = self.start_date
        seen_issuers_in_window: dict[str, date] = {}
        running_monthly_rewards = 0.0
        total_monthly_spend = summary.get("total_spend", 1)

        # Add existing card rewards to running total
        for card_name in self.existing_cards:
            if card_name in breakdown:
                running_monthly_rewards += breakdown[card_name]["rewards"]

        for i, card_info in enumerate(missing_cards):
            issuer = card_info["issuer"]

            # Build rationale
            if card_info["annual_fee"] > 0:
                fee_note = f"${card_info['annual_fee']}/yr fee offset by ${card_info['annual_rewards']:,.0f}/yr in rewards"
            else:
                fee_note = "No annual fee"

            rationale = (
                f"Captures ${card_info['spend']:,.0f}/mo in "
                f"{', '.join(card_info['cats_unlocked'][:3])} spend. {fee_note}."
            )

            # Check for issuer velocity conflicts
            velocity_note = ISSUER_VELOCITY_NOTES.get(issuer, "")
            if issuer in seen_issuers_in_window:
                last_app = seen_issuers_in_window[issuer]
                days_since = (apply_date - last_app).days
                if days_since < 90:
                    velocity_note += f" ⚠️ Same issuer applied {days_since}d ago — consider spacing further."

            running_monthly_rewards += card_info["monthly_rewards"]
            cumulative_blended = (running_monthly_rewards / total_monthly_spend) * 100 if total_monthly_spend else 0

            steps.append(CardAcquisitionStep(
                priority=i + 1,
                card=card_info["card"],
                apply_date=apply_date,
                annual_fee=card_info["annual_fee"],
                projected_monthly_rewards=card_info["monthly_rewards"],
                projected_annual_rewards=card_info["annual_rewards"],
                spend_captured=card_info["spend"],
                categories_unlocked=card_info["cats_unlocked"],
                rationale=rationale,
                signup_bonus=card_info["sub_text"],
                hard_inquiry_note=velocity_note,
                cumulative_blended_rate=round(cumulative_blended, 2),
            ))

            seen_issuers_in_window[issuer] = apply_date
            apply_date = apply_date + pd.Timedelta(days=self.CADENCE_DAYS)

        return steps

    @staticmethod
    def print_plan(steps: list[CardAcquisitionStep], existing_cards: set[str] | None = None) -> None:
        """Print a formatted acquisition roadmap."""
        print("\n" + "=" * 72)
        print("  CARD ACQUISITION ROADMAP (90-Day Cadence)")
        print("=" * 72)

        if existing_cards:
            print(f"\n  Cards Already in Wallet: {', '.join(sorted(existing_cards))}")

        if not steps:
            print("\n  ✅ Client already holds all recommended cards!")
            print("=" * 72)
            return

        total_new_annual_rewards = 0
        total_new_fees = 0

        for step in steps:
            total_new_annual_rewards += step.projected_annual_rewards
            total_new_fees += step.annual_fee

            print(f"\n  ┌─ #{step.priority}  {step.card}")
            print(f"  │  Apply by:       {step.apply_date.strftime('%B %d, %Y')}")
            print(f"  │  Annual Fee:     ${step.annual_fee:,.0f}")
            print(f"  │  Monthly Spend:  ${step.spend_captured:>10,.2f}")
            print(f"  │  Monthly Reward: ${step.projected_monthly_rewards:>10,.2f}")
            print(f"  │  Annual Reward:  ${step.projected_annual_rewards:>10,.2f}")
            if step.signup_bonus:
                print(f"  │  Sign-Up Bonus:  {step.signup_bonus}")
            print(f"  │  Categories:     {', '.join(step.categories_unlocked[:4])}")
            print(f"  │  Rationale:      {step.rationale}")
            if step.hard_inquiry_note:
                print(f"  │  Issuer Note:    {step.hard_inquiry_note}")
            print(f"  │  Cumulative Rate: {step.cumulative_blended_rate:.2f}% blended")
            print(f"  └{'─' * 70}")

        print(f"\n  ── ACQUISITION SUMMARY ──")
        print(f"  New cards to apply for:  {len(steps)}")
        print(f"  Timeline:                {steps[0].apply_date.strftime('%b %Y')} → {steps[-1].apply_date.strftime('%b %Y')}")
        print(f"  New annual rewards:      ${total_new_annual_rewards:>10,.2f}")
        print(f"  New annual fees:         ${total_new_fees:>10,.2f}")
        print(f"  Net new value:           ${total_new_annual_rewards - total_new_fees:>10,.2f}")
        print(f"  Final blended rate:      {steps[-1].cumulative_blended_rate:.2f}%")
        print("=" * 72 + "\n")


# ─────────────────────────────────────────────
#  Demo / Quick Test
# ─────────────────────────────────────────────

if __name__ == "__main__":

    # Sample Monarch-style spending data
    sample_data = pd.DataFrame([
        {"Category": "Rent",              "Amount": 3000, "Date": "2026-02-01"},
        {"Category": "Groceries",         "Amount": 800,  "Date": "2026-02-10"},
        {"Category": "Restaurants",       "Amount": 400,  "Date": "2026-02-07 19:30"},  # Fri night
        {"Category": "Restaurants",       "Amount": 150,  "Date": "2026-02-12 12:00"},  # Wed lunch
        {"Category": "Gas & Electric",    "Amount": 180,  "Date": "2026-02-15"},
        {"Category": "Internet & Cable",  "Amount": 80,   "Date": "2026-02-15"},
        {"Category": "Streaming Services","Amount": 45,   "Date": "2026-02-15"},
        {"Category": "Fitness",           "Amount": 120,  "Date": "2026-02-01"},
        {"Category": "Gas",               "Amount": 200,  "Date": "2026-02-20"},
        {"Category": "Auto Insurance",    "Amount": 150,  "Date": "2026-02-01"},  # 1st of month
        {"Category": "Shopping",          "Amount": 300,  "Date": "2026-02-18"},
        {"Category": "Airlines",          "Amount": 500,  "Date": "2026-02-25"},
        {"Category": "Pets",              "Amount": 75,   "Date": "2026-02-22"},
        {"Category": "Phone",             "Amount": 90,   "Date": "2026-02-15"},
        {"Category": "Insurance",         "Amount": 200,  "Date": "2026-02-15"},
    ])

    optimizer = RewardOptimizer()
    results, summary = optimizer.analyze(
        sample_data,
        monthly_housing=3000,
        monthly_nonhousing_bilt=3500,  # spending more than housing on Bilt → max tier
    )

    print(results.to_string(index=False))
    optimizer.print_summary(summary)
