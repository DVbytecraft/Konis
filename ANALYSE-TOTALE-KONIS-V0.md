# ANALYSE TOTALE KONIS V0 — ÉTAT APP + BASE DE DONNÉES

**Contexte** : Projet KONIS V0 (provenderie), 1 entreprise, 1 usine + plusieurs boutiques. Stack : Django 5 + DRF + Next.js 14. DB cible : PostgreSQL (local et prod).

---

## A) RÉSUMÉ EXÉCUTIF

- **V0 utilisable ou pas ?** **Oui**, en environnement de dev (SQLite ou Postgres) avec correctifs mineurs (lint front, DB réelle Postgres à valider).
- **3 forces** : (1) Backend cohérent : atomic + select_for_update sur vente/transfert, contraintes stock ≥ 0 et unicité ticket. (2) API REST complète (auth, admin, boutique, comptable) avec permissions par rôle. (3) Frontend Next.js 14 avec /login, /admin, /comptable, /boutique/caisse et composant ticket 58mm.
- **3 risques** : (1) En dev sans `DATABASE_URL`, Django utilise **SQLite** (pas Postgres) — à valider en local avec Postgres. (2) Build frontend échoue (ESLint : variable non utilisée). (3) Pas de contrainte DB sur dépense.montant ≥ 0 (uniquement validation serializer).

---

## B) BACKEND (PREUVES)

### B.1 Commandes exécutées et résultats

**1) python manage.py check**

```
System check identified no issues (0 silenced).
```
*Preuve : sortie réelle, exit code 0.*

**2) python manage.py showmigrations (résumé)**

- **Appliquées** : toutes (admin, audit, auth, contenttypes, core, depenses, inventaire, produits, sessions, token_blacklist, ventes).
- **Non appliquées** : 0.
- **Apps sans migrations** : api, rapports.

*Preuve : 47 migrations [X], 0 [ ].*

**3) python manage.py test api**

```
Ran 9 tests in 4.567s
OK
Destroying test database for alias 'default'...
```
*Preuve : exit code 0, 9 tests (test_security + test_ventes).*

**4) python manage.py runserver**

```
# Démarrage en arrière-plan puis :
curl -s http://127.0.0.1:8000/api/health/
{"status":"ok","db":"ok","version":"v0"}
```
*Preuve : serveur répond sur /api/health/.*

### B.2 Endpoints réellement disponibles (routes) + accès

| Préfixe | Route (exemples) | Accès |
|--------|-------------------|--------|
| **Public** | `GET /api/health/` | AllowAny |
| **Auth** | `POST /api/auth/login/`, `POST /api/auth/refresh/`, `POST /api/auth/logout/`, `GET /api/auth/me/` | login : AllowAny ; me/logout : IsAuthenticated |
| **Boutique** | `GET/POST /api/boutique/stock/`, `GET /api/boutique/produits/`, `GET/POST /api/boutique/ventes/` | IsBoutiqueRole (boutique ou admin) |
| **Admin** | `GET/POST/PUT/PATCH/DELETE` sur `/api/admin/entreprises/`, `lieux/`, `users/`, `categories/`, `produits/`, `stocks/`, `transferts/`, `achats-usine/`, `tickets/` (GET), `categories-depense/`, `depenses/` | IsAdminRole |
| **Comptable** | `GET /api/comptable/stocks/`, `transferts/`, `ventes/`, `depenses/` | IsComptableRole (comptable ou admin) |

*Preuve : `api/urls.py` + `api/views/*.py` (permission_classes sur chaque ViewSet).*

### B.3 Services critiques

**Vente** (`ventes/services.py`) :
- **atomic** : L41 `with transaction.atomic():`
- **Verrouillage stock** : L47-49 `Stock.objects.select_for_update().get(produit=..., lieu=lieu)` avant vérification ; L69-74 même chose avant débit.
- **Anti-stock négatif** : vérification `stock.quantite < quantite` → ErreurStock ; modèle `inventaire.Stock` : `CheckConstraint(quantite__gte=0)` + `save()` lève ValidationError si quantite < 0.

**Transfert** (`inventaire/services.py`) :
- **atomic** : L67 `with transaction.atomic():`
- **Mise à jour stock** : L73-76 select_for_update usine ; L96-113 débit usine, crédit boutique (select_for_update sur stock destination si existant).

