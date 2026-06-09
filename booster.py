"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  FalconFX — BOOSTER  |  Predictive Demand Engine  v1.0                     ║
║  Accra, Ghana  |  Companion Map Architecture                                ║
║                                                                              ║
║  Outputs: Hot Spot Centroids + Drift Vectors → floating mobile widget        ║
║  Does NOT assign drivers — feeds alongside Yango / Bolt / Uber / Hubtel      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import json
import math
import random
import time
import datetime
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — CONSTANTS & CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

EARTH_RADIUS_KM = 6371.0
GRID_RESOLUTION = 3          # decimal places → ~110m cell at Accra latitude
FUEL_COST_GHS_PER_KM = 1.80  # GHS per km (petrol equivalent for motorbike)
MIN_PROFIT_THRESHOLD = 4.00  # GHS — below this, HOLD is recommended
ACCRA_LAT_CENTRE = 5.60
ACCRA_LNG_CENTRE = -0.18

# ── Category demand weights (how likely a place type generates delivery orders)
CATEGORY_DEMAND_WEIGHT = {
    "food":       10,
    "market":      9,
    "mall":        8,
    "hospital":    6,
    "university":  5,
    "school":      4,
    "bank":        3,
    "hotel":       5,
    "leisure":     4,
    "transport":   7,
    "office":      4,
    "govt":        2,
    "church":      1,
    "fuel":        1,
    "police":      0,
    "area":        2,
    "other":       1,
}

# ── Kitchen prep buffers in minutes (category → min, max)
KITCHEN_PREP_BUFFER = {
    "food":    (12, 15),   # chop bars, local restaurants — cook-to-order
    "mall":    (3, 5),     # retail pick-pack
    "market":  (5, 8),     # market vendors assembling orders
    "hotel":   (10, 20),   # room service / F&B
    "other":   (2, 4),
}
INSTANT_CATEGORIES = {"hospital", "bank", "fuel", "transport", "university", "school", "office", "govt"}

# ── Known Accra traffic bottlenecks: (name, lat, lng, peak_hour_start, peak_hour_end, severity)
#    severity: 0-1 multiplier applied to speed degradation at peak hours
BOTTLENECKS = [
    ("Spintex Road",             5.620, -0.110, 7, 9,  0.55),
    ("Spintex Road (PM)",        5.620, -0.110, 16, 19, 0.50),
    ("Tetteh Quarshie",          5.650, -0.172, 7, 9,  0.65),
    ("Tetteh Quarshie (PM)",     5.650, -0.172, 16, 19, 0.60),
    ("Kwame Nkrumah Circle",     5.571, -0.222, 7, 19, 0.50),
    ("Kaneshie",                 5.560, -0.242, 7, 19, 0.55),
    ("Tema Motorway Toll",       5.620,  0.000, 7, 9,  0.60),
    ("37 Military Hospital Jct", 5.590, -0.188, 7, 19, 0.60),
    ("Achimota",                 5.639, -0.237, 7, 9,  0.58),
    ("Caprice/Labone",           5.572, -0.166, 17, 20, 0.65),
    ("Adenta Barrier",           5.696, -0.163, 7, 9,  0.50),
    ("Madina Market",            5.680, -0.168, 8, 18, 0.55),
]

# ── Low-density outskirt zones for Return Ticket Arbitrage
LOW_DENSITY_ZONES = [
    ("Adenta",   5.706, -0.163, 5.0),   # (name, lat, lng, radius_km)
    ("Kasoa",    5.534, -0.419, 4.0),
    ("Weija",    5.567, -0.321, 3.5),
    ("Dodowa",   5.884, -0.104, 4.0),
    ("Ashaiman", 5.698,  0.031, 3.5),
    ("Bortianor", 5.557, -0.323, 3.0),
    ("Oyibi",    5.770, -0.120, 3.0),
]

# ── Major transit hubs for Waybill Pipeline Interception
TRANSIT_HUBS = [
    ("Kaneshie Terminal",   5.557, -0.244, 6, 20),  # (name, lat, lng, active_from, active_to)
    ("Neoplan/Circle",      5.571, -0.222, 5, 22),
    ("Tema Station",        5.673,  0.013, 6, 21),
    ("37 Station",          5.590, -0.188, 6, 20),
    ("Madina Lorry Park",   5.682, -0.169, 6, 20),
    ("Accra Central (UTC)", 5.550, -0.205, 6, 20),
]

# ── Rain-impacted district polygons (approx centre + radius)
RAIN_FLOOD_ZONES = [
    ("Accra Central",  5.550, -0.206, 1.5),
    ("Lapaz",          5.609, -0.243, 1.2),
    ("Kaneshie Low",   5.556, -0.244, 1.0),
    ("Adabraka",       5.562, -0.212, 0.8),
    ("Nima",           5.589, -0.211, 1.0),
    ("Alajo",          5.591, -0.225, 0.9),
    ("Abossey Okai",   5.566, -0.231, 0.8),
]


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class GridCell:
    grid_lat: float
    grid_lng: float
    places: list  = field(default_factory=list)
    base_weight: float = 0.0
    demand_score: float = 0.0        # live demand signal
    surge_probability: float = 0.0   # 0-1
    checkout_eta_min: Optional[float] = None   # minutes until estimated checkout peak
    prep_buffer_min: float = 0.0
    is_hotspot: bool = False

    @property
    def centroid(self):
        return (self.grid_lat + 0.0005, self.grid_lng + 0.0005)  # cell centre

    def __repr__(self):
        return (f"GridCell({self.grid_lat},{self.grid_lng} | "
                f"score={self.demand_score:.1f} | surge={self.surge_probability:.2f})")


