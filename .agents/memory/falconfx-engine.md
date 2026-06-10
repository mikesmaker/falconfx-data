---
name: FalconFX v4.0 Engine Decisions
description: Core algorithmic decisions for the FalconFX Booster Engine — Ghost Penalty, Cash Cow Guard, velocity threshold, mega-church waves, corporate arbitrage.
---

## Cash Cow Guard vs Ghost Penalty (v4.0)

The single most non-obvious architectural decision:

- `score >= 85 AND velocity < VELOCITY_TREND_STABLE_THRESHOLD (8.0)` → **Ghost Penalty**: 75% haircut. Zone is dying — mainstream sees it.
- `score >= 85 AND velocity >= 8.0` → **Cash Cow Guard**: NO haircut. Zone still printing money.

**Why:** Previously a flat threshold caused false positives — heavy downpours at Makola or mass church dismissals would hit score=100 while velocity was still rising (active rush). The 75% haircut was throttling exactly the zones riders should be locking onto.

**How to apply:** Always pass `velocity` to `_acceleration_band(score, velocity)`. The `acceleration_band_label(score, velocity)` method also requires velocity. Without it, defaults to 0.0 and all high-score zones incorrectly get ghost haircut.

Check: `ghost_penalty_applied = top_band.startswith("GHOST")` — NOT a raw score threshold.

## Mega-Church Event Zones (v4.0)

Four zones in `MEGACHURCH_EVENT_ZONES`:
1. Perez Dome — Dzorwulu (lat=5.602, lng=-0.186, capacity=14,000)
2. Action Chapel — Impact Arena Spintex (lat=5.627, lng=-0.103, capacity=30,000) — triggers Spintex gridlock advisory
3. ICGC Christ Temple — Abossey Okai (lat=5.556, lng=-0.227, capacity=8,000)
4. Black Star Square & Accra Sports Stadium (lat=5.548, lng=-0.196, capacity=40,000)

Independence Day events (March 6-7) are checked against the live system clock inside `_megachurch_event_boost`. They are NOT in the regular `windows` list — they use `independence_parade` / `independence_run` sub-keys.

Friday Night Vigil (Perez Dome, 22:00-01:00) uses `crosses_midnight=True` — check: `h_float >= h_start OR h_float < (h_end % 24)`.

## Corporate Arbitrage Router (v4.0)

Two activation windows:
- `LEGAL_PUSH_WINDOW = (10.0, 11.5)` → Flow A (Regulatory/Judicial)
- `PRE_COB_WINDOW = (15.5, 17.0)` → Flow A/B/C depending on zone
- `MINISTRIES_CUTOFF = 16.5` → Hard deadline skip inside pre-COB window

Three outbound flows (A=Regulatory/Judicial, B=International Cargo KIA, C=Upcountry/STC).

`corporate_time_penalty_min` returns gate+walk+lift overhead in minutes, used to discount expected GHS yield at cost of GHS 8/hr.

Sunday: Ministries District fully closed (`sunday_closed=True`). Airport City: Saturday 50% capacity.
