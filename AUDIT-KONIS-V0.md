# Audit complet KONIS V0 — Analyse des manquants

Contexte : KONIS V0 (provenderie), 1 entreprise, 1 usine + plusieurs boutiques, 1 boutique = 1 compte. Stack : Django 5 + DRF + Next.js 14, PostgreSQL (prod) / SQLite (dev). Sécurité : JWT (cookies), permissions, audit log, throttling, tests sécurité.

---

## 1) Résumé de l’état actuel (ce qui est déjà fait)

- **Backend** : Django 5, DRF, JWT (access 10 min, refresh 7 j, rotation, blacklist au logout), API complète (auth, health, admin CRUD : entreprises, lieux, users, catégories, produits, stocks, transferts, achats usine, tickets, catégories dépense, dépenses ; boutique : stock, produits, ventes ; comptable : lecture stocks, transferts, ventes, dépenses). Permissions par rôle (IsAdminRole, IsComptableRole, IsBoutiqueRole), filtrage boutique par `user.lieu`. Validation (quantités/prix/montant), transactions atomiques ventes/transferts, contraintes DB (stock ≥ 0). Audit (connexion, vente, transfert, dépense), throttling (login 10/min, ventes 60/min), SecurityHeadersMiddleware, CORS, prod HTTPS. Index sur Stock, Transfert, Ticket, Depense, AuditLog. Seed : 1 entreprise, 1 usine, 3 boutiques, admin/comptable/3 boutiques, 20 produits, stocks usine. **Django Admin** : Entreprise, Lieu, CustomUser enregistrés ; utilisateur seed `admin` avec `is_staff=True` pour accéder à `/admin/`. **Frontend** : Next.js 14, login, redirection par rôle, dashboard admin (KPI, ventes, stocks, alertes), comptable (synthèse, dépenses, ventes, export CSV), caisse boutique (ventes du jour, stock local, panier, ticket 58 mm, raccourcis). Proxy API + cookies JWT. **Déploiement** : render.yaml, README-DEPLOYMENT.md, prod.py (PostgreSQL, env obligatoires). **Tests** : 6 tests sécurité (api.tests.test_security).

---

## 2) Manquants CRITIQUES (bloquants production)

| Priorité | Manquant | Preuve / détail |
|----------|----------|------------------|
| **P0** | Exécution du seed en production après 1er déploiement | Sans seed (ou createsuperuser), aucun compte pour se connecter. Procédure dans README mais pas automatique. |
| **P0** | Variables d’environnement prod non définies = crash | `DJANGO_ALLOWED_HOSTS`, `DJANGO_SECRET_KEY`, `CORS_ALLOWED_ORIGINS`, `DATABASE_URL` obligatoires ; si oubli, ValueError au démarrage. |
| **P1** | Pas de backup automatisé PostgreSQL documenté côté hébergeur | README décrit `pg_dump` manuel ; pas de cron/script ni fréquence recommandée. |
| **P1** | Free tier Render : service et DB peuvent s’arrêter / données perdues (DB free) | Risque perte données ou indispo ; documenter passage au plan payant. |
| **P2** | Pas de monitoring / health check externe | `/api/health/` existe mais pas d’Uptime Robot ou équivalent configuré. |

---

## 3) Manquants MÉTIER (cahier des charges)

| Priorité | Manquant | Preuve |
|----------|----------|--------|
| **P1** | App « rapports » vide | `rapports` est dans INSTALLED_APPS mais pas de modèles ni vues dédiées ; les rapports passent par API admin/comptable. Cohérent si « rapports » = dashboards existants. |
| **P2** | Catégories de dépense non créées par le seed | Seed supprime `CategorieDepense` mais ne recrée aucune ; première dépense nécessite d’abord une catégorie (API ou Django Admin). |
| **P2** | Aucun stock initial en boutique après seed | Stocks uniquement à l’usine ; il faut au moins un transfert usine→boutique pour vendre en boutique. Comportement attendu mais à documenter. |

---

## 4) Manquants UI/UX (POS, dashboards)

| Priorité | Manquant | Preuve |
|----------|----------|--------|
| **P1** | Pas d’interface admin (front) pour créer lieux / utilisateurs | Dashboard admin = KPI + tableaux ; création de boutiques et comptes se fait via **Django Admin** (`/admin/`) ou API. |
| **P2** | Pas de gestion des transferts dans le front | Transferts possibles uniquement via API (admin) ou Django Admin si on expose les modèles inventaire. |
| **P2** | Pas de gestion des dépenses / catégories dépense dans le front | Comptable voit les dépenses ; création via API ou Django Admin. |
| **P2** | Seuil alerte stock fixe (10) dans le code | `SEUIL_ALERTE_STOCK = 10` en dur dans `admin/page.tsx` ; pas de paramétrage par produit ou global. |

