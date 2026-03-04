# Déploiement KONIS V0 – Production

Documentation pour déployer le backend Django sur **Render** et le frontend Next.js sur **Vercel**, avec PostgreSQL managé.

---

## 1. Vue d’ensemble

| Composant        | Plateforme   | Rôle                                      |
|------------------|-------------|-------------------------------------------|
| Backend Django   | Render      | API REST, JWT, PostgreSQL                 |
| Base PostgreSQL | Render      | Base managée, connectée au backend        |
| Frontend Next.js | Vercel      | App React, auth via route handlers, HTTPS |

Flux : **Navigateur → Vercel (Next.js) → Render (Django)**. Les appels API du client vont vers Next.js (même origine) ; Next.js proxy vers Django avec le JWT (cookie httpOnly).

---

## 2. Backend Django sur Render

### 2.1 Créer la base PostgreSQL (Render)

1. **Dashboard Render** → **New** → **PostgreSQL**.
2. **Name** : `konis-db`.
3. **Region** : même que le Web Service (ex. Frankfurt).
4. **Plan** : **Starter** recommandé (backups automatiques). Free pour test.
5. Créer la base. Noter l’**Internal Database URL** (pour le service Django).

### 2.2 Créer le Web Service (Django)

1. **New** → **Web Service**.
2. **Connect** le dépôt Git (dossier backend = racine du dépôt ou sous-dossier `konis`).
3. **Root Directory** : si le backend est dans un sous-dossier, indiquer `konis` (ou laisser vide si la racine = backend).
4. **Runtime** : Python 3.
5. **Build Command** :
   ```bash
   pip install -r requirements.txt && python manage.py collectstatic --noinput
   ```
6. **Start Command** :
   ```bash
   gunicorn konis.wsgi -b 0.0.0.0:$PORT -w 2 --timeout 120
   ```
7. **Release Command** (optionnel, pour migrations avant démarrage) :
   ```bash
   python manage.py migrate --noinput
   ```

### 2.3 Variables d’environnement (Backend – Render)

À définir dans **Environment** du Web Service :

| Variable                | Obligatoire | Exemple / remarque |
|-------------------------|------------|--------------------|
| `DJANGO_SETTINGS_MODULE`| Oui        | `konis.settings.prod` |
| `DJANGO_SECRET_KEY`     | Oui        | Chaîne longue aléatoire (générateur Render ou `openssl rand -base64 64`) |
| `DJANGO_ALLOWED_HOSTS`  | Oui        | `konis-api.onrender.com` (ou votre domaine custom) |
| `DATABASE_URL`          | Oui        | Coller l’**Internal Database URL** de la base Render |
| `CORS_ALLOWED_ORIGINS`  | Oui        | `https://votre-app.vercel.app` (URL du frontend Vercel, sans slash final) |
| `DEBUG`                 | Non        | Ne pas définir ou `False` (prod) |

**Remarque** : avec un Blueprint `render.yaml`, une partie de ces variables peut être liée automatiquement (ex. `DATABASE_URL` depuis la base).

### 2.4 Vérification API

- URL du service : `https://konis-api.onrender.com` (adapter au nom réel).
- Tester : `GET https://konis-api.onrender.com/api/auth/me/` → 401 sans token (normal).
- Tester login (depuis le front ou Postman) :  
  `POST https://konis-api.onrender.com/api/auth/login/`  
  Body : `{"username":"admin","password":"admin123"}`  
  (après avoir exécuté le seed une fois, voir ci‑dessous.)

---

## 3. Frontend Next.js sur Vercel

### 3.1 Importer le projet

1. **vercel.com** → **Add New** → **Project**.
2. Importer le dépôt contenant le frontend (dossier `konis-frontend` ou racine du front).
3. **Root Directory** : `konis-frontend` si le front est dans un sous-dossier.
4. **Framework Preset** : Next.js (détecté automatiquement).

### 3.2 Variables d’environnement (Frontend – Vercel)

Dans **Settings** → **Environment Variables** :

| Variable                 | Valeur                                      |
|--------------------------|---------------------------------------------|
| `NEXT_PUBLIC_API_URL`    | URL du backend Render, **sans** `/api` ni slash final. Ex. : `https://konis-api.onrender.com` |

