"""
FastAPI backend for the Icono Credit Card Reward Optimizer.

Run with:  uvicorn api:app --reload
"""

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from io import StringIO

from card_models import CARD_DB
from icono_engine import analyze_cards
from guide_jvn import generate_guide

app = FastAPI(
    title="Icono Card Reward Optimizer",
    description="Upload a Monarch CSV, get Icono-scored card rankings and a JVN-style guide.",
    version="1.0.0",
)

# CORS — allow any frontend during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """Health check."""
    return {"status": "ok", "service": "icono-card-optimizer"}


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    cpp_mode: str = Form("floor"),
):
    """Analyze a Monarch CSV and return Icono-scored card rankings.

    Parameters
    ----------
    file : CSV file (Monarch Money export format).
    cpp_mode : ``"floor"`` (conservative) or ``"awardwallet"`` (live valuations).

    Returns
    -------
    JSON with ``cards`` (list of scored cards) and ``guide`` (JVN commentary).
    """
    content = await file.read()
    text = content.decode("utf-8")
    df = pd.read_csv(StringIO(text))

    cards = list(CARD_DB.values())
    results = analyze_cards(df, cards=cards, cpp_mode=cpp_mode)

    total_spend = df["Amount"].apply(pd.to_numeric, errors="coerce").fillna(0)
    total_spend = float(total_spend[total_spend < 0].abs().sum())

    guide = generate_guide(results, total_spend=total_spend)

    return {
        "cards": results,
        "guide": guide,
        "meta": {
            "cpp_mode": cpp_mode,
            "total_spend": round(total_spend, 2),
            "cards_evaluated": len(results),
        },
    }
