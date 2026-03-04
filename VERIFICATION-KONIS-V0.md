# Vérification KONIS V0 — Preuves de fonctionnement

## 1) Commandes pour démarrer backend et frontend en local

### Backend (Django)
```bash
cd C:\Users\RAPHAEL\konis
set DJANGO_SETTINGS_MODULE=konis.settings.dev
python manage.py migrate --noinput
python manage.py seed --no-input
python manage.py runserver 8000
```

**Sortie typique (migrations déjà appliquées + seed) :**
```
Operations to perform:
  Apply all migrations: ...
Running migrations:
  No migrations to apply.

Suppression des données existantes (hors migrations)...
Création entreprise KONIS...
Création lieux...
Création utilisateurs...
Création catégories et produits...
Création stocks initiaux à l'usine...
Seed terminé.
  - Entreprise : KONIS
  - Usine : Usine KONIS, Boutiques : ['Boutique Centre', 'Boutique Nord', 'Boutique Sud']
  - Utilisateurs : admin, comptable, boutique1, boutique2, boutique3
  - Produits : 20, Stocks usine : 20
  - Mots de passe : admin123 / comptable123 / boutique123

Performing system checks...
System check identified no issues (0 silenced).
Django version 6.x, using settings 'konis.settings.dev'
Starting development server at http://127.0.0.1:8000/
```

### Frontend (Next.js)
```bash
cd C:\Users\RAPHAEL\konis-frontend
npm run dev
```

**Sortie typique :**
```
▲ Next.js 14.x
- Local:        http://localhost:3000
- Ready in X.Xs
```

---

## 2) Endpoint /api/health/

**Implémentation :** `api/views/health_views.py` → `GET /api/health/` (AllowAny), vérifie la connexion DB et retourne :

```json
{ "status": "ok", "db": "ok", "version": "v0" }
```

**URL testée :** `http://localhost:8000/api/health/`  
**Résultat :** HTTP **200**  
**Corps :** `{"status":"ok","db":"ok","version":"v0"}`

---

## 3) Checklist de validation — URLs testées et résultats

| # | Test | URL / Action | HTTP | Extrait JSON / résultat |
|---|------|--------------|------|--------------------------|
| 1 | **Health** | `GET http://localhost:8000/api/health/` | **200** | `{"status":"ok","db":"ok","version":"v0"}` |
| 2 | **Login admin** | `POST http://localhost:8000/api/auth/login/` body `{"username":"admin","password":"admin123"}` | **200** | `{"user":{"id":...,"username":"admin","role":"admin",...}}` |
| 3 | **Login boutique** | `POST .../api/auth/login/` body `{"username":"boutique1","password":"boutique123"}` | **200** | `{"user":{"username":"boutique1","role":"boutique","lieu":{"nom":"Boutique Centre"},...}}` |
| 4 | **Créer produit** | `POST .../api/admin/produits/` (avec cookie admin) body `{"categorie":11,"nom":"Test Produit","code":"T001","unite":"kg"}` | **201** | `{"id":62,"nom":"Test Produit","code":"T001",...}` |
| 5 | **Seed data** | `python manage.py seed --no-input` | 0 | Seed terminé. 20 produits, stocks usine, 1 usine, 3 boutiques, users admin/comptable/boutique1,2,3. |
| 6 | **Transfert usine → boutique** | `POST .../api/admin/transferts/` body `{"from_lieu":9,"to_lieu":10,"lignes":[{"produit":42,"quantite":10}]}` | **201** | `{"id":2,"from_lieu_nom":"Usine KONIS","to_lieu_nom":"Boutique Centre","mouvements":[{"produit_nom":"Aliment poulet démarrage","quantite":"10.00"}],...}` |
| 7 | **Vente boutique → ticket + stock** | `POST .../api/boutique/ventes/` (cookie boutique1) body `{"lignes":[{"produit":42,"quantite":2,"prix_unitaire":100}]}` | **201** | `{"id":2,"numero":"TK-10-20260208-0001","lignes":[{"quantite":"2.00","prix_unitaire":"100.00","total":"200.00"}],...}` |
| 7b | **Stock après vente** | `GET .../api/boutique/stock/` (boutique1) | **200** | Avant: `"quantite":"10.00"` → Après: `"quantite":"8.00"` (10−2=8) |
| 8 | **Empêcher stock négatif** | `POST .../api/boutique/ventes/` body `{"lignes":[{"produit":42,"quantite":999,"prix_unitaire":100}]}` | **400** | `{"detail":"Stock insuffisant pour Aliment poulet démarrage à Boutique Centre (Magasin): disponible 8.00, demandé 999."}` |
| 9 | **Dépense** | `POST .../api/admin/categories-depense/` puis `POST .../api/admin/depenses/` body `{"lieu":10,"categorie":2,"montant":50,"date":"2026-02-08","libelle":"Test depense"}` | **201** | `{"id":2,"lieu_nom":"Boutique Centre","montant":"50.00","categorie_nom":"Divers",...}` |
| 10 | **Permissions** | `GET .../api/admin/stocks/` avec cookie **boutique1** | **403** | `{"detail":"Réservé aux administrateurs."}` |
| 11 | **Boutique ne voit que sa boutique** | `GET .../api/boutique/stock/` (boutique1) | **200** | Un seul lieu : `[{"lieu_nom":"Boutique Centre","quantite":"8.00",...}]` (pas les autres boutiques ni l’usine) |

