#!/bin/sh
# End-to-end smoke test against a running stack. It checks that the security configuration holds, then
# runs the seeded order_priority_workflow down both branches and checks the results.
#
#   sh scripts/init-env.sh && docker compose up --build -d && sh scripts/smoke.sh
#
# The API key comes from $API_KEY or from .env. API_URL (default http://localhost:8000) and UI_URL
# (default http://localhost:3000) point at the stack.
set -eu

API="${API_URL:-http://localhost:8000}"
UI="${UI_URL:-http://localhost:3000}"

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

KEY="${API_KEY:-}"
if [ -z "$KEY" ] && [ -f .env ]; then
  KEY="$(grep '^API_KEY=' .env | head -1 | cut -d= -f2-)"
fi
[ -n "$KEY" ] || fail "no API key: set API_KEY or run sh scripts/init-env.sh"
AUTH="Authorization: Bearer $KEY"

status() {  # status <curl args...>  prints the HTTP status code
  curl -s -o /dev/null -w '%{http_code}' "$@"
}

expect_status() {  # expect_status <expected> <description> <curl args...>
  expected="$1"; description="$2"; shift 2
  got="$(status "$@")"
  [ "$got" = "$expected" ] || fail "$description: expected HTTP $expected, got $got"
  echo "  ok: $description"
}

wait_for_health() {
  echo "Waiting for $API/health (postgres and the job queue) ..."
  i=0
  until curl -fsS -H "$AUTH" "$API/health" >/dev/null 2>&1; do
    i=$((i + 1))
    [ "$i" -le 90 ] || fail "stack did not become healthy within 180 s"
    sleep 2
  done
  echo "healthy"
}

port_closed() {  # port_closed <port> <name>
  "$PY" -c '
import socket, sys
s = socket.socket(); s.settimeout(1)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) != 0 else 1)
' "$1" || fail "$2 (port $1) is reachable from the host; it should only be reachable inside the compose network"
  echo "  ok: $2 is not published (port $1)"
}

check_security() {
  echo "Security checks:"
  expect_status 401 "API rejects a request without a key" "$API/workflows"
  expect_status 401 "API rejects a wrong key" -H "Authorization: Bearer not-the-key" "$API/workflows"
  expect_status 401 "instance listing needs the key" "$API/instances"
  expect_status 200 "readiness probe stays public" "$API/ready"
  expect_status 401 "unsigned GitHub webhook is rejected" -X POST -d '{}' "$API/triggers/github/webhook"
  expect_status 401 "unsigned Slack webhook is rejected" -X POST -d '{}' "$API/triggers/slack/webhook"
  expect_status 404 "UI proxy does not expose /webhooks" -X POST -H "$AUTH" "$UI/api/webhooks/anything"
  expect_status 404 "UI proxy does not expose /metrics" -H "$AUTH" "$UI/api/metrics"
  expect_status 200 "UI proxy passes API calls through" -H "$AUTH" "$UI/api/workflows"
  port_closed 5432 "PostgreSQL"
}

# create_and_start <name> <definition json>   prints the new instance id
create_and_start() {
  curl -fsS -X POST "$API/workflows" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"name\": \"$1\", \"definition\": $2}" >/dev/null || fail "could not create workflow $1"
  resp="$(curl -fsS -X POST "$API/workflows/$1/run" -H "$AUTH" -H 'Content-Type: application/json' -d '{"data": {}}')" \
    || fail "could not start workflow $1"
  printf '%s' "$resp" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["instance_id"])'
}

# wait_until_failed <instance id> <what the step must not have done>
wait_until_failed() {
  i=0
  while :; do
    state="$(curl -fsS -H "$AUTH" "$API/instances/$1" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
    case "$state" in
      failed) return 0 ;;
      completed) fail "$2" ;;
    esac
    i=$((i + 1))
    [ "$i" -le 60 ] || fail "instance $1 is still '$state' after 60 s (a failed step must fail its instance)"
    sleep 1
  done
}

# A workflow that tries to reach an internal service must fail visibly, not hang and not connect.
check_outbound_guard() {
  echo "Outbound request guard:"
  definition='{"trigger":{"connector_id":"http","trigger_id":"http_request_received","config":{}},"start_at":"probe","steps":{"probe":{"type":"action","connector_id":"http","action_id":"http_request","config":{"url":"http://api:8000/ready","method":"GET"},"next":"end"}}}'
  id="$(create_and_start "smoke_guard_$(date +%s)" "$definition")"
  wait_until_failed "$id" "a call to the internal API service succeeded; the outbound guard is not working"

  curl -fsS -H "$AUTH" "$API/instances/$id/steps" | "$PY" -c '
import json, sys
errors = [s.get("error_details") or "" for s in json.load(sys.stdin)]
assert any("Blocked outbound request" in e for e in errors), "no blocked-request reason in %r" % (errors,)
' || fail "instance $id failed, but not because the request was blocked"
  echo "  ok: a call to an internal service fails with the reason shown"
}

