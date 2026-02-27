"""
Unit tests for the Icono scoring engine and card model utilities.

Run with:  pytest tests/test_icono.py -v
"""

import pandas as pd
import pytest

from card_models import CardProfile, CARD_DB, get_effective_cpp, CPP_FLOOR_MAP, refresh_cpp_from_awardwallet
from icono_engine import (
    map_earn_category,
    icono_perk_value,
    icono_score_ongoing,
    icono_score_year1,
    load_transactions,
    card_base_rewards,
    analyze_cards,
    ICONO_WEIGHTS,
)


# ─────────────────────────────────────────────
#  get_effective_cpp tests
# ─────────────────────────────────────────────

class TestGetEffectiveCpp:
    def test_awardwallet_mode_returns_card_value(self):
        card = CARD_DB["Chase Sapphire Reserve"]
        assert get_effective_cpp(card, mode="awardwallet") == 2.0

    def test_floor_mode_ur(self):
        card = CARD_DB["Chase Sapphire Reserve"]
        assert get_effective_cpp(card, mode="floor") == 1.5

    def test_floor_mode_mr(self):
        card = CARD_DB["Amex Platinum"]
        assert get_effective_cpp(card, mode="floor") == 0.9

    def test_floor_mode_cashback(self):
        card = CARD_DB["Citi Double Cash"]
        assert get_effective_cpp(card, mode="floor") == 1.0

    def test_floor_mode_ty_points(self):
        card = CARD_DB["Citi Strata Premier"]
        assert get_effective_cpp(card, mode="floor") == 1.5

    def test_floor_mode_bilt(self):
        card = CARD_DB["Bilt Blue"]
        assert get_effective_cpp(card, mode="floor") == 2.2

    def test_default_mode_is_awardwallet(self):
        card = CARD_DB["Amex Gold"]
        assert get_effective_cpp(card) == card.cpp_valuation


# ─────────────────────────────────────────────
#  refresh_cpp_from_awardwallet stub tests
# ─────────────────────────────────────────────

class TestRefreshCppStub:
    def test_returns_all_cards(self):
        result = refresh_cpp_from_awardwallet(CARD_DB)
        assert len(result) == len(CARD_DB)

    def test_returns_current_values(self):
        result = refresh_cpp_from_awardwallet(CARD_DB)
        assert result["Chase Sapphire Reserve"] == 2.0
        assert result["Amex Platinum"] == 1.99


# ─────────────────────────────────────────────
#  map_earn_category tests
# ─────────────────────────────────────────────

class TestMapEarnCategory:
    def test_dining_categories(self):
        assert map_earn_category("Restaurants") == "dining"
        assert map_earn_category("Fast Food") == "dining"
        assert map_earn_category("Bars & Alcohol") == "dining"

    def test_groceries(self):
        assert map_earn_category("Groceries") == "groceries"
        assert map_earn_category("Grocery") == "groceries"

    def test_housing(self):
        assert map_earn_category("Rent") == "housing"
        assert map_earn_category("Mortgage") == "housing"

    def test_utilities(self):
        assert map_earn_category("Gas & Electric") == "utilities"
        assert map_earn_category("Water") == "utilities"

    def test_travel(self):
        assert map_earn_category("Airlines") == "airlines"
        assert map_earn_category("Hotels") == "hotels"

    def test_unknown_returns_other(self):
        assert map_earn_category("Totally Made Up Category") == "other"
        assert map_earn_category("") == "other"

    def test_general_fallback(self):
        assert map_earn_category("Shopping") == "general"
        assert map_earn_category("Clothing") == "general"


# ─────────────────────────────────────────────
#  icono_perk_value tests
# ─────────────────────────────────────────────

