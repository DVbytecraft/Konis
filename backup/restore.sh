#!/usr/bin/env bash
# ============================================================
# KONIS — Restauration d'un backup PostgreSQL
#
# ATTENTION : restaurer écrase complètement la base existante.
#             Toujours créer un backup AVANT de restaurer.
#
# Usage :
#   bash backup/restore.sh /opt/konis/backups/konis_20260224_020001.sql.gz
# ============================================================

set -euo pipefail

DB_CONTAINER="${DB_CONTAINER:-konis_db_prod}"
POSTGRES_USER="${POSTGRES_USER:-konis}"
POSTGRES_DB="${POSTGRES_DB:-konis_db}"

BACKUP_FILE="${1:-}"
if [[ -z "$BACKUP_FILE" ]]; then
    echo "Usage : bash backup/restore.sh <fichier_backup.sql.gz>"
    echo ""
    echo "Backups disponibles :"
    ls -lh /opt/konis/backups/konis_*.sql.gz 2>/dev/null || echo "  (aucun trouvé dans /opt/konis/backups/)"
    exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "[ERROR] Fichier introuvable : $BACKUP_FILE"
    exit 1
fi

# Vérification de l'intégrité
echo "[RESTORE] Vérification de l'intégrité du backup..."
gzip -t "$BACKUP_FILE" || { echo "[ERROR] Backup corrompu."; exit 1; }

echo ""
echo "========================================================"
echo " ATTENTION : Cette opération va ÉCRASER la base $POSTGRES_DB"
echo " Fichier   : $BACKUP_FILE"
echo " Conteneur : $DB_CONTAINER"
echo "========================================================"
read -rp " Confirmer la restauration ? (tapez 'OUI' pour confirmer) : " CONFIRM
if [[ "$CONFIRM" != "OUI" ]]; then
    echo "Annulé."
    exit 0
fi

# Créer un backup de sécurité avant restauration
SAFETY_BACKUP="/opt/konis/backups/konis_pre_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
echo "[RESTORE] Backup de sécurité → $SAFETY_BACKUP"
docker exec "$DB_CONTAINER" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip -9 > "$SAFETY_BACKUP"

echo "[RESTORE] Restauration en cours..."

# Décompresser et restaurer
zcat "$BACKUP_FILE" | docker exec -i "$DB_CONTAINER" psql \
    -U "$POSTGRES_USER" \
    -d postgres \
    -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};" \
    -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};" 2>/dev/null || true

zcat "$BACKUP_FILE" | docker exec -i "$DB_CONTAINER" psql \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --quiet

echo "[RESTORE] Restauration terminée."
echo "[RESTORE] Backup de sécurité pré-restauration : $SAFETY_BACKUP"
echo ""
echo "Redémarrer le backend pour vider les caches :"
echo "  docker compose -f docker-compose.prod.yml --env-file .env.prod restart backend"