**Dépense** (`api/serializers.py` DepenseSerializer) :
- **Validation montants** : L212-215 `validate_montant` → montant < 0 lève ValidationError.
- **Rattachement lieu** : modèle `Depense` FK `lieu` (PROTECT) ; pas de contrainte DB montant ≥ 0.

*Preuve : fichiers cités, lignes indiquées.*

---

## C) FRONTEND (PREUVES)

### C.1 npm run dev / build

- **npm run dev** : démarre (`next dev` lancé, pas d’erreur de démarrage observée).
- **npm run build** : **échoue** :
```
Failed to compile.
./src/app/api/[...path]/route.ts
13:10  Error: 'isPublicPath' is defined but never used.  @typescript-eslint/no-unused-vars
```

*Preuve : sortie réelle de `npm run build`.*

### C.2 Pages principales existantes

| Route | Fichier | Existant |
|-------|---------|----------|
| /login | `src/app/login/page.tsx` | Oui |
| /admin | `src/app/(app)/admin/page.tsx` | Oui |
| /comptable | `src/app/(app)/comptable/page.tsx` | Oui |
| /boutique/caisse | `src/app/(app)/boutique/caisse/page.tsx` | Oui |

*Preuve : structure `konis-frontend/src/app`.*

### C.3 Auth cookies et accès par rôle

- Login : `api/auth/login` (via proxy Next) → cookies JWT (access_token, refresh_token).
- Layout `(app)/layout.tsx` : `useAuth()` → si pas `user`, `router.replace("/login")` ; nav selon `user.role` : admin (admin, comptable, caisse), comptable (comptable), boutique (caisse).
*Preuve : `auth-context.tsx`, `(app)/layout.tsx` (navByRole).*

### C.4 Impression ticket 58mm

- **Backend** : template Django `templates/ticket_print.html`, vue `ventes/views.py` `ticket_print`, URL `/ventes/ticket/<id>/print/`. CSS print : 58mm, marges 2mm, police monospace 11px (dans le template).
- **Frontend** : composant React `src/components/caisse/ticket-58mm.tsx` (Ticket58mm) avec `printStyle`, largeur 58mm, fontSize 10px, pour aperçu/impression.
*Preuve : fichiers cités ; `docs/IMPRESSION-TICKET-58MM.md`.*

---

## D) BASE DE DONNÉES (PREUVES)

### D.1 DB réellement utilisée par Django

Sans variable `DATABASE_URL` (dev actuel) :

```
ENGINE: django.db.backends.sqlite3
NAME: db.sqlite3 (fichier local)
```

*Preuve : script Python avec `django.setup()` et `settings.DATABASES['default']` — pas de secret affiché.*

Avec `DATABASE_URL` défini : `konis/settings/dev.py` utilise `dj_database_url.parse(_db_url)` → **Postgres** (host/db name visibles dans l’URL, pas le mot de passe).

### D.2 Schéma et tables

Tables clés listées (introspection) :

- **Users / auth** : `core_customuser`, `core_entreprise`, `core_lieu`
- **Produits** : `produits_categorie`, `produits_produit`
- **Stock / inventaire** : `inventaire_stock`, `inventaire_transfert`, `inventaire_mouvementstock`, `inventaire_achatusine`
- **Ventes** : `ventes_ticket`, `ventes_lignevente`
- **Dépenses** : `depenses_categoriedepense`, `depenses_depense`
- **Audit** : `audit_auditlog`

*Preuve : `python manage.py shell -c "from django.db import connection; print(connection.introspection.table_names())"`.*

### D.3 Contraintes / index

- **Stock quantite ≥ 0** : `inventaire/models.py` L26 `CheckConstraint(condition=Q(quantite__gte=0), name="stock_quantite_positive")`.
- **Unique (produit, lieu) pour stock** : L25 `UniqueConstraint(fields=["produit", "lieu"], name="unique_stock_produit_lieu")`.
- **Unique ticket (lieu, numero)** : `ventes/models.py` L21-26 `UniqueConstraint(fields=["lieu", "numero"], condition=Q(numero__isnull=False) & ~Q(numero=""), name="unique_ticket_lieu_numero")`.

*Preuve : modèles + migrations correspondantes.*

### D.4 Données (après seed)

```
Entreprises: 1
Lieux: 4 (usine: 1, magasin: 3)
Produits: 20
Stocks: 20
Tickets: 0
Depenses: 0
CategorieDepense: 5
AuditLog: 0
```

