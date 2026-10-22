#!/usr/bin/env python3
"""Phase 7D non-destructive bounded HTTP latency probe, against isolated services only.

No mutation endpoints, credentials, database fixtures or production addresses.
Uses ThreadPoolExecutor(max_workers=2) and fixed 80 GETs per route.
"""
from __future__ import annotations

import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROUTES = [
    ("backend-health", "http://127.0.0.1:8101/api/v1/health/", 200),
    ("frontend-login", "http://127.0.0.1:3100/login", 200),
]
RUNS = 80
CONCURRENCY = 2


def request(url: str) -> tuple[float, int]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, method="GET", headers={"User-Agent": "MateERP-7D-ReadOnly-Probe"}),
            timeout=8,
        ) as response:
            response.read(8192)
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except (TimeoutError, OSError):
        status = 0
    return (time.perf_counter() - started) * 1000, status


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def main() -> None:
    output: dict[str, object] = {
        "scope": "MateERP Phase 7D dedicated disposable isolated test stack",
        "requests_per_route": RUNS,
        "concurrency": CONCURRENCY,
        "routes": [],
    }
    for label, url, expected in ROUTES:
        # Fail fast if the service is absent; NEVER accidentally benchmark a stale unrelated service.
        p, status = request(url)
        if status != expected:
            raise SystemExit(f"{label}: initial GET returned {status}; expected {expected}. Refusing benchmark.")
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            results = list(pool.map(lambda _: request(url), range(RUNS)))
        durations = [v for v, _ in results]
        statuses = Counter(status for _, status in results)
        record = {
            "name": label,
            "total": RUNS,
            "http_statuses": dict(statuses),
            "success": statuses.get(expected, 0),
            "p50_ms": round(percentile(durations, .50), 1),
            "p95_ms": round(percentile(durations, .95), 1),
            "max_ms": round(max(durations), 1),
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }
        output["routes"].append(record)
        print(json.dumps(record, sort_keys=True), flush=True)
    out = Path(__file__).parent / "phase-07d-latency-results.json"
    out.write_text(json.dumps(output, indent=2) + "\n")
    print(f"Saved: {out}", flush=True)


if __name__ == "__main__":
    main()
