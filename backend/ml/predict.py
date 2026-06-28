"""
predict.py
----------
Inference service. Loads the trained Pipeline once and exposes:
  - options()      -> the exact dropdown vocabularies the UI may use
  - predict(...)   -> real model prediction + efficiency banding + context

All categories offered to the UI come from the real, cleaned dataset, so the
frontend can never submit a value the model wasn't trained on.
"""

from __future__ import annotations
import os
import functools
import numpy as np
import joblib

from .preprocessing import (
    load_raw, clean, build_input_frame, TRANSMISSION_FAMILIES, FUEL_CODE_MAP,
)

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ART_DIR = os.path.join(BACKEND, "artifacts")
DATA_CSV = os.path.join(BACKEND, "data", "vehicles_data_2022.csv")
MODEL_PATH = os.path.join(ART_DIR, "model.joblib")


@functools.lru_cache(maxsize=1)
def _model():
    return joblib.load(MODEL_PATH)


_TWO_WHEELER_RE = "Motorcycle|Scooter|Bike"


@functools.lru_cache(maxsize=1)
def _fleet_segments():
    """
    Pre-split the real fleet target into segment families for an accurate
    percentile comparison.

    The dataset mixes cars with two-wheelers whose recorded consumption is on a
    very different (and internally inconsistent) scale. Comparing a car
    prediction against the whole fleet would distort the "more efficient than
    X%" figure, so we compare a prediction against the SAME family it belongs
    to. Returns (car_fleet, two_wheeler_fleet, full_fleet) as numpy arrays.
    """
    df = clean(load_raw(DATA_CSV))
    is_two = df["Vehicle Class"].str.contains(_TWO_WHEELER_RE, case=False, na=False)
    return (
        df.loc[~is_two, "Fuel Consumption"].to_numpy(dtype=float),
        df.loc[is_two, "Fuel Consumption"].to_numpy(dtype=float),
        df["Fuel Consumption"].to_numpy(dtype=float),
    )


@functools.lru_cache(maxsize=1)
def options() -> dict:
    """Dropdown vocabularies, derived from real data (sorted, deduped)."""
    df = clean(load_raw(DATA_CSV))
    # Only classes with enough support to be meaningful
    cls_counts = df["Vehicle Class"].value_counts()
    classes = sorted([c for c, n in cls_counts.items() if n >= 3])
    fuels = sorted(df["FuelN"].unique().tolist())
    trans = [t for t in TRANSMISSION_FAMILIES if t in set(df["TransFam"].unique())]
    return {
        "vehicle_classes": classes,
        "fuel_types": fuels,
        "transmissions": trans,
        "ranges": {
            "engine_size": {"min": 0.6, "max": float(df["Engine Size"].max()), "step": 0.1, "default": 1.5},
            "cylinders": {"min": 1, "max": int(df["Cylinders"].max()), "step": 1, "default": 4},
            "co2_rating": {"min": 1, "max": 10, "step": 1, "default": 5},
        },
    }


def _band(pred: float) -> dict:
    """Efficiency banding — thresholds tuned to the real target distribution."""
    if pred < 5:
        return {"label": "Exceptional", "tier": "exceptional",
                "note": "Outstanding economy — among the most efficient in the dataset."}
    if pred < 7:
        return {"label": "Excellent", "tier": "excellent",
                "note": "Strong economy with a good balance of performance and efficiency."}
    if pred < 9:
        return {"label": "Good", "tier": "good",
                "note": "Solid, dependable consumption for everyday driving."}
    if pred < 12:
        return {"label": "Moderate", "tier": "moderate",
                "note": "Above-average consumption; a smaller engine or hybrid would help."}
    return {"label": "High", "tier": "high",
            "note": "High consumption relative to the fleet; review the configuration."}


def predict(
    engine_size: float,
    cylinders: int,
    co2_rating: float,
    vehicle_class: str,
    transmission: str,
    fuel_type: str,
) -> dict:
    """Run a real prediction through the trained pipeline."""
    X = build_input_frame(
        engine_size=engine_size,
        cylinders=cylinders,
        co2_rating=co2_rating,
        vehicle_class=vehicle_class,
        trans_family=transmission,
        fuel_name=fuel_type,
    )
    pred_log = _model().predict(X)[0]
    pred = float(np.expm1(pred_log))
    pred = max(0.0, round(pred, 2))

    band = _band(pred)

    # Real fleet context: percentile of this prediction vs the SAME segment
    # family (cars vs cars, two-wheelers vs two-wheelers). This avoids the
    # mis-scaled two-wheeler rows distorting a car's "more efficient than"
    # figure. See _fleet_segments() for the rationale.
    import re as _re
    is_two_wheeler = bool(_re.search(_TWO_WHEELER_RE, vehicle_class, _re.I))
    car_fleet, two_fleet, full_fleet = _fleet_segments()
    segment_fleet = two_fleet if is_two_wheeler else car_fleet
    segment_label = "two-wheelers" if is_two_wheeler else "cars"
    if segment_fleet.size == 0:
        segment_fleet = full_fleet
        segment_label = "the fleet"
    pct = float((segment_fleet < pred).mean() * 100)

    return {
        "consumption_l_per_100km": pred,
        "consumption_mpg": round(235.215 / pred, 1) if pred > 0 else None,
        "efficiency": band,
        "fleet_percentile": round(pct, 1),  # lower percentile = more efficient
        "comparison_segment": segment_label,
        "inputs": {
            "engine_size": engine_size,
            "cylinders": cylinders,
            "co2_rating": co2_rating,
            "vehicle_class": vehicle_class,
            "transmission": transmission,
            "fuel_type": fuel_type,
        },
    }
