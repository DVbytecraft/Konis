#!/usr/bin/env bash
# ============================================================
# KONIS — Installation du cron de backup PostgreSQL
#
# À exécuter en root ou sudo sur le serveur de production.
# Configure une tâche cron quotidienne à 02h00.
#
# Usage :
#   sudo bash backup/setup-cron.sh
# ============================================================

set -euo pipefail

# Chemin absolu du script de backup (doit être accessible depuis cron)
KONIS_DIR="${KONIS_DIR:-/opt/konis}"
BACKUP_SCRIPT="${KONIS_DIR}/backup/backup.sh"
LOG_FILE="/var/log/konis-backup.log"
CRON_JOB="0 2 * * * ${BACKUP_SCRIPT} >> ${LOG_FILE} 2>&1"
CRON_TAG="# KONIS backup automatique"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "[ERROR] Ce script doit être exécuté en root (sudo)."
    exit 1
fi

# Vérifier que le script de backup existe
if [[ ! -f "$BACKUP_SCRIPT" ]]; then
    echo "[ERROR] Script de backup introuvable : $BACKUP_SCRIPT"
    echo "        Vérifiez que KONIS_DIR pointe vers le bon répertoire."
    exit 1
fi

chmod +x "$BACKUP_SCRIPT"

# Créer le fichier de log
touch "$LOG_FILE"
chmod 640 "$LOG_FILE"

# Ajouter le job cron uniquement s'il n'existe pas déjà
CURRENT_CRON=$(crontab -l 2>/dev/null || true)
if echo "$CURRENT_CRON" | grep -qF "$BACKUP_SCRIPT"; then
    echo "[INFO] Le job cron KONIS est déjà installé."
else
    (echo "$CURRENT_CRON"; echo "$CRON_TAG"; echo "$CRON_JOB") | crontab -
    echo "[OK] Job cron installé : backup quotidien à 02h00."
    echo "     Logs : $LOG_FILE"
fi

echo ""
echo "Vérification de la crontab :"
crontab -l | grep -A1 "KONIS" || true
echo ""
echo "Pour tester le backup maintenant :"
echo "  bash $BACKUP_SCRIPT"
