#!/usr/bin/env python3
"""Bounded Phase 7D read-only financial API benchmark on isolated test data.

Never transmits or logs credentials. Uses disposable E2E session from 7D only.
"""
import concurrent.futures
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
STATE = BASE / "frontend/tests/e2e/.auth/admin.json"
URL_BASE = "http://127.0.0.1:8101"
ROUTES = [
    "/api/v1/accounting/ledger/",
    "/api/v1/accounting/reports/tb/",
    "/api/v1/reporting/catalog/",
]
N = 35


def pct(values, fraction):
    v = sorted(values)
    return round(v[min(len(v) - 1, int((len(v) - 1) * fraction))], 2)


def main():
    state = json.loads(STATE.read_text())
    cookies = {c["name"]: c["value"] for c in state["cookies"]}
    session = cookies.get("mateerp_session")
    if not session:
        raise SystemExit("No isolated test session; refusing auth benchmark")
    headers = {"Cookie": "mateerp_session=" + session, "Accept": "application/json"}
    def probe(route):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(URL_BASE + route, headers=headers), timeout=12) as r:
                status = r.status
                r.read(8192)
        except urllib.error.HTTPError as err:
            status = err.code
        except (TimeoutError, OSError):
            status = 0
        return round((time.perf_counter() - t0) * 1000, 3), status
    reports=[]
    for route in ROUTES:
        startup=probe(route)
        if startup[1] != 200:
            raise SystemExit(f"Unexpected status {startup[1]} at {route}; aborting")
        started=time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            samples=list(pool.map(lambda _: probe(route), range(N)))
        status=Counter(s for _,s in samples)
        ms=[x for x,_ in samples]
        record={
            "route":route,
            "test_requests":N,
            "max_concurrency":2,
            "status_counts":dict(status),
            "p50_ms":pct(ms, .50),
            "p95_ms":pct(ms, .95),
            "max_ms":round(max(ms),2),
            "duration_s":round(time.perf_counter()-started,2),
        }
        reports.append(record)
        print(json.dumps(record),flush=True)
    out=Path(__file__).with_name("phase-07d-financial-results.json")
    out.write_text(json.dumps({"dataset":"isolated E2E fixture, non-production","result":reports}, indent=2)+"\n")
    if any(r["status_counts"].get(200, 0) != N for r in reports):
        raise SystemExit("Unexpected status during benchmark")


if __name__=="__main__":
    main()
