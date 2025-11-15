# agent/model.py
"""
SynthicSoft AEGIS::NeuroSentinel
Neural anomaly scoring interface.

This layer abstracts the anomaly scoring logic. It starts as a heuristic-based
model, but the interface is designed so you can later plug in an actual neural
network (e.g., autoencoder, one-class classifier) without changing the agent.
"""

from typing import Dict, Any
import random


class NeuroAnomalyModel:
    """
    Local anomaly scorer.

    Input: telemetry snapshot dict.
    Output: float score in range [0.0, 1.0], where higher = more anomalous.
    """

    def __init__(self) -> None:
        # Placeholder for future neural model loading (PyTorch/TF/etc.)
        self.initialized = True

    def score(self, snapshot: Dict[str, Any]) -> float:
        """
        Compute anomaly score.

        Current version: weighted heuristic that can be swapped out later.
        """
        cpu = snapshot.get("cpu_percent", 0.0)
        ram = snapshot.get("ram_percent", 0.0)
        proc_count = snapshot.get("process_count", 0)
        net_count = snapshot.get("net_connection_count", 0)

        # Normalize
        cpu_n = max(0.0, min(cpu / 100.0, 1.0))
        ram_n = max(0.0, min(ram / 100.0, 1.0))
        proc_n = max(0.0, min(proc_count / 300.0, 1.0))
        net_n = max(0.0, min(net_count / 200.0, 1.0))

        raw = (
            cpu_n * 0.35 +
            ram_n * 0.25 +
            proc_n * 0.20 +
            net_n * 0.20
        )

        # Tiny jitter to avoid perfectly flat lines
        jitter = random.uniform(-0.02, 0.02)
        score = max(0.0, min(1.0, raw + jitter))
        return float(score)