Utilisée côté serveur (route handlers Next) pour appeler Django. En production, le client appelle toujours le même domaine (Vercel), donc pas d’exposition directe du backend au navigateur.

### 3.3 Déploiement

- Chaque push sur la branche connectée déclenche un build et un déploiement.
- Build : `npm run build`.
- L’app est servie en HTTPS sur un domaine du type `*.vercel.app` (ou domaine custom).

---

## 4. Sécurité et stabilité

- **JWT** : émis par Django, transmis au client via les route handlers Next (cookies httpOnly en prod si vous les utilisez côté Next).
- **CORS** : `CORS_ALLOWED_ORIGINS` limité à l’origine du frontend Vercel.
- **HTTPS** : activé sur Render et Vercel ; Django prod : `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`, cookies sécurisés.
- **Secrets** : `DJANGO_SECRET_KEY` et `DATABASE_URL` uniquement dans les env (jamais en dur).
- **Logs** : Django prod envoie les logs vers la sortie standard (visible dans Render Logs).

---

## 5. Commandes utiles (production)

### Backend (exécution locale avec settings prod)

```bash
export DJANGO_SETTINGS_MODULE=konis.settings.prod
export DJANGO_SECRET_KEY="votre-secret"
export DJANGO_ALLOWED_HOSTS=konis-api.onrender.com
export DATABASE_URL="postgres://..."
export CORS_ALLOWED_ORIGINS=https://votre-app.vercel.app
python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn konis.wsgi -b 0.0.0.0:8000
```

### Créer un superutilisateur (première fois)

Sur Render : **Shell** du Web Service, puis :

```bash
python manage.py createsuperuser
```

Ou en local avec les variables prod :

```bash
python manage.py createsuperuser
```

### Seed (données de démo)

En Shell Render (ou en local avec prod) :

```bash
python manage.py seed --no-input
```

Cela crée 1 entreprise, 1 usine, 3 boutiques, utilisateurs (admin, comptable, boutique1/2/3), 20 produits et stocks initiaux. Mots de passe par défaut : `admin123`, `comptable123`, `boutique123`.

---

## 6. Backup base PostgreSQL (Render)

- **Plan Starter** (ou supérieur) : backups automatiques par Render. Consulter la doc Render pour la rétention et la restauration.
- **Export manuel** (pg_dump) : depuis une machine ayant accès au réseau Render (ou via **Shell** si disponible) :

  ```bash
  pg_dump $DATABASE_URL -F c -f konis_backup_$(date +%Y%m%d).dump
  ```

- **Restauration** (exemple) :

  ```bash
  pg_restore -d $DATABASE_URL -c konis_backup_YYYYMMDD.dump
  ```

Adapter selon que vous utilisez l’URL interne (depuis un autre service Render) ou l’URL externe (depuis votre PC avec accès autorisé).

---

## 7. Checklist de validation production

À valider après déploiement :

- [ ] **Backend (Render)**  
  - [ ] Le service démarre sans erreur (logs Render).  
  - [ ] `GET /api/auth/me/` retourne 401 sans cookie/token.  
  - [ ] `POST /api/auth/login/` avec identifiants valides retourne 200 et un token / user.

- [ ] **Frontend (Vercel)**  
  - [ ] La page d’accueil s’affiche et redirige vers login si non connecté.  
  - [ ] Connexion **admin** : redirection vers `/admin`, KPIs et listes chargés.  
  - [ ] Connexion **boutique** : redirection vers `/boutique/caisse`, ventes du jour et stock local visibles.

- [ ] **Flux métier**  
  - [ ] **Vente** : création d’un ticket depuis la caisse, stock du produit diminué.  
  - [ ] **Transfert** : (depuis admin ou API) transfert usine → boutique, stocks mis à jour.  
  - [ ] **Dépense** : (depuis admin ou API) une dépense est enregistrée et visible côté comptable.  
  - [ ] **Rapports** : admin et comptable voient des données cohérentes (ventes, dépenses, stocks).

- [ ] **Données**  
  - [ ] Données persistantes après redémarrage du Web Service (PostgreSQL).  
  - [ ] Aucune donnée sensible en dur (SECRET_KEY, DATABASE_URL, mots de passe).

