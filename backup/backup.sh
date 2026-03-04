#!/usr/bin/env bash
# ============================================================
# KONIS — Backup PostgreSQL automatisé
#
# Fonctionnement :
#   1. pg_dump via docker exec (sans exposer le port PostgreSQL)
#   2. Compression gzip niveau 9
#   3. Rotation : suppression des backups > RETENTION_DAYS jours
#
# Usage :
#   bash backup/backup.sh             # backup immédiat
#   BACKUP_DIR=/custom bash backup/backup.sh  # répertoire personnalisé
#
# Planification recommandée (via setup-cron.sh) :
#   0 2 * * * /opt/konis/backup/backup.sh >> /var/log/konis-backup.log 2>&1
# ============================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-/opt/konis/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DB_CONTAINER="${DB_CONTAINER:-konis_db_prod}"
POSTGRES_USER="${POSTGRES_USER:-konis}"
POSTGRES_DB="${POSTGRES_DB:-konis_db}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/konis_${TIMESTAMP}.sql.gz"

# ── Préparation du répertoire de backup ───────────────────────────────────
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"  # Répertoire lisible uniquement par root

echo "[$(date -Iseconds)] [BACKUP] Démarrage — ${POSTGRES_DB} → ${BACKUP_FILE}"

# ── Vérification que le conteneur DB tourne ───────────────────────────────
if ! docker inspect "$DB_CONTAINER" --format='{{.State.Running}}' 2>/dev/null | grep -q 'true'; then
    echo "[$(date -Iseconds)] [BACKUP] ERREUR : conteneur $DB_CONTAINER non actif."
    exit 1
fi

# ── Dump + compression atomique (écriture dans un fichier temp) ───────────
TEMP_FILE="${BACKUP_FILE}.tmp"
docker exec "$DB_CONTAINER" pg_dump \
    -U "$POSTGRES_USER" \
    --format=plain \
    --no-password \
    "$POSTGRES_DB" \
    | gzip -9 > "$TEMP_FILE"

# Renommer uniquement si pg_dump + gzip ont réussi (atomique)
mv "$TEMP_FILE" "$BACKUP_FILE"

FILESIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "[$(date -Iseconds)] [BACKUP] Fichier créé : $BACKUP_FILE ($FILESIZE)"

# ── Rotation : suppression des anciens backups ────────────────────────────
DELETED=$(find "$BACKUP_DIR" -name "konis_*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete 2>/dev/null | wc -l)
if [[ "$DELETED" -gt 0 ]]; then
    echo "[$(date -Iseconds)] [BACKUP] $DELETED fichier(s) de plus de ${RETENTION_DAYS} jours supprimé(s)."
fi

# ── Vérification de l'intégrité du backup ────────────────────────────────
if gzip -t "$BACKUP_FILE" 2>/dev/null; then
    echo "[$(date -Iseconds)] [BACKUP] Intégrité vérifiée (gzip -t : OK)."
else
    echo "[$(date -Iseconds)] [BACKUP] ERREUR : le fichier backup est corrompu !"
    rm -f "$BACKUP_FILE"
    exit 1
fi

echo "[$(date -Iseconds)] [BACKUP] Terminé avec succès."
