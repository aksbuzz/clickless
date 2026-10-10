#!/usr/bin/env python3
"""Throughput benchmark for the worker: how many workflow steps per second, and where the CPU goes.

Run it on the machine that will host Postgres and the worker (for example the VM you plan to rent):

    python benchmarks/bench_steps.py --dsn postgresql://postgres@127.0.0.1:5432/workflows --processes 1 --threads 8

It uses the real engine and the real connector handlers. Every instance runs three fast internal steps
(transform_data, log, transform_data), or three steps that each wait --io-latency-ms to imitate calls to an
external API. Reports steps/s, CPU per step for the worker processes and for PostgreSQL, commits and WAL
per step, and memory. The PostgreSQL CPU and memory figures need Linux and a Postgres on the same host or
container (they come from /proc and cgroup v2). The database must already have the schema (init.sql);
all instance and job rows in it are deleted first.
"""
import argparse
import glob
import json
import multiprocessing as mp
import os
import pathlib
import sys
import threading
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STEPS_PER_WORKFLOW = 3


def workflow_definition(io_latency_ms: int) -> dict:
    if io_latency_ms:
        step = {"type": "action", "connector_id": "bench", "action_id": "bench_sleep", "config": {}}
        return {"start_at": "a", "steps": {"a": {**step, "next": "b"}, "b": {**step, "next": "c"}, "c": {**step, "next": "end"}}}
    return {"start_at": "a", "steps": {
        "a": {"type": "action", "connector_id": "internal", "action_id": "transform_data", "config": {"set": {"a": 1}}, "next": "b"},
        "b": {"type": "action", "connector_id": "internal", "action_id": "log", "config": {"message": "n={{a}}"}, "next": "c"},
        "c": {"type": "action", "connector_id": "internal", "action_id": "transform_data", "config": {"set": {"c": 3}}, "next": "end"},
    }}


class SleepHandler:
    """Stands in for a call to an external API."""

    def __init__(self, ms):
        self.seconds = ms / 1000

    def execute(self, instance_id, data, config=None, **kwargs):
        from src.worker.models import ActionResult, ActionStatus
        time.sleep(self.seconds)
        return ActionResult(ActionStatus.SUCCESS, data)


def _proc_stats():
    for path in glob.glob("/proc/[0-9]*/stat"):
        try:
            raw = open(path).read()
            comm = raw[raw.index("(") + 1: raw.rindex(")")]
            fields = raw[raw.rindex(")") + 2:].split()
            yield comm, int(fields[11]) + int(fields[12])
        except (OSError, ValueError, IndexError):
            continue


def postgres_cpu_seconds():
    if not os.path.isdir("/proc/self"):
        return None
    return sum(t for comm, t in _proc_stats() if comm == "postgres") / os.sysconf("SC_CLK_TCK")


def box_memory_mb():
    """Memory the whole box uses (heap + shared memory, page cache excluded), from cgroup v2."""
    try:
        stat = dict(line.split() for line in open("/sys/fs/cgroup/memory.stat"))
        return round((int(stat["anon"]) + int(stat["shmem"])) / 1048576, 1)
    except (OSError, KeyError, ValueError):
        return None


def peak_rss_mb():
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except ImportError:
        return None


def worker_process(dsn, threads, io_latency_ms, barrier, stop_event, results):
    sys.stdout = open(os.devnull, "w")     # handler log lines still cost CPU, but do not hit a terminal
    os.environ["DATABASE_URL"] = dsn
    from src.engine.worker import Worker
    from src.worker.main import size_connection_pool
    from src.worker.registry import get_registry

    size_connection_pool(threads)       # the same pool sizing the real worker uses

    handlers = get_registry()
    if io_latency_ms:
        handlers["bench_sleep"] = SleepHandler(io_latency_ms)
    worker = Worker(handlers, concurrency=threads, lease_seconds=300.0, idle_poll=1.0)
    stop = threading.Event()
    threading.Thread(target=lambda: (stop_event.wait(), stop.set()), daemon=True).start()
    barrier.wait()
    start = os.times()
    worker.run(stop)
    end = os.times()
    results.put((end.user - start.user + end.system - start.system, peak_rss_mb()))


