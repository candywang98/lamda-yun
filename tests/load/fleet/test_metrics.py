import pytest
from cloudctl_observability import DeviceFleetMetrics, percentile


def test_percentile_nearest_rank_boundaries() -> None:
    assert percentile([], 0.5) == 0.0
    assert percentile([5.0], 0.5) == 5.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0
    with pytest.raises(ValueError):
        percentile([1.0], 1.5)


def test_device_metrics_counters_and_snapshots() -> None:
    metrics = DeviceFleetMetrics()
    metrics.incr("dev-a", "leaseConflict", 2)
    metrics.incr("dev-a", "unknown")
    metrics.incr("dev-b", "evidenceUploads")
    metrics.incr("dev-b", "evidenceBytes", 1024)
    metrics.observe("dev-a", "queueAgeSeconds", 0.1)
    metrics.observe("dev-a", "queueAgeSeconds", 0.2)
    metrics.observe("dev-a", "queueAgeSeconds", 0.3)

    with pytest.raises(ValueError):
        metrics.incr("dev-a", "not-a-counter")
    with pytest.raises(ValueError):
        metrics.observe("dev-a", "queueAgeSeconds", -1)

    snap = metrics.snapshot()
    assert snap["deviceCount"] == 2
    assert snap["perDevice"]["dev-a"]["leaseConflict"] == 2
    assert snap["perDevice"]["dev-b"]["evidenceBytes"] == 1024
    queue = snap["perDevice"]["dev-a"]["queueAgeSeconds"]
    assert queue["count"] == 3
    assert queue["p50"] == 0.2
    assert queue["p95"] == 0.3
    assert snap["fleet"]["unknown"] == 1
    assert snap["fleet"]["queueAgeSeconds"]["count"] == 3


def test_latency_ring_bounded() -> None:
    metrics = DeviceFleetMetrics(max_samples=10)
    for index in range(50):
        metrics.observe("dev", "claimLatencySeconds", float(index))
    snap = metrics.snapshot()
    assert snap["fleet"]["claimLatencySeconds"]["count"] == 10
    assert snap["fleet"]["claimLatencySeconds"]["max"] == 49.0
