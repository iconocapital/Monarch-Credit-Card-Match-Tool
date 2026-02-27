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

# ─── Imports from refactored modules ───
from card_models import CardProfile, CARD_DB
from icono_engine import (
    icono_perk_value, icono_score_ongoing, icono_score_year1,
    load_transactions, map_earn_category,
    CATEGORY_MAP, ACH_CATEGORIES,
    NON_EXPENSE_CATEGORIES, NON_EXPENSE_PATTERNS,
    NON_EXPENSE_MERCHANTS, NON_EXPENSE_MERCHANT_PATTERNS,
)


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


# CardProfile, CARD_DB, CATEGORY_MAP, ICONO functions, and NON_EXPENSE
# filters are now imported from card_models.py and icono_engine.py.
# QUARTERLY_ROTATIONS and ACCOUNT_NAME_PATTERNS remain here as they
# are specific to the transaction routing engine.

# ─────────────────────────────────────────────
#  Account Name → Card DB Key Mapping
# ─────────────────────────────────────────────
# Maps partial substrings found in Monarch's Account column to CARD_DB keys.
# Matching is case-insensitive. Order matters: more specific patterns first.

ACCOUNT_NAME_PATTERNS: list[tuple[str, str]] = [
    # Premium Travel
    ("venture x",               "Capital One Venture X"),
    ("sapphire reserve",        "Chase Sapphire Reserve"),
    ("amex platinum",           "Amex Platinum"),
    ("platinum card",           "Amex Platinum"),
    ("atmos summit",            "Bank of America Atmos Summit"),
    # Mid-Tier Travel
    ("sapphire preferred",      "Chase Sapphire Preferred"),
    ("ventureone",              "Capital One VentureOne"),
    ("venture one",             "Capital One VentureOne"),
    ("amex gold",               "Amex Gold"),
    ("gold card",               "Amex Gold"),
    ("strata premier",          "Citi Strata Premier"),
    ("atmos ascend",            "Bank of America Atmos Ascend"),
    # No-Fee Travel  (check "venture" AFTER venture x / ventureone)
    ("venture",                 "Capital One Venture"),
    ("bilt",                    "Bilt Mastercard"),
    # Flat Rate Cash Back
    ("freedom unlimited",       "Chase Freedom Unlimited"),
    ("double cash",             "Citi Double Cash"),
    ("paypal",                  "PayPal Cashback Mastercard"),
    # Category Cash Back
    ("blue cash preferred",     "Amex Blue Cash Preferred"),
    ("blue cash everyday",      "Amex Blue Cash Everyday"),
    ("freedom flex",            "Chase Freedom Flex"),
    ("savorone",                "Capital One SavorOne"),
    ("savor",                   "Capital One Savor"),
    ("custom cash",             "Citi Custom Cash"),
    ("premium rewards",         "Bank of America Premium Rewards"),
    # Business
    ("blue business plus",      "Blue Business Plus"),
    ("bbp",                     "Blue Business Plus"),
    # Store / Co-Brand
    ("amazon",                  "Amazon Prime Visa"),
    ("prime visa",              "Amazon Prime Visa"),
    ("apple card",              "Apple Card"),
    ("marriott",                "Chase Marriott Bonvoy Boundless"),
    ("bonvoy",                  "Chase Marriott Bonvoy Boundless"),
    # Wells Fargo (additional)
    ("autograph journey",       "Wells Fargo Autograph Journey"),
    ("attune",                  "Wells Fargo Attune"),
    # US Bank
    ("cash+",                   "US Bank Cash+"),
    ("us bank cash",            "US Bank Cash+"),
    # State Farm
    ("state farm",              "State Farm Premier Cash Rewards"),
]

# Bank account keywords to skip during card detection
_BANK_ACCOUNT_KEYWORDS = (
    "checking", "savings", "fund", "emergency", "target",
    "money market", "brokerage", "ira", "401k", "hsa",
)