@dataclass
class RiderTelemetry:
    lat: float
    lng: float
    speed_kmh: float        # current speed
    heading_deg: float      # 0=N, 90=E, 180=S, 270=W
    has_active_delivery: bool = False
    dropoff_lat: Optional[float] = None
    dropoff_lng: Optional[float] = None
    fuel_level_pct: float = 100.0


@dataclass
class DriftVector:
    target_lat: float
    target_lng: float
    bearing_deg: float
    distance_km: float
    tta_min: float
    expected_yield_ghs: float
    confidence: float         # 0-1
    action: str               # "MOVE" | "HOLD" | "LEAPFROG" | "ARBITRAGE" | "WAYBILL"
    reason: str


@dataclass
class HotSpot:
    lat: float
    lng: float
    radius_km: float
    demand_score: float
    surge_probability: float
    checkout_eta_min: float
    category_mix: dict
    label: str


@dataclass
class BoosterOutput:
    timestamp: str
    rider: dict
    hold_recommended: bool
    hold_reason: str
    hotspots: list
    primary_vector: Optional[dict]
    leapfrog_vector: Optional[dict]
    arbitrage_alert: Optional[dict]
    waybill_alert: Optional[dict]
    weather_advisory: Optional[dict]
    grid_stats: dict


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — SPATIAL UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance in km."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlng/2)**2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1, lng1, lat2, lng2) -> float:
    """Initial bearing from point 1 → point 2 in degrees (0=N)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlng = math.radians(lng2 - lng1)
    x = math.sin(dlng) * math.cos(phi2)
    y = math.cos(phi1)*math.sin(phi2) - math.sin(phi1)*math.cos(phi2)*math.cos(dlng)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination_point(lat, lng, bearing_deg_val, distance_km):
    """Given start, bearing, distance — return destination lat/lng."""
    R = EARTH_RADIUS_KM
    d = distance_km / R
    b = math.radians(bearing_deg_val)
    phi1 = math.radians(lat)
    lam1 = math.radians(lng)
    phi2 = math.asin(math.sin(phi1)*math.cos(d) + math.cos(phi1)*math.sin(d)*math.cos(b))
    lam2 = lam1 + math.atan2(math.sin(b)*math.sin(d)*math.cos(phi1),
                              math.cos(d) - math.sin(phi1)*math.sin(phi2))
    return math.degrees(phi2), math.degrees(lam2)


def grid_key(lat, lng) -> tuple:
    return (round(lat, GRID_RESOLUTION), round(lng, GRID_RESOLUTION))


def compass_label(deg) -> str:
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
            "S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return dirs[round(deg / 22.5) % 16]


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — GRID ENGINE  (builds spatial index from places.json)
# ══════════════════════════════════════════════════════════════════════════════

class GridEngine:
    def __init__(self, places_path: str = "places.json"):
        self.cells: dict[tuple, GridCell] = {}
        self._load(places_path)

    def _load(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            places = json.load(f)

        for p in places:
            lat, lng = p["lat"], p["lng"]
            key = grid_key(lat, lng)
            if key not in self.cells:
                self.cells[key] = GridCell(grid_lat=key[0], grid_lng=key[1])
            cell = self.cells[key]
            cell.places.append(p)
            cell.base_weight += CATEGORY_DEMAND_WEIGHT.get(p.get("cat","other"), 1)

        # Normalise base weights 0-100
        if self.cells:
            max_w = max(c.base_weight for c in self.cells.values()) or 1
            for c in self.cells.values():
                c.base_weight = (c.base_weight / max_w) * 100

        print(f"  [GridEngine] Indexed {len(places):,} places → {len(self.cells):,} grid cells")

    def get_cell(self, lat, lng) -> Optional[GridCell]:
        return self.cells.get(grid_key(lat, lng))

    def nearby_cells(self, lat, lng, radius_km: float) -> list[GridCell]:
        """Return cells within radius_km of a point."""
        results = []
        # approx degree span
        dlat = radius_km / 111.0
        dlng = radius_km / (111.0 * math.cos(math.radians(lat)))
        for (glat, glng), cell in self.cells.items():
            if abs(glat - lat) <= dlat and abs(glng - lng) <= dlng:
                if haversine_km(lat, lng, glat, glng) <= radius_km:
                    results.append(cell)
        return results


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — TRAFFIC FRICTION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class TrafficFriction:
    def __init__(self):
        self.bottlenecks = BOTTLENECKS

    def speed_multiplier(self, lat: float, lng: float, hour: int) -> float:
        """
        Returns a multiplier 0.2-1.0.
        1.0 = free flow, 0.2 = gridlock.
        Factors: proximity to bottlenecks + time of day alignment.
        """
        multiplier = 1.0
        for name, blat, blng, h_start, h_end, severity in self.bottlenecks:
            dist = haversine_km(lat, lng, blat, blng)
            if dist > 3.0:
                continue
            # Proximity decay: full impact within 500m, none beyond 3km
            proximity_factor = max(0.0, 1.0 - (dist / 3.0))
            # Time-of-day factor
            in_peak = h_start <= hour < h_end
            time_factor = 1.0 if in_peak else 0.25
            impact = severity * proximity_factor * time_factor
            multiplier = max(0.2, multiplier - impact)
        return multiplier

    def effective_speed(self, rider: RiderTelemetry, hour: int) -> float:
        """Rider's effective km/h after friction."""
        base = max(rider.speed_kmh, 15.0)  # minimum 15 km/h for routing
        return base * self.speed_multiplier(rider.lat, rider.lng, hour)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — DEMAND SIMULATOR  (pre-checkout flash trigger)
