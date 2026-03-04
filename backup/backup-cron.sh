#!/bin/sh
# ============================================================
# KONIS — Backup PostgreSQL automatique (container interne)
#
# Exécuté par le service backup-cron dans docker-compose.prod.yml.
# Tourne en boucle infinie, backup quotidien à minuit.
#
# Variables requises (injectées par docker-compose) :
#   POSTGRES_USER, POSTGRES_DB, PGPASSWORD
# Volume monté : /backups (= volume postgres_backups)
# ============================================================
set -e

BACKUP_DIR="/backups"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DB_HOST="${DB_HOST:-db}"

trap exit TERM INT

while :; do
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    FINAL="${BACKUP_DIR}/konis_${TIMESTAMP}.sql.gz"
    TMPFILE="${FINAL}.tmp"

    echo "[$(date -Iseconds)] [BACKUP] Démarrage → ${FINAL}"

    if pg_dump \
        -h "${DB_HOST}" \
        -U "${POSTGRES_USER}" \
        "${POSTGRES_DB}" \
        | gzip -9 > "${TMPFILE}"; then
        mv "${TMPFILE}" "${FINAL}"
        echo "[$(date -Iseconds)] [BACKUP] OK : ${FINAL} ($(du -sh "${FINAL}" | cut -f1))"
    else
        rm -f "${TMPFILE}"
        echo "[$(date -Iseconds)] [BACKUP] ERREUR : pg_dump a échoué !"
    fi

    # Rotation : supprimer les backups plus vieux que RETENTION_DAYS jours
    DELETED=$(find "${BACKUP_DIR}" -name "konis_*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete 2>/dev/null | wc -l)
    if [ "${DELETED}" -gt 0 ]; then
        echo "[$(date -Iseconds)] [BACKUP] ${DELETED} ancien(s) backup(s) supprimé(s) (>${RETENTION_DAYS}j)"
    fi

    # Pause 24h (interruptible par SIGTERM)
    sleep 86400 &
    wait $!
done