def detect_cards_from_accounts(df: pd.DataFrame, account_col: str = "Account") -> set[str]:
    """
    Scan the Account column of a Monarch export and return CARD_DB keys
    for any credit cards that can be identified from account names.
    """
    if account_col not in df.columns:
        return set()

    unique_accounts = df[account_col].dropna().unique()
    detected: set[str] = set()

    for account_name in unique_accounts:
        acct_lower = str(account_name).lower().strip()
        # Skip bank/savings accounts
        if any(kw in acct_lower for kw in _BANK_ACCOUNT_KEYWORDS):
            continue
        for pattern, card_key in ACCOUNT_NAME_PATTERNS:
            if pattern in acct_lower:
                detected.add(card_key)
                break  # first match wins for this account

    return detected





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

    def __init__(self, cards: dict[str, CardProfile] | None = None, owned_cards: set[str] | None = None):
        self.cards = cards or CARD_DB
        self.owned_cards: set[str] = owned_cards or set()
        self.floor_card, self.floor_rate = self._compute_floor()

    def _compute_floor(self) -> tuple[str, float]:
        """
        Among owned cards with base_rate >= 2%, find the one with the
        highest effective floor value (base_rate * cpp_valuation).
        Falls back to Capital One Venture X if no owned card qualifies.
        """
        DEFAULT_CARD = "Capital One Venture X"
        DEFAULT_RATE = 0.02
        default_cpp = self.cards.get(DEFAULT_CARD, CardProfile(name="", annual_fee=0)).cpp_valuation
        best_effective = DEFAULT_RATE * default_cpp  # 0.02 * 1.0 = 0.02
        best_card = DEFAULT_CARD
        best_rate = DEFAULT_RATE

        for card_name in self.owned_cards:
            profile = self.cards.get(card_name)
            if not profile or profile.base_rate < 0.02:
                continue
            effective = profile.base_rate * profile.cpp_valuation
            if effective > best_effective:
                best_effective = effective
                best_card = card_name
                best_rate = profile.base_rate

        return best_card, best_rate

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
        Bilt tiered housing multiplier:
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
                "Bilt Mastercard",
                bilt_housing_rate * 100,
                f"Bilt tiered housing multiplier ({bilt_housing_rate*100:.2f}%). Move from ACH to Bilt.",
            ))

        # Dining — check Citi Nights
        elif internal_tag == "dining":
            if self.is_citi_night(timestamp):
                flags.append(SpendFlag.CITI_NIGHT)
                candidates.append(("Citi Strata Premier", 6.0, "Citi Nights 6x (Fri/Sat 6pm–6am ET)."))

            # Bilt 1st of month double points on dining
            if self.is_bilt_first(timestamp):
                flags.append(SpendFlag.BILT_FIRST)
                candidates.append(("Bilt Mastercard", 6.0, "Bilt 1st-of-month: dining doubled to 6x."))

            candidates.append(("Citi Strata Premier", 3.0, "Standard 3x dining."))
            candidates.append(("Bilt Mastercard", 3.0, "Bilt 3x dining."))
            candidates.append(("Capital One Savor", 4.0, "4% dining."))
            candidates.append(("Bank of America Atmos Summit", 4.0, "4% dining."))

            # Add rotating if applicable
            if best_rotating_card:
                candidates.append((best_rotating_card, best_rotating_rate * 100, best_rotating_note))

        # Groceries
        elif internal_tag == "groceries":
            candidates.append(("Amex Blue Cash Preferred", 6.0, "6% groceries (up to $6k/yr)."))
            candidates.append(("Capital One Savor", 3.0, "3% groceries."))
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
            candidates.append(("Capital One Savor", 3.0, "3% streaming."))

        # Gas
        elif internal_tag == "gas":
            candidates.append(("Amex Blue Cash Preferred", 3.0, "3% gas stations."))
            candidates.append(("Bank of America Atmos Ascend", 2.0, "2% gas + Atmos status points."))

        # Transit
        elif internal_tag == "transit":
            candidates.append(("Wells Fargo Attune", 4.0, "4% transit."))
            candidates.append(("Amex Blue Cash Preferred", 3.0, "3% transit."))

        # Airlines
        elif internal_tag == "airlines":
            candidates.append(("Wells Fargo Autograph Journey", 5.0, "5x airlines."))
            candidates.append(("Citi Strata Premier", 3.0, "3x airlines."))
            candidates.append(("Bank of America Atmos Summit", 3.0, "3% airlines."))

        # Hotels
        elif internal_tag == "hotels":
            candidates.append(("Citi Strata Premier", 3.0, "3x hotels."))
            candidates.append(("Wells Fargo Autograph Journey", 4.0, "4x hotels."))
            candidates.append(("Chase Marriott Bonvoy Boundless", 6.0, "6x at Marriott properties."))
            candidates.append(("Bank of America Atmos Summit", 3.0, "3% hotels."))

        # Car Rental
        elif internal_tag == "car_rental":
            candidates.append(("Wells Fargo Autograph Journey", 3.0, "3x car rental."))

        # Travel (general)
        elif internal_tag == "travel":
            candidates.append(("Bilt Mastercard", 2.0, "2x travel."))
            candidates.append(("Wells Fargo Autograph Journey", 3.0, "3x travel (if classified)."))
            candidates.append(("Bank of America Atmos Summit", 3.0, "3% travel."))

        # Entertainment
        elif internal_tag == "entertainment":
            candidates.append(("Capital One Savor", 4.0, "4% entertainment."))

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
                candidates.append(("Bilt Mastercard", 4.0, "Bilt 1st-of-month: 2x base → 4x on insurance."))

        # Auto (general)
        elif internal_tag == "auto":
            candidates.append(("Bank of America Atmos Ascend", 2.0, "2% auto / transport for Atmos status."))

        # Amazon
        elif internal_tag == "amazon":
            candidates.append(("Amazon Prime Visa", 5.0, "5% Amazon with Prime."))

        # Whole Foods
        elif internal_tag == "whole_foods":
            candidates.append(("Amazon Prime Visa", 5.0, "5% Whole Foods with Prime."))
            candidates.append(("Amex Blue Cash Preferred", 6.0, "6% groceries (Whole Foods qualifies)."))

        # Apple
        elif internal_tag == "apple":
            candidates.append(("Apple Card", 3.0, "3% Apple purchases."))

        # Online retail
        elif internal_tag == "online_retail":
            candidates.append(("PayPal Cashback Mastercard", 3.0, "3% via PayPal checkout."))

        # Pharmacy
        elif internal_tag == "pharmacy":
            pass  # falls through to floor card

        # --- Pick the winner ---
        # Add the floor card as a baseline (dynamic: best owned 2%+ card or Capital One Venture X)
        floor_profile = self.cards.get(self.floor_card)
        floor_cpp = floor_profile.cpp_valuation if floor_profile else 1.0
        floor_note = f"{self.floor_rate*100:.0f}% flat-rate floor"
        if self.floor_card != "Capital One Venture X":
            floor_note += f" via {self.floor_card}"
        if floor_cpp > 1.0:
            floor_eff_pct = self.floor_rate * 100 * floor_cpp
            floor_note += f" ({floor_eff_pct:.1f}% effective at {floor_cpp:.2f}x cpp)"
        floor_note += "."
        candidates.append((self.floor_card, self.floor_rate * 100, floor_note))

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
        floor_effective = self.floor_rate * 100 * floor_cpp  # use actual floor card cpp

        if effective_pct < floor_effective:
            flags.append(SpendFlag.BELOW_FLOOR)
            best_card = self.floor_card
            best_rate = self.floor_rate * 100
            best_note = f"Below floor — defaulting to {self.floor_card}."
            best_cpp = floor_cpp

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

        # ── Step 1: Clean the data — use icono_engine.load_transactions ──
        # load_transactions is the single source of truth for non-expense
        # filtering and category normalization.
        work = load_transactions(df, category_col=category_col, amount_col=amount_col)

        # ── Step 2: Split by account type (credit card vs bank/savings) ──
        account_col = "Account"
        has_accounts = account_col in work.columns

        if has_accounts:
            acct_lower = work[account_col].str.lower().fillna("")
            is_bank = acct_lower.str.contains(
                r'checking|savings|fund|emergency|target|money market|brokerage|ira|401k|hsa',
                case=False, na=False,
            )
            card_txns = work[~is_bank]
            bank_txns = work[is_bank]
        else:
            card_txns = work
            bank_txns = pd.DataFrame()

        # ── Step 2b: Auto-detect owned cards from Account column ──
        auto_detected: set[str] = set()
        if has_accounts:
            auto_detected = detect_cards_from_accounts(df, account_col)
            merged = self.owned_cards | auto_detected
            if merged != self.owned_cards:
                self.owned_cards = merged
                self.floor_card, self.floor_rate = self._compute_floor()

        # ── Step 3: Calculate months of data for normalization ──
        all_expenses = work  # use full filtered set for date range
        if timestamp_col in all_expenses.columns:
            dates = pd.to_datetime(all_expenses[timestamp_col], errors="coerce").dropna()
            if len(dates) > 1:
                span_days = (dates.max() - dates.min()).days + 1  # inclusive
                months_of_data = max(span_days / 30.44, 1.0)
            else:
                months_of_data = 1.0
        else:
            months_of_data = 1.0

        # ── Step 4: Analyze credit card transactions (primary) ──
        rows = []
        totals = {
            "total_spend": 0.0,
            "total_rewards": 0.0,
            "ach_leakage_potential": 0.0,
            "ach_leakage_spend": 0.0,
            "insurance_opportunity": 0.0,
            "below_floor_spend": 0.0,
            "card_breakdown": {},
            "flag_counts": {f.name: 0 for f in SpendFlag},
            "months_of_data": round(months_of_data, 1),
            "rows_analyzed": len(card_txns),
            "rows_excluded": len(df) - len(work),
            "bank_rows_separated": len(bank_txns),
            "ach_leakage_items": [],
            "auto_detected_cards": sorted(auto_detected),
            "owned_cards": sorted(self.owned_cards),
            "floor_card": self.floor_card,
        }

        for _, row in card_txns.iterrows():
            cat = row.get(category_col, "")
            amt = float(row.get("_spend", abs(float(row.get(amount_col, 0)))))
            ts = row.get(timestamp_col)

            rec = self.get_optimal_card(cat, amt, ts, bilt_housing_rate)
            totals["total_spend"] += amt
            totals["total_rewards"] += rec.annual_reward

            if internal_tag := CATEGORY_MAP.get(cat, "general"):
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

        # ── Step 5: Analyze bank transactions for ACH leakage opportunities ──
        for _, row in bank_txns.iterrows():
            cat = row.get(category_col, "")
            amt = float(row.get("_spend", abs(float(row.get(amount_col, 0)))))
            ts = row.get(timestamp_col)
            merchant = str(row.get("Merchant", ""))
            account = row.get(account_col, "")
            internal_tag = CATEGORY_MAP.get(cat, "general")

            # Skip transactions > $5,000 — likely wires, construction, non-card-eligible
            if amt > 5000:
                continue

            # Skip non-card-eligible merchants (ATM, wire, person-to-person)
            merch_lower = merchant.lower().strip()
            if merch_lower in NON_EXPENSE_MERCHANTS:
                continue
            if any(merch_lower.startswith(p) for p in NON_EXPENSE_MERCHANT_PATTERNS):
                continue

            rec = self.get_optimal_card(cat, amt, ts, bilt_housing_rate)
            totals["ach_leakage_potential"] += rec.annual_reward
            totals["ach_leakage_spend"] += amt
            totals["ach_leakage_items"].append({
                "Category": cat,
                "Amount": amt,
                "Merchant": merchant,
                "Account": account,
                "Best Card": rec.card,
                "Rate": f"{rec.rate_pct:.1f}%",
                "Potential Reward": round(rec.annual_reward, 2),
            })

        results_df = pd.DataFrame(rows)

        # ── Step 6: Normalize to monthly figures ──
        if months_of_data > 0 and months_of_data != 1.0:
            monthly_factor = 1.0 / months_of_data
        else:
            monthly_factor = 1.0

        totals["total_spend"] = round(totals["total_spend"] * monthly_factor, 2)
        totals["total_rewards"] = round(totals["total_rewards"] * monthly_factor, 2)
        totals["ach_leakage_potential"] = round(totals["ach_leakage_potential"] * monthly_factor, 2)
        totals["ach_leakage_spend"] = round(totals["ach_leakage_spend"] * monthly_factor, 2)
        totals["insurance_opportunity"] = round(totals["insurance_opportunity"] * monthly_factor, 2)
        totals["below_floor_spend"] = round(totals["below_floor_spend"] * monthly_factor, 2)

        # Normalize card breakdown to monthly
        for card in totals["card_breakdown"]:
            totals["card_breakdown"][card]["spend"] = round(
                totals["card_breakdown"][card]["spend"] * monthly_factor, 2
            )
            totals["card_breakdown"][card]["rewards"] = round(
                totals["card_breakdown"][card]["rewards"] * monthly_factor, 2
            )

        # Effective blended rate
        if totals["total_spend"] > 0:
            totals["blended_rate_pct"] = round(
                (totals["total_rewards"] / totals["total_spend"]) * 100, 2
            )
        else:
            totals["blended_rate_pct"] = 0.0

        # Annual fee ROI — Icono weighted perk values instead of raw credits
        total_gross_fees = sum(
            self.cards[name].annual_fee
            for name in totals["card_breakdown"]
            if name in self.cards
        )
        total_raw_credits = sum(
            self.cards[name].annual_credits
            for name in totals["card_breakdown"]
            if name in self.cards
        )
        total_icono_perks = sum(
            icono_perk_value(self.cards[name])
            for name in totals["card_breakdown"]
            if name in self.cards
        )
        totals["total_annual_fees"] = total_gross_fees
        totals["total_annual_credits"] = total_raw_credits
        totals["total_icono_perks"] = round(total_icono_perks, 2)
        totals["effective_annual_fees"] = round(total_gross_fees - total_icono_perks, 2)
        totals["net_rewards_after_fees"] = round(
            totals["total_rewards"] - (total_gross_fees - total_icono_perks), 2
        )

        # Per-card Icono scores
        icono_card_scores = {}
        for name, data in totals["card_breakdown"].items():
            if name in self.cards:
                profile = self.cards[name]
                annual_rewards = data["rewards"] * 12
                icono_card_scores[name] = {
                    "icono_perks": round(icono_perk_value(profile), 2),
                    "icono_ongoing": round(icono_score_ongoing(profile, annual_rewards), 2),
                    "icono_year1": round(icono_score_year1(profile, annual_rewards), 2),
                }
        totals["icono_card_scores"] = icono_card_scores

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


