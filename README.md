# FuelSense

A fuel-consumption prediction and fleet-analysis platform built on real 2022
vehicle registration data. A machine-learning model predicts combined fuel
consumption (L/100 km) for a configured vehicle; an analytics layer and dataset
explorer surface how the full fleet behaves.

This is a ground-up rebuild of the original Streamlit app. The backend and
frontend are cleanly separated, the model has been retrained for accuracy, and
**every figure in the UI is computed from the real dataset** — there are no
placeholder, mock, or hardcoded values anywhere.

---

## Architecture

```
fuelsense/
├── backend/                 FastAPI service
│   ├── main.py              API routes + static frontend mount
│   ├── ml/
│   │   ├── preprocessing.py shared clean + feature engineering (train == serve)
│   │   ├── train.py         retrains the model, writes artifacts + metrics
│   │   ├── predict.py       inference service + dropdown vocabularies
│   │   └── eda.py           all dashboard figures, computed from the CSV
│   ├── data/                real datasets (CSV + source XLSX)
│   ├── artifacts/           model.joblib + metadata.json (regenerable)
│   └── requirements.txt
├── frontend/                custom HTML/CSS/JS (no framework, no build step)
│   ├── index.html
│   ├── css/  (base.css, components.css)
│   └── js/   (app.js, charts.js, chrome-bg.js)
├── notebook/                original EDA/training notebook (reference)
└── run.sh                   one-command launcher
```

The frontend is served by the same FastAPI process, so there's nothing to build
or deploy separately. The API is also usable on its own.

---

## Running it

```bash
./run.sh                     # installs deps, trains if needed, serves on :8000
```

or manually:

```bash
cd backend
pip install -r requirements.txt
python -m ml.train           # optional: regenerate model from the CSV
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Then open <http://127.0.0.1:8000>.

---

## The model

| | Old (`trained_model_lr.sav`) | New (`model.joblib`) |
|---|---|---|
| Algorithm | LinearRegression on ordinal-encoded nominal features | RandomForest on OneHot + StandardScaler, log-target |
| Test R² | ~0.53 | **0.94** |
| Test MAE | ~4.64 L/100 km | **1.22 L/100 km** |
| 5-fold CV R² | — | **0.90 ± 0.04** |
| Feature handling | scrambled order, 4 fuel dummies | deterministic, shared train/serve pipeline |

Metrics are written to `backend/artifacts/metadata.json` at training time and
surfaced live in the app's nav bar. They are honest hold-out numbers, not
training-set scores.

### Three problems this rebuild fixes

1. **Broken predictions.** The original app built its feature vector in the
   wrong order and with the wrong number of fuel dummy columns, so the deployed
   predictions did not match the trained model. The shared `preprocessing.py`
   guarantees training and serving use identical logic.
2. **Fabricated analytics.** The original "dashboard" used hardcoded monthly
   numbers and fixed stat tiles. Every chart and statistic is now derived from
   `data/vehicles_data_2022.csv` via `eda.py`.
3. **Weak model.** The retrained pipeline cleans invalid target rows, canonicalises
   fuel codes and the 26 noisy transmission codes into 6 families, and uses an
   appropriate model — raising accuracy substantially.

---

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | liveness + live model metrics |
| GET | `/api/metadata` | full training metrics + feature importances |
| GET | `/api/options` | dropdown vocabularies (from real data) |
| POST | `/api/predict` | real model prediction |
| GET | `/api/analytics` | full EDA payload for the dashboard |
| GET | `/api/dataset` | paginated/sortable/filterable dataset explorer |
| GET | `/api/fuel-rates` | live Indian metro petrol/diesel rates (with dated-snapshot fallback) |
| GET | `/api/news` | live automotive/fuel headlines (BBC RSS) |

`POST /api/predict` body:

```json
{
  "engine_size": 1.5,
  "cylinders": 4,
  "co2_rating": 6,
  "vehicle_class": "SUV: Small",
  "transmission": "Automatic",
  "fuel_type": "Gasoline"
}
```

Inputs are validated against the dataset's real vocabularies, so the model can
never receive a category it wasn't trained on.

---

## Frontend

A single-page, dependency-free interface. Design direction: an ultra-premium
dark "instrument cluster" — metallic chrome typography, an Apple-style liquid
glass surface treatment, and a large signature mercury-fill gauge for the
prediction. The predictor sits in the centre, flanked by a live Indian metro
fuel-rates table (left) and a vertical BBC fuel/mobility news feed (right). A
gas-tank "filling up" animation plays on load. Charts are hand-built SVG (no
Plotly/Chart.js), themed to match. The WebGL background and all motion respect
`prefers-reduced-motion` and the UI is responsive down to mobile (the side rails
stack below the predictor) with visible keyboard focus.

### A note on the live data feeds

`/api/fuel-rates` scrapes a public source for Indian metro petrol/diesel prices
and caches results for an hour. When the source is unreachable, it serves a
clearly-labelled dated snapshot so the table is never blank — the UI shows a
`LIVE` or `SNAPSHOT` badge accordingly. `/api/news` works the same way against
the BBC feed. Both degrade gracefully and require no API key.

---

Built by **RITWIK**. Model trained on real 2022 fleet data.
