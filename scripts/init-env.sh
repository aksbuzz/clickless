#!/bin/sh
# Create .env from .env.example with freshly generated secrets.
#
#   sh scripts/init-env.sh             # refuses to overwrite an existing .env
#   sh scripts/init-env.sh --force     # replace it
#   sh scripts/init-env.sh --upgrade   # keep an existing .env and add the SECRETS_KEY it may be missing
set -eu
umask 077
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--upgrade" ]; then
  if [ ! -f .env ]; then
    echo "There is no .env to upgrade; run without arguments to create one." >&2
    exit 1
  fi
  if grep -q '^SECRETS_KEY=.' .env; then
    echo ".env already has a SECRETS_KEY; nothing to do."
    exit 0
  fi
elif [ -f .env ] && [ "${1:-}" != "--force" ]; then
  echo ".env already exists; pass --force to replace it, or --upgrade to only add a missing SECRETS_KEY." >&2
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

# A Fernet key: url-safe base64 of 32 random bytes.
fernet_key() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'
    return
  fi
  for py in python3 python; do
    if "$py" -c 'import base64, os' >/dev/null 2>&1; then
      "$py" -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode(), end="")'
      return
    fi
  done
  echo "need openssl or python to generate secrets" >&2
  exit 1
}

value() {
  grep "^$1=" .env.example | head -1 | cut -d= -f2-
}

SECRETS_KEY="$(fernet_key)"

if [ "${1:-}" = "--upgrade" ]; then
  grep -v '^SECRETS_KEY=' .env > .env.upgrade || true
  printf 'SECRETS_KEY=%s\n' "$SECRETS_KEY" >> .env.upgrade
  mv .env.upgrade .env
  echo "Added SECRETS_KEY to .env. Keep a copy of it: without it stored connection credentials cannot be read."
  echo "If connections already exist, encrypt them now:"
  echo "  docker compose run --rm api python -m src.api.encrypt_connections"
  exit 0
fi

API_KEY="$(rand)"
PG_PASSWORD="$(rand)"
PG_USER="$(value POSTGRES_USER)"
PG_DB="$(value POSTGRES_DB)"

sed \
  -e "s|^API_KEY=.*|API_KEY=$API_KEY|" \
  -e "s|^SECRETS_KEY=.*|SECRETS_KEY=$SECRETS_KEY|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$PG_PASSWORD|" \
  -e "s|^DATABASE_URL=.*|DATABASE_URL=postgresql://$PG_USER:$PG_PASSWORD@postgres/$PG_DB|" \
  .env.example > .env

echo "Created .env with generated secrets."
echo "API key (enter it in the UI, or send 'Authorization: Bearer <key>'):"
echo "  $API_KEY"
echo "SECRETS_KEY encrypts stored connection credentials. Keep a copy of the .env file somewhere safe:"
echo "without this key those credentials cannot be read and would have to be entered again."