# Known SUBs as of Feb 2026 — dollar values based on current cpp valuations
SIGNUP_BONUSES: dict[str, str] = {
    # Premium Travel
    "Amex Platinum":             "150,000 MR pts ($8k/6mo) ≈ $3,000 at 1.99 cpp",
    "Chase Sapphire Reserve":    "60,000 UR pts ($4k/3mo) ≈ $1,200 at 2.0 cpp",
    "Capital One Venture X":     "75,000 miles ($4k/3mo) ≈ $1,530 at 2.04 cpp",
    "Bank of America Atmos Summit": "≈ $800 back ($4k/3mo)",
    # Mid-Tier Travel
    "Chase Sapphire Preferred":  "60,000 UR pts ($4k/3mo) ≈ $1,200 at 2.0 cpp",
    "Capital One Venture":       "75,000 miles ($4k/3mo) ≈ $1,530 at 2.04 cpp",
    "Amex Gold":                 "100,000 MR pts ($6k/6mo) ≈ $1,990 at 1.99 cpp",
    "Citi Strata Premier":       "60,000 TY pts ($4k/3mo) ≈ $1,374 at 2.29 cpp",
    "Bank of America Atmos Ascend": "≈ $600 back ($3k/3mo)",
    # No-Fee Travel
    "Capital One VentureOne":    "20,000 miles ($500/3mo) ≈ $408 at 2.04 cpp",
    "Bilt Mastercard":           "None (points on rent from day 1)",
    # Flat Rate Cash Back
    "Chase Freedom Unlimited":   "20,000 UR pts ($500/3mo) ≈ $400 at 2.0 cpp",
    "Citi Double Cash":          "$200 back ($1.5k/6mo)",
    "PayPal Cashback Mastercard":"None",
    # Category Cash Back
    "Amex Blue Cash Preferred":  "$300 back ($3k/6mo)",
    "Amex Blue Cash Everyday":   "$200 back ($2k/6mo)",
    "Chase Freedom Flex":        "$200 back ($500/3mo)",
    "Capital One SavorOne":      "$200 back ($500/3mo)",
    "Citi Custom Cash":          "20,000 TY pts ($1.5k/6mo) ≈ $458 at 2.29 cpp",
    "Capital One Savor":         "$200 back ($500/3mo)",
    "Bank of America Premium Rewards": "≈ $600 back ($3k/3mo)",
    # Business
    "Blue Business Plus":        "15,000 MR pts ($3k/3mo) ≈ $298.50 at 1.99 cpp",
    # Store / Co-Brand
    "Amazon Prime Visa":         "$150 Amazon gift card (instant approval)",
    "Apple Card":                "None (3% Daily Cash on Apple purchases)",
    "Chase Marriott Bonvoy Boundless": "75,000 Marriott pts ($3k/3mo) ≈ $525 at 0.7 cpp",
    # Wells Fargo (additional)
    "Wells Fargo Autograph Journey": "$500 back ($1k/3mo)",
    "Wells Fargo Attune":            "$200 back ($500/3mo)",
    # US Bank
    "US Bank Cash+":                 "$200 back ($1k/3mo)",
    # State Farm
    "State Farm Premier Cash Rewards": "None",
}

