# api/server.py
"""
SynthicSoft Labs – AEGIS::NeuroSentinel API

Read-only HTTP access to events.ndjson for dashboards and SIEMs.
"""

from pathlib import Path
from typing import List, Optional

import json
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(
    title="SynthicSoft AEGIS::NeuroSentinel API",
    description="Read-only event API for custom dashboards and SIEM integration.",
    version="0.1.0",
)

# Allow local dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later for production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

EVENT_LOG = (
    Path(__file__).resolve().parents[1]
    / "agent"
    / "outputs"
    / "events.ndjson"
)


@app.get("/api/events/latest", response_class=JSONResponse)
def latest_events(
    limit: int = Query(100, ge=1, le=1000),
    min_severity: Optional[str] = Query(None, regex="^(info|low|medium|high|critical)$"),
):
    if not EVENT_LOG.exists():
        return {"events": []}

    lines = EVENT_LOG.read_text(encoding="utf-8").strip().split("\n")
    events: List[dict] = []

    def sev_rank(sev: str) -> int:
        order = ["info", "low", "medium", "high", "critical"]
        return order.index(sev) if sev in order else 0

    min_rank = sev_rank(min_severity) if min_severity else 0

    for line in lines[-limit:]:
        try:
            ev = json.loads(line)
            sev = ev.get("classification", {}).get("severity", "info")
            if sev_rank(sev) >= min_rank:
                events.append(ev)
        except json.JSONDecodeError:
            continue

    return {"events": events}


@app.get("/api/health", response_class=JSONResponse)
def health():
    return {"status": "ok", "component": "neuro-sentinel-api"}