- [ ] **Sécurité**  
  - [ ] HTTPS actif sur frontend et backend.  
  - [ ] CORS limité à l’origine du frontend.  
  - [ ] Comptes de test (seed) : mots de passe changés ou seed désactivé en prod si besoin.

---

### Checklist "V0 OK TERRAIN" (15 items)

1. [ ] Backend démarre sans erreur (logs Render)
2. [ ] `GET /api/health/` → `db: "ok"`
3. [ ] `POST /api/auth/login/` valide → 200
4. [ ] Frontend s'affiche, redirige login si non connecté
5. [ ] Connexion admin → `/admin`, KPIs chargés
6. [ ] Connexion boutique → `/boutique/caisse`, ventes et stock visibles
7. [ ] Vente créée → ticket + stock diminué
8. [ ] Transfert usine → boutique → stocks mis à jour
9. [ ] Dépense créée → visible admin et comptable
10. [ ] Impression ticket 58mm (bouton Imprimer après vente)
11. [ ] Données persistantes (PostgreSQL)
12. [ ] Aucune donnée sensible en dur
13. [ ] HTTPS, CORS limité
14. [ ] Backups planifiés (pg_dump ou provider)
15. [ ] Comptes test : mots de passe changés en prod (si seed)

---

## 8. Dépannage

- **502 Bad Gateway** : le service Django ne répond pas (crash, timeout). Vérifier les logs Render et que `gunicorn` est bien lancé avec `$PORT`.
- **CORS** : si le frontend ne peut pas appeler le backend, vérifier `CORS_ALLOWED_ORIGINS` (exactement l’URL Vercel, sans slash final).
- **Static files** : en prod, Django sert les statics via WhiteNoise ; `collectstatic` doit être exécuté au build.
- **Migrations** : en cas d’erreur au démarrage, exécuter `python manage.py migrate --noinput` en Release Command ou en Shell.

---

## 9. Résumé des paramètres

### Render (Web Service)

| Paramètre        | Valeur |
|------------------|--------|
| Build Command    | `pip install -r requirements.txt && python manage.py collectstatic --noinput` |
| Start Command    | `gunicorn konis.wsgi -b 0.0.0.0:$PORT -w 2 --timeout 120` |
| Release Command  | `python manage.py migrate --noinput` |

### Vercel (Next.js)

| Paramètre   | Valeur        |
|-------------|---------------|
| Build       | `npm run build` (défaut Next.js) |
| Env         | `NEXT_PUBLIC_API_URL` = URL du backend Render |

### PostgreSQL (Render)

- Créer une instance **PostgreSQL**.
- Utiliser l’**Internal Database URL** dans `DATABASE_URL` du Web Service.
- Plan **Starter** recommandé pour les backups en production.

---

## 10. Configuration Render (résumé)

- **Type** : Web Service (Python).
- **Build** : `pip install -r requirements.txt && python manage.py collectstatic --noinput`
- **Start** : `gunicorn konis.wsgi -b 0.0.0.0:$PORT -w 2 --timeout 120`
- **Release** : `python manage.py migrate --noinput`
- **Env** : `DJANGO_SETTINGS_MODULE=konis.settings.prod`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`, `CORS_ALLOWED_ORIGINS`
- **Blueprint** : optionnel, utiliser `render.yaml` pour créer service + base d’un coup.

---

## 11. Configuration Vercel (résumé)

- **Framework** : Next.js (auto-détecté).
- **Build** : `npm run build`
- **Env** : `NEXT_PUBLIC_API_URL` = URL du backend (ex. `https://konis-api.onrender.com`)
- **HTTPS** : activé par défaut sur `*.vercel.app` et domaine custom.

---

## 12. Paramètres PostgreSQL (Render)

- **Création** : New → PostgreSQL, même région que le Web Service.
- **Connexion** : utiliser **Internal Database URL** dans `DATABASE_URL` du Web Service.
- **Backups** : plan **Starter** ou supérieur pour backups automatiques.
- **Compatibilité** : Django ORM avec `dj-database-url` et `psycopg2-binary`.

---

*Document KONIS V0 – Déploiement production.*