# Hard inquiry constraints per bureau (5/24 for Chase, 6/24 for Amex, etc.)
ISSUER_VELOCITY_NOTES: dict[str, str] = {
    "Chase":          "5/24 rule — denied if 5+ new cards across all issuers in 24 months",
    "Amex":           "1 credit card + 1 charge card per 5 days; limited to ~4-5 Amex cards; once-per-lifetime SUB",
    "Citi":           "8/65 rule (1 app/8 days, 2/65 days); 24-month SUB restriction on same card family",
    "Capital One":    "Typically limits to 2 C1 cards; may auto-deny if already at limit",
    "Wells Fargo":    "Generally 1 per product family at a time; cell phone restriction",
    "Bilt":           "Invite-only via rent network; no traditional hard pull for existing renters",
    "PayPal":         "Issued by Synchrony; moderate approval standards",
    "Amazon/Chase":   "Subject to Chase 5/24 rule (co-branded Chase card)",
    "Apple/Goldman":  "Soft pull for pre-approval; Goldman Sachs underwriting",
    "Bank of America": "7/12 rule (max 7 cards/12 months); 2/3/4 rule (2 BoA cards/2mo, 3/12mo, 4/24mo)",
    "US Bank":        "Generally conservative; may require existing US Bank relationship",
    "State Farm":     "Issued by US Bank; requires State Farm insurance policy",
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
            "Chase": ["Chase Sapphire Reserve", "Chase Sapphire Preferred",
                       "Chase Freedom Unlimited", "Chase Freedom Flex",
                       "Amazon Prime Visa", "Chase Marriott Bonvoy Boundless"],
            "Amex": ["Amex Platinum", "Amex Gold", "Amex Blue Cash Preferred",
                      "Amex Blue Cash Everyday", "Blue Business Plus"],
            "Citi": ["Citi Strata Premier", "Citi Double Cash", "Citi Custom Cash"],
            "Capital One": ["Capital One Venture X", "Capital One Venture", "Capital One VentureOne",
                            "Capital One SavorOne", "Capital One Savor"],
            "Wells Fargo": ["Wells Fargo Autograph Journey", "Wells Fargo Attune"],
            "Bilt": ["Bilt Mastercard"],
            "PayPal": ["PayPal Cashback Mastercard"],
            "Apple/Goldman": ["Apple Card"],
            "Bank of America": ["Bank of America Atmos Summit", "Bank of America Atmos Ascend",
                                "Bank of America Premium Rewards"],
            "US Bank": ["US Bank Cash+"],
            "State Farm": ["State Farm Premier Cash Rewards"],
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
            spend = data["spend"]

            # Use signup_bonus_value from CardProfile (accurate dollar amount)
            sub_value = profile.signup_bonus_value
            sub_text = SIGNUP_BONUSES.get(card_name, "Unknown")

            # Year-1 total value using Icono weighted perk haircuts
            year1_value = icono_score_year1(profile, annual_rewards)

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

    # Sample Monarch-style spending data (expenses are negative in Monarch)
    # Account column allows auto-detection of owned cards
    sample_data = pd.DataFrame([
        {"Category": "Rent",              "Amount": -3000, "Date": "2026-02-01", "Account": "Bilt Mastercard (...4321)"},
        {"Category": "Groceries",         "Amount": -800,  "Date": "2026-02-10", "Account": "Blue Cash Preferred (...9999)"},
        {"Category": "Restaurants",       "Amount": -400,  "Date": "2026-02-07 19:30", "Account": "Venture X (...6789)"},
        {"Category": "Restaurants",       "Amount": -150,  "Date": "2026-02-12 12:00", "Account": "Venture X (...6789)"},
        {"Category": "Gas & Electric",    "Amount": -180,  "Date": "2026-02-15", "Account": "Blue Cash Preferred (...9999)"},
        {"Category": "Internet & Cable",  "Amount": -80,   "Date": "2026-02-15", "Account": "Venture X (...6789)"},
        {"Category": "Streaming Services","Amount": -45,   "Date": "2026-02-15", "Account": "Blue Cash Preferred (...9999)"},
        {"Category": "Fitness",           "Amount": -120,  "Date": "2026-02-01", "Account": "Venture X (...6789)"},
        {"Category": "Gas",               "Amount": -200,  "Date": "2026-02-20", "Account": "Venture X (...6789)"},
        {"Category": "Auto Insurance",    "Amount": -150,  "Date": "2026-02-01", "Account": "Venture X (...6789)"},
        {"Category": "Shopping",          "Amount": -300,  "Date": "2026-02-18", "Account": "Venture X (...6789)"},
        {"Category": "Airlines",          "Amount": -500,  "Date": "2026-02-25", "Account": "Venture X (...6789)"},
        {"Category": "Pets",              "Amount": -75,   "Date": "2026-02-22", "Account": "Venture X (...6789)"},
        {"Category": "Phone",             "Amount": -90,   "Date": "2026-02-15", "Account": "Venture X (...6789)"},
        {"Category": "Insurance",         "Amount": -200,  "Date": "2026-02-15", "Account": "Venture X (...6789)"},
        # Bank transactions — should be separated and checked for ACH leakage
        {"Category": "Utilities",         "Amount": -120,  "Date": "2026-02-15", "Account": "Chase Checking (...1234)"},
        {"Category": "Insurance",         "Amount": -300,  "Date": "2026-02-01", "Account": "Chase Checking (...1234)"},
    ])

    # Owned cards: auto-detected from Account column + explicitly passed
    owned = {"Amex Blue Cash Preferred", "Capital One Venture X"}
    optimizer = RewardOptimizer(owned_cards=owned)
    results, summary = optimizer.analyze(
        sample_data,
        monthly_housing=3000,
        monthly_nonhousing_bilt=3500,  # spending more than housing on Bilt → max tier
    )

    print(results.to_string(index=False))
    optimizer.print_summary(summary)

    # Show owned-card awareness info
    print(f"  Auto-detected cards: {summary.get('auto_detected_cards', [])}")
    print(f"  All owned cards:     {summary.get('owned_cards', [])}")
    print(f"  Floor card:          {summary.get('floor_card', 'N/A')}")
    print()