# ══════════════════════════════════════════════════════════════════════════════

class DemandSimulator:
    """
    Simulates early-warning demand signals:
      - Cart footprint spikes
      - Restaurant app traffic surges
      - Historical time-of-day demand curve
    Injects these onto the grid cells as demand_score and checkout_eta.
    """

    # Time-of-day demand multipliers (hour → multiplier)
    HOUR_CURVE = {
        6: 0.4, 7: 0.6, 8: 0.8, 9: 0.7, 10: 0.6,
        11: 0.9, 12: 1.3, 13: 1.4, 14: 1.0, 15: 0.8,
        16: 0.9, 17: 1.2, 18: 1.5, 19: 1.6, 20: 1.3,
        21: 1.0, 22: 0.7, 23: 0.4,
    }

    def __init__(self, grid: GridEngine, seed: int = None):
        self.grid = grid
        if seed is not None:
            random.seed(seed)

    def _time_multiplier(self, hour: int) -> float:
        return self.HOUR_CURVE.get(hour, 0.3)

    def _prep_buffer(self, cell: GridCell) -> float:
        """Choose longest applicable prep buffer from cell's category mix."""
        cats = {p.get("cat","other") for p in cell.places}
        max_buf = 0.0
        for cat in cats:
            if cat in INSTANT_CATEGORIES:
                continue
            lo, hi = KITCHEN_PREP_BUFFER.get(cat, (2, 4))
            max_buf = max(max_buf, random.uniform(lo, hi))
        return max_buf

    def inject_signals(self, hour: int, simulate_hotspots: list[tuple] = None):
        """
        Compute demand_score for every cell.
        Optional simulate_hotspots: [(lat, lng, intensity)] for testing.
        """
        time_mult = self._time_multiplier(hour)

        # Base scoring pass
        for cell in self.grid.cells.values():
            noise = random.uniform(0.7, 1.3)
            cell.demand_score = cell.base_weight * time_mult * noise
            cell.prep_buffer_min = self._prep_buffer(cell)
            cell.surge_probability = min(1.0, cell.demand_score / 100.0)
            cell.is_hotspot = False
            cell.checkout_eta_min = None

        # Inject synthetic signal spikes (simulates cart/API data)
        if simulate_hotspots:
            for slat, slng, intensity in simulate_hotspots:
                nearby = self.grid.nearby_cells(slat, slng, 0.5)
                for cell in nearby:
                    dist = haversine_km(slat, slng, cell.grid_lat, cell.grid_lng)
                    boost = intensity * max(0.0, 1.0 - dist / 0.5)
                    cell.demand_score = min(100, cell.demand_score + boost)
                    cell.surge_probability = min(1.0, cell.demand_score / 100.0)

        # Mark hotspots (top 5% by demand score)
        scores = sorted(c.demand_score for c in self.grid.cells.values())
        if scores:
            threshold = scores[int(len(scores) * 0.95)]
            for cell in self.grid.cells.values():
                if cell.demand_score >= threshold:
                    cell.is_hotspot = True
                    # Checkout ETA = prep buffer + small random pre-checkout window
                    cell.checkout_eta_min = cell.prep_buffer_min + random.uniform(2, 5)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — RIDER VELOCITY WAVE ENGINE  (TTA + Drift Vector computation)
# ══════════════════════════════════════════════════════════════════════════════

