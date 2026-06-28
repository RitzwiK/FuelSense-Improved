"""
fuel_rates.py
-------------
Live Indian metro petrol/diesel rates for the predictor side rail.

Source chain (most authoritative first; each step is a fallback for the one
above so the table is never blank and never silently stale):

  1. indianapi.in Fuel Price API  -- used ONLY if FUEL_API_KEY is set in the
     environment. This is the user-requested primary source. It is a keyed
     marketplace API (free tier available at https://indianapi.in/fuel-price-api).
  2. newsrain.in city pages       -- keyless HTML scrape of the same public
     figures, parsed for petrol/diesel.
  3. dated snapshot               -- a hardcoded, clearly-labelled fallback so
     the UI always renders. Surfaced as `source: "snapshot"` with its date.

Every response carries:
  - live (bool)        : True only for sources 1 and 2.
  - source (str)       : "indianapi.in" | "newsrain.in" | "snapshot".
  - last_updated (str) : ISO timestamp the figures were retrieved/issued.
  - as_of (str)        : the date the prices themselves apply to (from the API
                         when available, else the retrieval date / snapshot date).

NOTE ON THE API: indianapi.in requires a free API key. Without FUEL_API_KEY the
code skips straight to the scrape + snapshot chain. The exact field names from
indianapi.in can vary by plan, so the parser below is defensive: it accepts
several common key spellings (petrol/petrol_price, diesel/diesel_price, etc.)
and validates every number before use. No value is ever fabricated; if a field
is missing it is backfilled from the snapshot and that row is flagged.
"""

from __future__ import annotations
import os
import re
import time
import datetime as dt

import requests

# ---------------------------------------------------------------------------
# Metros we display, with the slug each source uses.
# ---------------------------------------------------------------------------
METROS = [
    {"city": "Delhi",     "newsrain": "delhi",     "state": "delhi",       "api_city": "delhi"},
    {"city": "Mumbai",    "newsrain": "mumbai",    "state": "maharashtra", "api_city": "mumbai"},
    {"city": "Bengaluru", "newsrain": "bangalore", "state": "karnataka",   "api_city": "bangalore"},
    {"city": "Chennai",   "newsrain": "chennai",   "state": "tamil-nadu",  "api_city": "chennai"},
    {"city": "Kolkata",   "newsrain": "kolkata",   "state": "west-bengal", "api_city": "kolkata"},
    {"city": "Hyderabad", "newsrain": "hyderabad", "state": "telangana",   "api_city": "hyderabad"},
]

# Dated fallback snapshot (INR/litre). Used only when every live source fails.
_FALLBACK_AS_OF = "2025-06-01"
_FALLBACK = {
    "Delhi":     {"petrol": 94.72, "diesel": 87.62},
    "Mumbai":    {"petrol": 103.50, "diesel": 90.03},
    "Bengaluru": {"petrol": 102.86, "diesel": 88.94},
    "Chennai":   {"petrol": 100.80, "diesel": 92.39},
    "Kolkata":   {"petrol": 105.41, "diesel": 92.02},
    "Hyderabad": {"petrol": 107.41, "diesel": 95.65},
}

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FuelSense/2.1)"}
_API_KEY = os.environ.get("FUEL_API_KEY", "").strip()
_API_BASE = os.environ.get("FUEL_API_BASE", "https://fuel.indianapi.in").strip()

_cache = {"ts": 0.0, "data": None}
_TTL = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _num(v):
    """Coerce a value to a positive float, or None. Never raises."""
    try:
        f = float(str(v).replace(",", "").replace("\u20b9", "").strip())
        return round(f, 2) if f > 0 else None
    except Exception:
        return None


def _pick(d, *keys):
    """Return the first present, parseable numeric value among keys."""
    for k in keys:
        if k in d:
            n = _num(d[k])
            if n is not None:
                return n
    return None


