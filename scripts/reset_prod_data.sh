#!/usr/bin/env bash
# ============================================================
# KONIS — Reset total avant production (full_reset)
#
# Usage :
#   ./scripts/reset_prod_data.sh                      # production (docker-compose.prod.yml)
#   ./scripts/reset_prod_data.sh --env=dev            # développement (docker-compose.yml)
#   ./scripts/reset_prod_data.sh --superuser=raphael  # spécifier le superadmin
#   ./scripts/reset_prod_data.sh --skip-jwt-rotate    # ne pas régénérer la SECRET_KEY
#   ./scripts/reset_prod_data.sh --dry-run            # simulation seule, rien n'est modifié
#
# Ce que ce script fait (dans l'ordre) :
#   1. Vérifie les prérequis (Docker, env, superadmin)
#   2. Arrête le trafic (nginx + frontend) en prod
#   3. Backup PostgreSQL au format .dump
#   4. Dry-run full_reset (audit sans modification)
#   5. Exécute full_reset --confirm (suppression totale + séquences à 1)
#   6. Rotation de DJANGO_SECRET_KEY (invalide immédiatement tous les JWT)
#   7. Valide l'état post-reset avec check_db --after-reset --sequences
#   8. Rebuild + restart frontend/nginx
#   9. Validation finale via /api/health/
#
# Différence avec l'ancien reset_prod_data.sh :
#   Ancien → appelle reset_for_production (reset PARTIEL, conserve users/produits/lieux)
#   Nouveau → appelle full_reset (reset TOTAL, conserve uniquement le superadmin)
# ============================================================
set -euo pipefail

# ── Couleurs ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ts()    { date '+%H:%M:%S'; }
log()   { echo -e "${BLUE}[$(ts)] $*${NC}"; }
ok()    { echo -e "${GREEN}[$(ts)] ✓ $*${NC}"; }
warn()  { echo -e "${YELLOW}[$(ts)] ⚠ $*${NC}"; }
info()  { echo -e "${CYAN}[$(ts)] → $*${NC}"; }
die()   { echo -e "${RED}[$(ts)] ✗ $*${NC}" >&2; exit 1; }
step()  { echo ""; echo -e "${BOLD}${BLUE}══ $* ══${NC}"; }

# ── Defaults ─────────────────────────────────────────────────────────────────
ENV="prod"
SUPERUSER=""
SKIP_JWT_ROTATE=false
DRY_RUN=false

# ── Parsing arguments ─────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --env=dev)            ENV="dev" ;;
    --env=prod)           ENV="prod" ;;
    --superuser=*)        SUPERUSER="${arg#--superuser=}" ;;
    --skip-jwt-rotate)    SKIP_JWT_ROTATE=true ;;
    --dry-run)            DRY_RUN=true ;;
    --help|-h)
      sed -n '3,20p' "$0" | sed 's/^# \{0,2\}//'
      exit 0
      ;;
    *) warn "Argument inconnu ignoré : $arg" ;;
  esac
done

# ── Configuration selon l'environnement ──────────────────────────────────────
if [ "$ENV" = "prod" ]; then
  COMPOSE_FILE="docker-compose.prod.yml"
  ENV_FILE=".env.prod"
  BACKEND_CONTAINER="konis_backend_prod"
  DB_CONTAINER="konis_db_prod"
  FRONTEND_CONTAINER="konis_frontend_prod"
  NGINX_CONTAINER="konis_nginx_prod"
  HEALTH_URL="http://localhost:8000/api/health/"
else
  COMPOSE_FILE="docker-compose.yml"
  ENV_FILE=".env"
  BACKEND_CONTAINER="konis_backend"
  DB_CONTAINER="konis_db"
  FRONTEND_CONTAINER="konis_frontend"
  NGINX_CONTAINER=""
  HEALTH_URL="http://localhost:8000/api/health/"
fi

BACKUP_DIR="${BACKUP_DIR:-./backups}"
SUPERUSER_FLAG=""
[ -n "$SUPERUSER" ] && SUPERUSER_FLAG="--superuser=${SUPERUSER}"