# A stored credential is never returned by the API, yet the worker still gets it decrypted when a step runs.
# The step connects to the stack's own database through the connection: the outbound guard refuses it, and
# the reason names the host, which only happens if the stored (encrypted) string was decrypted and parsed.
check_credentials() {
  echo "Connection credentials:"
  secret="postgresql://smoke:smoke-secret-$(date +%s)@postgres:5432/none"
  cresp="$(curl -fsS -X POST "$API/connections" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"connector_id\": \"postgresql\", \"name\": \"smoke_conn_$(date +%s)\", \"config\": {\"connection_string\": \"$secret\"}}")" \
    || fail "could not create a connection"
  cid="$(printf '%s' "$cresp" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["connection_id"])')"

  shown="$(curl -fsS -H "$AUTH" "$API/connections/$cid")" || fail "could not read connection $cid"
  case "$shown" in *smoke-secret-*) fail "the API returned a stored credential: $shown" ;; esac
  printf '%s' "$shown" | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
assert d["config"] == {} and d["secrets_set"] == ["connection_string"], d
' || fail "connection $cid should show no secret value and list connection_string as set: $shown"
  case "$(curl -fsS -H "$AUTH" "$API/connections")" in *smoke-secret-*) fail "the connection list returned a stored credential" ;; esac
  echo "  ok: the API does not return a stored credential"

  definition="{\"trigger\":{\"connector_id\":\"http\",\"trigger_id\":\"http_request_received\",\"config\":{}},\"start_at\":\"probe\",\"steps\":{\"probe\":{\"type\":\"action\",\"connector_id\":\"postgresql\",\"action_id\":\"postgresql_query\",\"connection_id\":\"$cid\",\"config\":{\"query\":\"SELECT 1\"},\"next\":\"end\"}}}"
  id="$(create_and_start "smoke_credentials_$(date +%s)" "$definition")"
  wait_until_failed "$id" "a query to the internal database succeeded; the outbound guard is not working"
  steps="$(curl -fsS -H "$AUTH" "$API/instances/$id/steps")"
  printf '%s' "$steps" | "$PY" -c '
import json, sys
errors = [s.get("error_details") or "" for s in json.load(sys.stdin)]
assert any("Blocked outbound" in e and "'postgres'" in e for e in errors), "step did not get the decrypted connection string: %r" % (errors,)
' || fail "instance $id did not run with the decrypted credential: $steps"
  case "$steps$(curl -fsS -H "$AUTH" "$API/instances/$id")" in *smoke-secret-*) fail "the credential leaked into the instance or its steps" ;; esac
  echo "  ok: a step receives the decrypted credential, and it does not leak into the run"
}

# A definition with mistakes is refused when it is saved, with every mistake listed, and nothing is stored.
check_definition_validation() {
  echo "Workflow definition checks:"
  name="smoke_invalid_$(date +%s)"
  definition='{"start_at":"nowhere","steps":{"a":{"type":"action","connector_id":"internal","action_id":"log","config":{},"next":"ghost"},"b":{"type":"branch","condition":{"field":"x","operator":"roughly"},"on_true":"end","on_false":"end"}}}'
  body="$(curl -s -o /tmp/smoke_validation.json -w '%{http_code}' -X POST "$API/workflows" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"name\": \"$name\", \"definition\": $definition}")"
  [ "$body" = "400" ] || fail "an invalid definition was not refused: HTTP $body"
  "$PY" -c '
import json, sys
errors = json.load(open(sys.argv[1]))["validation_errors"]
text = " | ".join(errors)
for needle in ("nowhere", "ghost", "roughly"):
    assert needle in text, "no message about %r in %r" % (needle, errors)
' /tmp/smoke_validation.json || fail "the refusal did not list every mistake: $(cat /tmp/smoke_validation.json)"
  case "$(curl -fsS -H "$AUTH" "$API/workflows")" in *"$name"*) fail "the refused workflow was stored" ;; esac
  rm -f /tmp/smoke_validation.json
  echo "  ok: an invalid definition is refused with every mistake listed"
}

# run_case <quantity> <expected priority> <expected shipping_days>
run_case() {
  quantity="$1"; priority="$2"; days="$3"
  resp="$(curl -fsS -X POST "$API/workflows/order_priority_workflow/run" \
    -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"data\": {\"order\": {\"quantity\": $quantity}}}")" || fail "could not start the workflow"
  id="$(printf '%s' "$resp" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["instance_id"])')"
  echo "quantity=$quantity -> instance $id"

  i=0
  while :; do
    inst="$(curl -fsS -H "$AUTH" "$API/instances/$id")" || fail "could not read instance $id"
    state="$(printf '%s' "$inst" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
    case "$state" in
      completed) break ;;
      failed|cancelled) fail "instance $id ended as $state: $inst" ;;
    esac
    i=$((i + 1))
    [ "$i" -le 60 ] || fail "instance $id still '$state' after 60 s: $inst"
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

  steps="$(curl -fsS -H "$AUTH" "$API/instances/$id/steps")" || fail "could not read steps of $id"
  printf '%s' "$steps" | "$PY" -c '
import json, sys
steps = json.load(sys.stdin)
bad = [s["step_name"] for s in steps if s["status"] != "completed"]
assert steps and not bad, "steps not completed: %r" % (bad,)
' || fail "step executions for $id are not all completed: $steps"
  echo "  completed, priority=$priority, shipping_days=$days"
}

wait_for_health
check_security
check_outbound_guard
check_credentials
check_definition_validation
run_case 150 high 1
run_case 30 normal 5
echo "SMOKE OK"
