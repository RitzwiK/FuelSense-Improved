"""
main.py — FuelSense API
-----------------------
FastAPI backend. Serves:
  GET  /api/health          -> liveness + model metadata
  GET  /api/options         -> dropdown vocabularies (from real data)
  POST /api/predict         -> real model prediction
  GET  /api/analytics       -> full real-EDA payload for the dashboard
  GET  /api/dataset         -> paginated/queryable dataset explorer
  GET  /api/news            -> live automotive/fuel news (BBC RSS)
  GET  /api/metadata        -> training metrics & feature importances

Static frontend is served from /frontend at the root path.
"""

from __future__ import annotations
import os
import re
import json
import time
import functools

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

import pandas as pd

from ml.predict import predict as run_predict, options as get_options
from ml import eda
from ml.fuel_rates import get_rates
from ml.preprocessing import load_raw, clean

HERE = os.path.dirname(os.path.abspath(__file__))
ART_DIR = os.path.join(HERE, "artifacts")
DATA_CSV = os.path.join(HERE, "data", "vehicles_data_2022.csv")
FRONTEND_DIR = os.path.normpath(os.path.join(HERE, "..", "frontend"))

app = FastAPI(title="FuelSense API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class PredictRequest(BaseModel):
    engine_size: float = Field(..., ge=0.1, le=12)
    cylinders: int = Field(..., ge=0, le=20)
    co2_rating: float = Field(..., ge=0, le=10)
    vehicle_class: str
    transmission: str
    fuel_type: str

    @field_validator("vehicle_class", "transmission", "fuel_type")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def _metadata() -> dict:
    path = os.path.join(ART_DIR, "metadata.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


@functools.lru_cache(maxsize=1)
def _explorer_df() -> pd.DataFrame:
    df = clean(load_raw(DATA_CSV))
    keep = [c for c in [
        "Brand Name", "Model", "Vehicle Class", "Engine Size", "Cylinders",
        "TransFam", "FuelN", "CO2 Rating", "Fuel Consumption",
    ] if c in df.columns]
    out = df[keep].rename(columns={
        "Brand Name": "brand", "Model": "model", "Vehicle Class": "vehicle_class",
        "Engine Size": "engine", "Cylinders": "cylinders", "TransFam": "transmission",
        "FuelN": "fuel", "CO2 Rating": "co2_rating", "Fuel Consumption": "consumption",
    })
    out["engine"] = out["engine"].round(1)
    out["consumption"] = out["consumption"].round(2)
    out["co2_rating"] = out["co2_rating"].round(0).astype(int)
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return {"status": "ok", "model": _metadata().get("model_type"),
            "metrics": _metadata().get("metrics", {})}


@app.get("/api/metadata")
def metadata():
    return _metadata()


@app.get("/api/options")
def options():
    return get_options()


@app.post("/api/predict")
def predict(req: PredictRequest):
    opts = get_options()
    if req.vehicle_class not in opts["vehicle_classes"]:
        raise HTTPException(422, f"Unknown vehicle_class: {req.vehicle_class}")
    if req.transmission not in opts["transmissions"]:
        raise HTTPException(422, f"Unknown transmission: {req.transmission}")
    if req.fuel_type not in opts["fuel_types"]:
        raise HTTPException(422, f"Unknown fuel_type: {req.fuel_type}")
    try:
        return run_predict(
            engine_size=req.engine_size, cylinders=req.cylinders,
            co2_rating=req.co2_rating, vehicle_class=req.vehicle_class,
            transmission=req.transmission, fuel_type=req.fuel_type,
        )
    except Exception as e:
        raise HTTPException(500, f"Prediction failed: {e}")


@app.get("/api/analytics")
def analytics():
    return eda.full_payload()


@app.get("/api/dataset")
def dataset(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100),
    search: str = Query("", max_length=80),
    vehicle_class: str = Query(""),
    fuel: str = Query(""),
    sort_by: str = Query("consumption"),
    sort_dir: str = Query("asc"),
):
    df = _explorer_df()
    if search:
        s = search.lower()
        mask = (
            df["brand"].str.lower().str.contains(s, na=False)
            | df["model"].str.lower().str.contains(s, na=False)
            | df["vehicle_class"].str.lower().str.contains(s, na=False)
        )
        df = df[mask]
    if vehicle_class:
        df = df[df["vehicle_class"] == vehicle_class]
    if fuel:
        df = df[df["fuel"] == fuel]
    if sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=(sort_dir == "asc"))

    total = len(df)
    start = (page - 1) * page_size
    rows = df.iloc[start:start + page_size].to_dict(orient="records")
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "rows": rows,
        "facets": {
            "vehicle_classes": sorted(_explorer_df()["vehicle_class"].unique().tolist()),
            "fuels": sorted(_explorer_df()["fuel"].unique().tolist()),
        },
    }


@app.get("/api/fuel-rates")
def fuel_rates():
    return get_rates()


# Simple in-process cache for news (5 min TTL)
_news_cache = {"ts": 0, "data": None}


@app.get("/api/news")
def news():
    now = time.time()
    if _news_cache["data"] is not None and now - _news_cache["ts"] < 300:
        return _news_cache["data"]
    try:
        import feedparser
        feed = feedparser.parse("https://feeds.bbci.co.uk/news/topics/cpzpydkymr4t/rss.xml")
        keywords = ["fuel", "mileage", "electric", "efficiency", "car", "auto",
                    "vehicle", "hybrid", "gasoline", "diesel", "ev", "battery"]
        items = []
        for e in feed.entries:
            title = (e.get("title") or "").strip()
            summary = re.sub(r"<[^>]+>", "", e.get("summary", "")).strip()
            blob = (title + " " + summary).lower()
            if any(k in blob for k in keywords):
                items.append({
                    "title": title,
                    "summary": (summary[:160] + "…") if len(summary) > 160 else summary,
                    "link": e.get("link", "#"),
                    "published": e.get("published", ""),
                })
            if len(items) >= 8:
                break
        payload = {"items": items, "source": "BBC", "count": len(items)}
    except Exception as e:
        payload = {"items": [], "source": "BBC", "count": 0, "error": str(e)}
    _news_cache.update(ts=now, data=payload)
    return payload


# --------------------------------------------------------------------------- #
# Static frontend (mounted last so /api/* wins)
# --------------------------------------------------------------------------- #
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.exception_handler(404)
def not_found(request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    index = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index):
        from fastapi.responses import FileResponse
        return FileResponse(index)
    return JSONResponse({"detail": "Not found"}, status_code=404)