class TestIconoPerkValue:
    def test_zero_perk_card(self):
        """No-fee card with no credits should have zero perk value."""
        card = CardProfile(name="Test", annual_fee=0)
        assert icono_perk_value(card) == 0.0

    def test_travel_only(self):
        """Travel credit at 1.0 weight."""
        card = CardProfile(name="Test", annual_fee=0, travel_credit=300)
        assert icono_perk_value(card) == 300.0

    def test_hotel_haircut(self):
        """Hotel credit should be 0.7 * 0.5 = 35% of face value."""
        card = CardProfile(name="Test", annual_fee=0, hotel_credit=100)
        expected = 100 * ICONO_WEIGHTS["hotel_util"] * ICONO_WEIGHTS["hotel_difficulty"]
        assert icono_perk_value(card) == expected
        assert icono_perk_value(card) == 35.0

    def test_amex_platinum(self):
        """Amex Platinum: travel $200 + uber $200*0.7 + streaming $240*0.5 + hotel $200*0.35."""
        plat = CARD_DB["Amex Platinum"]
        expected = (
            200 * 1.0      # travel
            + 200 * 0.7    # uber
            + 240 * 0.5    # streaming
            + 200 * 0.35   # hotel
        )
        assert icono_perk_value(plat) == expected

    def test_amex_gold(self):
        """Amex Gold: dining $304*0.7 + uber $120*0.7."""
        gold = CARD_DB["Amex Gold"]
        expected = 304 * 0.7 + 120 * 0.7
        assert icono_perk_value(gold) == expected

    def test_venture_x(self):
        """Venture X: travel $300*1.0 + other $100*0.7."""
        vx = CARD_DB["Capital One Venture X"]
        expected = 300 * 1.0 + 100 * 0.7
        assert icono_perk_value(vx) == expected


# ─────────────────────────────────────────────
#  icono_score_ongoing / year1 tests
# ─────────────────────────────────────────────

class TestIconoScores:
    def test_ongoing_manual(self):
        """Ongoing = rewards + perks - fee."""
        card = CardProfile(
            name="Test", annual_fee=95, travel_credit=100,
        )
        annual_rewards = 500.0
        perks = icono_perk_value(card)  # 100 * 1.0 = 100
        expected = annual_rewards + perks - 95
        assert icono_score_ongoing(card, annual_rewards) == expected
        assert icono_score_ongoing(card, annual_rewards) == 505.0

    def test_year1_includes_sub(self):
        """Year-1 = rewards + SUB + perks - fee."""
        card = CardProfile(
            name="Test", annual_fee=95, travel_credit=100,
            signup_bonus_value=1200,
        )
        annual_rewards = 500.0
        expected = annual_rewards + 1200 + 100 - 95
        assert icono_score_year1(card, annual_rewards) == expected
        assert icono_score_year1(card, annual_rewards) == 1705.0

    def test_year1_minus_ongoing_equals_sub(self):
        """Year-1 - Ongoing = SUB."""
        card = CARD_DB["Chase Sapphire Reserve"]
        annual_rewards = 600.0
        diff = icono_score_year1(card, annual_rewards) - icono_score_ongoing(card, annual_rewards)
        assert diff == card.signup_bonus_value

    def test_nofee_card_ongoing_positive(self):
        """No-fee card should always have positive ongoing if rewards > 0."""
        cfu = CARD_DB["Chase Freedom Unlimited"]
        assert cfu.annual_fee == 0
        assert icono_score_ongoing(cfu, 500.0) == 500.0  # no perks, no fee


# ─────────────────────────────────────────────
#  load_transactions tests
# ─────────────────────────────────────────────

class TestLoadTransactions:
    def test_filters_income(self):
        df = pd.DataFrame([
            {"Category": "Groceries", "Amount": -100},
            {"Category": "Paychecks", "Amount": 5000},
        ])
        clean = load_transactions(df)
        assert len(clean) == 1
        assert clean.iloc[0]["_earn_category"] == "groceries"

    def test_filters_transfers(self):
        df = pd.DataFrame([
            {"Category": "Transfer", "Amount": -500},
            {"Category": "Restaurants", "Amount": -50},
        ])
        clean = load_transactions(df)
        assert len(clean) == 1

    def test_positive_amounts_excluded(self):
        df = pd.DataFrame([
            {"Category": "Groceries", "Amount": 100},  # refund
            {"Category": "Groceries", "Amount": -100},  # expense
        ])
        clean = load_transactions(df)
        assert len(clean) == 1

    def test_spend_column_positive(self):
        df = pd.DataFrame([{"Category": "Groceries", "Amount": -250}])
        clean = load_transactions(df)
        assert clean.iloc[0]["_spend"] == 250.0


# ─────────────────────────────────────────────
#  card_base_rewards tests
# ─────────────────────────────────────────────

