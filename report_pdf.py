# report_pdf.py
from io import BytesIO
import pandas as pd
from datetime import datetime


def _sanitize(text: str) -> str:
    """Replace characters that cannot be encoded in Latin-1 (ISO-8859-1).

    FPDF's built-in fonts only support Latin-1. This function strips or
    replaces problematic Unicode characters so pdf.cell() / multi_cell()
    never raise FPDFUnicodeEncodingException.
    """
    if not isinstance(text, str):
        text = str(text)
    # Try encoding to latin-1; replace failures with '?'
    return text.encode("latin-1", errors="replace").decode("latin-1")


def generate_report(
    results: pd.DataFrame,
    summary: dict,
    plan: list,
    guide: dict | None = None,
    icono_scores: list[dict] | None = None,
) -> bytes:
    """Generate a PDF report and return as bytes.

    Parameters
    ----------
    results : DataFrame with per-transaction routing details.
    summary : dict from ``RewardOptimizer.analyze()`` containing KPIs.
    plan : list of acquisition plan lines (strings).
    guide : optional dict from ``generate_guide()`` with headline/bullets.
    icono_scores : optional list of card dicts (from ``analyze_cards``)
                   sorted by ``icono_year1`` descending.
    """
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "Credit Card Reward Optimizer Report", ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%B %d, %Y')}", ln=True, align="C")
    pdf.ln(6)

    # Summary KPIs
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Summary", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Monthly Card Spend:   ${summary.get('total_spend', 0):,.2f}", ln=True)
    pdf.cell(0, 7, f"Monthly Rewards:      ${summary.get('total_rewards', 0):,.2f}", ln=True)
    pdf.cell(0, 7, f"Blended Rate:         {summary.get('blended_rate_pct', 0):.2f}%", ln=True)
    net_annual = summary.get('total_rewards', 0) * 12 - summary.get(
        'effective_annual_fees', summary.get('total_annual_fees', 0)
    )
    pdf.cell(0, 7, f"Net Annual Value:     ${net_annual:,.2f}", ln=True)
    pdf.ln(4)

    # JVN-Style Commentary
    if guide:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Icono Says...", ln=True)
        pdf.set_font("Helvetica", "I", 11)
        pdf.multi_cell(0, 7, _sanitize(guide.get("headline", "")))
        pdf.set_font("Helvetica", "", 10)
        for bullet in guide.get("bullets", []):
            pdf.multi_cell(0, 6, _sanitize(f"  - {bullet}"))
        pdf.ln(4)

    # Top Icono-Ranked Cards
    if icono_scores:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Top Icono-Ranked Cards", ln=True)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(60, 7, "Card", border=1)
        pdf.cell(30, 7, "Ongoing", border=1, align="R")
        pdf.cell(30, 7, "Year-1", border=1, align="R")
        pdf.cell(25, 7, "Perks", border=1, align="R")
        pdf.cell(25, 7, "Fee", border=1, align="R")
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        for card in icono_scores[:10]:
            pdf.cell(60, 7, _sanitize(card["name"][:28]), border=1)
            pdf.cell(30, 7, f"${card['icono_ongoing']:,.0f}", border=1, align="R")
            pdf.cell(30, 7, f"${card['icono_year1']:,.0f}", border=1, align="R")
            pdf.cell(25, 7, f"${card['perks_value']:,.0f}", border=1, align="R")
            pdf.cell(25, 7, f"${card['annual_fee']:,.0f}", border=1, align="R")
            pdf.ln()
        pdf.ln(4)

    # Card Breakdown
    breakdown = summary.get("card_breakdown", {})
    if breakdown:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Card-by-Card Routing", ln=True)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(80, 7, "Card", border=1)
        pdf.cell(35, 7, "Monthly Spend", border=1, align="R")
        pdf.cell(35, 7, "Monthly Rewards", border=1, align="R")
        pdf.cell(30, 7, "Rate", border=1, align="R")
        pdf.ln()
        pdf.set_font("Helvetica", "", 10)
        for card, data in sorted(breakdown.items(), key=lambda x: x[1]["rewards"], reverse=True):
            spend = data["spend"]
            rewards = data["rewards"]
            rate = (rewards / spend * 100) if spend > 0 else 0
            pdf.cell(80, 7, _sanitize(card[:38]), border=1)
            pdf.cell(35, 7, f"${spend:,.2f}", border=1, align="R")
            pdf.cell(35, 7, f"${rewards:,.2f}", border=1, align="R")
            pdf.cell(30, 7, f"{rate:.1f}%", border=1, align="R")
            pdf.ln()
        pdf.ln(4)

    # Acquisition Plan
    if plan:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Acquisition Roadmap", ln=True)
        pdf.set_font("Helvetica", "", 11)
        for i, item in enumerate(plan, 1):
            pdf.multi_cell(0, 7, _sanitize(f"{i}. {item}"))
        pdf.ln(4)

    # Transaction Detail
    if results is not None and not results.empty:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Transaction-Level Routing (top 50)", ln=True)
        cols = list(results.columns)
        col_w = min(190 // max(len(cols), 1), 50)
        pdf.set_font("Helvetica", "B", 8)
        for col in cols:
            pdf.cell(col_w, 6, _sanitize(str(col)[:16]), border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for _, row in results.head(50).iterrows():
            for col in cols:
                val = row[col]
                if isinstance(val, float):
                    cell_text = f"{val:,.2f}"
                else:
                    cell_text = _sanitize(str(val)[:16])
                pdf.cell(col_w, 6, cell_text, border=1)
            pdf.ln()

    # Footer
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(
        0, 5,
        "Built by Icono (Iconoclastic Capital Management) - Fee-Only Fiduciary Wealth Management - "
        "Rochester, NY - iconoclasticcapital.com\n"
        "This report is for informational purposes only and does not constitute financial advice."
    )
    return bytes(pdf.output())


def generate_csv_routing(results: pd.DataFrame) -> bytes:
    """Return the routing DataFrame as UTF-8 CSV bytes."""
    return results.to_csv(index=False).encode("utf-8")
