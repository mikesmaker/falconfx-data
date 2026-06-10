# FalconFX — Booster Engine v4.0

Predictive demand engine for a rider companion app in Accra, Ghana. Processes 27,001 OpenStreetMap POIs to predict high-demand pickup zones and outputs hot spot centroids + drift vectors for a floating mobile widget used alongside Yango/Bolt/Uber/Hubtel.

**PURE PREDICTION NOT REACTION paradigm.**

## Run & Operate

- `python3 api.py` — start FastAPI server (port 8000, auto-managed by "FalconFX Booster API" workflow)
- `python3 booster.py` — run the 7-scenario console simulation (verification)
- `pnpm --filter @workspace/api-server run dev` — Node.js scaffolding API server (port 8080, path `/api`)
- CDN data source: `https://cdn.jsdelivr.net/gh/mikesmaker/falconfx-data@main/places.json`

## Stack

- Pure Python 3.11 + FastAPI + uvicorn (booster engine + API)
- pnpm workspaces, Node.js 24, TypeScript (scaffolding/api-server artifact)
- Root-level files: `booster.py`, `api.py`, `booster-client.js`, `places.json`

## Where things live

- `booster.py` — main engine v4.0 (~2,350 lines). All intelligence lives here.
- `api.py` — FastAPI wrapper v3.0. Weekday threading, health endpoint.
- `booster-client.js` — JS frontend integration (BoosterClient + BoosterMapRenderer + 3 map adapters)
- `places.json` — 27,001 Accra POIs (OpenStreetMap)
- `booster_output_sample.json` — regenerated on each simulation run
- `artifacts/api-server/` — Node.js TypeScript API scaffold (not the Python booster)

## Architecture decisions

- **Ghost Penalty vs Cash Cow Guard (v4.0):** `score ≥ 85 AND velocity < 8.0` → 75% haircut (dying surge). `score ≥ 85 AND velocity ≥ 8.0` → NO haircut (sustained cash cow, still printing money).
- **VELOCITY_TREND_STABLE_THRESHOLD = 8.0** — the velocity above which a high-score zone is treated as active cash cow rather than fading ghost.
- **Mega-Church Waves:** 4 zones (Perez Dome, Action Chapel Impact Arena, ICGC Christ Temple, Black Star Square/Accra Sports Stadium) inject synchronized demand spikes on dismissal. Action Chapel triggers Spintex road gridlock advisory (70% speed penalty).
- **Corporate Arbitrage Router:** Two windows — Mid-Morning Legal Push (10:00-11:30) and Pre-COB Crunch (15:30-17:00). Ministries District cuts off at 16:30. Three outbound flows: A=Regulatory/Judicial, B=International Cargo KIA, C=Upcountry Domestic.
- **Corporate Landing Zone gate+walk+lift overhead** baked into net yield GHS calculation.
- **5-layer traffic friction:** Base + arterial + road surface + pedestrian congestion + event friction advisory.
- **Adaptive polling:** 8-120s interval based on ride state and demand velocity.
- **POST /booster/compute** — main API endpoint. Returns full BoosterOutput JSON with all alerts.

## Product

- Floating mobile widget alongside Yango/Bolt/Uber/Hubtel
- Predicts high-demand pickup zones 3-5 minutes before mainstream apps see them
- Outputs: primary drift vector (bearing + TTA + expected GHS yield), leapfrog vector, hotspot centroids with demand bands
- Alerts: return ticket arbitrage, waybill pipeline intercept, corporate landing zone arbitrage, monsoon dry-edge advisory, megachurch event waves
- Ghost/Cash Cow classification prevents riders entering dying surges

## User preferences

- GitHub username: mikesmaker
- GITHUB_TOKEN secret available for CDN data pushes

## Gotchas

- `python3 booster.py` runs all 7 simulation scenarios — if any fail, the engine has a regression.
- `places.json` must be in the workspace root (not in artifacts/) for `booster.py` and `api.py` to find it.
- The Node.js `artifacts/api-server` (path `/api`, port 8080) is a separate scaffold unrelated to the Python booster.
- `acceleration_band_label(score, velocity)` must receive velocity — without it the Cash Cow Guard defaults to 0.0 velocity (all high-score zones get ghost haircut).
- Independence Day events (March 6-7) in `MEGACHURCH_EVENT_ZONES` are checked against the live system clock in `_megachurch_event_boost`.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
- booster.py Section numbering: 1=Constants, 2=DataStructures, 3=SpatialUtils, 4=GridEngine, 5=TrafficFriction, 6=DemandSimulator, 7=VelocityWaveEngine, 8=LeapfrogRouter, 9=ReturnTicketArbitrage, 9.5=CorporateArbitrageRouter, 10=WaybillInterceptor, 11=MonsoonLayer, 12=PredictiveHoldSM, 13=AdaptivePoller, 14=BoosterEngine, 17=Simulation
