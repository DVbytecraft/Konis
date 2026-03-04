# Architecture KONIS

## Vue d'ensemble

KONIS est une plateforme de gestion pour provenderie (fabrication et distribution d'aliments pour bétail).
Elle couvre la production en usine, la distribution vers les boutiques, et la comptabilité associée.

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                         │
│                    Next.js 15 App Router                        │
│                 (frontend/ — port 3000 en dev)                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS / cookies httpOnly JWT
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    nginx (reverse proxy)                        │
│         SSL termination · rate limiting · static files          │
└──────┬───────────────────────────────────────────┬──────────────┘
       │ /api/*                                    │ /*
       │                                           │
┌──────▼──────────┐                      ┌─────────▼──────────────┐
│  Django 5.2 +   │                      │   Next.js route        │
│  DRF 3.16       │                      │   handlers (/api/auth) │
│  (port 8000)    │                      └────────────────────────┘
└──────┬──────────┘
       │
┌──────▼──────────┐
│  PostgreSQL 16  │
│  (port 5432)    │
└─────────────────┘
```

---

## Applications Django

| App | Rôle |
|-----|------|
| `core` | Modèles fondamentaux : `Entreprise`, `Lieu`, `CustomUser`, `TokenRevocationEpoch` |
| `produits` | Catalogue produits (`Produit`, `Categorie`) — géré par l'usine |
| `inventaire` | Stocks (`Stock`), transferts (`Transfert`, `MouvementStock`), achats usine (`AchatUsine`) |
| `usine` | Production (`LotProduction`), cessions boutique (`TransfertCession`), inter-usines (`TransfertInterUsine`) |
| `ventes` | Tickets de caisse (`Ticket`, `LigneVente`), factures (`Facture`, `LigneFacture`) |
| `depenses` | Dépenses opérationnelles (`Depense`, `CategorieDepense`) |
| `audit` | Journal d'audit (`AuditLog`) — traçabilité de toutes les actions |
| `api` | Views DRF, serializers, permissions, throttling |

Branding transverse:
- `core/branding.py` centralise la charte KONIS (vert principal, bordures, logo, mention legale)

---

## Modèle de données (simplifié)

```
Entreprise
  └── Lieu (type: usine | magasin)
        └── CustomUser (1 lieu par utilisateur usine/boutique)

Produit ←──── Categorie
  ├── Stock (produit × lieu, quantite >= 0)
  └── LotProduction (produit_fini × lieu_usine)
        ├── TransfertCession → Lieu (magasin)
        └── TransfertInterUsine → Lieu (usine)

Ticket (lieu, date, numero)
  ├── LigneVente (produit, quantite, prix_unitaire)
  └── [mouture] (cout_mouture, prix_mouture_kg/tonne/sac)

Transfert (from_lieu → to_lieu)
  └── MouvementStock (produit, quantite, unit_price)
```

---

## Rôles et accès

| Rôle | Lieu associé | Endpoints autorisés |
|------|-------------|---------------------|
| `admin` | aucun (gestion globale) | `/api/admin/*`, `/api/boutique/*` (avec `?lieu=`), `/api/usine/*` |
| `boutique` | magasin (1-1) | `/api/boutique/*` (filtré sur son lieu) |
| `usine` | usine (1-1) | `/api/usine/*`, `/api/factory/*` (filtré sur son lieu) |
| `comptable` | aucun | `/api/comptable/*` (lecture seule) |

### Isolation multi-entites (tenant logique)

Regles appliquees:
- `boutique`: acces borne a `request.user.lieu` (magasin unique).
- `usine`: acces borne a `request.user.lieu` (usine unique).
- `comptable`: lecture globale strictement bornee a `request.user.entreprise`.
- Transferts interdits entre entreprises (`from_lieu.entreprise_id == to_lieu.entreprise_id` obligatoire).
- Factures comptables: listing/detail/creation limites a l'entreprise du comptable.
- Endpoints comptables: lecture seule uniquement (aucune creation/modification/suppression).

Garanties d'isolation:
- Une boutique A ne lit jamais les donnees de boutique B.
- Une usine A ne transfere jamais vers une usine/boutique d'une autre entreprise.
- Les acces par ID hors perimetre renvoient `404` (detail) ou `400` (commande invalide).

---

## Flux de données métier

### 1. Cycle de production
```
Achat intrant (AchatUsine) — comptabilité uniquement
    ↓
Création LotProduction → crédite Stock[produit_fini, usine]
    ↓
TransfertCession → débite Stock[usine], crédite Stock[boutique]
    OU
TransfertInterUsine → débite Stock[usine_src], crédite Stock[usine_dst]
```

### 2. Cycle de vente boutique
```
vente_boutique(lieu, lignes, mouture?)
    ↓
Validation stock (select_for_update, atomic)
Validation calcul mouture (backend uniquement, unité par unité)
    ↓
Ticket + LigneVente(s) créés
Stock[produit, boutique] débité par quantite
montant_total = Σ(quantite × prix_unitaire) + cout_mouture
```

Règles strictes de calcul :
- Source de vérité unique : `ventes/services.py::_compute_boutique_totals()`
- Si `mouture=True`, chaque ligne vendue doit avoir une unité supportée (`kg`, `tonne`, `sac`)
- Si `mouture=True`, chaque unité rencontrée doit avoir un tarif non-null
- Le ticket persiste `cout_mouture` et `montant_total`; impression et réimpression lisent ces champs DB, sans recalcul frontend

### 3. Mouture seule
```
vente_mouture_seule(lieu, quantite, unite, prix_unitaire, idempotency_key?)
    ↓
Validation serializer + permissions RBAC + throttling dédié
    ↓
Idempotence persistée (Ticket.idempotency_key unique par lieu)
    ↓
Ticket créé (mouture=True, lignes=[], produit_apporte optionnel)
ou ticket existant renvoyé (replay idempotent)
Aucun stock modifié
montant_total = cout_mouture = quantite × prix_unitaire
```

### 4. Historique mouture (exhaustif)
```
GET /api/boutique/mouture-seule/
GET /api/factory/mouture-seule/
    ↓
Ticket.objects.filter(lieu=..., mouture=True)
    ↓
Inclut:
  - mouture_seule (ticket sans ligne de vente)
  - vente_avec_mouture (ticket avec lignes de vente)
```

Filtre optionnel:
- `?source=seule` -> uniquement mouture seule
- `?source=vente` -> uniquement ventes avec mouture

---

## Couche service (business logic)

La logique métier est isolée dans des modules `services.py`, jamais dans les views.

| Module | Fonctions principales |
|--------|-----------------------|
| `inventaire/services.py` | `enregistrer_achat_usine()`, `transfert_usine_vers_boutique()`, `transfert_entre_usines()` |
| `usine/services.py` | `creer_lot_production()`, `transferer_lot_vers_boutique()`, `transferer_lot_vers_usine()` |
| `ventes/services.py` | `vente_boutique()`, `vente_mouture_seule()`, `generer_numero_ticket()` |
| `ventes/views.py` | `ticket_print()`, `facture_print()` (rendu impression DB-driven) |
| `audit/services.py` | `audit_log()` — appelé dans toutes les views mutantes |

**Convention** : toutes les erreurs métier lèvent `ErreurStock` (inventaire/services.py).

---

## Numérotation des tickets

Format : `KONIS-{CODE_LIEU}-{YYYYMMDD}-{SEQ:06d}`

Exemple : `KONIS-KARA-20260227-000001`

Le séquenceur est atomique (select_for_update) — pas de doublon même sous charge.

---

## API REST — Endpoints principaux

```
/api/health/                          → statut applicatif

/api/auth/login/                      → POST : connexion JWT (cookies)
/api/auth/me/                         → GET  : profil utilisateur courant
/api/auth/refresh/                    → POST : renouveler l'access token
/api/auth/logout/                     → POST : déconnexion

/api/boutique/stock/                  → GET/POST (admin seul pour POST)
/api/boutique/produits/               → GET (lecture seule)
/api/boutique/ventes/                 → GET/POST
/api/boutique/mouture-seule/          → GET/POST (historique mouture exhaustif)

/api/usine/lots/                      → GET/POST
/api/usine/cessions/                  → GET/POST
/api/usine/achats/                    → GET/POST
/api/usine/transferts-inter-usines/   → GET/POST
/api/factory/dashboard/               → GET (KPIs usine)
/api/factory/mouture-seule/           → GET/POST (historique mouture exhaustif)

/api/admin/users/                     → CRUD
/api/admin/lieux/                     → CRUD
/api/admin/factories/                 → CRUD (création usine + compte usine)
/api/admin/produits/                  → GET (lecture seule)
/api/admin/stocks/                    → GET (lecture seule)

/api/comptable/bilan/                 → GET (total_ventes, total_mouture, total_depenses…)
/api/comptable/rapport-boutiques/     → GET
/api/comptable/rapport-usines/        → GET

/api/factures/                        → GET/POST
/ventes/facture/<id>/pdf/             → GET (PDF A4 officiel)
/ventes/facture/<id>/print/           → GET (alias PDF officiel)
```

**Pagination** : tous les endpoints ViewSet retournent `{count, next, previous, results[]}` (PAGE_SIZE=50).

---

## Authentification & Sécurité

- **JWT via cookies httpOnly** — pas de token exposé en JavaScript
- **Rotation silencieuse** — l'access token est renouvelé automatiquement via le refresh token
- **Révocation globale** — `TokenRevocationEpoch` permet d'invalider tous les tokens émis avant une date
- **CSRF** — token lu du cookie `csrftoken` (non-httpOnly) et envoyé en `X-CSRFToken` sur les méthodes mutantes
- **RBAC** — `IsAdminRole`, `IsBoutiqueRole`, `IsFactoryUser` dans `api/permissions.py`
- **Rate limiting** — 600 req/heure (user global), 60/min (ventes_create, mouture_create), 10/min (login)
- **Audit log** — toute action mutante (vente, transfert, cession, dépense) est enregistrée dans `AuditLog`
- **Idempotence transactionnelle** — `Idempotency-Key` supportée sur la mouture-seule avec contrainte DB par lieu

---

## Frontend Next.js

```
frontend/src/
├── app/(app)/              # Pages authentifiées (layout avec sidebar)
│   ├── admin/              # Gestion globale (usines, users, stocks, rapports)
│   ├── boutique/           # Caisse, historique, mouture, stock
│   ├── factory/            # Production, cessions, achats, dashboard usine
│   ├── comptable/          # Bilan, rapports boutiques/usines
│   └── factures/           # Gestion factures
├── app/(auth)/             # Pages non authentifiées (login)
├── components/             # Composants réutilisables
│   └── caisse/ticket-58mm.tsx  # Rendu ticket thermique 58mm
├── contexts/
│   └── auth-context.tsx    # AuthProvider, useAuth()
├── hooks/
│   └── use-fetch.ts        # useFetch<T>(url) → {data, loading, error, refetch, cancel}
└── lib/
    └── api.ts              # apiFetch<T>(), apiUrl() — toutes les requêtes HTTP
```

### Conventions frontend

- **Toutes les requêtes HTTP** passent par `apiFetch<T>()` (jamais `fetch()` directement)
- **Pattern de chargement** : utiliser `useFetch<T>(url)` pour les données en lecture
- **Pagination** : les réponses ViewSet sont paginées — toujours utiliser `res.results ?? res`
- **Typage strict** : `apiFetch<T>()` est générique — typer `T` explicitement

## Impression A4 / PDF

- Vue PDF: `ventes.views.facture_pdf` (génération backend)
- Moteur: `ventes/pdf.py` (ReportLab, A4 strict)
- Source de vérité: `Facture` et `LigneFacture` persistées en base
- Branding: `core/branding.py`
- Réimpression fidèle: PDF invariant basé sur les données DB

---

## Infrastructure Docker

```
docker-compose.prod.yml
├── backend   (Django + Gunicorn, image multi-stage)
├── frontend  (Next.js standalone build)
├── nginx     (reverse proxy SSL, rate-limiting)
└── db        (PostgreSQL 16, volume persistant)
```

Variables d'environnement clés (`.env.prod`) :
- `DJANGO_SECRET_KEY`, `DATABASE_URL`
- `DJANGO_ALLOWED_HOSTS=agrokonis.com,www.agrokonis.com`
- `CORS_ALLOWED_ORIGINS=https://agrokonis.com,https://www.agrokonis.com`
- `NEXT_PUBLIC_API_URL=https://agrokonis.com`

### Procedure officielle de rebuild propre (anti-version obsolete)

Developpement local:
1. `docker compose down`
2. `docker compose build --no-cache backend frontend`
3. `docker compose up -d db`
4. `docker compose up -d backend frontend`
5. `docker compose exec backend python manage.py migrate`
6. Verification:
   - `curl http://localhost:8000/api/health/`
   - `curl http://localhost:3000/api/auth/me`

Production:
1. `docker compose -f docker-compose.prod.yml --env-file .env.prod down`
2. `docker compose -f docker-compose.prod.yml --env-file .env.prod build --no-cache backend frontend`
3. `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d`
4. `docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend python manage.py migrate`
5. Verification:
   - `docker compose -f docker-compose.prod.yml --env-file .env.prod ps`
   - `docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail=100 backend`

---

## Procédure reset officielle (développement)

Utiliser la commande `full_reset` — elle supprime toutes les données, recrée les tables, et crée un superuser :

```bash
docker compose exec backend python manage.py full_reset --superuser=admin --confirm
```

Puis charger les fixtures initiales :

```bash
docker compose exec backend python manage.py loaddata \
  fixtures/initial_groups.json \
  fixtures/initial_categories_produits.json \
  fixtures/initial_categories_depenses.json
```

Ensuite créer les utilisateurs et lieux via l'interface admin Django ou l'endpoint `/api/admin/factories/`.

---

## Procédure sauvegarde

```bash
# Sauvegarde PostgreSQL
docker compose exec db pg_dump -U konis_user -d konis_db -F c -f /tmp/konis_backup_$(date +%Y%m%d_%H%M%S).dump

# Copie hors conteneur
docker compose cp db:/tmp/konis_backup_*.dump ./backup/
```

**Restauration** :
```bash
docker compose exec db pg_restore -U konis_user -d konis_db -c /tmp/konis_backup_YYYYMMDD.dump
```

---

## Procédure redémarrage

```bash
# Redémarrage doux (sans perte de données ni volumes)
docker compose restart backend frontend

# Vérification
docker compose ps
docker compose logs --tail=50 backend
curl http://localhost:8000/api/health/
```

---

## Procédure incident

### 1. Identifier le problème

```bash
docker compose logs --tail=200 backend 2>&1 | grep -E "ERROR|Exception|Traceback"
docker compose exec db psql -U konis_user -d konis_db -c "SELECT count(*) FROM django_migrations;"
```

### 2. Migration bloquée

```bash
docker compose exec backend python manage.py showmigrations
docker compose exec backend python manage.py migrate --run-syncdb
```

### 3. Rollback rapide (si migration corrompue)

```bash
# Revenir à une migration précédente (exemple : produits.0005)
docker compose exec backend python manage.py migrate produits 0005
```

### 4. Base irrécupérable — reset total

```bash
docker compose down -v
docker compose up -d db
docker compose exec db psql -U konis_user -c "CREATE DATABASE konis_db;"  # si besoin
docker compose up -d backend
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py full_reset --superuser=admin --confirm
docker compose exec backend python manage.py loaddata \
  fixtures/initial_groups.json \
  fixtures/initial_categories_produits.json \
  fixtures/initial_categories_depenses.json
docker compose up -d frontend
```

---

## Phase suivante (hors périmètre actuel)

- **CI/CD** — GitHub Actions : lint, tests, build Docker, déploiement automatique
- **Secrets manager** — Render / AWS Secrets Manager (ne pas stocker `.env.prod` en clair)
- **Monitoring** — Sentry pour erreurs backend + frontend
- **Celery/Redis** — tâches asynchrones (rapports lourds, exports Excel)
- **Tests E2E frontend** — Playwright sur les flux caisse et production
