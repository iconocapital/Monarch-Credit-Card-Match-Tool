"""
FastAPI backend for the Icono Credit Card Reward Optimizer.

Run with:  uvicorn api:app --reload
"""

import os

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

# CORS — restrict to known front-end origins in production.
# Set ALLOWED_ORIGINS env var to a comma-separated list of origins,
# e.g. "https://iconocapital.com,https://www.iconocapital.com"
# Falls back to "*" for local development.
_allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*")
allow_origins = [o.strip() for o in _allowed_origins.split(",")] if _allowed_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
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
    JSON with ``cards`` (list of scored cards), ``guide`` (JVN commentary),
    and ``meta`` (cpp_mode, total_spend, cards_evaluated, txn_count).
    """
    content = await file.read()
    text = content.decode("utf-8")
    df = pd.read_csv(StringIO(text))

    cards = list(CARD_DB.values())
    analysis = analyze_cards(df, cards=cards, cpp_mode=cpp_mode)

    guide = generate_guide(analysis["cards"], total_spend=analysis["total_spend"])

    return {
        "cards": analysis["cards"],
        "guide": guide,
        "meta": analysis["meta"],
    }
