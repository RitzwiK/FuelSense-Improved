"""
eda.py
------
Computes every analytics figure shown in the UI directly from the real
cleaned dataset. NOTHING here is hardcoded or mocked — each number is derived
from data/vehicles_data_2022.csv at load time and cached.

This replaces the deployed app's fabricated `sample_data` (made-up Jan-Jun
numbers) and hardcoded stat tiles (7.85, 85%, $118, 12%).
"""

from __future__ import annotations
import os
import functools
import numpy as np
import pandas as pd

from .preprocessing import load_raw, clean, FUEL_CODE_MAP

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
DATA_CSV = os.path.join(BACKEND, "data", "vehicles_data_2022.csv")


@functools.lru_cache(maxsize=1)
def _df() -> pd.DataFrame:
    return clean(load_raw(DATA_CSV))


def _round_list(vals, n=2):
    return [round(float(v), n) for v in vals]


def summary_stats() -> dict:
    """Headline KPI tiles — all computed from real data."""
    df = _df()
    eff = df["Fuel Consumption"]
    # Cleanest car-like segment for a representative "best efficiency" figure
    cars = df[~df["Vehicle Class"].str.contains(
        "Motorcycle|Scooter|Bike|Rickshaw", case=False, na=False
    )]
    return {
        "total_vehicles": int(len(df)),
        "avg_consumption": round(float(eff.mean()), 2),
        "median_consumption": round(float(eff.median()), 2),
        "best_consumption": round(float(eff.min()), 2),
        "worst_consumption": round(float(eff.max()), 2),
        "n_brands": int(df["Brand Name"].nunique()) if "Brand Name" in df else None,
        "n_classes": int(df["Vehicle Class"].nunique()),
        "electric_share_pct": round(
            float((df["FuelN"] == "Electric").mean() * 100), 1
        ),
        "avg_engine_size": round(float(df["Engine Size"].mean()), 2),
        "avg_co2_rating": round(float(df["CO2 Rating"].mean()), 1),
        "car_avg_consumption": round(float(cars["Fuel Consumption"].mean()), 2),
    }


def consumption_distribution(bins: int = 24) -> dict:
    """Histogram of combined fuel consumption."""
    df = _df()
    vals = df["Fuel Consumption"].clip(upper=df["Fuel Consumption"].quantile(0.99))
    counts, edges = np.histogram(vals, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    return {
        "x": _round_list(centers, 2),
        "y": [int(c) for c in counts],
        "mean": round(float(df["Fuel Consumption"].mean()), 2),
        "median": round(float(df["Fuel Consumption"].median()), 2),
    }


def consumption_by_class(top: int = 12) -> dict:
    """Mean consumption per vehicle class (sorted, most efficient first)."""
    df = _df()
    g = (
        df.groupby("Vehicle Class")["Fuel Consumption"]
        .agg(["mean", "count"])
        .query("count >= 3")
        .sort_values("mean")
    )
    g = g.head(top)
    return {
        "labels": g.index.tolist(),
        "values": _round_list(g["mean"].values, 2),
        "counts": [int(c) for c in g["count"].values],
    }


def consumption_by_fuel() -> dict:
    """Mean consumption grouped by canonical fuel type."""
    df = _df()
    g = df.groupby("FuelN")["Fuel Consumption"].agg(["mean", "count"]).sort_values("mean")
    return {
        "labels": g.index.tolist(),
        "values": _round_list(g["mean"].values, 2),
        "counts": [int(c) for c in g["count"].values],
    }


def engine_vs_consumption(max_points: int = 400) -> dict:
    """Scatter of engine size vs consumption, colored by fuel, with a fit line."""
    df = _df().copy()
    df = df[(df["Engine Size"] > 0) & (df["Fuel Consumption"] > 0)]
    if len(df) > max_points:
        df = df.sample(max_points, random_state=7)
    # least-squares trend (real, computed)
    x = df["Engine Size"].values.astype(float)
    y = df["Fuel Consumption"].values.astype(float)
    if len(np.unique(x)) > 1:
        slope, intercept = np.polyfit(x, y, 1)
        xs = [float(x.min()), float(x.max())]
        ys = [round(slope * xs[0] + intercept, 2), round(slope * xs[1] + intercept, 2)]
    else:
        xs, ys = [], []
    return {
        "points": [
            {"x": round(float(a), 2), "y": round(float(b), 2), "fuel": str(fn)}
            for a, b, fn in zip(x, y, df["FuelN"].values)
        ],
        "trend_x": xs,
        "trend_y": ys,
    }


def cylinders_vs_consumption() -> dict:
    """Mean consumption per cylinder count (real grouped means)."""
    df = _df()
    g = (
        df[df["Cylinders"] > 0]
        .groupby("Cylinders")["Fuel Consumption"]
        .agg(["mean", "count"])
        .query("count >= 3")
        .sort_index()
    )
    return {
        "labels": [int(c) for c in g.index.tolist()],
        "values": _round_list(g["mean"].values, 2),
        "counts": [int(c) for c in g["count"].values],
    }


def correlation_matrix() -> dict:
    """Pearson correlation among numeric engineering features + target."""
    df = _df()
    cols = ["Engine Size", "Cylinders", "CO2 Rating", "Fuel Consumption"]
    sub = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    corr = sub.corr().round(3)
    return {"labels": cols, "matrix": corr.values.tolist()}


def most_efficient(top: int = 8) -> list:
    """Real most-efficient car-like vehicles from the dataset."""
    df = _df()
    cars = df[~df["Vehicle Class"].str.contains(
        "Motorcycle|Scooter|Bike|Rickshaw", case=False, na=False
    )].copy()
    cars = cars.sort_values("Fuel Consumption").head(top)
    out = []
    for _, r in cars.iterrows():
        out.append({
            "brand": str(r.get("Brand Name", "—")),
            "model": str(r.get("Model", "—")),
            "vehicle_class": str(r["Vehicle Class"]),
            "fuel": str(r["FuelN"]),
            "engine": round(float(r["Engine Size"]), 1),
            "consumption": round(float(r["Fuel Consumption"]), 2),
        })
    return out


def full_payload() -> dict:
    """One call -> everything the analytics dashboard needs."""
    return {
        "summary": summary_stats(),
        "distribution": consumption_distribution(),
        "by_class": consumption_by_class(),
        "by_fuel": consumption_by_fuel(),
        "engine_scatter": engine_vs_consumption(),
        "by_cylinders": cylinders_vs_consumption(),
        "correlation": correlation_matrix(),
        "most_efficient": most_efficient(),
    }