def counters(cur):
    cur.execute("SELECT xact_commit FROM pg_stat_database WHERE datname = current_database()")
    commits = cur.fetchone()[0]
    cur.execute("SELECT wal_bytes FROM pg_stat_wal")
    return commits, int(cur.fetchone()[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default="postgresql://postgres@127.0.0.1:5432/workflows")
    ap.add_argument("--processes", type=int, default=1, help="worker processes")
    ap.add_argument("--threads", type=int, default=8, help="steps run at once in each process")
    ap.add_argument("--instances", type=int, default=600)
    ap.add_argument("--io-latency-ms", type=int, default=0, help="make every step wait this long, like an external API call")
    ap.add_argument("--sync-commit", choices=["on", "off"], default="on")
    args = ap.parse_args()

    import psycopg2

    dsn = args.dsn
    if args.sync_commit == "off":
        dsn += ("&" if "?" in dsn else "?") + "options=-c%20synchronous_commit%3Doff"

    admin = psycopg2.connect(args.dsn)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute("TRUNCATE jobs, workflow_step_executions, workflow_instances CASCADE")
    name = f"bench_{uuid.uuid4().hex[:8]}"
    cur.execute("INSERT INTO workflows (name) VALUES (%s) RETURNING id", (name,))
    workflow_id = cur.fetchone()[0]
    cur.execute("INSERT INTO workflow_versions (workflow_id, version, definition) VALUES (%s, 1, %s)",
                (workflow_id, json.dumps(workflow_definition(args.io_latency_ms))))

    os.environ["DATABASE_URL"] = dsn
    from src.engine import runtime
    from src.shared.db import db_cursor, reset_pool

    started = time.monotonic()
    for _ in range(args.instances):
        with db_cursor() as c:
            runtime.start_instance(c, name, {})
    ingest_seconds = time.monotonic() - started
    reset_pool()

    ctx = mp.get_context("spawn")
    barrier, stop_event, results = ctx.Barrier(args.processes + 1), ctx.Event(), ctx.Queue()
    procs = [ctx.Process(target=worker_process, args=(dsn, args.threads, args.io_latency_ms, barrier, stop_event, results))
             for _ in range(args.processes)]
    for p in procs:
        p.start()
    barrier.wait()

    commits0, wal0 = counters(cur)
    pg_cpu0 = postgres_cpu_seconds()
    started = time.monotonic()
    done = 0
    while done < args.instances:
        time.sleep(0.25)
        cur.execute("SELECT count(*) FROM workflow_instances WHERE status = 'completed'")
        done = cur.fetchone()[0]
        if time.monotonic() - started > 900:
            raise SystemExit("timed out")
    elapsed = time.monotonic() - started
    pg_cpu1 = postgres_cpu_seconds()
    memory = box_memory_mb()

    stop_event.set()
    worker_cpu, worker_rss = 0.0, []
    for _ in procs:
        cpu, rss = results.get(timeout=120)
        worker_cpu += cpu
        worker_rss.append(rss)
    for p in procs:
        p.join()
    time.sleep(1.5)     # PostgreSQL publishes its statistics with a short delay
    commits1, wal1 = counters(cur)

    steps = args.instances * STEPS_PER_WORKFLOW
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()
    print(json.dumps({
        "processes": args.processes, "threads": args.threads, "io_latency_ms": args.io_latency_ms,
        "sync_commit": args.sync_commit, "cpus_visible": cpus,
        "instances": args.instances, "steps": steps, "seconds": round(elapsed, 2),
        "ingest_workflows_per_s": round(args.instances / ingest_seconds),
        "steps_per_s": round(steps / elapsed),
        "worker_cpu_ms_per_step": round(1000 * worker_cpu / steps, 2),
        "postgres_cpu_ms_per_step": None if pg_cpu0 is None else round(1000 * (pg_cpu1 - pg_cpu0) / steps, 2),
        "commits_per_step": round((commits1 - commits0) / steps, 2),
        "wal_bytes_per_step": round((wal1 - wal0) / steps),
        "cpu_busy_pct": None if pg_cpu0 is None else round(100 * (worker_cpu + pg_cpu1 - pg_cpu0) / (elapsed * cpus)),
        "worker_rss_mb_each": worker_rss, "box_memory_mb": memory,
    }))


if __name__ == "__main__":
    main()
