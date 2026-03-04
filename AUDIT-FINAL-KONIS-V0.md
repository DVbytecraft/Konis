# AUDIT FINAL KONIS V0 — ACTIONS + PREUVES TECHNIQUES

## 1. Stock en concurrence

### 1.1 transaction.atomic()

| Fichier | Fonction | Ligne |
|---------|----------|-------|
| `ventes/services.py` | `vente_boutique` | 41 |
| `inventaire/services.py` | `achat_usine` | 34 |
| `inventaire/services.py` | `transfert_usine_vers_boutique` | 67 |

### 1.2 select_for_update()

| Fichier | Fonction | Contexte |
|---------|----------|----------|
| `ventes/services.py` | `vente_boutique` | L47-49 : vérification stock avant vente |
| `ventes/services.py` | `vente_boutique` | L69-74 : débit stock après création ticket |
| `ventes/services.py` | `generer_numero_ticket` | Verrouillage Lieu pour unicité numéro |
| `inventaire/services.py` | `transfert_usine_vers_boutique` | L73-76, L96-97, L102-104 : verrouillage stocks |

### 1.3 Stock négatif

- **Validation** : `inventaire/models.py` L36-40 — `save()` lève `ValidationError` si `quantite < 0`
- **Contrainte DB** : `inventaire/models.py` L26 — `CheckConstraint(quantite__gte=0, name="stock_quantite_positive")`

### 1.4 Test unitaire

- **Fichier** : `api/tests/test_ventes.py`
- **Tests** :
  - `test_vente_ok_stock_diminue` : vente valide → stock passe de 50 à 40
  - `test_stock_insuffisant_400` : quantité > stock → 400 + "Stock insuffisant"
- **Exécution** : `python manage.py test api.tests.test_ventes`

---

## 2. Ticket numbering

### 2.1 Format

`TK-{lieu_id}-{YYYYMMDD}-{seq:04d}`  
Exemple : `TK-2-20260208-0001`

### 2.2 Unicité en concurrence

- **Contrainte** : `ventes/models.py` — `UniqueConstraint(lieu, numero)` (condition: numero non vide)
- **Migration** : `ventes/migrations/0003_ticket_unique_ticket_lieu_numero.py`
- **Génération** : `ventes/services.py` — verrouillage `Lieu.objects.select_for_update().get(pk=lieu.pk)` avant `count()` pour sérialiser les créations par lieu/jour

### 2.3 Test

- **Fichier** : `api/tests/test_ventes.py` — `test_deux_ventes_consecutives_numeros_differents`
- **Assertions** : 2 ventes consécutives → 2 numéros différents, format TK-*

---

## 3. Impression ticket 58mm

### 3.1 Page / template

- **URL** : `/ventes/ticket/<id>/print/`
- **Template** : `templates/ticket_print.html`
- **Vue** : `ventes/views.py` — `ticket_print`

### 3.2 CSS print

```css
@page { size: 58mm auto; margin: 2mm; }
body { width: 58mm; max-width: 58mm; font-family: 'Courier New'; font-size: 11px; padding: 2mm 3mm; }
```

### 3.3 Doc réglage

- **Fichier** : `docs/IMPRESSION-TICKET-58MM.md`
- Contenu : XPrinter, Chrome, marges, raccourci frontend

---

## 4. Catégories dépenses

### 4.1 Seed corrigé

- **Fichier** : `core/management/commands/seed.py`
- **Catégories créées** : Fournitures, Transport, Entretien, Salaires, Autres
- **Commande** : `python manage.py seed --no-input`

### 4.2 Preuve

Après seed :
- `GET /api/admin/categories-depense/` (auth admin) → liste des catégories
- `POST /api/admin/depenses/` avec `lieu`, `categorie`, `montant`, `date` → 201

---

## 5. Admin

### 5.1 Django Admin (/admin/)

- **Lieu boutique** : `core/admin.py` — `LieuAdmin`
- **Compte boutique** : `core/admin.py` — `CustomUserAdmin` (champ `lieu`, `is_active`)
- **Dépenses** : `depenses/admin.py` — `CategorieDepenseAdmin`, `DepenseAdmin`

### 5.2 API Admin (/api/admin/)

- Lieux : `GET/POST /api/admin/lieux/`
- Users : `GET/POST /api/admin/users/`
- Déjà en place via `api/views/admin_views.py`

**Conclusion** : Admin via Django `/admin/` + API REST. Pas de front admin custom.

---

## 6. Production readiness

- **Backups** : `docs/PRODUCTION-READINESS.md` — stratégie pg_dump
- **Monitoring** : `/api/health/` — `db: "ok"`
- **Logs** : proposition Sentry dans la doc

---

## CHECKLIST V0 OK TERRAIN (15 cases max)

1. [ ] `python manage.py migrate` OK
2. [ ] `python manage.py seed --no-input` OK
3. [ ] `python manage.py test api` OK
4. [ ] `python manage.py runserver` OK
5. [ ] `GET /api/health/` → `db: "ok"`
6. [ ] Vente test créée → stock diminué en Postgres
7. [ ] Stock insuffisant → 400
8. [ ] 2 ventes consécutives → 2 numéros différents
9. [ ] `/ventes/ticket/1/print/` s'affiche (58mm)
10. [ ] Catégories dépenses présentes après seed
11. [ ] Création dépense possible après seed
12. [ ] Django admin : Lieu, User, CategorieDepense, Depense enregistrés
13. [ ] DATABASE_URL configuré (Postgres)
14. [ ] Backups planifiés (doc lue)
15. [ ] Health check configuré (doc lue)

---

## COMMANDES EXACTES

```bash
# 1. PostgreSQL (Docker) — démarrer Docker Desktop puis :
docker compose up -d

# 2. Variables (PowerShell)
$env:DATABASE_URL="postgres://konis:CHANGE_ME@localhost:5432/konis"
$env:DJANGO_SETTINGS_MODULE="konis.settings.dev"

# 3. Migrations + seed + tests + run
cd C:\Users\RAPHAEL\konis
python manage.py migrate
python manage.py seed --no-input
python manage.py test api
python manage.py runserver
```

**Sans Docker** : ne pas définir `DATABASE_URL` → Django utilise SQLite (`db.sqlite3`). Migrate/seed/test fonctionnent.

```bash
# Linux/macOS
export DATABASE_URL=postgres://konis:CHANGE_ME@localhost:5432/konis
export DJANGO_SETTINGS_MODULE=konis.settings.dev
python manage.py migrate
python manage.py seed --no-input
python manage.py test api
python manage.py runserver
```

---

## IDENTIFIANTS DE TEST

| Utilisateur | Mot de passe | Rôle | Défini dans |
|-------------|--------------|------|-------------|
| admin | admin123 | Admin | `core/management/commands/seed.py` |
| comptable | comptable123 | Comptable | idem |
| boutique1 | boutique123 | Boutique (Boutique Centre) | idem |
| boutique2 | boutique123 | Boutique (Boutique Nord) | idem |
| boutique3 | boutique123 | Boutique (Boutique Sud) | idem |

Voir aussi : `README-DEPLOYMENT.md` si existant.