# ---------------------------------------------------------------------------
# Source 1: indianapi.in (keyed)
# ---------------------------------------------------------------------------
def _fetch_indianapi():
    if not _API_KEY:
        return None
    try:
        r = requests.get(
            f"{_API_BASE}/",
            headers={**_HEADERS, "x-api-key": _API_KEY},
            timeout=8,
        )
        if r.status_code != 200:
            return None
        payload = r.json()
    except Exception:
        return None

    index = {}
    api_date = {"v": None}

    def consume(node):
        if isinstance(node, dict):
            for dk in ("date", "last_updated", "updated_at", "as_on"):
                if dk in node and api_date["v"] is None:
                    api_date["v"] = str(node[dk])
            name = node.get("city") or node.get("district") or node.get("name")
            petrol = _pick(node, "petrol", "petrol_price", "petrolPrice", "retailPrice")
            diesel = _pick(node, "diesel", "diesel_price", "dieselPrice")
            if name and (petrol or diesel):
                index[str(name).strip().lower()] = {"petrol": petrol, "diesel": diesel}
            for v in node.values():
                consume(v)
        elif isinstance(node, list):
            for v in node:
                consume(v)

    consume(payload)
    if not index:
        return None

    rows, ok = [], 0
    for m in METROS:
        hit = index.get(m["api_city"].lower()) or index.get(m["city"].lower())
        if hit and (hit.get("petrol") or hit.get("diesel")):
            rows.append({"city": m["city"], "petrol": hit.get("petrol"), "diesel": hit.get("diesel")})
            ok += 1
        else:
            rows.append({"city": m["city"], "petrol": None, "diesel": None})

    if ok < max(2, len(METROS) // 2):
        return None
    return {"source": "indianapi.in", "as_of": api_date["v"] or dt.date.today().isoformat(), "rows": rows}


# ---------------------------------------------------------------------------
# Source 2: newsrain.in (keyless scrape)
# ---------------------------------------------------------------------------
def _parse_newsrain_city(slug):
    url = f"https://www.newsrain.in/petrol-diesel-price/{slug}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=6)
        if r.status_code != 200 or not r.text:
            return None
        html = r.text

        def grab(label):
            m = re.search(label + r"[^0-9\u20b9]{0,40}\u20b9?\s*([0-9]{2,3}\.[0-9]{1,2})", html, re.I)
            return _num(m.group(1)) if m else None

        petrol, diesel = grab("Petrol"), grab("Diesel")
        if petrol and diesel:
            return {"petrol": petrol, "diesel": diesel}
    except Exception:
        pass
    return None


def _fetch_newsrain():
    rows, ok = [], 0
    for m in METROS:
        data = _parse_newsrain_city(m["newsrain"])
        if data:
            rows.append({"city": m["city"], **data})
            ok += 1
        else:
            rows.append({"city": m["city"], "petrol": None, "diesel": None})
    if ok < max(2, len(METROS) // 2):
        return None
    return {"source": "newsrain.in", "as_of": dt.date.today().isoformat(), "rows": rows}


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
def get_rates():
    now = time.time()
    if _cache["data"] is not None and now - _cache["ts"] < _TTL:
        return _cache["data"]

    result = _fetch_indianapi() or _fetch_newsrain()

    if result:
        for row in result["rows"]:
            if (row.get("petrol") is None or row.get("diesel") is None) and row["city"] in _FALLBACK:
                fb = _FALLBACK[row["city"]]
                row["petrol"] = row.get("petrol") or fb["petrol"]
                row["diesel"] = row.get("diesel") or fb["diesel"]
                row["estimated"] = True
        payload = {
            "live": True,
            "source": result["source"],
            "as_of": result["as_of"],
            "last_updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "currency": "INR",
            "unit": "per litre",
            "rows": result["rows"],
        }
    else:
        payload = {
            "live": False,
            "source": "snapshot",
            "as_of": _FALLBACK_AS_OF,
            "last_updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "currency": "INR",
            "unit": "per litre",
            "rows": [{"city": c, **v} for c, v in _FALLBACK.items()],
        }

    _cache.update(ts=now, data=payload)
    return payload