---

## 5) Manquants TECH (tests, perf, logs, migrations, seed, docs)

| Priorité | Manquant | Preuve |
|----------|----------|--------|
| **P1** | Tests limités aux 6 tests sécurité (api) | `core`, `produits`, `inventaire`, `ventes`, `depenses`, `rapports` ont des `tests.py` vides ou quasi vides. |
| **P2** | Pas de tests E2E / front | Pas de Playwright/Cypress ; pas de tests sur login, caisse, transfert depuis l’UI. |
| **P2** | Logging prod basique (console uniquement) | `prod.py` : handlers console ; pas de fichier ni service externe (ex. Sentry). |
| **P2** | Pas de versionnage d’API (version dans health uniquement) | `/api/health/` renvoie `version: "v0"` ; pas de préfixe `/api/v1/`. |
| **P2** | Seed destructif sans confirmation en `--no-input` | Avec `--no-input`, le seed supprime toutes les données ; à utiliser uniquement en dev ou première install. |

---

## 6) Risques majeurs et corrections

| Risque | Correction |
|--------|------------|
| **Sécurité** : token volé / rejeu | JWT court (10 min), refresh en blacklist au logout, HTTPS en prod ; déjà en place. |
| **Données** : perte DB | PostgreSQL managé (Render) avec plan payant + backups ; documenter `pg_dump` et fréquence. |
| **Cohérence stock** : concurrence | Ventes/transferts en `transaction.atomic()` + `select_for_update()` dans les services ; déjà en place. |
| **Accès admin** : oubli de seed ou compte non staff | Seed met `is_staff=True` sur l’utilisateur `admin` ; documenter la création d’un superuser si besoin. |

---

## 7) Plan d’action en 12 étapes (ordre) pour « V0 OK PROD »

1. **Vérifier variables d’env prod** (Render) : `DJANGO_SETTINGS_MODULE`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`, `CORS_ALLOWED_ORIGINS`.
2. **Déployer le backend** sur Render (build + start + release = migrate).
3. **Créer la base PostgreSQL** Render et lier `DATABASE_URL`.
4. **Exécuter le seed une fois** (Shell Render : `python manage.py seed --no-input`) ou créer un superuser.
5. **Déployer le frontend** sur Vercel avec `NEXT_PUBLIC_API_URL` = URL du backend.
6. **Tester** : health, login admin, login boutique, vente, transfert, dépense (voir preuves ci‑dessous).
7. **Documenter** la procédure de backup PostgreSQL (commande + fréquence) dans README-DEPLOYMENT.
8. **Optionnel** : enregistrer les modèles inventaire/ventes/depenses dans Django Admin si besoin de saisie depuis `/admin/`.
9. **Optionnel** : ajouter un monitoring (ex. health check externe sur `/api/health/`).
10. **Optionnel** : tests unitaires métier (services ventes/inventaire) et tests API CRUD.
11. **Optionnel** : Sentry (ou équivalent) pour les erreurs prod.
12. **Valider** la checklist README-DEPLOYMENT (connexions, ventes, transferts, persistance).

---

## 8) Preuves : commandes exécutées et résultats attendus

### Backend (runserver)

```bash
cd konis
set DJANGO_SETTINGS_MODULE=konis.settings.dev
python manage.py migrate --noinput
python manage.py seed --no-input
python manage.py runserver 8000
```

**Résultat attendu** : `Starting development server at http://127.0.0.1:8000/`, pas d’erreur.

### Tests

```bash
cd konis
set DJANGO_SETTINGS_MODULE=konis.settings.dev
python manage.py test api -v 1
```

**Résultat attendu** : `Ran 6 tests ... OK`.

### Seed

```bash
python manage.py seed --no-input
```

**Résultat attendu** : `Seed terminé. - Utilisateurs : admin, comptable, boutique1, boutique2, boutique3 - Mots de passe : admin123 / comptable123 / boutique123`.

### Endpoints (après démarrage backend)