class VelocityWaveEngine:
    def __init__(self, friction: TrafficFriction):
        self.friction = friction

    def compute_tta(self, rider: RiderTelemetry, target_lat: float,
                    target_lng: float, hour: int) -> float:
        """Time to arrival in minutes accounting for traffic friction."""
        dist_km = haversine_km(rider.lat, rider.lng, target_lat, target_lng)
        eff_speed = self.friction.effective_speed(rider, hour)
        return (dist_km / eff_speed) * 60.0 if eff_speed > 0 else 9999.0

    def intercept_score(self, rider: RiderTelemetry, cell: GridCell,
                        hour: int) -> float:
        """
        Score how well the rider can intercept the cell's demand wave.
        High score = rider arrives ≈ checkout_eta_min → maximum intercept value.
        """
        if cell.checkout_eta_min is None:
            return 0.0
        tta = self.compute_tta(rider, cell.grid_lat, cell.grid_lng, hour)
        # Perfect arrival = tta matches checkout_eta exactly. Decay on either side.
        delta = abs(tta - cell.checkout_eta_min)
        timing_score = math.exp(-0.1 * delta)    # Gaussian decay on timing error
        return cell.demand_score * cell.surge_probability * timing_score

    def rank_cells(self, rider: RiderTelemetry, cells: list[GridCell],
                   hour: int, top_n: int = 5) -> list[tuple]:
        """Returns list of (score, cell) sorted descending."""
        scored = []
        for cell in cells:
            s = self.intercept_score(rider, cell, hour)
            if s > 0:
                scored.append((s, cell))
        scored.sort(key=lambda x: -x[0])
        return scored[:top_n]


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — LEAPFROG SEQUENTIAL ROUTER
# ══════════════════════════════════════════════════════════════════════════════

class LeapfrogRouter:
    """
    While rider is delivering, pre-cache the best next pickup zone
    concentrated around the drop-off destination.
    """

    def __init__(self, grid: GridEngine, wave: VelocityWaveEngine,
                 friction: TrafficFriction):
        self.grid = grid
        self.wave = wave
        self.friction = friction

    def next_zone(self, rider: RiderTelemetry, hour: int,
                  search_radius_km: float = 2.0) -> Optional[DriftVector]:
        if not rider.has_active_delivery or rider.dropoff_lat is None:
            return None

        nearby = self.grid.nearby_cells(rider.dropoff_lat, rider.dropoff_lng,
                                         search_radius_km)
        hotspots = [c for c in nearby if c.is_hotspot]
        if not hotspots:
            return None

        ranked = self.wave.rank_cells(rider, hotspots, hour, top_n=1)
        if not ranked:
            return None

        score, best = ranked[0]
        dist = haversine_km(rider.dropoff_lat, rider.dropoff_lng,
                            best.grid_lat, best.grid_lng)
        bear = bearing_deg(rider.dropoff_lat, rider.dropoff_lng,
                           best.grid_lat, best.grid_lng)
        tta = self.wave.compute_tta(rider, best.grid_lat, best.grid_lng, hour)
        fuel = dist * FUEL_COST_GHS_PER_KM
        expected = score * 0.08  # convert demand score → GHS estimate

        return DriftVector(
            target_lat=best.grid_lat,
            target_lng=best.grid_lng,
            bearing_deg=bear,
            distance_km=round(dist, 2),
            tta_min=round(tta, 1),
            expected_yield_ghs=round(expected, 2),
            confidence=round(min(0.95, score / 100.0), 2),
            action="LEAPFROG",
            reason=(f"Pre-cached next pickup zone {dist:.1f}km from your drop-off. "
                    f"ETA after delivery: {tta:.0f}min. Surge in ~{best.checkout_eta_min:.0f}min.")
        )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — RETURN TICKET ARBITRAGE
# ══════════════════════════════════════════════════════════════════════════════

class ReturnTicketArbitrage:
    """
    Detects when a rider is heading toward a low-density outskirt zone
    and pre-locks B2B / wholesale return runs from that perimeter.
    """

    def __init__(self, grid: GridEngine, wave: VelocityWaveEngine):
        self.grid = grid
        self.wave = wave

    def check(self, rider: RiderTelemetry, hour: int) -> Optional[dict]:
        if not rider.has_active_delivery or rider.dropoff_lat is None:
            return None

        for zone_name, zlat, zlng, radius_km in LOW_DENSITY_ZONES:
            dist_to_zone = haversine_km(rider.dropoff_lat, rider.dropoff_lng,
                                        zlat, zlng)
            if dist_to_zone > radius_km:
                continue

            # Rider is heading into a low-density zone → scan B2B clusters
            # Search inside zone for any high-weight commercial cells
            nearby = self.grid.nearby_cells(zlat, zlng, radius_km)
            commercial = [c for c in nearby
                          if any(p.get("cat") in ("market","mall","office","transport")
                                 for p in c.places)]
            if not commercial:
                continue

            best = max(commercial, key=lambda c: c.base_weight)
            return {
                "zone": zone_name,
                "alert": "RETURN_TICKET_ARBITRAGE",
                "message": (f"Drop-off is in {zone_name} — low-density outskirt. "
                            f"Pre-lock B2B/wholesale return run from "
                            f"{best.grid_lat:.4f},{best.grid_lng:.4f} "
                            f"(base demand weight {best.base_weight:.0f})."),
                "pickup_lat": best.grid_lat,
                "pickup_lng": best.grid_lng,
                "minutes_to_lock": 30,
            }
        return None


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — WAYBILL PIPELINE INTERCEPTOR
# ══════════════════════════════════════════════════════════════════════════════

