"""
train.py
--------
Retrains the FuelSense regression model from the real 2022 dataset and writes
production artifacts:

  artifacts/model.joblib      -> full sklearn Pipeline (preprocess + RF)
  artifacts/metadata.json     -> metrics, vocabularies, feature importances,
                                 training date, dataset hash.

Run:  python -m ml.train   (from backend/)  or  python ml/train.py

The model is a log-target RandomForest on a OneHot/StandardScaler ColumnTransformer.
This replaces the original broken LinearRegression (.sav) which suffered from
scrambled feature ordering and ordinal-on-nominal encoding.
"""

from __future__ import annotations
import os
import json
import hashlib
import datetime as dt
import numpy as np
import pandas as pd
import joblib

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split, cross_val_score, KFold
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error

from .preprocessing import (
    load_raw, clean, NUMERIC_FEATURES, CATEGORICAL_FEATURES,
    FEATURE_COLUMNS, TARGET, TRANSMISSION_FAMILIES,
)

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
DATA_CSV = os.path.join(BACKEND, "data", "vehicles_data_2022.csv")
ART_DIR = os.path.join(BACKEND, "artifacts")
os.makedirs(ART_DIR, exist_ok=True)


def _log_target_pipeline() -> Pipeline:
    pre = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ]
    )
    rf = RandomForestRegressor(
        n_estimators=400, max_depth=18, min_samples_leaf=2,
        random_state=42, n_jobs=-1,
    )
    return Pipeline([("pre", pre), ("model", rf)])


def main() -> dict:
    df = clean(load_raw(DATA_CSV))
    X = df[FEATURE_COLUMNS].copy()
    y = df[TARGET].astype(float)
    y_log = np.log1p(y)

    # Honest hold-out evaluation
    Xtr, Xte, ytr_log, yte_log = train_test_split(
        X, y_log, test_size=0.2, random_state=42
    )
    pipe = _log_target_pipeline()
    pipe.fit(Xtr, ytr_log)
    pred = np.expm1(pipe.predict(Xte))
    yte = np.expm1(yte_log)

    test_r2 = float(r2_score(yte, pred))
    test_mae = float(mean_absolute_error(yte, pred))
    test_rmse = float(np.sqrt(mean_squared_error(yte, pred)))

    # Shuffled 5-fold cross validation (stability check)
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    cv = cross_val_score(pipe, X, y_log, cv=kf, scoring="r2")

    # Refit on ALL data for the production artifact
    final = _log_target_pipeline()
    final.fit(X, y_log)

    # Feature importances (back-mapped to readable names)
    ohe = final.named_steps["pre"].named_transformers_["cat"]
    cat_names = list(ohe.get_feature_names_out(CATEGORICAL_FEATURES))
    feat_names = NUMERIC_FEATURES + cat_names
    importances = final.named_steps["model"].feature_importances_
    imp_sorted = sorted(
        zip(feat_names, importances.tolist()), key=lambda z: -z[1]
    )

    # Dataset hash for reproducibility / drift detection
    with open(DATA_CSV, "rb") as f:
        data_hash = hashlib.sha256(f.read()).hexdigest()[:16]

    metadata = {
        "model_type": "RandomForestRegressor (log-target)",
        "trained_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_samples": int(len(df)),
        "n_features_raw": len(FEATURE_COLUMNS),
        "n_features_encoded": len(feat_names),
        "dataset_sha256_16": data_hash,
        "metrics": {
            "test_r2": round(test_r2, 4),
            "test_mae": round(test_mae, 4),
            "test_rmse": round(test_rmse, 4),
            "cv_r2_mean": round(float(cv.mean()), 4),
            "cv_r2_std": round(float(cv.std()), 4),
        },
        "feature_importances": [
            {"feature": f, "importance": round(v, 5)} for f, v in imp_sorted
        ],
        "target_stats": {
            "min": round(float(y.min()), 2),
            "max": round(float(y.max()), 2),
            "mean": round(float(y.mean()), 2),
            "median": round(float(y.median()), 2),
        },
    }

    joblib.dump(final, os.path.join(ART_DIR, "model.joblib"))
    with open(os.path.join(ART_DIR, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    print("=== FuelSense model trained ===")
    print(json.dumps(metadata["metrics"], indent=2))
    print(f"Samples: {metadata['n_samples']}  Encoded features: {metadata['n_features_encoded']}")
    print(f"Artifacts -> {ART_DIR}")
    return metadata


if __name__ == "__main__":
    main()
