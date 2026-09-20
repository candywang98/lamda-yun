"""Per-device fleet metrics with nearest-rank percentiles.

D11 观测口径：queueAge / claimLatency / leaseConflict / rebind / UNKNOWN /
inputFailure / evidenceUploads / evidenceBytes 按设备分别累计；直方图输出
p50/p95/mean/max/count。纯内存实现，进程内单实例；不承诺跨进程聚合
（那是部署侧 OTel 的事，见 infra/otel）。
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

COUNTER_NAMES = (
    "leaseConflict",
    "rebind",
    "unknown",
    "inputFailure",
    "evidenceUploads",
    "evidenceBytes",
)

LATENCY_NAMES = ("queueAgeSeconds", "claimLatencySeconds")


def percentile(samples: list[float], q: float) -> float:
    """Nearest-rank percentile; q in [0,1]; empty input returns 0.0."""
    if not samples:
        return 0.0
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be within [0, 1]")
    ordered = sorted(samples)
    rank = max(1, min(len(ordered), int(q * len(ordered) + 0.999999)))
    return ordered[rank - 1]


@dataclass
class _LatencySeries:
    samples: list[float] = field(default_factory=list)
    observe: Callable[[float], None] | None = None  # set by registry

    def summary(self) -> dict[str, float | int]:
        ordered = sorted(self.samples)
        count = len(ordered)
        total = sum(ordered)
        return {
            "count": count,
            "p50": percentile(ordered, 0.50),
            "p95": percentile(ordered, 0.95),
            "mean": round(total / count, 6) if count else 0.0,
            "max": ordered[-1] if ordered else 0.0,
        }


class DeviceFleetMetrics:
    """Thread-safe in-process per-device metric registry."""

    def __init__(self, max_samples: int = 50_000) -> None:
        self._lock = threading.Lock()
        self._max_samples = max_samples
        self._counters: dict[str, dict[str, float]] = {}
        self._latencies: dict[str, dict[str, list[float]]] = {
            name: {} for name in LATENCY_NAMES
        }

    def incr(self, device_id: str, name: str, value: float = 1) -> None:
        if name not in COUNTER_NAMES:
            raise ValueError(f"unknown counter {name!r}; allowed: {COUNTER_NAMES}")
        with self._lock:
            device = self._counters.setdefault(device_id, {n: 0 for n in COUNTER_NAMES})
            device[name] += value

    def observe(self, device_id: str, name: str, seconds: float) -> None:
        if name not in LATENCY_NAMES:
            raise ValueError(f"unknown latency {name!r}; allowed: {LATENCY_NAMES}")
        if seconds < 0:
            raise ValueError("latency samples must be non-negative")
        with self._lock:
            series = self._latencies[name].setdefault(device_id, [])
            if len(series) >= self._max_samples:
                del series[: len(series) - self._max_samples + 1]
            series.append(seconds)

    def snapshot(self) -> dict[str, dict]:
        """Per-device view + fleet roll-up. Latencies report p50/p95/mean/max."""
        with self._lock:
            devices = sorted(set(self._counters) | {d for s in self._latencies.values() for d in s})
            per_device: dict[str, dict] = {}
            for device in devices:
                view: dict[str, object] = dict(self._counters.get(device, {}))
                for name in LATENCY_NAMES:
                    view[name] = _LatencySeries(
                        list(self._latencies[name].get(device, []))
                    ).summary()
                per_device[device] = view
            fleet: dict[str, object] = {}
            for counter in COUNTER_NAMES:
                fleet[counter] = sum(
                    self._counters.get(device, {}).get(counter, 0) for device in devices
                )
            for name in LATENCY_NAMES:
                merged = [
                    sample
                for device in devices
                for sample in self._latencies[name].get(device, [])
                ]
                fleet[name] = _LatencySeries(merged).summary()
            return {"perDevice": per_device, "fleet": fleet, "deviceCount": len(devices)}