class WaybillInterceptor:
    """
    Maps fixed arrival patterns of inter-city buses / trotros into transit hubs.
    Triggers Booster Cluster alerts when buses are expected to arrive.
    """

    # Simulated arrival windows: buses arrive every 25-40 min during active hours
    ARRIVAL_INTERVAL_MIN = 30

    def check(self, rider: RiderTelemetry, hour: int, minute: int) -> Optional[dict]:
        best_hub = None
        best_dist = 999.0

        for hub_name, hlat, hlng, h_start, h_end in TRANSIT_HUBS:
            if not (h_start <= hour < h_end):
                continue
            dist = haversine_km(rider.lat, rider.lng, hlat, hlng)
            if dist < best_dist:
                best_dist = dist
                best_hub = (hub_name, hlat, hlng, dist)

        if best_hub is None or best_dist > 8.0:
            return None

        hub_name, hlat, hlng, dist = best_hub
        # Next bus arrival window (deterministic modulo simulation)
        mins_since_interval = minute % self.ARRIVAL_INTERVAL_MIN
        next_arrival_min = self.ARRIVAL_INTERVAL_MIN - mins_since_interval

        if next_arrival_min > 15:
            return None  # Too far out to recommend intercept now

        bear = bearing_deg(rider.lat, rider.lng, hlat, hlng)
        return {
            "alert": "WAYBILL_INTERCEPT",
            "hub": hub_name,
            "hub_lat": hlat,
            "hub_lng": hlng,
            "distance_km": round(dist, 2),
            "bearing_deg": round(bear, 1),
            "next_arrival_min": next_arrival_min,
            "message": (f"Inter-city bus arriving at {hub_name} in ~{next_arrival_min}min. "
                        f"Hub is {dist:.1f}km {compass_label(bear)}. "
                        f"Position for wholesale multi-package waybill run."),
        }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — MONSOON MICRO-CLIMATE MULTIPLIER
# ══════════════════════════════════════════════════════════════════════════════

class MonsoonLayer:
    """
    When rain paralyses a district, demand explodes in nearby dry zones.
    Computes the 'dry edge' boundary and nudges rider toward it.
    """

    def __init__(self, grid: GridEngine):
        self.grid = grid

    def apply(self, rider: RiderTelemetry, rain_active_zones: list[str],
              hour: int) -> Optional[dict]:
        if not rain_active_zones:
            return None

        # Boost demand in dry neighbouring cells
        flooded_centres = [(zlat, zlng, zrad)
                           for zname, zlat, zlng, zrad in RAIN_FLOOD_ZONES
                           if zname in rain_active_zones]
        if not flooded_centres:
            return None

        # Find 'dry edge': cells just outside flooded zones with high demand
        dry_edge_cells = []
        for zlat, zlng, zrad in flooded_centres:
            outer_cells = self.grid.nearby_cells(zlat, zlng, zrad + 1.5)
            inner_keys  = {grid_key(c.grid_lat, c.grid_lng)
                           for c in self.grid.nearby_cells(zlat, zlng, zrad)}
            for cell in outer_cells:
                if grid_key(cell.grid_lat, cell.grid_lng) not in inner_keys:
                    # Apply rain-demand multiplier: 2x on dry edge
                    cell.demand_score = min(100, cell.demand_score * 2.0)
                    cell.surge_probability = min(1.0, cell.surge_probability * 2.0)
                    dry_edge_cells.append(cell)

        if not dry_edge_cells:
            return None

        best = max(dry_edge_cells, key=lambda c: c.demand_score)
        dist = haversine_km(rider.lat, rider.lng, best.grid_lat, best.grid_lng)
        bear = bearing_deg(rider.lat, rider.lng, best.grid_lat, best.grid_lng)

        return {
            "alert": "MONSOON_DRY_EDGE",
            "flooded_zones": rain_active_zones,
            "dry_edge_lat": best.grid_lat,
            "dry_edge_lng": best.grid_lng,
            "distance_km": round(dist, 2),
            "bearing_deg": round(bear, 1),
            "demand_score": round(best.demand_score, 1),
            "message": (f"Rain blocking {', '.join(rain_active_zones)}. "
                        f"Courier deficit spiking at dry edge "
                        f"{dist:.1f}km {compass_label(bear)}. "
                        f"Move there NOW — demand multiplier 2x."),
        }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12 — PREDICTIVE HOLD STATE MACHINE
# ══════════════════════════════════════════════════════════════════════════════

class PredictiveHoldSM:
    """
    Determines if fuel cost of moving outweighs intercept probability.
    States: MOVE | HOLD | CHARGE (low fuel)
    """

    def evaluate(self, rider: RiderTelemetry, primary_vector: Optional[DriftVector],
                 hour: int) -> tuple[bool, str]:
        if rider.fuel_level_pct < 15:
            return True, "CHARGE — fuel critically low (<15%). Locate nearest fuel station."

        if primary_vector is None:
            return True, ("HOLD — no high-confidence surge detected in your radius. "
                          "Save fuel. Stand by.")

        fuel_cost = primary_vector.distance_km * FUEL_COST_GHS_PER_KM
        net_yield  = primary_vector.expected_yield_ghs - fuel_cost

        if net_yield < MIN_PROFIT_THRESHOLD:
            return True, (f"HOLD — projected net yield GHS {net_yield:.2f} after fuel is below "
                          f"threshold GHS {MIN_PROFIT_THRESHOLD:.2f}. Wait for stronger surge.")

        if primary_vector.confidence < 0.30:
            return True, (f"HOLD — surge confidence {primary_vector.confidence:.0%} too low. "
                          f"Insufficient pre-checkout signal. Stand by.")

        # Night-time quiet period
        if 23 <= hour or hour < 5:
            if primary_vector.demand_score if hasattr(primary_vector, 'demand_score') else 0 < 40:
                return True, "HOLD — low overnight demand. Rest until 05:00."

        return False, ""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 13 — BOOSTER ENGINE  (main orchestrator)
