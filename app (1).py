"""
Credit Card Reward Optimizer — Streamlit App
=============================================
Upload a Monarch Money CSV export → get optimal card routing,
acquisition roadmap, and actionable insights.

Designed for: Icono (Iconoclastic Capital Management)
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
from io import StringIO

# ─── Import the optimizer engine ───
from reward_optimizer import (
    RewardOptimizer, CardAcquisitionPlanner, CARD_DB,
    CATEGORY_MAP, SIGNUP_BONUSES, ISSUER_VELOCITY_NOTES,
)

# ─────────────────────────────────────────────
#  Page Config
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="Card Reward Optimizer | Icono",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  Custom Styling
# ─────────────────────────────────────────────

st.markdown("""
<style>
    /* Clean typography */
    .main h1 { font-size: 2rem; font-weight: 700; margin-bottom: 0.25rem; }
    .main h2 { font-size: 1.4rem; font-weight: 600; color: #334155; }
    .main h3 { font-size: 1.1rem; font-weight: 600; color: #475569; }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px;
    }
    [data-testid="stMetricLabel"] { font-size: 0.8rem; color: #64748b; }
    [data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; color: #0f172a; }

    /* Acquisition timeline cards */
    .acq-card {
        background: #f8fafc;
        border-left: 4px solid #3b82f6;
        border-radius: 0 8px 8px 0;
        padding: 16px 20px;
        margin-bottom: 12px;
    }
    .acq-card h4 { margin: 0 0 8px 0; color: #1e293b; }
    .acq-card .meta { color: #64748b; font-size: 0.85rem; }
    .acq-card .value { color: #059669; font-weight: 600; }
    .acq-card .warning { color: #d97706; font-size: 0.85rem; }

    /* Footer */
    .footer { text-align: center; color: #94a3b8; font-size: 0.8rem; margin-top: 3rem; padding: 1rem; border-top: 1px solid #e2e8f0; }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  Header
# ─────────────────────────────────────────────

st.title("💳 Credit Card Reward Optimizer")
st.markdown("*Upload your Monarch Money export. Get optimal card routing and an acquisition roadmap.*")
st.markdown("---")


# ─────────────────────────────────────────────
#  Sidebar — Configuration
# ─────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Settings")

    st.subheader("Your Current Cards")
    st.caption("Check cards you already have in your wallet.")

    CARD_GROUPS = {
        "✈️ Premium Travel": [
            ("Amex Platinum", "$695/yr · 5x flights/hotels"),
            ("Chase Sapphire Reserve", "$795/yr · 3x dining/travel"),
            ("Capital One Venture X", "$395/yr · 2x everything"),
        ],
        "🗺️ Mid-Tier Travel": [
            ("Chase Sapphire Preferred", "$95/yr · 3x dining, 2x travel"),
            ("Capital One Venture", "$95/yr · 2x everything"),
            ("Amex Gold", "$325/yr · 4x dining & groceries"),
            ("Citi Strata Premier", "$95/yr · 3x hotels/air/dining/gas"),
        ],
        "🆓 No-Fee Travel": [
            ("Capital One VentureOne", "$0 · 1.25x miles"),
            ("Bilt Mastercard", "$0 · Earn on rent, 2x dining"),
        ],
        "💵 Cash Back – Flat Rate": [
            ("Chase Freedom Unlimited", "$0 · 1.5% + 3% dining"),
            ("Wells Fargo Active Cash", "$0 · 2% everything"),
            ("Citi Double Cash", "$0 · 2% everything"),
            ("PayPal Cashback Mastercard", "$0 · 3% PayPal, 1.5% other"),
        ],
        "🏷️ Cash Back – Category": [
            ("Amex Blue Cash Preferred", "$95/yr · 6% groceries/streaming"),
            ("Amex Blue Cash Everyday", "$0 · 3% groceries/gas/online"),
            ("Chase Freedom Flex", "$0 · 5% rotating, 3% dining"),
            ("Capital One SavorOne", "$0 · 3% dining/groceries/entertainment"),
            ("Citi Custom Cash", "$0 · 5% top category"),
        ],
        "🛒 Store / Co-Brand": [
            ("Amazon Prime Visa", "$0 · 5% Amazon/Whole Foods"),
            ("Apple Card", "$0 · 3% Apple, 2% Apple Pay"),
        ],
    }

    existing_cards = []
    for group_name, cards in CARD_GROUPS.items():
        st.markdown(f"**{group_name}**")
        for card_name, card_desc in cards:
            if st.checkbox(f"{card_name}", key=f"card_{card_name}", help=card_desc):
                existing_cards.append(card_name)

    st.markdown("---")
    st.subheader("Bilt Housing Details")
    monthly_housing = st.number_input(
        "Monthly housing payment ($)", min_value=0, value=3000, step=100,
        help="Rent, mortgage, HOA combined."
    )
    monthly_nonhousing_bilt = st.number_input(
        "Monthly non-housing spend on Bilt ($)", min_value=0, value=3500, step=100,
        help="All non-housing transactions you put on your Bilt card."
    )

    st.markdown("---")
    st.subheader("Acquisition Cadence")
    cadence_days = st.slider("Days between applications", 60, 180, 90, step=15)
    start_date = st.date_input("Start date for new applications", value=date.today())

    st.markdown("---")
    st.caption("Built by [Icono](https://iconoclasticcapital.com) — Fee-Only Wealth Management")


# ─────────────────────────────────────────────
#  File Upload
# ─────────────────────────────────────────────

uploaded_file = st.file_uploader(
    "Upload Monarch Money CSV Export",
    type=["csv"],
    help="Export from Monarch Money → Transactions → Export CSV"
)

# Also allow a demo mode
use_demo = st.checkbox("Use demo data instead", value=not bool(uploaded_file))

if uploaded_file:
    use_demo = False
    df = pd.read_csv(uploaded_file)
elif use_demo:
    # Demo dataset (Monarch-style: expenses are negative)
    df = pd.DataFrame([
        {"Category": "Rent",              "Amount": -3200, "Date": "2026-02-01", "Account": "Checking (...1234)"},
        {"Category": "Renters Insurance", "Amount": -120,  "Date": "2026-02-01", "Account": "Blue Cash Preferred (...9999)"},
        {"Category": "HOA Dues",          "Amount": -880,  "Date": "2026-02-01", "Account": "Checking (...1234)"},
        {"Category": "Groceries",         "Amount": -320,  "Date": "2026-02-05", "Account": "Blue Cash Preferred (...9999)"},
        {"Category": "Groceries",         "Amount": -285.50,"Date": "2026-02-12", "Account": "Blue Cash Preferred (...9999)"},
        {"Category": "Groceries",         "Amount": -310,  "Date": "2026-02-19", "Account": "Blue Cash Preferred (...9999)"},
        {"Category": "Groceries",         "Amount": -235,  "Date": "2026-02-26", "Account": "Blue Cash Preferred (...9999)"},
        {"Category": "Restaurants",       "Amount": -185,  "Date": "2026-02-07", "Account": "Venture X (...6789)"},
        {"Category": "Restaurants",       "Amount": -95,   "Date": "2026-02-08", "Account": "Venture X (...6789)"},
        {"Category": "Coffee Shops",      "Amount": -65,   "Date": "2026-02-10", "Account": "Venture X (...6789)"},
        {"Category": "Fast Food",         "Amount": -45,   "Date": "2026-02-15", "Account": "Venture X (...6789)"},
        {"Category": "Restaurants",       "Amount": -160,  "Date": "2026-02-18", "Account": "Venture X (...6789)"},
        {"Category": "Bars & Alcohol",    "Amount": -150,  "Date": "2026-02-14", "Account": "Venture X (...6789)"},
        {"Category": "Gas",               "Amount": -245,  "Date": "2026-02-06", "Account": "CREDIT CARD (...5555)"},
        {"Category": "Gas",               "Amount": -210,  "Date": "2026-02-20", "Account": "CREDIT CARD (...5555)"},
        {"Category": "Auto Insurance",    "Amount": -285,  "Date": "2026-02-01", "Account": "Checking (...1234)"},
        {"Category": "Auto Maintenance",  "Amount": -180.30,"Date": "2026-02-22", "Account": "CREDIT CARD (...5555)"},
        {"Category": "Public Transit",    "Amount": -200,  "Date": "2026-02-15", "Account": "Venture X (...6789)"},
        {"Category": "Shopping",          "Amount": -520,  "Date": "2026-02-03", "Account": "CREDIT CARD (...5555)"},
        {"Category": "Electronics",       "Amount": -380,  "Date": "2026-02-10", "Account": "CREDIT CARD (...5555)"},
        {"Category": "Clothing",          "Amount": -350,  "Date": "2026-02-14", "Account": "CREDIT CARD (...5555)"},
        {"Category": "Home Improvement",  "Amount": -200,  "Date": "2026-02-21", "Account": "CREDIT CARD (...5555)"},
        {"Category": "Gas & Electric",    "Amount": -420,  "Date": "2026-02-15", "Account": "Checking (...1234)"},
        {"Category": "Water",             "Amount": -85,   "Date": "2026-02-15", "Account": "Checking (...1234)"},
        {"Category": "Internet & Cable",  "Amount": -110,  "Date": "2026-02-01", "Account": "Checking (...1234)"},
        {"Category": "Phone",             "Amount": -145,  "Date": "2026-02-01", "Account": "CREDIT CARD (...5555)"},
        {"Category": "Streaming Services","Amount": -80,   "Date": "2026-02-01", "Account": "CREDIT CARD (...5555)"},
        {"Category": "Education",         "Amount": -1060, "Date": "2026-02-01", "Account": "Venture X (...6789)"},
        {"Category": "Insurance",         "Amount": -340,  "Date": "2026-02-15", "Account": "Checking (...1234)"},
        {"Category": "Health Insurance",  "Amount": -520,  "Date": "2026-02-01", "Account": "Checking (...1234)"},
        {"Category": "Charity",           "Amount": -250,  "Date": "2026-02-20", "Account": "CREDIT CARD (...5555)"},
        {"Category": "Financial Fees",    "Amount": -125,  "Date": "2026-02-15", "Account": "Checking (...1234)"},
        {"Category": "Gifts",             "Amount": -180,  "Date": "2026-02-14", "Account": "CREDIT CARD (...5555)"},
        {"Category": "Pets",              "Amount": -275,  "Date": "2026-02-22", "Account": "Blue Cash Preferred (...9999)"},
        {"Category": "Medical",           "Amount": -239.02,"Date": "2026-02-18", "Account": "CREDIT CARD (...5555)"},
        # Non-expenses that should be filtered
        {"Category": "Transfer",          "Amount": -1500, "Date": "2026-02-10", "Account": "Checking (...1234)"},
        {"Category": "Credit Card Payment","Amount": -2800, "Date": "2026-02-15", "Account": "Checking (...1234)"},
        {"Category": "Paychecks",         "Amount": 6500,  "Date": "2026-02-01", "Account": "Checking (...1234)"},
        {"Category": "Paychecks",         "Amount": 6500,  "Date": "2026-02-15", "Account": "Checking (...1234)"},
    ])
    st.info("📊 Using demo data — upload a Monarch CSV for personalized results.")
else:
    st.stop()


# ─────────────────────────────────────────────
#  Run Optimizer
# ─────────────────────────────────────────────

optimizer = RewardOptimizer()
results, summary = optimizer.analyze(
    df,
    monthly_housing=monthly_housing,
    monthly_nonhousing_bilt=monthly_nonhousing_bilt,
)


# ─────────────────────────────────────────────
#  KPI Row
# ─────────────────────────────────────────────

st.header("📊 Optimization Results")

# Data quality context
months = summary.get('months_of_data', 1)
cc_rows = summary.get('rows_analyzed', 0)
excluded = summary.get('rows_excluded', 0)
bank_sep = summary.get('bank_rows_separated', 0)
st.caption(f"📅 {months} months of data • {cc_rows} credit card transactions analyzed • {excluded} non-expenses filtered • {bank_sep} bank account transactions separated")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Monthly Card Spend", f"${summary['total_spend']:,.0f}")
with col2:
    st.metric("Monthly Rewards", f"${summary['total_rewards']:,.2f}")
with col3:
    st.metric("Blended Rate", f"{summary['blended_rate_pct']:.2f}%")
with col4:
    net_annual = summary['total_rewards'] * 12 - summary['total_annual_fees']
    st.metric("Net Annual Value", f"${net_annual:,.0f}")

# Opportunity flags
has_ach = summary.get("ach_leakage_potential", 0) > 0
has_ins = summary.get("insurance_opportunity", 0) > 0
if has_ach or has_ins:
    st.markdown("---")
    opp1, opp2 = st.columns(2)
    with opp1:
        if has_ach:
            annual_ach = summary["ach_leakage_potential"] * 12
            monthly_ach_spend = summary.get("ach_leakage_spend", 0)
            st.warning(f"⚡ **ACH Leakage:** ~${annual_ach:,.0f}/yr in rewards left on the table from ${monthly_ach_spend:,.0f}/mo in bank account expenses")
            ach_items = summary.get("ach_leakage_items", [])
            if ach_items:
                with st.expander("View ACH leakage detail"):
                    ach_df = pd.DataFrame(ach_items)
                    st.dataframe(
                        ach_df[["Category", "Amount", "Merchant", "Best Card", "Rate", "Potential Reward"]].style.format({
                            "Amount": "${:,.2f}",
                            "Potential Reward": "${:,.2f}",
                        }),
                        use_container_width=True,
                        hide_index=True,
                    )
    with opp2:
        if has_ins:
            annual_ins = summary["insurance_opportunity"] * 12
            st.info(f"🛡️ **Insurance Opportunity:** ${annual_ins:,.0f}/yr available by routing insurance premiums to cards")


# ─────────────────────────────────────────────
#  Card Routing Breakdown
# ─────────────────────────────────────────────

st.markdown("---")
st.header("🃏 Card-by-Card Routing")

breakdown = summary["card_breakdown"]
breakdown_df = pd.DataFrame([
    {
        "Card": card,
        "Monthly Spend": data["spend"],
        "Monthly Rewards": data["rewards"],
        "Effective Rate": f"{(data['rewards'] / data['spend'] * 100):.1f}%" if data["spend"] > 0 else "0%",
        "Annual Rewards": data["rewards"] * 12,
    }
    for card, data in sorted(breakdown.items(), key=lambda x: x[1]["rewards"], reverse=True)
])

st.dataframe(
    breakdown_df.style.format({
        "Monthly Spend": "${:,.2f}",
        "Monthly Rewards": "${:,.2f}",
        "Annual Rewards": "${:,.0f}",
    }),
    use_container_width=True,
    hide_index=True,
)

# Bar chart of rewards by card
chart_data = breakdown_df.set_index("Card")[["Monthly Rewards"]].sort_values("Monthly Rewards", ascending=True)
st.bar_chart(chart_data, horizontal=True)


# ─────────────────────────────────────────────
#  Transaction Detail
# ─────────────────────────────────────────────

with st.expander("🔍 Full Transaction-Level Routing", expanded=False):
    st.dataframe(
        results.style.format({"Amount": "${:,.2f}", "Reward Value": "${:,.2f}"}),
        use_container_width=True,
        hide_index=True,
    )


# ─────────────────────────────────────────────
#  Acquisition Roadmap
# ─────────────────────────────────────────────

st.markdown("---")
st.header("🗓️ Card Acquisition Roadmap")
st.caption(f"One new card every {cadence_days} days — minimizes hard inquiry impact on credit score.")

planner = CardAcquisitionPlanner(
    existing_cards=existing_cards,
    start_date=start_date,
)
planner.CADENCE_DAYS = cadence_days
plan = planner.plan(summary)

if not plan:
    st.success("✅ You already have all the recommended cards — no new applications needed!")
else:
    # Summary metrics
    total_new_rewards = sum(s.projected_annual_rewards for s in plan)
    total_new_fees = sum(s.annual_fee for s in plan)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("New Cards", len(plan))
    with m2:
        st.metric("Timeline", f"{plan[0].apply_date.strftime('%b %y')} → {plan[-1].apply_date.strftime('%b %y')}")
    with m3:
        st.metric("New Annual Rewards", f"${total_new_rewards:,.0f}")
    with m4:
        st.metric("Net New Value", f"${total_new_rewards - total_new_fees:,.0f}")

    st.markdown("")

    for step in plan:
        # Color code by priority
        colors = ["#3b82f6", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#6366f1", "#ec4899"]
        color = colors[step.priority % len(colors) - 1]

        sub_display = ""
        if step.signup_bonus and step.signup_bonus != "Unknown":
            sub_display = f"<br><span class='value'>🎁 SUB: {step.signup_bonus}</span>"

        warning = ""
        if step.hard_inquiry_note:
            warning = f"<br><span class='warning'>⚠️ {step.hard_inquiry_note}</span>"

        st.markdown(f"""
        <div class="acq-card" style="border-left-color: {color};">
            <h4>#{step.priority} — {step.card}</h4>
            <span class="meta">Apply by <strong>{step.apply_date.strftime('%B %d, %Y')}</strong></span>
            &nbsp;·&nbsp;
            <span class="meta">Fee: ${step.annual_fee:,.0f}/yr</span>
            &nbsp;·&nbsp;
            <span class="value">${step.projected_monthly_rewards:,.2f}/mo → ${step.projected_annual_rewards:,.0f}/yr</span>
            <br>
            <span class="meta">Captures ${step.spend_captured:,.0f}/mo in: {', '.join(step.categories_unlocked[:4])}</span>
            <br>
            <span class="meta">Cumulative blended rate: <strong>{step.cumulative_blended_rate:.2f}%</strong></span>
            {sub_display}
            {warning}
        </div>
        """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  Annualized Projections
# ─────────────────────────────────────────────

st.markdown("---")
st.header("📈 Annualized Projections")

p1, p2, p3 = st.columns(3)
with p1:
    st.metric("Annual Spend", f"${summary['total_spend'] * 12:,.0f}")
with p2:
    st.metric("Annual Reward Value", f"${summary['total_rewards'] * 12:,.0f}")
with p3:
    st.metric("Net After Fees", f"${net_annual:,.0f}")


# ─────────────────────────────────────────────
#  Footer
# ─────────────────────────────────────────────

st.markdown("""
<div class="footer">
    Built by <strong>Icono</strong> (Iconoclastic Capital Management) · Fee-Only Fiduciary Wealth Management<br>
    Rochester, NY · <a href="https://iconoclasticcapital.com">iconoclasticcapital.com</a><br>
    <em>This tool is for informational purposes only and does not constitute financial advice.<br>
    Card terms, rates, and sign-up bonuses may change — verify before applying.</em>
</div>
""", unsafe_allow_html=True)
