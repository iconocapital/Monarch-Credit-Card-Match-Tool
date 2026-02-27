# report_pdf.py
from fpdf import FPDF
from io import BytesIO
import pandas as pd
from datetime import datetime
def generate_report(results: pd.DataFrame, summary: dict, plan: list) -> bytes:
    """Generate a PDF report and return as bytes."""
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
            pdf.cell(80, 7, card[:38], border=1)
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
            pdf.multi_cell(0, 7, f"{i}. {item}")
        pdf.ln(4)
    # Transaction Detail
    if results is not None and not results.empty:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Transaction-Level Routing (top 50)", ln=True)
        cols = list(results.columns)
        col_w = min(190 // max(len(cols), 1), 50)
        pdf.set_font("Helvetica", "B", 8)
        for col in cols:
            pdf.cell(col_w, 6, str(col)[:16], border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for _, row in results.head(50).iterrows():
            for col in cols:
                val = row[col]
                if isinstance(val, float):
                    cell_text = f"{val:,.2f}"
                else:
                    cell_text = str(val)[:16]
                pdf.cell(col_w, 6, cell_text, border=1)
            pdf.ln()
    # Footer
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(
        0, 5,
        "Built by Icono (Iconoclastic Capital Management) · Fee-Only Fiduciary Wealth Management · "
        "Rochester, NY · iconoclasticcapital.com\\n"
        "This report is for informational purposes only and does not constitute financial advice."
    )
    return bytes(pdf.output())
def generate_csv_routing(results: pd.DataFrame) -> bytes:
    """Return the routing DataFrame as UTF-8 CSV bytes."""
    return results.to_csv(index=False).encode("utf-8")
