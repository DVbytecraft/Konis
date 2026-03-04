#!/usr/bin/env bash
# ============================================================
# KONIS — Script de déploiement production
# Usage : ./deploy.sh [--reset-data] [--skip-backup]
#
# Ce script :
#   1. Vérifie les prérequis (.env.prod, Docker, etc.)
#   2. Sauvegarde la base de données (sauf --skip-backup)
#   3. Build les images Docker
#   4. Remet la base à zéro si --reset-data
#   5. Démarre les conteneurs
#   6. Valide que tout fonctionne
# ============================================================

set -euo pipefail

# ── Couleurs ─────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()    { echo -e "${BLUE}[$(date '+%H:%M:%S')] $*${NC}"; }
ok()     { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✓ $*${NC}"; }
warn()   { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠ $*${NC}"; }
error()  { echo -e "${RED}[$(date '+%H:%M:%S')] ✗ $*${NC}" >&2; exit 1; }

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
RESET_DATA=false
SKIP_BACKUP=false

# ── Parsing des arguments ─────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --reset-data)   RESET_DATA=true ;;
    --skip-backup)  SKIP_BACKUP=true ;;
    --help)
      echo "Usage: $0 [--reset-data] [--skip-backup]"
      echo ""
      echo "  --reset-data   Supprime les données de test avant le déploiement"
      echo "  --skip-backup  Ignore la sauvegarde (dangereux, à n'utiliser qu'en premier déploiement)"
      exit 0
      ;;
    *) warn "Argument inconnu : $arg" ;;
  esac
done

# ──────────────────────────────────────────────────────────────
log "=== KONIS — Déploiement production ==="
echo ""

# ── Étape 1 : Vérifications prérequis ────────────────────────
log "Étape 1/6 — Vérification des prérequis..."

[ -f "$ENV_FILE" ] || error "Fichier $ENV_FILE manquant. Copiez .env.prod.example en .env.prod et remplissez les valeurs."

# Vérifier les variables critiques
source "$ENV_FILE"
[ -n "${DJANGO_SECRET_KEY:-}" ]    || error "DJANGO_SECRET_KEY non défini dans $ENV_FILE"
[ -n "${POSTGRES_PASSWORD:-}" ]    || error "POSTGRES_PASSWORD non défini dans $ENV_FILE"
[ -n "${DJANGO_ALLOWED_HOSTS:-}" ] || error "DJANGO_ALLOWED_HOSTS non défini dans $ENV_FILE"

# Vérifier que les valeurs par défaut insécurisées n'ont pas été gardées
[[ "${DJANGO_SECRET_KEY}" == *"CHANGER_MOI"* ]] && error "DJANGO_SECRET_KEY contient encore la valeur par défaut. Générez une vraie clé secrète."
[[ "${POSTGRES_PASSWORD}" == *"CHANGER_MOI"* ]] && error "POSTGRES_PASSWORD contient encore la valeur par défaut."

command -v docker >/dev/null 2>&1 || error "Docker n'est pas installé."
docker info >/dev/null 2>&1       || error "Docker daemon n'est pas démarré."

ok "Prérequis validés."

# ── Étape 2 : Sauvegarde ─────────────────────────────────────
if [ "$SKIP_BACKUP" = false ]; then
  log "Étape 2/6 — Sauvegarde de la base de données..."

  BACKUP_DIR="./backups"
  mkdir -p "$BACKUP_DIR"

  # Vérifier si le conteneur DB tourne déjà (pas le premier déploiement)
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "konis_db_prod"; then
    BACKUP_FILE="$BACKUP_DIR/konis_prod_$(date +%Y%m%d_%H%M%S).sql"
    docker exec konis_db_prod pg_dump \
      -U "${POSTGRES_USER}" \
      -d "${POSTGRES_DB}" \
      --no-password \
      -F c \
      -f /tmp/backup.dump 2>/dev/null && \
    docker cp konis_db_prod:/tmp/backup.dump "$BACKUP_FILE" && \
    ok "Backup créé : $BACKUP_FILE" || \
    warn "Backup échoué (peut-être premier déploiement — continuons)."
  else
    warn "Conteneur DB non trouvé — premier déploiement, pas de backup nécessaire."
  fi
else
  warn "Étape 2/6 — Sauvegarde ignorée (--skip-backup)."
fi

# ── Étape 3 : Build des images ───────────────────────────────
log "Étape 3/6 — Build des images Docker..."

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build --no-cache

ok "Images construites."

# ── Étape 4 : Reset des données (optionnel) ──────────────────
if [ "$RESET_DATA" = true ]; then
  log "Étape 4/6 — Reset TOTAL des données (full_reset)..."

  warn "ATTENTION : Suppression de TOUTES les données (ventes, stocks, produits,"
  warn "boutiques, usines, utilisateurs). Seul le superadmin désigné est conservé."
  warn "Utilisez scripts/reset_prod_data.sh pour un contrôle plus fin (superuser, rotation JWT, etc.)."
  read -rp "Tapez 'RESET-TOTAL' pour continuer : " confirm
  [ "$confirm" = "RESET-TOTAL" ] || error "Opération annulée."

  # Démarrer uniquement la DB pour la réinitialisation
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d db
  sleep 5

  # Exécuter full_reset dans un conteneur backend temporaire
  # Note : sans --superuser, prend automatiquement le premier is_superuser=True
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" run --rm backend \
    sh -c "python manage.py migrate --noinput && python manage.py full_reset --confirm"

  # Valider l'état post-reset
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" run --rm backend \
    python manage.py check_db --after-reset --sequences 2>/dev/null || \
    warn "check_db a signalé des avertissements — vérifiez les logs."

  ok "Reset total terminé."
else
  log "Étape 4/6 — Reset des données ignoré (pas de --reset-data)."
fi

# ── Étape 5 : Démarrage des conteneurs ───────────────────────
log "Étape 5/6 — Démarrage des conteneurs..."

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --remove-orphans

# Attendre que le backend soit prêt (max 60 secondes)
log "Attente du démarrage du backend..."
for i in $(seq 1 12); do
  if docker exec konis_backend_prod curl -sf http://localhost:8000/api/health/ >/dev/null 2>&1; then
    ok "Backend opérationnel."
    break
  fi
  [ "$i" -eq 12 ] && error "Le backend n'a pas démarré dans les 60 secondes. Vérifiez : docker logs konis_backend_prod"
  sleep 5
done

ok "Conteneurs démarrés."

# ── Étape 6 : Validation ─────────────────────────────────────
log "Étape 6/6 — Validation du déploiement..."

# Health check
HEALTH=$(docker exec konis_backend_prod curl -sf http://localhost:8000/api/health/ 2>/dev/null || echo "ERREUR")
if echo "$HEALTH" | grep -q '"db"'; then
  ok "Health check OK : $HEALTH"
else
  warn "Health check inattendu : $HEALTH"
fi

# Vérification migrations
docker exec konis_backend_prod python manage.py migrate --check 2>/dev/null && \
  ok "Migrations : à jour." || \
  warn "Des migrations en attente ont été détectées."

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✓ KONIS déployé avec succès en production !${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Application : ${BLUE}http://${DJANGO_ALLOWED_HOSTS%%,*}${NC}"
echo -e "  Logs        : ${BLUE}docker compose -f $COMPOSE_FILE logs -f${NC}"
echo -e "  Arrêt       : ${BLUE}docker compose -f $COMPOSE_FILE down${NC}"
echo ""