class TestCardBaseRewards:
    @pytest.fixture
    def sample_df(self):
        return load_transactions(pd.DataFrame([
            {"Category": "Groceries", "Amount": -500},
            {"Category": "Restaurants", "Amount": -200},
            {"Category": "Shopping", "Amount": -100},
        ]))

    def test_cfu_rewards(self, sample_df):
        """CFU: dining 3%, general 1.5%, groceries 1.5% (no grocery bonus)."""
        cfu = CARD_DB["Chase Freedom Unlimited"]
        val = card_base_rewards(cfu, sample_df, cpp_mode="awardwallet")
        # groceries 500 * 0.015 * 2.0 = 15
        # dining 200 * 0.03 * 2.0 = 12
        # general 100 * 0.015 * 2.0 = 3
        assert val == pytest.approx(30.0, abs=0.01)

    def test_floor_mode_reduces_value(self, sample_df):
        """Floor CPP should produce lower values for premium cards."""
        csp = CARD_DB["Chase Sapphire Preferred"]
        aw_val = card_base_rewards(csp, sample_df, cpp_mode="awardwallet")
        floor_val = card_base_rewards(csp, sample_df, cpp_mode="floor")
        assert floor_val < aw_val  # floor CPP is 1.5 vs AW 2.0


# ─────────────────────────────────────────────
#  analyze_cards tests (now returns dict)
# ─────────────────────────────────────────────

class TestAnalyzeCards:
    def test_returns_dict_with_expected_keys(self):
        df = pd.DataFrame([{"Category": "Groceries", "Amount": -100}])
        result = analyze_cards(df, cards=[CARD_DB["Citi Double Cash"]])
        assert "cards" in result
        assert "total_spend" in result
        assert "meta" in result

    def test_cards_sorted_by_year1(self):
        df = pd.DataFrame([
            {"Category": "Groceries", "Amount": -500},
            {"Category": "Restaurants", "Amount": -300},
        ])
        result = analyze_cards(df, cards=[
            CARD_DB["Chase Freedom Unlimited"],
            CARD_DB["Amex Gold"],
        ])
        cards = result["cards"]
        assert len(cards) == 2
        assert cards[0]["icono_year1"] >= cards[1]["icono_year1"]

    def test_result_card_keys(self):
        df = pd.DataFrame([{"Category": "Groceries", "Amount": -100}])
        result = analyze_cards(df, cards=[CARD_DB["Citi Double Cash"]])
        cards = result["cards"]
        assert len(cards) == 1
        r = cards[0]
        assert "name" in r
        assert "base_rewards_value" in r
        assert "perks_value" in r
        assert "icono_ongoing" in r
        assert "icono_year1" in r
        assert "annual_fee" in r

    def test_total_spend_computed(self):
        df = pd.DataFrame([
            {"Category": "Groceries", "Amount": -500},
            {"Category": "Restaurants", "Amount": -300},
        ])
        result = analyze_cards(df, cards=[CARD_DB["Citi Double Cash"]])
        assert result["total_spend"] == 800.0

    def test_meta_contains_expected_fields(self):
        df = pd.DataFrame([{"Category": "Groceries", "Amount": -100}])
        result = analyze_cards(df, cards=[CARD_DB["Citi Double Cash"]], cpp_mode="floor")
        meta = result["meta"]
        assert meta["cpp_mode"] == "floor"
        assert meta["cards_evaluated"] == 1
        assert meta["txn_count"] == 1


# ─────────────────────────────────────────────
#  generate_guide tests
# ─────────────────────────────────────────────

from guide_jvn import generate_guide


def _make_result(name="TestCard", base_rewards=500.0, perks=250.0, ongoing=600.0,
                 year1=1800.0, fee=95):
    """Helper to build a fake card result dict."""
    return {
        "name": name,
        "base_rewards_value": base_rewards,
        "perks_value": perks,
        "icono_ongoing": ongoing,
        "icono_year1": year1,
        "annual_fee": fee,
    }