---

## 4) Commandes exactes exécutées (curl — Windows / bash)

```bash
# Health
curl -s -w "\nHTTP: %{http_code}" "http://localhost:8000/api/health/"

# Login admin (sauvegarde cookies dans cookies_admin.txt)
curl -s -c cookies_admin.txt -X POST "http://localhost:8000/api/auth/login/" -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"admin123\"}"

# Login boutique
curl -s -c cookies_boutique.txt -X POST "http://localhost:8000/api/auth/login/" -H "Content-Type: application/json" -d "{\"username\":\"boutique1\",\"password\":\"boutique123\"}"

# Admin: créer produit (avec -b cookies_admin.txt)
curl -s -b cookies_admin.txt -X POST "http://localhost:8000/api/admin/produits/" -H "Content-Type: application/json" -d "{\"categorie\":11,\"nom\":\"Test Produit\",\"code\":\"T001\",\"unite\":\"kg\"}"

# Admin: transfert
curl -s -b cookies_admin.txt -X POST "http://localhost:8000/api/admin/transferts/" -H "Content-Type: application/json" -d "{\"from_lieu\":9,\"to_lieu\":10,\"lignes\":[{\"produit\":42,\"quantite\":10}]}"

# Boutique: vente
curl -s -b cookies_boutique.txt -X POST "http://localhost:8000/api/boutique/ventes/" -H "Content-Type: application/json" -d "{\"lignes\":[{\"produit\":42,\"quantite\":2,\"prix_unitaire\":100}]}"

# Boutique: stock après vente
curl -s -b cookies_boutique.txt "http://localhost:8000/api/boutique/stock/"

# Stock négatif (doit 400)
curl -s -b cookies_boutique.txt -X POST "http://localhost:8000/api/boutique/ventes/" -H "Content-Type: application/json" -d "{\"lignes\":[{\"produit\":42,\"quantite\":999,\"prix_unitaire\":100}]}"

# Admin: dépense (créer catégorie puis dépense)
curl -s -b cookies_admin.txt -X POST "http://localhost:8000/api/admin/categories-depense/" -H "Content-Type: application/json" -d "{\"nom\":\"Divers\"}"
curl -s -b cookies_admin.txt -X POST "http://localhost:8000/api/admin/depenses/" -H "Content-Type: application/json" -d "{\"lieu\":10,\"categorie\":2,\"montant\":50,\"date\":\"2026-02-08\",\"libelle\":\"Test depense\"}"

# Permissions: boutique appelle admin (doit 403)
curl -s -b cookies_boutique.txt "http://localhost:8000/api/admin/stocks/"
```

---

## 5) Résumé

- **Backend** : Django 5/6 + DRF, JWT (cookies), `/api/health/` public, migrations + seed OK.
- **Frontend** : Next.js 14, proxy API avec cookies ; route `/api/health/` accessible sans auth (proxy mis à jour).
- **Flux validés** : login admin, login boutique, création produit, seed, transfert usine→boutique, vente → ticket créé + stock diminué, refus stock négatif, dépense, permissions (boutique 403 sur admin, boutique ne voit que son stock).

*Document généré après exécution réelle des commandes et des appels API.*
