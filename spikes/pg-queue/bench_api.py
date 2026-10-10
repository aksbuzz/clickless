#!/usr/bin/env python3
"""HTTP ingestion benchmark: how much CPU does it cost to accept one workflow start over HTTP?

Starts a minimal FastAPI app (uvicorn) that calls Engine.start_workflow, drives it with concurrent
requests, and reports CPU per request for the API server, for PostgreSQL, and for the load generator
itself. The load generator shares the machine, so requests/s is a lower bound; the CPU-per-request
figures are the useful ones. Needs Linux (/proc) and a Postgres on the same host or container.

    python bench_api.py --dsn postgresql://postgres@127.0.0.1:5432/spike --server-workers 1
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import uuid

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

from fastapi import FastAPI  # noqa: E402

DSN = os.environ.get("BENCH_DSN", "postgresql://postgres@127.0.0.1:5432/spike")
PORT = 8099

app = FastAPI()
_local = threading.local()


def _engine():
    if not hasattr(_local, "engine"):
        from pg_engine import Engine
        _local.engine = Engine(DSN, {})
    return _local.engine


@app.post("/workflows/{name}/run")
def run(name: str, payload: dict):
    return {"instance_id": _engine().start_workflow(name, payload.get("data", {}))}


# ---------------------------------------------------------------------------------------- benchmark driver

def _ticks(pid):
    raw = open(f"/proc/{pid}/stat").read()
    fields = raw[raw.rindex(")") + 2:].split()
    return int(fields[11]) + int(fields[12]), int(fields[1])   # utime+stime, ppid


def tree_cpu_seconds(root_pid):
    procs = {}
    for path in os.listdir("/proc"):
        if path.isdigit():
            try:
                procs[int(path)] = _ticks(path)
            except (OSError, ValueError, IndexError):
                pass
    members, grew = {root_pid}, True
    while grew:
        grew = False
        for pid, (_, ppid) in procs.items():
            if ppid in members and pid not in members:
                members.add(pid)
                grew = True
    return sum(procs[p][0] for p in members if p in procs) / os.sysconf("SC_CLK_TCK")


def drive(requests, concurrency, name):
    """Cheap load generator: one blocking keep-alive connection per thread (a few hundred microseconds of CPU
    per request), so it disturbs the measurement far less than an async HTTP client would."""
    import http.client
    body = json.dumps({"data": {"order": {"quantity": 5}}})
    headers = {"Content-Type": "application/json"}
    latencies, lock, remaining = [], threading.Lock(), [requests]

    def worker():
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=60)
        while True:
            with lock:
                if remaining[0] <= 0:
                    break
                remaining[0] -= 1
            t = time.perf_counter()
            conn.request("POST", f"/workflows/{name}/run", body, headers)
            resp = conn.getresponse()
            resp.read()
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            with lock:
                latencies.append(time.perf_counter() - t)
        conn.close()

    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(latencies)


def main():
    import psycopg2
    import bench

    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=DSN)
    ap.add_argument("--server-workers", type=int, default=1, help="uvicorn worker processes")
    ap.add_argument("--requests", type=int, default=3000)
    ap.add_argument("--concurrency", type=int, default=32)
    args = ap.parse_args()

    admin = psycopg2.connect(args.dsn)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute((HERE / "schema.sql").read_text())
    cur.execute("TRUNCATE jobs, workflow_step_executions, workflow_instances CASCADE")
    name = f"bench_{uuid.uuid4().hex[:8]}"
    cur.execute("INSERT INTO workflows (name) VALUES (%s) RETURNING id", (name,))
    wf_id = cur.fetchone()[0]
    cur.execute("INSERT INTO workflow_versions (workflow_id, version, definition) VALUES (%s, 1, %s)",
                (wf_id, json.dumps(bench.WORKFLOW)))

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "bench_api:app", "--app-dir", str(HERE), "--port", str(PORT),
         "--workers", str(args.server_workers), "--log-level", "warning"],
        env={**os.environ, "BENCH_DSN": args.dsn})
    try:
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/openapi.json", timeout=1).read()
                break
            except Exception:
                time.sleep(0.2)
        drive(200, args.concurrency, name)   # warm-up: opens the thread-local DB connections

        commits0, _ = bench.db_counters(cur)
        srv0, pg0, me0 = tree_cpu_seconds(server.pid), bench.postgres_cpu_seconds(), time.process_time()
        t0 = time.perf_counter()
        latencies = drive(args.requests, args.concurrency, name)
        elapsed = time.perf_counter() - t0
        srv1, pg1, me1 = tree_cpu_seconds(server.pid), bench.postgres_cpu_seconds(), time.process_time()
        mem = bench.cgroup_memory_mb()
    finally:
        server.terminate()
        server.wait(timeout=20)
    time.sleep(1.5)
    commits1, _ = bench.db_counters(cur)

    n = args.requests
    print(json.dumps({
        "server_workers": args.server_workers, "concurrency": args.concurrency, "requests": n,
        "cpus_visible": len(os.sched_getaffinity(0)),
        "requests_per_s": round(n / elapsed),
        "api_cpu_ms_per_request": round(1000 * (srv1 - srv0) / n, 2),
        "postgres_cpu_ms_per_request": round(1000 * (pg1 - pg0) / n, 2),
        "loadgen_cpu_ms_per_request": round(1000 * (me1 - me0) / n, 2),
        "commits_per_request": round((commits1 - commits0) / n, 2),
        "p50_ms": round(1000 * latencies[n // 2], 1), "p95_ms": round(1000 * latencies[int(n * 0.95)], 1),
        "box_memory_mb": mem,
    }))


if __name__ == "__main__":
    main()
