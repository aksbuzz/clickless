#!/usr/bin/env python3
"""Throughput benchmark for the Postgres-only runtime.

Run it on the machine that will host the workers and Postgres (for example the VM you plan to rent),
so the numbers describe that machine rather than a laptop:

    python bench.py --dsn postgresql://postgres@127.0.0.1:5432/spike --workers 2 --instances 600

Reports steps/s and where the CPU went (worker processes vs PostgreSQL), plus commits, WAL bytes and
memory used. CPU figures for PostgreSQL need Linux and a Postgres running on the same host or
container as this script (they come from /proc); the memory figure needs cgroup v2 (any recent Docker host). Everything else works anywhere.
"""
import argparse
import glob
import json
import multiprocessing as mp
import os
import pathlib
import sys
import time
import uuid

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

WORKFLOW = {
    "start_at": "a",
    "steps": {
        "a": {"type": "action", "connector_id": "internal", "action_id": "transform_data",
              "config": {"set": {"a": 1}}, "next": "b"},
        "b": {"type": "action", "connector_id": "internal", "action_id": "log",
              "config": {"message": "n={{a}}"}, "next": "c"},
        "c": {"type": "action", "connector_id": "internal", "action_id": "transform_data",
              "config": {"set": {"c": 3}}, "next": "end"},
    },
}
STEPS_PER_WORKFLOW = 3


def _proc_stats():
    """Yield (comm, utime+stime in ticks, pid) for every process we can see."""
    for path in glob.glob("/proc/[0-9]*/stat"):
        try:
            raw = open(path).read()
            comm = raw[raw.index("(") + 1: raw.rindex(")")]
            fields = raw[raw.rindex(")") + 2:].split()
            yield comm, int(fields[11]) + int(fields[12]), path.split("/")[2]
        except (OSError, ValueError, IndexError):
            continue


def postgres_cpu_seconds():
    if not os.path.isdir("/proc/self"):
        return None
    return sum(t for comm, t, _ in _proc_stats() if comm == "postgres") / os.sysconf("SC_CLK_TCK")


def cgroup_memory_mb():
    """Memory the whole box needs (heap + shared memory, page cache excluded), from cgroup v2."""
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


def worker_main(dsn, barrier, stop, results):
    sys.stdout = open(os.devnull, "w")   # handler logs still cost CPU, but do not hit a terminal
    from pg_engine import Engine
    from src.worker.registry import get_registry
    engine = Engine(dsn, get_registry())
    barrier.wait()
    start = os.times()
    engine.run_forever(stop, max_sleep=0.2)
    end = os.times()
    results.put((end.user - start.user + end.system - start.system, peak_rss_mb()))
    engine.close()


def db_counters(cur):
    cur.execute("SELECT xact_commit FROM pg_stat_database WHERE datname = current_database()")
    commits = cur.fetchone()[0]
    cur.execute("SELECT wal_bytes FROM pg_stat_wal")
    return commits, int(cur.fetchone()[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default="postgresql://postgres@127.0.0.1:55432/spike")
    ap.add_argument("--workers", type=int, default=2, help="worker processes (one job at a time each)")
    ap.add_argument("--instances", type=int, default=600)
    ap.add_argument("--sync-commit", choices=["on", "off"], default="on")
    args = ap.parse_args()

    import psycopg2
    from pg_engine import Engine

    dsn = args.dsn
    if args.sync_commit == "off":
        dsn += ("&" if "?" in dsn else "?") + "options=-c%20synchronous_commit%3Doff"

    admin = psycopg2.connect(args.dsn)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute((HERE / "schema.sql").read_text())
    cur.execute("TRUNCATE jobs, workflow_step_executions, workflow_instances CASCADE")
    name = f"bench_{uuid.uuid4().hex[:8]}"
    cur.execute("INSERT INTO workflows (name) VALUES (%s) RETURNING id", (name,))
    wf_id = cur.fetchone()[0]
    cur.execute("INSERT INTO workflow_versions (workflow_id, version, definition) VALUES (%s, 1, %s)",
                (wf_id, json.dumps(WORKFLOW)))

    starter = Engine(dsn, {})
    t0 = time.monotonic()
    for _ in range(args.instances):
        starter.start_workflow(name, {})
    ingest_s = time.monotonic() - t0
    starter.close()

    ctx = mp.get_context("spawn")
    barrier, stop, results = ctx.Barrier(args.workers + 1), ctx.Event(), ctx.Queue()
    procs = [ctx.Process(target=worker_main, args=(dsn, barrier, stop, results)) for _ in range(args.workers)]
    for p in procs:
        p.start()
    barrier.wait()

    commits0, wal0 = db_counters(cur)
    pg_cpu0 = postgres_cpu_seconds()
    t0 = time.monotonic()
    done = 0
    while done < args.instances:
        time.sleep(0.25)
        cur.execute("SELECT count(*) FROM workflow_instances WHERE status = 'completed'")
        done = cur.fetchone()[0]
        if time.monotonic() - t0 > 600:
            raise SystemExit("timed out")
    elapsed = time.monotonic() - t0
    pg_cpu1 = postgres_cpu_seconds()
    box_mem = cgroup_memory_mb()   # sampled while Postgres and the workers are still running

    stop.set()
    worker_cpu, worker_rss = 0.0, []
    for _ in procs:
        cpu, rss = results.get(timeout=30)
        worker_cpu += cpu
        worker_rss.append(rss)
    for p in procs:
        p.join()
    time.sleep(1.5)   # PostgreSQL publishes its statistics with a short delay
    commits1, wal1 = db_counters(cur)

    steps = args.instances * STEPS_PER_WORKFLOW
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()
    out = {
        "workers": args.workers, "sync_commit": args.sync_commit, "cpus_visible": cpus,
        "instances": args.instances, "steps": steps, "seconds": round(elapsed, 2),
        "ingest_workflows_per_s": round(args.instances / ingest_s),
        "steps_per_s": round(steps / elapsed),
        "worker_cpu_ms_per_step": round(1000 * worker_cpu / steps, 2),
        "postgres_cpu_ms_per_step": None if pg_cpu0 is None else round(1000 * (pg_cpu1 - pg_cpu0) / steps, 2),
        "commits_per_step": round((commits1 - commits0) / steps, 2),
        "wal_bytes_per_step": round((wal1 - wal0) / steps),
        "cpu_utilisation_pct": None if pg_cpu0 is None else round(
            100 * (worker_cpu + pg_cpu1 - pg_cpu0) / (elapsed * cpus)),
        "worker_rss_mb_each": worker_rss, "box_memory_mb": box_mem,
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