# ── En-tête ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${RED}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${RED}${BOLD}║      KONIS — RESET TOTAL AVANT PRODUCTION            ║${NC}"
echo -e "${RED}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Environnement   : ${BOLD}${ENV}${NC}"
echo -e "  Compose file    : ${BOLD}${COMPOSE_FILE}${NC}"
echo -e "  Superadmin      : ${BOLD}${SUPERUSER:-automatique (premier is_superuser=True)}${NC}"
echo -e "  Rotation JWT    : ${BOLD}$( [ "$SKIP_JWT_ROTATE" = true ] && echo "ignorée" || echo "oui (nouvelle SECRET_KEY)" )${NC}"
echo -e "  Mode dry-run    : ${BOLD}${DRY_RUN}${NC}"
echo ""
warn "Ce script supprime TOUTES les données sauf le superadministrateur."
warn "Un backup sera créé automatiquement avant toute modification."
echo ""

if [ "$DRY_RUN" = true ]; then
  echo -e "${YELLOW}${BOLD}MODE DRY-RUN — Aucune donnée ne sera supprimée.${NC}"
  echo ""
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Étape 1 — Prérequis
# ═══════════════════════════════════════════════════════════════════════════════
step "Étape 1/9 — Vérification des prérequis"

command -v docker >/dev/null 2>&1  || die "Docker n'est pas installé."
docker info >/dev/null 2>&1        || die "Docker daemon non démarré."
[ -f "$COMPOSE_FILE" ]             || die "Fichier $COMPOSE_FILE introuvable. Lancez ce script depuis la racine du projet."
[ -f "$ENV_FILE" ]                 || die "$ENV_FILE introuvable. Copiez .env.example en $ENV_FILE."

# Charger les variables d'env (silencieux — on ne les affiche pas)
set -o allexport
source "$ENV_FILE" 2>/dev/null || true
set +o allexport

# Vérifier que le backend tourne
docker ps --format '{{.Names}}' | grep -q "^${BACKEND_CONTAINER}$" \
  || die "Conteneur ${BACKEND_CONTAINER} non démarré. Lancez d'abord : docker compose -f ${COMPOSE_FILE} up -d"

