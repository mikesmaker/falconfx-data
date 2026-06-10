---
name: FalconFX Workspace Layout
description: File locations, workflow setup, API port, and booster.py section map for the FalconFX project.
---

## File Layout

All Python engine files live in the **workspace root**, not inside any artifact:
- `booster.py` — main engine (~2,350 lines after v4.0)
- `api.py` — FastAPI wrapper (port 8000, reads PORT env var)
- `booster-client.js` — JS frontend integration (BoosterClient + BoosterMapRenderer)
- `places.json` — 27,001 Accra POIs

`artifacts/api-server/` is a Node.js TypeScript API scaffold at path `/api` (port 8080). It is **unrelated** to the Python booster engine.

## Persistent Workflow

Name: `"FalconFX Booster API"`, command: `python3 api.py`, port: 8000, outputType: console.

## API Endpoint

`POST /booster/compute` — main endpoint. `GET /health` — health check.

## Verification

`python3 booster.py` runs 7 simulation scenarios. All 7 must pass. If any fail, there's a regression in the engine.

## booster.py Section Map

1=Constants, 2=DataStructures, 3=SpatialUtils, 4=GridEngine, 5=TrafficFriction, 6=DemandSimulator, 7=VelocityWaveEngine, 8=LeapfrogRouter, 9=ReturnTicketArbitrage, 9.5=CorporateArbitrageRouter (v4.0), 10=WaybillInterceptor, 11=MonsoonLayer, 12=PredictiveHoldSM, 13=AdaptivePoller, 14=BoosterEngine, 17=Simulation
