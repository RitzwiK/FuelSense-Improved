"""
preprocessing.py
----------------
Single source of truth for cleaning the 2022 vehicle dataset and engineering
the feature set used by both training (train.py) and inference (predict.py).

The original notebook scrambled feature ordering and used ordinal encoding on
nominal categories, which produced an unreliable model. This module replaces
that with a clean, documented, deterministic pipeline so that training and
serving share *exactly* the same logic — eliminating the train/serve skew that
broke the deployed Streamlit app.
"""

from __future__ import annotations
import pandas as pd
import numpy as np

# ----------------------------------------------------------------------------
# Canonical vocabularies. These are derived from the real dataset and are the
# *only* categories the UI is allowed to offer. Keeping them here means the API,
# the model, and the frontend never drift apart.
# ----------------------------------------------------------------------------

# Raw fuel codes in the CSV -> human-readable canonical fuel names.
FUEL_CODE_MAP = {
    "X": "Gasoline",
    "Petrol": "Gasoline",
    "D": "Diesel",
    "Diesel": "Diesel",
    "E": "Ethanol",
    "Z": "Electric",
    "Electric": "Electric",
}

# Transmission families. The CSV has 26 noisy codes (A8, AS10, AV7, ...).
# We consolidate them into 6 meaningful families.
TRANSMISSION_FAMILIES = ["Automatic", "Manual", "CVT", "AutoManual", "AutoSelect", "Other"]

# Canonical column names after rename.
RENAME_MAP = {
    "Vehicle Category": "Vehicle Class",
    "Engine Capacity (Liters)": "Engine Size",
    "Number of Cylinders": "Cylinders",
    "TYPE OF FUEL": "Fuel Type",
    "Combined Fuel Efficiency (L/100 km)": "Fuel Consumption",
    "Carbon Dioxide Rating": "CO2 Rating",
    "CO2 Emission Rate (g/km)": "CO2 gkm",
    "City Fuel Efficiency (L/100 km)": "City Consumption",
    "Highway Fuel Efficiency (L/100 km)": "Highway Consumption",
}

# Feature groups consumed by the ColumnTransformer in train.py.
NUMERIC_FEATURES = ["Engine Size", "Cylinders", "CO2 Rating"]
CATEGORICAL_FEATURES = ["Vehicle Class", "TransFam", "FuelN"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = "Fuel Consumption"


def _transmission_family(code: str) -> str:
    """Map a raw transmission code to one of TRANSMISSION_FAMILIES."""
    t = str(code)
    if t.startswith("AV") or t == "CVT":
        return "CVT"
    if t.startswith("AM"):
        return "AutoManual"
    if t.startswith("AS"):
        return "AutoSelect"
    if t.startswith("A") or t == "Automatic":
        return "Automatic"
    if t.startswith("M") or t == "Manual":
        return "Manual"
    return "Other"


def load_raw(csv_path: str) -> pd.DataFrame:
    """Load the raw CSV and apply canonical renames (no row filtering)."""
    df = pd.read_csv(csv_path)
    df = df.rename(columns=RENAME_MAP)
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean + engineer features deterministically.

    Steps:
      1. Drop rows with non-positive / missing target (invalid records).
      2. Impute Fuel Type with mode, CO2 Rating with median.
      3. Engineer canonical FuelN and TransFam categories.
      4. Coerce numerics.
    Returns a frame containing FEATURE_COLUMNS + TARGET (+ helpful extras).
    """
    df = df.copy()

    # 1. Valid target only — the original data has 0/blank consumption rows.
    df = df[pd.to_numeric(df[TARGET], errors="coerce").notna()]
    df[TARGET] = df[TARGET].astype(float)
    df = df[df[TARGET] > 0]

    # 2. Imputation
    if df["Fuel Type"].isna().any():
        df["Fuel Type"] = df["Fuel Type"].fillna(df["Fuel Type"].mode()[0])
    df["CO2 Rating"] = pd.to_numeric(df["CO2 Rating"], errors="coerce")
    df["CO2 Rating"] = df["CO2 Rating"].fillna(df["CO2 Rating"].median())

    # 3. Canonical categories
    df["FuelN"] = df["Fuel Type"].map(FUEL_CODE_MAP).fillna("Gasoline")
    df["TransFam"] = df["Transmission"].apply(_transmission_family)

    # 4. Numeric coercion
    df["Engine Size"] = pd.to_numeric(df["Engine Size"], errors="coerce").fillna(
        df["Engine Size"].median() if "Engine Size" in df else 0
    )
    df["Cylinders"] = pd.to_numeric(df["Cylinders"], errors="coerce").fillna(0).astype(int)

    return df


def build_input_frame(
    engine_size: float,
    cylinders: int,
    co2_rating: float,
    vehicle_class: str,
    trans_family: str,
    fuel_name: str,
) -> pd.DataFrame:
    """
    Build a single-row DataFrame in EXACTLY the schema the pipeline expects.
    Used at inference time so serving == training preprocessing.
    """
    return pd.DataFrame(
        [{
            "Engine Size": float(engine_size),
            "Cylinders": int(cylinders),
            "CO2 Rating": float(co2_rating),
            "Vehicle Class": vehicle_class,
            "TransFam": trans_family,
            "FuelN": fuel_name,
        }]
    )
