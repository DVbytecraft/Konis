# KONIS V0

Application de gestion (caisse, inventaire, dépenses, rapports) : backend **Django** (API REST, JWT), frontend **Next.js**, base **PostgreSQL**.

---

## Prérequis

- **Docker** et **Docker Compose** (pour lancer tout le stack ou seulement la base)
- **Python 3.12+** (pour le dev local du backend)
- **Node.js 18+** (pour le dev local du frontend)

---

## Lancer le projet

### Option 1 : Tout avec Docker (recommandé)

Une seule commande pour la base de données, le backend et le frontend :

```bash
cd konis
docker compose up -d
```

- **Backend (API)** : http://localhost:8000  
- **Frontend** : http://localhost:3000  
- **Admin Django** : http://localhost:8000/admin/

Les migrations sont exécutées automatiquement au démarrage du backend.
Le seed de démo est manuel (pour éviter d'écraser les données) :

```bash
docker compose exec backend python manage.py seed --no-input
```

Vérifier que l’API répond :

```bash
curl http://127.0.0.1:8000/api/health/
# Attendu : {"status":"ok","db":"ok","version":"v0"}
```

---

### Option 2 : Développement local (sans conteneurs pour Django/Next)

Utile pour modifier le code et avoir le rechargement à chaud.

#### 1. Base de données

**A. PostgreSQL via Docker (recommandé)**

```bash
cd konis
docker compose up -d db
```

Puis définir l’URL (identifiants du `docker-compose.yml`) :

```bash
export DATABASE_URL="postgres://konis_user:konis_password@localhost:5433/konis_db"
export DJANGO_SETTINGS_MODULE="konis.settings.dev"
```

**B. Sans PostgreSQL**  
Ne pas définir `DATABASE_URL`. Django utilisera **SQLite** (`db.sqlite3`) en développement.

#### 2. Backend Django

```bash
cd konis
python -m venv .venv
source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed --no-input
python manage.py runserver
```

- API : http://127.0.0.1:8000  
- Health : http://127.0.0.1:8000/api/health/

#### 3. Frontend Next.js (dans un autre terminal)

```bash
cd konis/frontend
npm install
npm run dev
```

- Frontend : http://localhost:3000  

Le frontend appelle l’API sur `http://localhost:8000` (voir `NEXT_PUBLIC_API_URL` dans le frontend si besoin).

---

## Variables d’environnement

En local, pour éviter de réexporter les variables à chaque fois :

```bash
cp .env.example .env
```

Puis éditer `.env`. Exemple avec Postgres dans Docker :

```env
DATABASE_URL=postgres://konis_user:konis_password@localhost:5433/konis_db
# DJANGO_SETTINGS_MODULE=konis.settings.dev
```

**Important** : ne jamais commiter le fichier `.env` (il est ignoré par Git).

JWT access token : durée de vie alignée à **10 minutes** (backend + cookies frontend).

---

## Commandes utiles

| Action | Commande |
|--------|----------|
| Migrations | `python manage.py migrate` |
| Données de démo | `python manage.py seed --no-input` |
| Tests API | `python manage.py test api` |
| Vérifier Postgres | `python scripts/proof_postgres.py` |
| Arrêter Docker | `docker compose down` |

### Procedure Docker fiable (stop/clean/rebuild/migrate/restart/verif)

Quand vous suspectez qu'un container tourne avec un ancien code:

```bash
docker compose down
docker compose build --no-cache backend frontend
docker compose up -d db
docker compose up -d backend frontend
docker compose exec backend python manage.py migrate
curl http://127.0.0.1:8000/api/health/
```

Production:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod down
docker compose -f docker-compose.prod.yml --env-file .env.prod build --no-cache backend frontend
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend python manage.py migrate
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
```

---

## Structure du projet

| Dossier / Fichier | Rôle |
|-------------------|------|
| `api/` | API REST, auth JWT, health, vues métier |
| `core/` | Modèles communs, commande `seed` |
| `ventes/` | Tickets, caisse |
| `inventaire/` | Stock, produits |
| `depenses/` | Dépenses |
| `rapports/` | Rapports |
| `audit/` | Audit |
| `konis/settings/` | Settings Django (base, dev, prod) |
| `frontend/` | App Next.js (React, Tailwind) |

---

## Documentation complémentaire

- **Déploiement (Render + Vercel)** : [README-DEPLOYMENT.md](README-DEPLOYMENT.md)  
- **PostgreSQL en local** : [docs/POSTGRES-LOCAL.md](docs/POSTGRES-LOCAL.md)  
- **Production** : [docs/PRODUCTION-READINESS.md](docs/PRODUCTION-READINESS.md)  
- **Impression ticket thermique 80 mm (XPrinter)** : [docs/IMPRESSION-TICKET-58MM.md](docs/IMPRESSION-TICKET-58MM.md)
- **Facture A4 professionnelle** : [docs/FACTURE-A4.md](docs/FACTURE-A4.md)

---

## Module Usine (Nouveau)

Endpoints principaux :

- `GET /api/factory/dashboard/`
- `GET /api/factory/raw-materials/`
- `GET|POST /api/factory/raw-materials/receipt/`
- `GET|POST /api/factory/production/`
- `GET /api/factory/production/<id>/`
- `GET /api/factory/shop-stock/`
- `GET /api/reports/profit-by-lot/` (comptable/admin)
- `GET /api/reports/profit-by-period/?group_by=month|year` (comptable/admin)

Compatibilite :

- Les endpoints historiques restent disponibles (`/api/usine/*`, `/api/admin/transferts/`).
- Les transferts supportent desormais `unit_price` et `production_order` par ligne.

## Facturation transversale (A4)

La facture A4 est disponible pour les roles `admin`, `comptable`, `usine` et `boutique`.

- Page frontend: `GET /factures`
- API backend:
  - `GET|POST /api/factures/`
  - `GET /api/factures/<id>/`
  - `GET /ventes/facture/<id>/print/` (impression A4)

Regles d'impression:

- Les **tickets de caisse** sont imprimes en **ticket thermique 80 mm** (XPrinter).
- Les **factures** sont imprimees en **A4**.

Regles de calcul ticket (vente + mouture):

- Calcul financier fait uniquement par le backend (`ventes/services.py`).
- Formule canonique: `montant_total = somme(lignes) + cout_mouture`.
- Si `mouture=true`, chaque unite vendue (`kg`, `tonne`, `sac`) doit avoir son tarif mouture.
- Le total imprime et le total de reimpression proviennent strictement des champs persistes en base (`Ticket.montant_total`, `Ticket.cout_mouture`).

Historique mouture:

- `GET /api/boutique/mouture-seule/` et `GET /api/factory/mouture-seule/` retournent toutes les operations de mouture (`mouture_seule` + `vente_avec_mouture`).
- Filtre optionnel: `?source=seule|vente`.

Facture PDF officielle:

- Endpoint PDF: `GET /ventes/facture/<id>/pdf/` (inline) et `?download=1` (telechargement).
- Impression: le frontend ouvre le PDF puis declenche `window.print()` pour afficher la fenetre native de choix d'imprimante.
- Branding centralise: `core/branding.py` (`KONIS_BRAND`, couleur verte KONIS, logo optionnel `KONIS_LOGO_PATH`).

## Administration multi-usines

Un administrateur peut maintenant creer et gerer les usines directement depuis l'interface:

- Page frontend: `GET /admin/factories`
- API backend:
  - `GET /api/admin/factories/` liste des usines (avec utilisateur associe)
  - `POST /api/admin/factories/` creation usine + compte usine en une operation
  - `PATCH /api/admin/factories/<id>/` mise a jour (nom, adresse, statut, infos utilisateur, mot de passe)
  - `DELETE /api/admin/factories/<id>/` desactivation logique de l'usine et du compte associe

Payload de creation:

```json
{
  "factory_name": "Usine de Dakar",
  "factory_address": "Zone industrielle",
  "user_email": "responsable@usine.com",
  "user_first_name": "Jean",
  "user_last_name": "Dupont",
  "user_password": "StrongPass123!"
}
```

Regles de coherence:

- un utilisateur `usine` est rattache a une seule `Lieu` de type `usine`
- les endpoints `/api/factory/*` sont filtres par l'usine du compte connecte
- les rapports comptables supportent `factory_id` pour filtrer par usine