class TestGenerateGuide:
    def test_empty_results(self):
        """No results should prompt the user to upload."""
        guide = generate_guide([])
        assert "headline" in guide
        assert "bullets" in guide
        assert "tone" in guide
        assert guide["tone"] == "sassy-supportive"
        assert "transactions" in guide["headline"].lower()

    def test_returns_required_keys(self):
        """Guide dict must have headline, bullets, tone."""
        results = [_make_result()]
        guide = generate_guide(results)
        assert isinstance(guide["headline"], str)
        assert isinstance(guide["bullets"], list)
        assert guide["tone"] == "sassy-supportive"

    def test_high_year1_headline(self):
        """Year-1 > $3000 should trigger the SERVING headline."""
        results = [_make_result(name="Amex Platinum", year1=3500.0)]
        guide = generate_guide(results)
        assert "SERVING" in guide["headline"]
        assert "3,500" in guide["headline"]

    def test_medium_year1_headline(self):
        """Year-1 between $1500-$3000 should trigger main character headline."""
        results = [_make_result(name="CSR", year1=2000.0)]
        guide = generate_guide(results)
        assert "main character" in guide["headline"]

    def test_neck_and_neck_headline(self):
        """Two cards within $100 should trigger neck-and-neck."""
        results = [
            _make_result(name="CardA", year1=1200.0),
            _make_result(name="CardB", year1=1150.0),
        ]
        guide = generate_guide(results)
        assert "neck-and-neck" in guide["headline"]

    def test_runaway_headline(self):
        """Big gap > $500 should trigger the runaway headline."""
        results = [
            _make_result(name="Winner", year1=1400.0),
            _make_result(name="Loser", year1=800.0),
        ]
        guide = generate_guide(results)
        assert "running away" in guide["headline"]

    def test_perks_bullet(self):
        """High perks (>$200) should produce a perks bullet."""
        results = [_make_result(perks=350.0)]
        guide = generate_guide(results)
        assert any("perk" in b.lower() for b in guide["bullets"])

    def test_negative_ongoing_roast(self):
        """A card with negative ongoing should get called out."""
        results = [
            _make_result(name="Good", ongoing=500.0, year1=1500.0),
            _make_result(name="Bad", ongoing=-200.0, year1=300.0),
        ]
        guide = generate_guide(results)
        assert any("Bad" in b for b in guide["bullets"])

    def test_bilt_callout(self):
        """Any Bilt card should get a rent callout when it has rewards."""
        results = [
            _make_result(name="Bilt Blue", base_rewards=600.0, year1=1000.0),
        ]
        guide = generate_guide(results)
        assert any("Bilt" in b and "rent" in b for b in guide["bullets"])

    def test_travel_card_bullet(self):
        """A travel card with high year-1 should get a travel bullet."""
        results = [
            _make_result(name="Chase Sapphire Reserve", year1=2000.0),
        ]
        guide = generate_guide(results)
        assert any("travel" in b.lower() or "wanderlust" in b.lower() for b in guide["bullets"])

    def test_floor_card_roast(self):
        """Low-earning card (<$100) should get roasted."""
        results = [
            _make_result(name="Good", base_rewards=500.0, year1=1500.0),
            _make_result(name="Weak", base_rewards=50.0, year1=200.0),
        ]
        guide = generate_guide(results)
        assert any("Weak" in b for b in guide["bullets"])

    def test_bullets_capped_at_four(self):
        """Should never return more than 4 bullets."""
        results = [
            _make_result(name="Chase Sapphire Reserve", perks=300.0, ongoing=-50.0, year1=2000.0),
            _make_result(name="Bilt Blue", base_rewards=600.0, ongoing=-100.0, year1=500.0, perks=0.0),
            _make_result(name="Weak", base_rewards=50.0, ongoing=10.0, year1=100.0, perks=0.0),
        ]
        guide = generate_guide(results)
        assert len(guide["bullets"]) <= 4

    def test_fallback_bullet(self):
        """When no special conditions trigger, should still get encouragement."""
        results = [_make_result(perks=0.0, base_rewards=200.0)]
        guide = generate_guide(results)
        assert len(guide["bullets"]) >= 1


# ─────────────────────────────────────────────
#  CardProfile.annual_credits deprecation test
# ─────────────────────────────────────────────

class TestAnnualCreditsDeprecation:
    def test_annual_credits_still_accessible(self):
        """annual_credits should still be readable for display purposes."""
        plat = CARD_DB["Amex Platinum"]
        assert plat.annual_credits == 840

    def test_annual_credits_not_used_in_scoring(self):
        """icono_perk_value should use granular credit fields, not annual_credits."""
        card = CardProfile(
            name="Test", annual_fee=0,
            annual_credits=9999,  # huge value that should NOT affect perk calc
        )
        assert icono_perk_value(card) == 0.0  # no granular credits set

    def test_granular_credits_match_annual_credits(self):
        """For Amex Platinum, sum of granular credits should equal annual_credits."""
        plat = CARD_DB["Amex Platinum"]
        granular_sum = (
            plat.hotel_credit + plat.travel_credit + plat.uber_credit
            + plat.dining_credit + plat.streaming_credit + plat.other_credit
        )
        assert granular_sum == plat.annual_credits


