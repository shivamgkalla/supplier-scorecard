"""HTTP API: upload purchase orders as CSV, get scores as JSON or an Excel report."""

from __future__ import annotations

from io import BytesIO

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

from . import __version__
from .features import InputError, build_features, load_orders
from .report import build_report
from .scoring import load_config, score_suppliers, tier_counts

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

app = FastAPI(
    title="Supplier Scorecard",
    version=__version__,
    description="Scores suppliers from purchase-order history using a configurable, "
    "fully traceable rule set.",
)
CFG = load_config()


async def _score_upload(file: UploadFile):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    try:
        orders = load_orders(BytesIO(data))
    except InputError as exc:
        raise HTTPException(422, str(exc)) from exc
    return score_suppliers(build_features(orders), CFG)


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@app.post("/score")
async def score(file: UploadFile = File(...), top: int = 10):
    """Return tier counts and the `top` lowest-scoring suppliers."""
    scored = await _score_upload(file)
    worst = scored.dropna(subset=["score"]).head(max(0, min(top, 200)))
    cols = ["supplier_id", "score", "risk_tier", "main_driver", "n_orders"]
    return {
        "suppliers": int(len(scored)),
        "tiers": tier_counts(scored, CFG),
        "lowest_scoring": worst[cols].round({"score": 2}).to_dict(orient="records"),
    }


@app.post("/report")
async def report(file: UploadFile = File(...)):
    """Return the full Excel report for the uploaded purchase orders."""
    scored = await _score_upload(file)
    return Response(
        content=build_report(scored, CFG),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="supplier_scorecard.xlsx"'},
    )
