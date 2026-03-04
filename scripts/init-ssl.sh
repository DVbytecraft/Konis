#!/usr/bin/env bash
# ============================================================
# KONIS — Acquisition initiale du certificat SSL Let's Encrypt
#
# À exécuter UNE SEULE FOIS sur le serveur de production,
# APRÈS avoir démarré le service nginx (port 80 accessible).
#
# Prérequis :
#   - Le DNS du domaine pointe vers ce serveur
#   - Le port 80 est ouvert dans le firewall
#   - docker compose est installé
#   - Le fichier .env.prod est rempli (DOMAIN, CERTBOT_EMAIL)
#
# Usage :
#   bash scripts/init-ssl.sh
# ============================================================

set -euo pipefail

# ── Chargement des variables d'environnement ──────────────────────────────
ENV_FILE="${ENV_FILE:-.env.prod}"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[ERROR] Fichier d'environnement '$ENV_FILE' introuvable."
    echo "        Copier .env.prod.example → .env.prod et remplir les valeurs."
    exit 1
fi

# Charger seulement les variables nécessaires
DOMAIN=$(grep -E '^DOMAIN=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")
CERTBOT_EMAIL=$(grep -E '^CERTBOT_EMAIL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

if [[ -z "$DOMAIN" ]]; then
    echo "[ERROR] DOMAIN n'est pas défini dans $ENV_FILE"
    exit 1
fi
if [[ -z "$CERTBOT_EMAIL" ]]; then
    echo "[ERROR] CERTBOT_EMAIL n'est pas défini dans $ENV_FILE"
    exit 1
fi

echo "========================================================"
echo " KONIS — Acquisition certificat SSL Let's Encrypt"
echo " Domaine  : $DOMAIN"
echo " Email    : $CERTBOT_EMAIL"
echo "========================================================"

# ── Étape 1 : vérification que nginx est démarré et répond ────────────────
echo ""
echo "[1/4] Vérification que nginx répond sur le port 80..."
if ! curl -sf --max-time 5 "http://${DOMAIN}/.well-known/acme-challenge/test" > /dev/null 2>&1; then
    # 404 est acceptable (le fichier n'existe pas encore) — l'important est que nginx répond
    HTTP_CODE=$(curl -o /dev/null -sw "%{http_code}" --max-time 5 "http://${DOMAIN}/" 2>/dev/null || true)
    if [[ "$HTTP_CODE" == "000" ]]; then
        echo "[ERROR] nginx ne répond pas sur http://${DOMAIN}/"
        echo "        Vérifiez que le service nginx est démarré :"
        echo "        docker compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d nginx"
        exit 1
    fi
fi
echo "        nginx répond correctement."

# ── Étape 2 : vérification DNS ────────────────────────────────────────────
echo ""
echo "[2/4] Vérification de la résolution DNS pour $DOMAIN..."
RESOLVED_IP=$(dig +short "$DOMAIN" | tail -1)
SERVER_IP=$(curl -sf --max-time 5 https://api.ipify.org 2>/dev/null || echo "inconnu")
if [[ -z "$RESOLVED_IP" ]]; then
    echo "[WARN] Impossible de résoudre $DOMAIN via DNS."
    echo "       Vérifiez que l'entrée DNS A/AAAA pointe vers ce serveur ($SERVER_IP)."
    read -rp "       Continuer quand même ? (o/N) " confirm
    [[ "$confirm" =~ ^[oO]$ ]] || exit 1
else
    echo "       $DOMAIN → $RESOLVED_IP (IP serveur : $SERVER_IP)"
fi

# ── Étape 3 : acquisition du certificat ──────────────────────────────────
echo ""
echo "[3/4] Acquisition du certificat Let's Encrypt..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" run --rm certbot \
    certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --email "$CERTBOT_EMAIL" \
    --agree-tos \
    --no-eff-email \
    --domain "$DOMAIN" \
    --non-interactive

echo "       Certificat acquis avec succès."

# ── Étape 4 : rechargement de nginx avec la config HTTPS ─────────────────
echo ""
echo "[4/4] Rechargement de nginx avec le certificat..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec nginx nginx -s reload

echo ""
echo "========================================================"
echo " SUCCÈS : HTTPS opérationnel sur https://$DOMAIN"
echo ""
echo " Prochaines étapes :"
echo "  - Démarrer tous les services : docker compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d"
echo "  - Configurer le backup auto   : bash backup/setup-cron.sh"
echo "  - Vérifier les headers HTTPS  : curl -I https://$DOMAIN/api/health/"
echo "========================================================"