# ─────────────────────────────────────────────
#  Bilt 2.0 card lineup tests
# ─────────────────────────────────────────────

class TestBilt20Lineup:
    def test_bilt_blue_exists(self):
        assert "Bilt Blue" in CARD_DB
        blue = CARD_DB["Bilt Blue"]
        assert blue.annual_fee == 0
        assert blue.base_rate == 0.01
        assert blue.cpp_valuation == 2.2

    def test_bilt_obsidian_exists(self):
        assert "Bilt Obsidian" in CARD_DB
        obs = CARD_DB["Bilt Obsidian"]
        assert obs.annual_fee == 95
        assert obs.categories.get("dining") == 0.03
        assert obs.categories.get("groceries") == 0.03
        assert obs.hotel_credit == 100

    def test_bilt_palladium_exists(self):
        assert "Bilt Palladium" in CARD_DB
        pal = CARD_DB["Bilt Palladium"]
        assert pal.annual_fee == 495
        assert pal.base_rate == 0.02  # 2x on everything
        assert pal.hotel_credit == 400

    def test_bilt_mastercard_removed(self):
        assert "Bilt Mastercard" not in CARD_DB

    def test_bilt_cpp_is_2_2(self):
        """All Bilt cards should use 2.2 cpp (Atmos/Hyatt trifecta)."""
        for name in ("Bilt Blue", "Bilt Obsidian", "Bilt Palladium"):
            assert CARD_DB[name].cpp_valuation == 2.2

    def test_bilt_housing_rate_in_categories(self):
        """All Bilt cards should have housing rate in categories."""
        for name in ("Bilt Blue", "Bilt Obsidian", "Bilt Palladium"):
            assert CARD_DB[name].categories.get("housing") == 0.0125


# ─────────────────────────────────────────────
#  Bilt 2.0 tiered housing logic tests
# ─────────────────────────────────────────────

from reward_optimizer import RewardOptimizer


class TestBilt20Housing:
    def test_max_tier_100pct(self):
        """Spend >= 100% housing → 1.25x."""
        rate = RewardOptimizer.calc_bilt_housing_rate(3000, 3000)
        assert rate == 0.0125

    def test_tier_75pct(self):
        """Spend >= 75% but < 100% housing → 1.0x."""
        rate = RewardOptimizer.calc_bilt_housing_rate(3000, 2250)
        assert rate == 0.01

    def test_tier_50pct(self):
        """Spend >= 50% but < 75% housing → 0.75x."""
        rate = RewardOptimizer.calc_bilt_housing_rate(3000, 1500)
        assert rate == 0.0075

    def test_tier_below_50pct(self):
        """Spend < 50% housing → 0.5x."""
        rate = RewardOptimizer.calc_bilt_housing_rate(3000, 1000)
        assert rate == 0.005

    def test_zero_housing(self):
        """Zero housing payment → default 1% rate."""
        rate = RewardOptimizer.calc_bilt_housing_rate(0, 1000)
        assert rate == 0.01

    def test_bilt_cash_path(self):
        """Bilt Cash path: 4% Bilt Cash → redeem for housing points."""
        # $3000 everyday spend × 4% = $120 Bilt Cash
        # $120 / $30 × 1000 = 4,000 points
        # Max housing points at 1x: $3000 × 0.01 = 30 (in rate terms)
        rate = RewardOptimizer.calc_bilt_cash_housing_value(3000, 3000)
        # 4000 points vs 30 point cap → capped at 30 → rate = 30/3000 = 0.01
        assert rate == pytest.approx(0.01, abs=0.001)


# ─────────────────────────────────────────────
#  Removed cards tests
# ─────────────────────────────────────────────

class TestRemovedCards:
    def test_blue_business_plus_removed(self):
        assert "Blue Business Plus" not in CARD_DB

    def test_state_farm_removed(self):
        assert "State Farm Premier Cash Rewards" not in CARD_DB

    def test_target_circle_added(self):
        assert "Target Circle Card" in CARD_DB
        target = CARD_DB["Target Circle Card"]
        assert target.categories.get("target") == 0.05
        assert target.annual_fee == 0
