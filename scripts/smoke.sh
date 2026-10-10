#!/bin/sh
# End-to-end smoke test against a running stack: wait until healthy, run the seeded
# order_priority_workflow down both branches, and check the results.
#
#   docker compose up --build -d && sh scripts/smoke.sh
#
# API_URL overrides the default http://localhost:8000.
set -eu

API="${API_URL:-http://localhost:8000}"
fail() {
  echo "SMOKE FAILED: $*" >&2
  exit 1
}

# Pick a Python that really runs (on Windows, python3 can be a Microsoft Store stub).
PY=""
for candidate in python3 python; do
  if "$candidate" -c 'import sys' >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
[ -n "$PY" ] || fail "no working python3 or python on PATH"

wait_for_health() {
  echo "Waiting for $API/health (postgres, redis, rabbitmq and celery workers) ..."
  i=0
  until curl -fsS "$API/health" >/dev/null 2>&1; do
    i=$((i + 1))
    [ "$i" -le 90 ] || fail "stack did not become healthy within 180 s"
    sleep 2
  done
  echo "healthy"
}

# run_case <quantity> <expected priority> <expected shipping_days>
run_case() {
  quantity="$1"; priority="$2"; days="$3"
  resp="$(curl -fsS -X POST "$API/workflows/order_priority_workflow/run" \
    -H 'Content-Type: application/json' \
    -d "{\"data\": {\"order\": {\"quantity\": $quantity}}}")" || fail "could not start the workflow"
  id="$(printf '%s' "$resp" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["instance_id"])')"
  echo "quantity=$quantity -> instance $id"

  i=0
  while :; do
    inst="$(curl -fsS "$API/instances/$id")" || fail "could not read instance $id"
    status="$(printf '%s' "$inst" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
    case "$status" in
      completed) break ;;
      failed|cancelled) fail "instance $id ended as $status: $inst" ;;
    esac
    i=$((i + 1))
    [ "$i" -le 60 ] || fail "instance $id still '$status' after 60 s: $inst"
    sleep 1
  done

  printf '%s' "$inst" | "$PY" -c '
import json, sys
want_priority, want_days = sys.argv[1], int(sys.argv[2])
data = json.load(sys.stdin)["data"]
got_priority, got_days = data.get("priority"), data.get("shipping_days")
assert got_priority == want_priority, "priority %r != %r" % (got_priority, want_priority)
assert got_days == want_days, "shipping_days %r != %r" % (got_days, want_days)
' "$priority" "$days" || fail "unexpected result data for instance $id: $inst"

  steps="$(curl -fsS "$API/instances/$id/steps")" || fail "could not read steps of $id"
  printf '%s' "$steps" | "$PY" -c '
import json, sys
steps = json.load(sys.stdin)
bad = [s["step_name"] for s in steps if s["status"] != "completed"]
assert steps and not bad, "steps not completed: %r" % (bad,)
' || fail "step executions for $id are not all completed: $steps"
  echo "  completed, priority=$priority, shipping_days=$days"
}

wait_for_health
run_case 150 high 1
run_case 30 normal 5
echo "SMOKE OK"
