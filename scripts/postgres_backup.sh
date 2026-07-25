#!/bin/sh

set -u

POSTGRES_HOST="${POSTGRES_HOST:-echo-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-echo}"
POSTGRES_USER="${POSTGRES_USER:-echo}"
BACKUP_DIR="${POSTGRES_BACKUP_DIR:-/backups}"
BACKUP_INTERVAL_SECONDS="${POSTGRES_BACKUP_INTERVAL_SECONDS:-86400}"
BACKUP_RETENTION_DAYS="${POSTGRES_BACKUP_RETENTION_DAYS:-7}"

export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

create_backup() {
    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    temporary_path="${BACKUP_DIR}/echo_${timestamp}.dump.tmp"
    backup_path="${BACKUP_DIR}/echo_${timestamp}.dump"

    rm -f "${temporary_path}"
    if ! pg_dump \
        --host="${POSTGRES_HOST}" \
        --port="${POSTGRES_PORT}" \
        --username="${POSTGRES_USER}" \
        --dbname="${POSTGRES_DB}" \
        --format=custom \
        --no-owner \
        --no-privileges \
        --file="${temporary_path}"; then
        rm -f "${temporary_path}"
        echo "PostgreSQL backup failed at ${timestamp}" >&2
        return 1
    fi

    if ! pg_restore --list "${temporary_path}" >/dev/null; then
        rm -f "${temporary_path}"
        echo "PostgreSQL backup validation failed at ${timestamp}" >&2
        return 1
    fi

    mv "${temporary_path}" "${backup_path}"
    find "${BACKUP_DIR}" -type f -name 'echo_*.dump' -mtime "+${BACKUP_RETENTION_DAYS}" -delete
    echo "PostgreSQL backup completed: ${backup_path}"
}

mkdir -p "${BACKUP_DIR}"

if [ "${1:-}" = "once" ]; then
    create_backup
    exit 0
fi

while true; do
    create_backup || true
    sleep "${BACKUP_INTERVAL_SECONDS}"
done