| Action | Commande / URL | Résultat attendu |
|--------|----------------|------------------|
| Health | `GET http://localhost:8000/api/health/` | 200, `{"status":"ok","db":"ok","version":"v0"}` |
| Login admin | `POST .../api/auth/login/` body `{"username":"admin","password":"admin123"}` | 200, `{"user":{...}}` + cookies |
| Login boutique | `POST .../api/auth/login/` body `{"username":"boutique1","password":"boutique123"}` | 200, `{"user":{...,"lieu":{...}}}` |
| Admin stocks | `GET .../api/admin/stocks/` (avec cookie admin) | 200, liste des stocks |
| Boutique stock | `GET .../api/boutique/stock/` (avec cookie boutique1) | 200, stock du lieu de la boutique |

---

## SQLite vs PostgreSQL

### A) SQLite suffisant pour la V0 en prod ?

**Non.** Raisons : concurrence limitée (un writer à la fois), pas de backup managé, pas adapté à un déploiement multi-process (ex. Gunicorn multi-workers) ni à une plateforme type Render pour un service web persistant. Pour une V0 entreprise, une base managée (PostgreSQL) est recommandée.

### B) Recommandation finale

- **SQLite en dev + PostgreSQL en prod** : déjà en place (dev.py = SQLite, prod.py = DATABASE_URL PostgreSQL). C’est la configuration recommandée pour KONIS V0.

### C) Si Postgres partout (dev + prod)

- **Config minimale** : dans `konis/settings/dev.py`, utiliser `DATABASE_URL` ou des variables `POSTGRES_*` (comme en prod) pointant vers une instance locale.
- **Docker (optionnel)** :  
  `docker run -d --name konis-pg -e POSTGRES_USER=konis -e POSTGRES_PASSWORD=konis -e POSTGRES_DB=konis -p 5432:5432 postgres:15`  
  Puis `DATABASE_URL=postgres://konis:konis@localhost:5432/konis` (ou équivalent) en dev.
- **Migration** : pas de migration de schéma à prévoir ; les migrations Django sont identiques pour SQLite et PostgreSQL. Pour **données** (baseline prod) : après premier seed en prod, les backups se font via `pg_dump` (voir README-DEPLOYMENT).

---

## Identifiants pour se connecter et ajouter des boutiques (compte admin)

### Connexion à l’application (frontend)

- **URL** : `http://localhost:3000/login` (en local) ou l’URL Vercel en prod.
- **Compte admin** :  
  - **Identifiant** : `admin`  
  - **Mot de passe** : `admin123`  
- **Compte comptable** : `comptable` / `comptable123`  
- **Comptes boutique** (après seed) : `boutique1`, `boutique2`, `boutique3` / `boutique123`

### Ajouter des boutiques à partir du compte admin

- **Option 1 — Django Admin (recommandé)**  
  1. Aller sur l’URL **back-office Django** : `http://localhost:8000/admin/` (en local) ou `https://<votre-backend>.onrender.com/admin/` en prod.  
  2. Se connecter avec le **même compte admin** :  
     - **Identifiant** : `admin`  
     - **Mot de passe** : `admin123`  
  3. **Créer un nouveau lieu (boutique)** :  
     - Menu **Lieux** → **Ajouter Lieu**.  
     - Renseigner : **Entreprise** (KONIS), **Nom** (ex. « Boutique Est »), **Type lieu** : **Magasin**.  
     - Enregistrer.  
  4. **Créer le compte de connexion de la boutique** :  
     - Menu **Utilisateurs** → **Ajouter Utilisateur**.  
     - **Nom d’utilisateur** (ex. `boutique4`), **Mot de passe** (x2).  
     - **Rôle** : **Boutique**.  
     - **Entreprise** : KONIS.  
     - **Lieu** : choisir le lieu « Boutique Est » créé à l’étape 3.  
     - Cocher **Actif** ; pour un accès au seul back-office Django, cocher **Membre du personnel** si besoin.  
     - Enregistrer.  

  Après cela, le nouveau compte (ex. `boutique4`) peut se connecter à l’app (frontend) et utiliser la caisse pour ce lieu.

- **Option 2 — API (avec token admin)**  
  - Créer le lieu : `POST /api/admin/lieux/` avec body `{"entreprise": <id_entreprise>, "nom": "Boutique Est", "type_lieu": "magasin"}` (en envoyant le cookie JWT après login admin).  
  - Créer l’utilisateur : `POST /api/admin/users/` avec body incluant `username`, `password`, `role`: `"boutique"`, `entreprise`, `lieu` (id du lieu créé).

Les identifiants ci‑dessus sont ceux créés par le **seed** ; en production, changer les mots de passe après première connexion.