# Identifier le superadmin
if [ -n "$SUPERUSER" ]; then
  FOUND=$(docker exec "$BACKEND_CONTAINER" python manage.py shell -c "
from core.models import CustomUser
try:
    u = CustomUser.objects.get(username='${SUPERUSER}', is_superuser=True)
    print(f'OK:{u.username}:id={u.pk}')
except CustomUser.DoesNotExist:
    print('NOT_FOUND')
" 2>/dev/null || echo "ERROR")
  [[ "$FOUND" == OK:* ]] || die "Superuser '${SUPERUSER}' (is_superuser=True) introuvable. Vérifiez le username."
  info "Superadmin identifié : $FOUND"
else
  FOUND=$(docker exec "$BACKEND_CONTAINER" python manage.py shell -c "
from core.models import CustomUser
u = CustomUser.objects.filter(is_superuser=True).order_by('date_joined').first()
if u:
    print(f'OK:{u.username}:id={u.pk}')
else:
    print('NONE')
" 2>/dev/null || echo "ERROR")
  if [[ "$FOUND" == NONE* ]] || [[ "$FOUND" == ERROR* ]]; then
    die "Aucun superadministrateur trouvé. Créez-en un : docker exec -it ${BACKEND_CONTAINER} python manage.py createsuperuser"
  fi
  info "Superadmin sélectionné automatiquement : $FOUND"
  ADMIN_USERNAME=$(echo "$FOUND" | cut -d: -f2)
  SUPERUSER_FLAG="--superuser=${ADMIN_USERNAME}"
fi

ok "Prérequis validés."

# ═══════════════════════════════════════════════════════════════════════════════
# Étape 2 — Confirmation
# ═══════════════════════════════════════════════════════════════════════════════
step "Étape 2/9 — Confirmation"

if [ "$DRY_RUN" = false ]; then
  echo ""
  echo -e "${RED}${BOLD}  ATTENTION — OPÉRATION IRRÉVERSIBLE${NC}"
  echo ""
  echo "  Ce script va :"
  echo "    • Supprimer TOUTES les données (ventes, stocks, produits, usines,"
  echo "      boutiques, utilisateurs, entreprises, tokens JWT)"
  echo "    • Conserver UNIQUEMENT le superadministrateur"
  echo "    • Réinitialiser TOUTES les séquences PostgreSQL à 1"
  [ "$SKIP_JWT_ROTATE" = false ] && echo "    • Générer une nouvelle DJANGO_SECRET_KEY (invalide tous les JWT)"
  echo ""
  echo -e "  ${YELLOW}Effectuez un backup AVANT de confirmer.${NC}"
  echo "  (Ce script en crée un automatiquement à l'étape suivante.)"
  echo ""
  read -rp "  Tapez 'RESET-TOTAL' pour confirmer : " USER_CONFIRM
  [ "$USER_CONFIRM" = "RESET-TOTAL" ] || { echo "  Opération annulée."; exit 0; }
  echo ""
fi

ok "Confirmation reçue."

# ═══════════════════════════════════════════════════════════════════════════════
# Étape 3 — Arrêt du trafic (prod uniquement)
# ═══════════════════════════════════════════════════════════════════════════════
step "Étape 3/9 — Arrêt du trafic entrant"

if [ "$ENV" = "prod" ] && [ "$DRY_RUN" = false ]; then
  SERVICES_TO_STOP=""
  docker ps --format '{{.Names}}' | grep -q "^${NGINX_CONTAINER}$"    && SERVICES_TO_STOP="nginx"
  docker ps --format '{{.Names}}' | grep -q "^${FRONTEND_CONTAINER}$" && SERVICES_TO_STOP="${SERVICES_TO_STOP} frontend"

  if [ -n "$SERVICES_TO_STOP" ]; then
    # shellcheck disable=SC2086
    docker compose -f "$COMPOSE_FILE" stop $SERVICES_TO_STOP
    ok "Trafic coupé : nginx + frontend arrêtés."
  else
    info "nginx/frontend déjà arrêtés."
  fi
else
  info "Dev ou dry-run : arrêt du trafic ignoré."
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Étape 4 — Backup PostgreSQL
# ═══════════════════════════════════════════════════════════════════════════════
step "Étape 4/9 — Backup PostgreSQL"

mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_CONTAINER_PATH="/tmp/konis_backup_${TIMESTAMP}.dump"
BACKUP_HOST_PATH="${BACKUP_DIR}/konis_${ENV}_${TIMESTAMP}.dump"

if [ "$DRY_RUN" = false ]; then
  # Lire les variables DB depuis l'env chargé ou utiliser les defaults dev
  DB_USER="${POSTGRES_USER:-konis_user}"
  DB_NAME="${POSTGRES_DB:-konis_db}"

  docker exec "$DB_CONTAINER" pg_dump \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -F c \
    -f "$BACKUP_CONTAINER_PATH"

  docker cp "${DB_CONTAINER}:${BACKUP_CONTAINER_PATH}" "$BACKUP_HOST_PATH"
  docker exec "$DB_CONTAINER" rm -f "$BACKUP_CONTAINER_PATH"

  BACKUP_SIZE=$(du -sh "$BACKUP_HOST_PATH" 2>/dev/null | cut -f1 || echo "?")
  ok "Backup créé : ${BACKUP_HOST_PATH} (${BACKUP_SIZE})"
  info "Pour restaurer : ./scripts/restore_db.sh ${BACKUP_HOST_PATH}"
else
  warn "Dry-run : backup ignoré."
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Étape 5 — Dry-run full_reset (audit)
# ═══════════════════════════════════════════════════════════════════════════════
step "Étape 5/9 — Dry-run (audit de ce qui sera supprimé)"

docker exec "$BACKEND_CONTAINER" python manage.py \
  full_reset --dry-run $SUPERUSER_FLAG

echo ""
if [ "$DRY_RUN" = true ]; then
  ok "Dry-run terminé. Relancez sans --dry-run pour exécuter le reset."
  echo ""
  exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Étape 6 — Reset total
# ═══════════════════════════════════════════════════════════════════════════════
step "Étape 6/9 — Exécution du reset total"

docker exec "$BACKEND_CONTAINER" python manage.py \
  full_reset $SUPERUSER_FLAG --confirm

ok "Reset total exécuté."

# ═══════════════════════════════════════════════════════════════════════════════
# Étape 7 — Rotation de la SECRET_KEY (invalide tous les JWT non trackés)
# ═══════════════════════════════════════════════════════════════════════════════
step "Étape 7/9 — Rotation JWT (SECRET_KEY)"

if [ "$SKIP_JWT_ROTATE" = true ]; then
  warn "Rotation JWT ignorée (--skip-jwt-rotate)."
  warn "Les tokens access existants resteront valides pendant leur durée de vie (10 min)."
else
  info "Génération d'une nouvelle DJANGO_SECRET_KEY..."

  NEW_KEY=$(docker exec "$BACKEND_CONTAINER" python -c \
    "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")

  if [ -z "$NEW_KEY" ]; then
    warn "Impossible de générer une nouvelle clé. Rotation ignorée."
  else
    # Remplacement dans le fichier env (si la variable existe)
    if grep -q "^DJANGO_SECRET_KEY=" "$ENV_FILE" 2>/dev/null; then
      # Sauvegarde du fichier env avant modification
      cp "$ENV_FILE" "${ENV_FILE}.bak_${TIMESTAMP}"
      sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${NEW_KEY}|" "$ENV_FILE"
      ok "DJANGO_SECRET_KEY mise à jour dans ${ENV_FILE}."
      info "Ancienne config sauvegardée : ${ENV_FILE}.bak_${TIMESTAMP}"
    else
      warn "DJANGO_SECRET_KEY absent de ${ENV_FILE}. Mettez-la à jour manuellement :"
      echo "      DJANGO_SECRET_KEY=${NEW_KEY}"
    fi

    # Redémarrer le backend pour appliquer la nouvelle clé
    docker compose -f "$COMPOSE_FILE" restart backend 2>/dev/null || \
      docker restart "$BACKEND_CONTAINER"

    # Attendre le redémarrage
    info "Attente du redémarrage du backend..."
    for i in $(seq 1 12); do
      if docker exec "$BACKEND_CONTAINER" curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        ok "Backend redémarré avec la nouvelle SECRET_KEY."
        break
      fi
      [ "$i" -eq 12 ] && die "Backend non redémarré après 60s. Vérifiez : docker logs ${BACKEND_CONTAINER}"
      sleep 5
    done
    ok "Tous les tokens JWT sont maintenant invalidés."
  fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Étape 8 — Validation post-reset
# ═══════════════════════════════════════════════════════════════════════════════
step "Étape 8/9 — Validation de la base de données"

docker exec "$BACKEND_CONTAINER" python manage.py \
  check_db --after-reset --sequences

# check_db retourne exit code 1 si des problèmes sont détectés (set -e lèvera l'erreur)
ok "Base de données validée."

# ═══════════════════════════════════════════════════════════════════════════════
# Étape 9 — Restart frontend + nginx
# ═══════════════════════════════════════════════════════════════════════════════
step "Étape 9/9 — Redémarrage du frontend"

if [ "$ENV" = "prod" ]; then
  info "Rebuild du frontend (purge cache Next.js)..."
  docker compose -f "$COMPOSE_FILE" build --no-cache frontend 2>/dev/null || \
    warn "Build frontend échoué — démarrage avec l'image existante."
  docker compose -f "$COMPOSE_FILE" up -d frontend nginx
  ok "Frontend et nginx redémarrés."
else
  # Dev : supprimer le cache .next et redémarrer
  NEXTJS_CACHE="./frontend/.next"
  if [ -d "$NEXTJS_CACHE" ]; then
    rm -rf "$NEXTJS_CACHE"
    ok "Cache Next.js supprimé : ${NEXTJS_CACHE}"
  fi
  docker compose -f "$COMPOSE_FILE" restart frontend 2>/dev/null || \
    docker restart "$FRONTEND_CONTAINER" 2>/dev/null || \
    warn "Frontend non démarré — redémarrez-le manuellement."
  ok "Frontend redémarré."
fi

# ── Validation finale via health ──────────────────────────────────────────────
info "Validation health check final..."
sleep 3
HEALTH_RESPONSE=$(docker exec "$BACKEND_CONTAINER" \
  curl -sf "$HEALTH_URL" 2>/dev/null || echo '{"status":"error"}')

if echo "$HEALTH_RESPONSE" | grep -q '"status":"ok"'; then
  ok "Health check OK : $HEALTH_RESPONSE"
else
  warn "Health check inattendu : $HEALTH_RESPONSE"
fi

# ── Résumé ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║     ✅ RESET TOTAL TERMINÉ AVEC SUCCÈS               ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Backup sauvegardé  : ${BACKUP_HOST_PATH}"
echo ""
echo "  Prochaines étapes :"
echo "    1. Connectez-vous avec le superadministrateur"
echo "    2. Créez l'entreprise via l'Admin Django ou l'API"
echo "    3. Créez les usines et boutiques"
echo "    4. Créez les comptes utilisateurs opérationnels"
echo "    5. Saisissez les catégories et produits"
echo ""
echo "  Vérification rapide :"
if [ "$ENV" = "prod" ]; then
  echo "    curl https://\${VOTRE_DOMAINE}/api/health/"
else
  echo "    curl http://localhost:8000/api/health/"
fi
echo "    docker exec ${BACKEND_CONTAINER} python manage.py check_db --after-reset"
echo ""
