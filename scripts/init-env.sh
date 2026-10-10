#!/bin/sh
# Create .env from .env.example with freshly generated secrets.
#
#   sh scripts/init-env.sh           # refuses to overwrite an existing .env
#   sh scripts/init-env.sh --force   # replace it
set -eu
cd "$(dirname "$0")/.."

if [ -f .env ] && [ "${1:-}" != "--force" ]; then
  echo ".env already exists; pass --force to replace it." >&2
  exit 1
fi

rand() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
    return
  fi
  for py in python3 python; do
    if "$py" -c 'import secrets' >/dev/null 2>&1; then
      "$py" -c 'import secrets; print(secrets.token_hex(24))'
      return
    fi
  done
  echo "need openssl or python to generate secrets" >&2
  exit 1
}

value() {
  grep "^$1=" .env.example | head -1 | cut -d= -f2-
}

API_KEY="$(rand)"
PG_PASSWORD="$(rand)"
MQ_PASSWORD="$(rand)"
REDIS_PASSWORD="$(rand)"
PG_USER="$(value POSTGRES_USER)"
PG_DB="$(value POSTGRES_DB)"
MQ_USER="$(value RABBITMQ_DEFAULT_USER)"

sed \
  -e "s|^API_KEY=.*|API_KEY=$API_KEY|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$PG_PASSWORD|" \
  -e "s|^DATABASE_URL=.*|DATABASE_URL=postgresql://$PG_USER:$PG_PASSWORD@postgres/$PG_DB|" \
  -e "s|^RABBITMQ_DEFAULT_PASS=.*|RABBITMQ_DEFAULT_PASS=$MQ_PASSWORD|" \
  -e "s|^RABBITMQ_URL=.*|RABBITMQ_URL=amqp://$MQ_USER:$MQ_PASSWORD@rabbitmq:5672/|" \
  -e "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=$REDIS_PASSWORD|" \
  -e "s|^REDIS_URL=.*|REDIS_URL=redis://:$REDIS_PASSWORD@redis:6379/0|" \
  .env.example > .env
chmod 600 .env 2>/dev/null || true

echo "Created .env with generated secrets."
echo "API key (enter it in the UI, or send 'Authorization: Bearer <key>'):"
echo "  $API_KEY"
