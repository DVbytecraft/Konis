# KONIS — Guide de déploiement production (Docker)

## Architecture de production

```
Internet
    │
    ▼
[Nginx :80]  ← reverse proxy unique
    │
    ├── /api/*        → [Backend Django/Gunicorn :8000]
    ├── /admin/*      → [Backend Django/Gunicorn :8000]
    ├── /static/*     → [Backend Django/Gunicorn :8000]  (WhiteNoise)
    └── /*            → [Frontend Next.js :3000]
                              │
                              └── SSR calls → [Backend Django/Gunicorn :8000]
                                                        │
                                                        └── [PostgreSQL :5432]  (interne)
```

---

## Fichiers créés pour la production

| Fichier | Rôle |
|---|---|
| `Dockerfile.prod` | Image Docker backend (multi-stage, user non-root) |
| `frontend/Dockerfile.prod` | Image Docker frontend Next.js (standalone) |
| `docker-compose.prod.yml` | Orchestration production complète |
| `entrypoint.sh` | Startup backend (migrate + collectstatic + gunicorn) |
| `nginx/nginx.conf` | Reverse proxy nginx |
| `.env.prod.example` | Template des variables d'environnement |
| `deploy.sh` | Script de déploiement automatisé |

---

## Procédure complète — premier déploiement

### 1. Préparer le serveur

```bash
# Installer Docker et Docker Compose sur le serveur Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Se reconnecter pour que le groupe prenne effet
```

### 2. Cloner le projet

```bash
git clone <url-du-repo> /opt/konis
cd /opt/konis
```

### 3. Configurer les variables d'environnement

```bash
# Copier le template
cp .env.prod.example .env.prod

# Éditer .env.prod avec vos vraies valeurs
nano .env.prod
```

**Variables obligatoires à remplir :**

```bash
# Générer la clé secrète Django
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# Générer le mot de passe PostgreSQL
openssl rand -hex 24
```

### 4. Reset et préparation de la base (AVANT premier déploiement)

```bash
# Option A — Premier déploiement propre (aucune donnée de test)
./deploy.sh --skip-backup

# Option B — Si vous avez des données de test à supprimer
./deploy.sh --reset-data --skip-backup
```

### 5. Créer l'administrateur

```bash
docker exec -it konis_backend_prod python manage.py createsuperuser
```

### 6. Vérification finale

```bash
# Health check
curl http://localhost/api/health/

# Logs en temps réel
docker compose -f docker-compose.prod.yml logs -f

# État des conteneurs
docker compose -f docker-compose.prod.yml ps
```

---

## Procédure — mise à jour (déploiements suivants)

```bash
cd /opt/konis
git pull

# Déploiement avec backup automatique
./deploy.sh
```

Le script `deploy.sh` effectue automatiquement :
1. Backup de la base avant toute modification
2. Build des nouvelles images
3. Migration de la base
4. Redémarrage des conteneurs

---

## Procédure — remise à zéro complète des données

### Scénario : passage de la phase de test à la production réelle

```bash
# 1. Backup complet (précaution)
docker exec konis_backend_prod python manage.py dumpdata --indent 2 > backup_complet.json

# 2. Remise à zéro des données opérationnelles
#    (conserve : usines, boutiques, produits, utilisateurs)
docker exec konis_backend_prod python manage.py reset_for_production --confirm

# Ce que la commande supprime :
#   - Tous les tickets de vente et factures
#   - Tous les stocks et mouvements de stock
#   - Tous les achats usine
#   - Tous les lots de production
#   - Tous les transferts (cessions boutiques + inter-usines)
#   - Toutes les dépenses
#   - Tous les logs d'audit

# Ce qui est conservé :
#   - Entreprise, Lieux (usines + boutiques)
#   - Utilisateurs et leurs rôles
#   - Produits et catégories
#   - Catégories de dépenses
```

### Scénario : reset total (base vide)

```bash
# ATTENTION : supprime TOUT, y compris users et configuration
docker compose -f docker-compose.prod.yml down
docker volume rm konis_postgres_data

# Redémarrer : recréera une base vide
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

# Recréer l'admin
docker exec -it konis_backend_prod python manage.py createsuperuser
```

---

## Commandes utiles

```bash
# Voir les logs d'un service
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f nginx

# Ouvrir un shell dans le backend
docker exec -it konis_backend_prod sh

# Vérifier les migrations en attente
docker exec konis_backend_prod python manage.py migrate --check

# Appliquer des migrations manuellement
docker exec konis_backend_prod python manage.py migrate

# Backup PostgreSQL natif (format binaire, compact)
docker exec konis_db_prod pg_dump -U konis_user -d konis_prod -F c -f /tmp/backup.dump
docker cp konis_db_prod:/tmp/backup.dump ./backups/

# Restaurer un backup
docker cp ./backups/backup.dump konis_db_prod:/tmp/restore.dump
docker exec konis_db_prod pg_restore -U konis_user -d konis_prod -c /tmp/restore.dump
```

---

## Sécurité en production

| Mesure | Statut |
|---|---|
| JWT httpOnly cookies | ✓ Configuré |
| HTTPS (HSTS 1 an) | ✓ Configuré dans prod.py (activer nginx SSL) |
| DEBUG = False | ✓ Configuré |
| SECRET_KEY aléatoire | ✓ Requis dans .env.prod |
| PostgreSQL non exposé | ✓ Réseau Docker interne uniquement |
| Utilisateur non-root | ✓ Conteneurs backend et frontend |
| Headers sécurité | ✓ X-Frame-Options, CSP, XSS-Protection |
| Rate limiting | ✓ 200 req/h utilisateur, 10/min login |
| Token rotation + blacklist | ✓ Configuré |
| CORS strict | ✓ Origines explicites requises |

---

## En cas de problème

```bash
# Backend ne démarre pas
docker logs konis_backend_prod

# Erreur de migration
docker exec konis_backend_prod python manage.py showmigrations
docker exec konis_backend_prod python manage.py migrate --verbosity 2

# Vérifier la connexion DB
docker exec konis_backend_prod python manage.py dbshell

# Nginx erreur 502
docker logs konis_nginx_prod
docker exec konis_backend_prod curl -sf http://localhost:8000/api/health/
```