# ══════════════════════════════════════════════════════════════════════════════

class BoosterEngine:
    def __init__(self, places_path: str = "places.json"):
        print("\n  Initialising FalconFX Booster Engine...")
        self.grid      = GridEngine(places_path)
        self.friction  = TrafficFriction()
        self.demand    = DemandSimulator(self.grid)
        self.wave      = VelocityWaveEngine(self.friction)
        self.leapfrog  = LeapfrogRouter(self.grid, self.wave, self.friction)
        self.arbitrage = ReturnTicketArbitrage(self.grid, self.wave)
        self.waybill   = WaybillInterceptor()
        self.monsoon   = MonsoonLayer(self.grid)
        self.hold_sm   = PredictiveHoldSM()
        print("  Engine ready.\n")

    def compute(self,
                rider: RiderTelemetry,
                hour: int,
                minute: int = 0,
                search_radius_km: float = 5.0,
                simulate_hotspots: list = None,
                rain_active_zones: list = None) -> BoosterOutput:

        ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        # ── 1. Inject demand signals onto grid
        self.demand.inject_signals(hour, simulate_hotspots=simulate_hotspots)

        # ── 2. Pull candidate hotspot cells within rider's search radius
        nearby = self.grid.nearby_cells(rider.lat, rider.lng, search_radius_km)
        hotspot_cells = [c for c in nearby if c.is_hotspot]

        # ── 3. Rank by intercept score
        ranked = self.wave.rank_cells(rider, hotspot_cells, hour, top_n=5)

        # ── 4. Build primary drift vector from top-ranked cell
        primary_vector = None
        if ranked:
            top_score, top_cell = ranked[0]
            dist = haversine_km(rider.lat, rider.lng,
                                top_cell.grid_lat, top_cell.grid_lng)
            bear = bearing_deg(rider.lat, rider.lng,
                               top_cell.grid_lat, top_cell.grid_lng)
            tta  = self.wave.compute_tta(rider, top_cell.grid_lat,
                                         top_cell.grid_lng, hour)
            friction_mult = self.friction.speed_multiplier(rider.lat, rider.lng, hour)
            expected_ghs  = top_score * 0.08

            primary_vector = DriftVector(
                target_lat=top_cell.grid_lat,
                target_lng=top_cell.grid_lng,
                bearing_deg=round(bear, 1),
                distance_km=round(dist, 2),
                tta_min=round(tta, 1),
                expected_yield_ghs=round(expected_ghs, 2),
                confidence=round(min(0.99, top_score / 100.0), 2),
                action="MOVE",
                reason=(f"Surge wave peaking in {top_cell.checkout_eta_min:.0f}min at "
                        f"{top_cell.grid_lat:.4f},{top_cell.grid_lng:.4f}. "
                        f"Head {compass_label(bear)} — arrive in {tta:.0f}min. "
                        f"Traffic friction: {(1-friction_mult)*100:.0f}% degradation.")
            )

        # ── 5. Hold state machine
        hold, hold_reason = self.hold_sm.evaluate(rider, primary_vector, hour)

        # ── 6. Build hotspot summary objects
        hotspots_out = []
        for score, cell in ranked[:3]:
            cat_counter = defaultdict(int)
            for p in cell.places:
                cat_counter[p.get("cat","other")] += 1
            hotspots_out.append(HotSpot(
                lat=cell.grid_lat,
                lng=cell.grid_lng,
                radius_km=0.11,
                demand_score=round(cell.demand_score, 1),
                surge_probability=round(cell.surge_probability, 2),
                checkout_eta_min=round(cell.checkout_eta_min or 0, 1),
                category_mix=dict(cat_counter),
                label=", ".join(p["name"] for p in cell.places[:2]) or "Unnamed cluster",
            ))

        # ── 7. Leapfrog routing
        leapfrog_vector = self.leapfrog.next_zone(rider, hour)

        # ── 8. Return ticket arbitrage
        arb_alert = self.arbitrage.check(rider, hour)

        # ── 9. Waybill intercept
        waybill_alert = self.waybill.check(rider, hour, minute)

        # ── 10. Monsoon layer
        weather_advisory = self.monsoon.apply(rider, rain_active_zones or [], hour)

        # ── 11. Grid stats
        active_cells   = [c for c in nearby if c.demand_score > 0]
        avg_score      = (sum(c.demand_score for c in active_cells) / len(active_cells)
                          if active_cells else 0)
        friction_here  = self.friction.speed_multiplier(rider.lat, rider.lng, hour)

        grid_stats = {
            "cells_scanned": len(nearby),
            "hotspot_cells": len(hotspot_cells),
            "avg_demand_score": round(avg_score, 1),
            "traffic_friction_at_rider": round(friction_here, 2),
            "effective_speed_kmh": round(self.friction.effective_speed(rider, hour), 1),
        }

        return BoosterOutput(
            timestamp=ts,
            rider=asdict(rider),
            hold_recommended=hold,
            hold_reason=hold_reason,
            hotspots=[asdict(h) for h in hotspots_out],
            primary_vector=asdict(primary_vector) if primary_vector else None,
            leapfrog_vector=asdict(leapfrog_vector) if leapfrog_vector else None,
            arbitrage_alert=arb_alert,
            waybill_alert=waybill_alert,
            weather_advisory=weather_advisory,
            grid_stats=grid_stats,
        )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 14 — CONSOLE SIMULATION DEMO
