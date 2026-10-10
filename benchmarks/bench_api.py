#!/usr/bin/env python3
"""HTTP ingestion benchmark: how much CPU does it cost to accept one workflow start through the real API?

Starts the real FastAPI app (src.api.main) under uvicorn, drives it with concurrent authenticated requests to
POST /workflows/{name}/run, and reports requests/s plus CPU per request for the API server, for PostgreSQL
and for the load generator itself. The load generator shares the machine, so requests/s is a lower bound; the
CPU-per-request figures are the useful ones. Needs Linux (/proc) and a Postgres on the same host or container.

    python benchmarks/bench_api.py --dsn postgresql://postgres@127.0.0.1:5432/workflows --server-workers 1
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

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

PORT = 8099
KEY = "benchmark-key-benchmark-key-0000"


def _ticks(pid):
    raw = open(f"/proc/{pid}/stat").read()
    fields = raw[raw.rindex(")") + 2:].split()
    return int(fields[11]) + int(fields[12]), int(fields[1])   # utime+stime, ppid


def tree_cpu_seconds(root_pid):
    procs = {}
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                procs[int(entry)] = _ticks(entry)
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
    """One blocking keep-alive connection per thread: a few hundred microseconds of CPU per request."""
    import http.client
    body = json.dumps({"data": {"order": {"quantity": 5}}})
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"}
    latencies, lock, remaining = [], threading.Lock(), [requests]

    def worker():
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=60)
        while True:
            with lock:
                if remaining[0] <= 0:
                    break
                remaining[0] -= 1
            started = time.perf_counter()
            conn.request("POST", f"/workflows/{name}/run", body, headers)
            resp = conn.getresponse()
            resp.read()
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            with lock:
                latencies.append(time.perf_counter() - started)
        conn.close()

    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(latencies)


def main():
    import psycopg2
    import bench_steps

    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default="postgresql://postgres@127.0.0.1:5432/workflows")
    ap.add_argument("--server-workers", type=int, default=1, help="uvicorn worker processes")
    ap.add_argument("--requests", type=int, default=3000)
    ap.add_argument("--concurrency", type=int, default=32)
    args = ap.parse_args()

    admin = psycopg2.connect(args.dsn)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute("TRUNCATE jobs, workflow_step_executions, workflow_instances CASCADE")
    name = f"bench_{uuid.uuid4().hex[:8]}"
    cur.execute("INSERT INTO workflows (name) VALUES (%s) RETURNING id", (name,))
    workflow_id = cur.fetchone()[0]
    definition = bench_steps.workflow_definition(0)
    cur.execute("INSERT INTO workflow_versions (workflow_id, version, definition) VALUES (%s, 1, %s)",
                (workflow_id, json.dumps(definition)))

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api.main:app", "--app-dir", str(ROOT), "--port", str(PORT),
         "--workers", str(args.server_workers), "--log-level", "warning"],
        env={**os.environ, "DATABASE_URL": args.dsn, "API_KEY": KEY})
    try:
        import urllib.request
        for _ in range(150):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/ready", timeout=1).read()
                break
            except Exception:
                time.sleep(0.2)
        drive(200, args.concurrency, name)      # warm-up: opens the database connections

        commits0, _ = bench_steps.counters(cur)
        srv0, pg0, me0 = tree_cpu_seconds(server.pid), bench_steps.postgres_cpu_seconds(), time.process_time()
        started = time.perf_counter()
        latencies = drive(args.requests, args.concurrency, name)
        elapsed = time.perf_counter() - started
        srv1, pg1, me1 = tree_cpu_seconds(server.pid), bench_steps.postgres_cpu_seconds(), time.process_time()
        memory = bench_steps.box_memory_mb()
    finally:
        server.terminate()
        server.wait(timeout=20)
    time.sleep(1.5)
    commits1, _ = bench_steps.counters(cur)

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
        "box_memory_mb": memory,
    }))


if __name__ == "__main__":
    main()
