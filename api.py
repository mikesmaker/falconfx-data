"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  FalconFX BOOSTER  —  FastAPI Endpoint  v3.0                                ║
║                                                                              ║
║  POST /booster/compute  →  BoosterOutput JSON                                ║
║  GET  /booster/health   →  engine status                                     ║
║  GET  /booster/shadow   →  currently-active shadow matrix windows            ║
╚══════════════════════════════════════════════════════════════════════════════╝

Usage (dev):
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload

Mobile widget integration:
    POST https://<your-domain>/booster/compute
    Content-Type: application/json
    Body: see ComputeRequest schema below
"""

from __future__ import annotations

import datetime
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from booster import BoosterEngine, RiderTelemetry


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC SCHEMAS  (request / response)
# ══════════════════════════════════════════════════════════════════════════════

class RiderInput(BaseModel):
    lat:                 float = Field(..., description="Rider latitude (decimal degrees)")
    lng:                 float = Field(..., description="Rider longitude (decimal degrees)")
    speed_kmh:           float = Field(..., ge=0, description="Current speed in km/h")
    heading_deg:         float = Field(..., ge=0, lt=360, description="Heading in degrees (0=N)")
    has_active_delivery: bool  = Field(False)
    dropoff_lat:         Optional[float] = None
    dropoff_lng:         Optional[float] = None
    fuel_level_pct:      float = Field(100.0, ge=0, le=100)


class HotspotSignal(BaseModel):
    lat:       float
    lng:       float
    intensity: float = Field(..., ge=0, le=100,
                             description="Pre-checkout signal strength 0-100")


class ComputeRequest(BaseModel):
    rider:              RiderInput
    hour:               Optional[int]   = Field(None, ge=0, lt=24,
                                                description="Override hour (default: server time)")
    minute:             Optional[int]   = Field(None, ge=0, lt=60,
                                                description="Override minute (default: server time)")
    search_radius_km:   float           = Field(5.0, ge=0.5, le=20.0)
    simulate_hotspots:  list[HotspotSignal] = Field(default_factory=list,
                                                     description="Platform API cart-spike signals")
    rain_active_zones:  list[str]       = Field(default_factory=list,
                                                description="Active flood zone names from RAIN_FLOOD_ZONES")

    class Config:
        json_schema_extra = {
            "example": {
                "rider": {
                    "lat": 5.605, "lng": -0.173,
                    "speed_kmh": 28, "heading_deg": 135,
                    "has_active_delivery": False,
                    "fuel_level_pct": 78
                },
                "search_radius_km": 5.0,
                "simulate_hotspots": [
                    {"lat": 5.570, "lng": -0.170, "intensity": 65}
                ],
                "rain_active_zones": []
            }
        }


# ══════════════════════════════════════════════════════════════════════════════
# LIFESPAN — engine loaded once at startup, shared across all requests
# ══════════════════════════════════════════════════════════════════════════════

PLACES_PATH = os.environ.get("PLACES_PATH", "places.json")
_engine: Optional[BoosterEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    print("[Booster API] Loading engine...")
    _engine = BoosterEngine(PLACES_PATH)
    print("[Booster API] Ready.")
    yield
    _engine = None
    print("[Booster API] Shutdown.")


# ══════════════════════════════════════════════════════════════════════════════
# APP SETUP
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="FalconFX Booster API",
    description=(
        "Predictive demand engine for FalconFX rider companion app. "
        "Returns hot spot centroids, drift vectors, leapfrog routing, "
        "waybill intercepts, shadow matrix demand, and adaptive poll intervals."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/booster/health")
def health():
    """Quick health check — confirms engine is loaded and grid cell count."""
    if _engine is None:
        raise HTTPException(503, detail="Engine not initialised")
    return {
        "status": "ok",
        "version": "3.0.0",
        "grid_cells": len(_engine.grid.cells),
        "places_loaded": sum(len(c.places) for c in _engine.grid.cells.values()),
        "shadow_matrix_zones": len(_engine.demand.shadow_matrix),
        "road_quality_zones": len(_engine.friction.road_quality_zones),
        "b2b_wholesale_zones": len(_engine.demand.b2b_zones),
        "terminal_schedules": 5,
        "front_running_mode": True,
        "algorithm": "ghost_penalty + acceleration_scoring + 4layer_friction",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@app.get("/booster/shadow")
def shadow_active(hour: Optional[int] = None, minute: Optional[int] = None):
    """
    Returns which shadow matrix (offline chop bar / canteen) windows
    are currently firing for a given time. Defaults to server UTC time
    adjusted for Accra (GMT+0 = UTC).
    """
    if _engine is None:
        raise HTTPException(503, detail="Engine not initialised")
    now = datetime.datetime.utcnow()
    h = hour   if hour   is not None else now.hour
    m = minute if minute is not None else now.minute
    active = _engine.demand.active_shadow_windows(h, m)
    return {
        "hour": h,
        "minute": m,
        "active_windows": active,
        "count": len(active),
    }


@app.post("/booster/compute")
def compute(req: ComputeRequest):
    """
    Main endpoint. POST rider telemetry → receive full BoosterOutput:
      - hotspots          : top 3 hot spot centroids with surge probabilities
      - primary_vector    : drift vector to best intercept zone
      - leapfrog_vector   : pre-cached next pickup zone (active deliveries only)
      - arbitrage_alert   : return ticket opportunity if heading to outskirts
      - waybill_alert     : inter-city bus / trotro arrival intercept window
      - weather_advisory  : monsoon dry-edge nudge if rain is displacing demand
      - grid_stats        : road surface quality, shadow matrix activity, friction
      - next_poll_interval_seconds : adaptive battery/data saver (8s–120s)
    """
    if _engine is None:
        raise HTTPException(503, detail="Engine not initialised")

    # Default hour/minute/weekday to current Accra time (UTC = GMT+0)
    now     = datetime.datetime.utcnow()
    hour    = req.hour   if req.hour   is not None else now.hour
    minute  = req.minute if req.minute is not None else now.minute
    weekday = now.weekday()   # 0=Mon … 6=Sun

    rider = RiderTelemetry(
        lat=req.rider.lat,
        lng=req.rider.lng,
        speed_kmh=req.rider.speed_kmh,
        heading_deg=req.rider.heading_deg,
        has_active_delivery=req.rider.has_active_delivery,
        dropoff_lat=req.rider.dropoff_lat,
        dropoff_lng=req.rider.dropoff_lng,
        fuel_level_pct=req.rider.fuel_level_pct,
    )

    spikes = [(s.lat, s.lng, s.intensity) for s in req.simulate_hotspots]

    result = _engine.compute(
        rider=rider,
        hour=hour,
        minute=minute,
        search_radius_km=req.search_radius_km,
        simulate_hotspots=spikes or None,
        rain_active_zones=req.rain_active_zones,
        weekday=weekday,
    )

    return asdict(result)


# ══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)