*Preuve : `python manage.py shell` avec `*.objects.count()` après `seed --no-input`.*

### D.5 Cohérence

- **Stock après seed** : stocks uniquement à l’usine (20 lignes Stock, lieu=usine).
- **Transfert + vente test** : possible (admin crée transfert usine→boutique ; boutique crée vente). Vérifié par les tests métier (voir E).

---

## E) TESTS MÉTIER “IMPOSSIBLES À TRICHER” (PREUVES)

Exécution : `python manage.py test api.tests.test_metier_proof -v 2`

**Résultat** :

```
test_1_vente_valide_ticket_et_stock_diminue ... ok
test_2_vente_quantite_superieure_stock_refus_400 ... ok
test_3_transfert_usine_boutique_stocks_ok ... ok
test_4_boutique_ne_voit_pas_autre_boutique ... ok
test_5_depense_visible_admin_et_comptable ... ok

Ran 5 tests in 3.969s
OK
```

**Détail des 5 tests** :
1. **Vente valide** → ticket créé (id, numero) + stock boutique diminue de la quantité vendue.
2. **Vente quantité > stock** → 400 + `detail` contenant une mention de stock (insuffisant / pas de stock).
3. **Transfert usine→boutique** → stock usine baisse, stock boutique augmente des quantités transférées.
4. **Boutique ne voit pas l’autre** → liste `/api/boutique/ventes/` pour boutique2 ne contient pas les ids des tickets de boutique1.
5. **Dépense créée** → visible dans `/api/admin/depenses/` (admin) et `/api/comptable/depenses/` (comptable).

*Preuve : fichier `api/tests/test_metier_proof.py` + sortie ci-dessus.*

---

## F) CE QUI MANQUE (PRIORITÉ)

**P0 (bloquant prod)**  
- Corriger le build frontend (ESLint : supprimer ou utiliser `isPublicPath` dans `api/[...path]/route.ts`).  
- Valider en local avec **PostgreSQL** (DATABASE_URL + migrate/seed/test) pour alignement prod.

**P1 (métier)**  
- Contrainte DB `depense.montant >= 0` (optionnel si serializer seul jugé suffisant).  
- Aucun autre manque métier critique identifié.

**P2 (UX)**  
- Lien “Imprimer ticket” depuis la caisse vers `/ventes/ticket/<id>/print/` ou ouverture popup (doc dans `docs/IMPRESSION-TICKET-58MM.md`).

**P2 (déploiement)**  
- Backups : stratégie documentée dans `docs/PRODUCTION-READINESS.md`.  
- Monitoring : health check sur `/api/health/` (db=ok).  
- Sentry : proposition dans la même doc (optionnel).

---

## G) PLAN D’ACTION (MAX 10 ÉTAPES)

1. **Corriger le lint frontend** : dans `konis-frontend/src/app/api/[...path]/route.ts`, supprimer ou utiliser `isPublicPath` pour que `npm run build` passe.
2. **PostgreSQL local** : lancer `docker compose up -d`, définir `DATABASE_URL` (et `DJANGO_SETTINGS_MODULE=konis.settings.dev`), puis `migrate`, `seed --no-input`, `test api`.
3. **Vérifier** : `GET /api/health/` avec Postgres → `db: "ok"`.
4. **Créer une vente test** (boutique) et contrôler en base que le stock a diminué (script shell ou test existant).
5. **Documenter** dans le README ou AUDIT : “En dev sans DATABASE_URL → SQLite ; avec DATABASE_URL → Postgres.”
6. **Optionnel** : ajouter une migration `CheckConstraint` sur `Depense.montant >= 0` si souhaité en base.
7. **Optionnel** : depuis la caisse, ajouter un bouton “Imprimer” ouvrant `/ventes/ticket/<id>/print/`.
8. **Backup** : mettre en place un cron (ou tâche planifiée) avec la commande pg_dump décrite dans `docs/PRODUCTION-READINESS.md`.
9. **Monitoring** : configurer un uptime check sur `/api/health/` (db=ok).
10. **Checklist finale** : valider les 15 points de la checklist “V0 OK TERRAIN” dans `AUDIT-FINAL-KONIS-V0.md`.

---

*Document généré à partir des commandes et fichiers du projet — pas de refactorisation effectuée pendant l’audit.*
