#!/bin/sh

set -eu

backup_path="${1:-}"
if [ -z "${backup_path}" ] || [ ! -f "${backup_path}" ]; then
    echo "Usage: CONFIRM_POSTGRES_RESTORE=echo sh /scripts/postgres_restore.sh /backups/<file>.dump" >&2
    exit 2
fi

if [ "${CONFIRM_POSTGRES_RESTORE:-}" != "echo" ]; then
    echo "Restore refused: set CONFIRM_POSTGRES_RESTORE=echo after stopping the backend and backup service." >&2
    exit 2
fi

POSTGRES_HOST="${POSTGRES_HOST:-echo-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-echo}"
POSTGRES_USER="${POSTGRES_USER:-echo}"
export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

pg_restore --list "${backup_path}" >/dev/null

dropdb \
    --host="${POSTGRES_HOST}" \
    --port="${POSTGRES_PORT}" \
    --username="${POSTGRES_USER}" \
    --force \
    --if-exists \
    "${POSTGRES_DB}"

createdb \
    --host="${POSTGRES_HOST}" \
    --port="${POSTGRES_PORT}" \
    --username="${POSTGRES_USER}" \
    "${POSTGRES_DB}"

pg_restore \
    --host="${POSTGRES_HOST}" \
    --port="${POSTGRES_PORT}" \
    --username="${POSTGRES_USER}" \
    --dbname="${POSTGRES_DB}" \
    --exit-on-error \
    --no-owner \
    --no-privileges \
    "${backup_path}"

echo "PostgreSQL restore completed from ${backup_path}"
