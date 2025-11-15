#!/usr/bin/env python3
# agent/neuro_sentinel.py
"""
SynthicSoft Labs – AEGIS::NeuroSentinel
Cross-platform neural SOC agent, sentinel, and watchdog.

- Collects system telemetry (CPU, RAM, processes, network)
- Scores anomalies via NeuroAnomalyModel
- Emits JSON events for dashboards and SIEMs (NDJSON file)
- Fully self-contained; no cloud calls required

Brand:
- SynthicSoft Cyan: #19E3C8
- Midnight Base:    #0F172A
- Steel Slate:      #1E293B
"""

import argparse
import json
import os
import platform
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import psutil
import yaml

from model import NeuroAnomalyModel

# SynthicSoft Alert Palette (CLI)
C_CRIT = "\033[38;2;220;38;38m"
C_HIGH = "\033[38;2;234;88;12m"
C_MED = "\033[38;2;245;158;11m"
C_LOW = "\033[38;2;59;130;246m"
C_ACC = "\033[38;2;25;227;200m"
C_RST = "\033[0m"

BANNER = f"""
{C_ACC}┌─────────────────────────────────────────────────────────────────────┐
│  SynthicSoft Labs // AEGIS::NeuroSentinel                             │
│  Cross-Platform Neural SOC Agent / Sentinel / Watchdog                │
│  Local-First · Autonomous · SIEM-Ready                                │
└─────────────────────────────────────────────────────────────────────┘{C_RST}
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config(cfg_path: Path) -> Dict[str, Any]:
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def collect_snapshot() -> Dict[str, Any]:
    """
    Collect a single telemetry snapshot.
    SOC-focused: high-level behavioral fingerprint.
    """
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().percent
    procs = list(psutil.process_iter(["pid", "name", "exe"]))
    net = psutil.net_connections()

    process_names = [p.info.get("name") or "" for p in procs]

    return {
        "timestamp": now_iso(),
        "cpu_percent": cpu,
        "ram_percent": ram,
        "process_count": len(procs),
        "net_connection_count": len(net),
        "top_processes": sorted(process_names)[:15],
    }


def score_to_severity(score: float, thresholds: Dict[str, float]) -> str:
    if score >= thresholds.get("critical", 0.85):
        return "critical"
    if score >= thresholds.get("high", 0.70):
        return "high"
    if score >= thresholds.get("medium", 0.50):
        return "medium"
    if score >= thresholds.get("low", 0.30):
        return "low"
    return "info"


def severity_color(sev: str) -> str:
    return {
        "critical": C_CRIT,
        "high": C_HIGH,
        "medium": C_MED,
        "low": C_LOW,
        "info": C_ACC,
    }.get(sev, C_ACC)


def severity_rank(sev: str) -> int:
    # Lower number = less severe
    order = ["info", "low", "medium", "high", "critical"]
    return order.index(sev) if sev in order else 0


def build_event(
    snapshot: Dict[str, Any],
    score: float,
    cfg: Dict[str, Any],
    host_id: str,
) -> Dict[str, Any]:
    thresholds = cfg.get("scoring", {}).get("thresholds", {})
    sev = score_to_severity(score, thresholds)

    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": snapshot["timestamp"],
        "agent": {
            "name": cfg["agent"]["name"],
            "vendor": cfg["agent"]["vendor"],
            "version": cfg["agent"]["version"],
            "host_id": host_id,
            "platform": platform.platform(),
        },
        "classification": {
            "type": "behavioral_anomaly",
            "severity": sev,
            "score": round(score, 3),
        },
        "snapshot": snapshot,
        "tags": [
            "synthicsoft",
            "aegis",
            "neuro-sentinel",
            "behavioral-fingerprint",
            "local-model",
        ],
    }


def rotate_if_needed(events_file: Path, max_mb: int) -> None:
    if not events_file.exists():
        return
    size_mb = events_file.stat().st_size / (1024 * 1024)
    if size_mb >= max_mb:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        rotated = events_file.with_name(f"{events_file.stem}-{ts}.ndjson")
        events_file.rename(rotated)


def write_event(events_file: Path, event: Dict[str, Any]) -> None:
    with events_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def pretty_console(event: Dict[str, Any]) -> None:
    sev = event["classification"]["severity"]
    score = event["classification"]["score"]
    snap = event["snapshot"]

    col = severity_color(sev)
    print(
        f"{col}[{sev.upper():8}] score={score:.3f}  "
        f"cpu={snap['cpu_percent']:.1f}%  "
        f"ram={snap['ram_percent']:.1f}%  "
        f"procs={snap['process_count']}  "
        f"net={snap['net_connection_count']}{C_RST}"
    )


def run_agent(args: argparse.Namespace) -> None:
    cfg_path = Path(args.config).resolve()
    cfg = load_config(cfg_path)

    print(BANNER)
    print(f"{C_ACC}Config loaded from {cfg_path}{C_RST}")

    poll_interval = cfg["agent"].get("poll_interval_seconds", 10)
    out_cfg = cfg.get("output", {})
    events_file = Path(__file__).resolve().parent / out_cfg.get(
        "events_file", "outputs/events.ndjson"
    )
    events_file.parent.mkdir(parents=True, exist_ok=True)

    limits = cfg.get("limits", {})
    max_mb = limits.get("max_events_file_mb", 25)

    thresholds = cfg.get("scoring", {}).get("thresholds", {})
    min_sev = cfg["agent"].get("min_severity_to_log", "info").lower()

    host_id = platform.node() or "unknown-host"
    model = NeuroAnomalyModel()

    print(
        f"{C_ACC}Agent: {cfg['agent']['name']} v{cfg['agent']['version']} "
        f"on {host_id} (interval={poll_interval}s){C_RST}"
    )

    while True:
        snapshot = collect_snapshot()
        score = model.score(snapshot)
        event = build_event(snapshot, score, cfg, host_id)

        # Filter on minimum severity
        sev = event["classification"]["severity"]
        if severity_rank(sev) < severity_rank(min_sev):
            time.sleep(poll_interval)
            continue

        # Write & rotate
        rotate_if_needed(events_file, max_mb)
        write_event(events_file, event)
        pretty_console(event)
        time.sleep(poll_interval)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SynthicSoft AEGIS::NeuroSentinel – neural SOC agent."
    )
    parser.add_argument(
        "-c",
        "--config",
        default=str(Path(__file__).resolve().parent / "config.yaml"),
        help="Path to config.yaml",
    )
    args = parser.parse_args()
    run_agent(args)


if __name__ == "__main__":
    main()