# ══════════════════════════════════════════════════════════════════════════════

def _divider(char="═", width=72): print(char * width)
def _title(t): _divider(); print(f"  {t}"); _divider()
def _section(t): print(f"\n  ── {t} " + "─"*(65-len(t)))

def _print_vector(label, v):
    if not v: print(f"    {label}: none"); return
    print(f"    {label}:")
    print(f"      Action     : {v['action']}")
    print(f"      Target     : {v['target_lat']:.4f}, {v['target_lng']:.4f}")
    print(f"      Bearing    : {v['bearing_deg']:.1f}° ({compass_label(v['bearing_deg'])})")
    print(f"      Distance   : {v['distance_km']} km")
    print(f"      TTA        : {v['tta_min']} min")
    print(f"      Yield Est  : GHS {v['expected_yield_ghs']:.2f}")
    print(f"      Confidence : {v['confidence']:.0%}")
    print(f"      Reason     : {v['reason']}")

def run_simulation():
    _title("FalconFX BOOSTER — Predictive Demand Engine  |  Console Simulation")

    # ── Initialise engine
    engine = BoosterEngine("places.json")

    # ── Scenario 1: Active rider near Osu/Airport area, evening peak
    print("  SCENARIO 1 — Active rider, evening peak, heading toward Osu cluster")
    print("  Rider: near Airport Residential, speed 28 km/h, heading SE")
    print("  Time:  18:12 (peak dinner hour)")
    _divider("─")

    rider1 = RiderTelemetry(
        lat=5.605,
        lng=-0.173,
        speed_kmh=28,
        heading_deg=135,      # SE
        has_active_delivery=False,
        fuel_level_pct=78,
    )

    # Synthetic pre-checkout signal spikes (simulating cart surges from Bolt/Yango)
    signal_spikes = [
        (5.570, -0.170, 65),   # Osu food cluster
        (5.560, -0.205, 55),   # Accra Central markets
        (5.617, -0.172, 45),   # Airport commercial strip
    ]

    out1 = engine.compute(
        rider=rider1,
        hour=18,
        minute=12,
        search_radius_km=5.0,
        simulate_hotspots=signal_spikes,
        rain_active_zones=[],
    )

    _section("RIDER STATE")
    print(f"    Position   : {rider1.lat}°N, {rider1.lng}°E")
    print(f"    Speed      : {rider1.speed_kmh} km/h  |  Heading: {rider1.heading_deg}° {compass_label(rider1.heading_deg)}")
    print(f"    Fuel       : {rider1.fuel_level_pct}%")

    _section("GRID REPORT")
    g = out1.grid_stats
    print(f"    Cells scanned      : {g['cells_scanned']}")
    print(f"    Hotspot cells      : {g['hotspot_cells']}")
    print(f"    Avg demand score   : {g['avg_demand_score']}")
    print(f"    Traffic friction   : {g['traffic_friction_at_rider']:.0%} speed retained")
    print(f"    Effective speed    : {g['effective_speed_kmh']} km/h")

    _section("HOT SPOT CENTROIDS")
    for i, hs in enumerate(out1.hotspots, 1):
        print(f"    [{i}] {hs['lat']:.4f},{hs['lng']:.4f}  "
              f"score={hs['demand_score']:.1f}  "
              f"surge={hs['surge_probability']:.0%}  "
              f"checkout in ~{hs['checkout_eta_min']}min")
        print(f"        {hs['label']}")
        cats = ", ".join(f"{v}x {k}" for k,v in sorted(hs['category_mix'].items(), key=lambda x:-x[1])[:3])
        print(f"        [{cats}]")

    _section("HOLD STATE MACHINE")
    status = "🛑 HOLD" if out1.hold_recommended else "✅ MOVE"
    print(f"    Recommendation: {status}")
    if out1.hold_reason:
        print(f"    Reason: {out1.hold_reason}")

    _section("PRIMARY DRIFT VECTOR")
    _print_vector("Primary", out1.primary_vector)

    _section("LEAPFROG VECTOR")
    print("    (No active delivery — leapfrog not applicable)")

    _section("WAYBILL INTERCEPT")
    if out1.waybill_alert:
        print(f"    ⚡ {out1.waybill_alert['message']}")
    else:
        print("    No imminent bus arrivals within intercept window.")

    _section("WEATHER ADVISORY")
    if out1.weather_advisory:
        print(f"    🌧  {out1.weather_advisory['message']}")
    else:
        print("    Clear conditions — no rain displacement active.")

    # ── Scenario 2: Rider on active delivery heading to Adenta (outskirt), waybill window
    print("\n\n")
    _title("SCENARIO 2 — Rider on delivery to Adenta + Rain in Central + Waybill Alert")
    print("  Rider: near Madina, en route to Adenta drop-off, speed 38 km/h")
    print("  Time:  07:22 (morning peak, Kaneshie buses arriving)")
    _divider("─")

    rider2 = RiderTelemetry(
        lat=5.680,
        lng=-0.168,
        speed_kmh=38,
        heading_deg=10,        # NNE toward Adenta
        has_active_delivery=True,
        dropoff_lat=5.706,
        dropoff_lng=-0.163,
        fuel_level_pct=55,
    )

    out2 = engine.compute(
        rider=rider2,
        hour=7,
        minute=22,
        search_radius_km=6.0,
        simulate_hotspots=[
            (5.706, -0.160, 30),   # Adenta wholesale signal
            (5.557, -0.244, 70),   # Kaneshie spike (waybill)
        ],
        rain_active_zones=["Accra Central", "Kaneshie Low", "Adabraka"],
    )

    _section("RIDER STATE")
    print(f"    Position   : {rider2.lat}°N, {rider2.lng}°E")
    print(f"    Delivering : YES  → Drop-off at {rider2.dropoff_lat},{rider2.dropoff_lng} (Adenta)")
    print(f"    Speed      : {rider2.speed_kmh} km/h  |  Heading: {rider2.heading_deg}° {compass_label(rider2.heading_deg)}")
    print(f"    Fuel       : {rider2.fuel_level_pct}%")

    _section("GRID REPORT")
    g2 = out2.grid_stats
    print(f"    Cells scanned      : {g2['cells_scanned']}")
    print(f"    Hotspot cells      : {g2['hotspot_cells']}")
    print(f"    Traffic friction   : {g2['traffic_friction_at_rider']:.0%} speed retained")
    print(f"    Effective speed    : {g2['effective_speed_kmh']} km/h")

    _section("HOLD STATE MACHINE")
    status2 = "🛑 HOLD" if out2.hold_recommended else "✅ MOVE"
    print(f"    Recommendation: {status2}")
    if out2.hold_reason:
        print(f"    Reason: {out2.hold_reason}")

    _section("PRIMARY DRIFT VECTOR")
    _print_vector("Primary", out2.primary_vector)

    _section("LEAPFROG — Post Drop-off Pre-cache")
    _print_vector("Leapfrog", out2.leapfrog_vector)

    _section("RETURN TICKET ARBITRAGE")
    if out2.arbitrage_alert:
        print(f"    📦 {out2.arbitrage_alert['message']}")
    else:
        print("    No arbitrage opportunity detected.")

    _section("WAYBILL INTERCEPT")
    if out2.waybill_alert:
        print(f"    ⚡ {out2.waybill_alert['message']}")
    else:
        print("    No waybill window active.")

    _section("MONSOON DRY-EDGE ADVISORY")
    if out2.weather_advisory:
        wa = out2.weather_advisory
        print(f"    🌧  {wa['message']}")
    else:
        print("    No rain displacement.")

    # ── Scenario 3: Predictive Hold demo (low demand, not worth moving)
    print("\n\n")
    _title("SCENARIO 3 — Predictive HOLD: fuel cost > expected yield")
    print("  Rider: Tema outskirts, 14:30, low inter-peak demand")
    _divider("─")

    rider3 = RiderTelemetry(
        lat=5.673,
        lng=0.013,
        speed_kmh=5,
        heading_deg=270,
        has_active_delivery=False,
        fuel_level_pct=42,
    )

    out3 = engine.compute(
        rider=rider3,
        hour=14,
        minute=30,
        search_radius_km=4.0,
        simulate_hotspots=[],   # no injected spikes
        rain_active_zones=[],
    )

    g3 = out3.grid_stats
    _section("GRID REPORT")
    print(f"    Cells scanned    : {g3['cells_scanned']}")
    print(f"    Hotspot cells    : {g3['hotspot_cells']}")
    print(f"    Avg demand score : {g3['avg_demand_score']}")

    _section("HOLD STATE MACHINE")
    status3 = "🛑 HOLD" if out3.hold_recommended else "✅ MOVE"
    print(f"    Recommendation: {status3}")
    if out3.hold_reason:
        print(f"    Reason: {out3.hold_reason}")

    if out3.primary_vector:
        _section("PRIMARY DRIFT VECTOR (low confidence)")
        _print_vector("Primary", out3.primary_vector)

    _divider()
    print(f"  Simulation complete.  Timestamp: {out1.timestamp}")
    print(f"  Output schema is JSON-serialisable — pipe to mobile widget or notification layer.")
    _divider()

    # Export one full JSON output for inspection
    with open("booster_output_sample.json", "w") as f:
        json.dump(asdict(out1), f, indent=2, default=str)
    print(f"\n  Sample JSON output saved → booster_output_sample.json")
    print()


if __name__ == "__main__":
    run_simulation()
