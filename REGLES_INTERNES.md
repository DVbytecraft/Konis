# KONIS — Règles internes, rôles et seuils

Ce document centralise les règles métier et techniques non triviales de KONIS.
À mettre à jour à chaque changement de comportement significatif.

---

## Rôles et permissions

### Hiérarchie des rôles

| Rôle            | Accès                                                                 |
|-----------------|-----------------------------------------------------------------------|
| `supreme_admin` | Tout — cross-tenant, création stock boutique, supervision globale     |
| `admin`         | Son entreprise — gestion complète (users, produits, finances, stock)  |
| `daf`           | Lecture seule sur toutes les vues (bloqué par `DafReadOnlyMixin`)     |
| `comptable`     | Lecture seule (même restriction que DAF)                              |
| `boutique`      | Caisse, stock propre, créances locales                                |
| `mpsl`          | Achats MP, transferts stock                                           |
| `usine`         | Lots de production, cessions de finis                                 |
| `collecteur`    | Collectes argent, dépôt bancaire                                      |

### `DafReadOnlyMixin`

Bloque les actions d'écriture pour les rôles `daf` et `comptable` sur 11 actions :
`create`, `update`, `partial_update`, `destroy`, et les custom actions de mutation.
Retourne HTTP 403 avec message explicite.

### `supreme_admin` — règles spécifiques

- Peut accéder à toutes les entreprises (pas de filtre `entreprise_id`).
- Peut créer du stock dans **n'importe quelle boutique** via `POST /api/boutique/stock/`.
  - Vérification dans `StockBoutiqueViewSet.create()` :
    ```python
    if request.user.role not in (ROLE_ADMIN, ROLE_SUPREME_ADMIN):
        raise PermissionDenied
    ```
- N'est **pas** bloqué par `DafReadOnlyMixin`.
- Ses actions sont auditées comme celles de `admin` (via `audit_log()`).

---

## Isolation multi-tenant

- Chaque modèle métier porte un `entreprise_id` (FK vers `core.Entreprise`).
- Tous les querysets dans les views sont filtrés par `request.user.entreprise`.
- Les serializers avec queryset scopé (`BoutiqueStockReceiptSerializer`,
  `LotProductionCreateSerializer`, `UserSerializer`) utilisent `get_fields()`
  pour filtrer les FKs — ils nécessitent `context={"request": request}`.
- Transferts de stock inter-entreprises : **interdits** au niveau service
  (`inventaire/services.py` et `usine/services.py` vérifient que
  `lieu_source.entreprise == lieu_destination.entreprise`).

---

## Idempotency et STRICT_MODE

### Header `Idempotency-Key`

Toutes les opérations critiques doivent envoyer un header `Idempotency-Key` :

| Opération                    | Vue                         | Format clé          |
|------------------------------|-----------------------------|---------------------|
| Vente boutique               | `VenteBoutiqueViewSet`      | `vente-{uuid}`      |
| Mouture seule                | `MoutureSeuleView`          | `mouture-{uuid}`    |
| Conversion sacs → kg         | `ConvertirSacEnKgView`      | `conversion-{uuid}` |
| Dépense                      | `DepenseViewSet`            | `depense-{uuid}`    |

Générée côté frontend par `buildIdempotencyKey(scope)` dans `frontend/src/lib/utils.ts`.

### `IDEMPOTENCY_STRICT_MODE`

- Défini dans `konis/settings/base.py` : `True` par défaut.
- Quand `True` : toute requête POST critique **sans** `Idempotency-Key` → HTTP 400.
- Quand `False` : header optionnel, pas de rejet.
- En production, **ne jamais désactiver** — garantit la traçabilité des ventes.

### Replay idempotent

- Même clé envoyée deux fois → HTTP 200 avec la ressource existante (pas de doublon).
- Implémenté via `get_idempotency_info()` dans les views DRF concernées.

---

## Stock — règles de conversion sacs → kg

### Modèle dual

Chaque `Stock` porte deux champs :
- `quantite` : nombre de sacs entiers
- `quantite_kg` : kg issus de conversions

### `Stock.convertir_sacs_en_kg(nombre_sacs)`

- Protégé par `transaction.atomic()` + `select_for_update()` (race condition safe).
- Prérequis : `produit.poids_par_sac` doit être défini et > 0.
- Résultat : `quantite -= nombre_sacs`, `quantite_kg += nombre_sacs * poids_par_sac`.
- Lance `ValueError` si stock insuffisant ou `poids_par_sac` absent.

### Conversion automatique lors d'une vente

Dans `inventaire/services.py:_prelever_stock_unite()` :
- Si le stock en kg est insuffisant mais qu'il reste des sacs, une conversion
  automatique est déclenchée pour couvrir la demande.
- L'événement est loggué à `konis.alerts` niveau `INFO` :
  `CONVERSION_AUTO lieu=X produit=Y sacs=N kg=Z`

---

## Surveillance — `check_alerts`

### Usage

```bash
# Avec seuils par défaut
python manage.py check_alerts

# Seuils personnalisés
python manage.py check_alerts --seuil-stock 5 --seuil-creances 500000 \
    --jours-collectes 7 --seuil-conversions-jour 30
```

### Détecteurs et seuils par défaut

| Détecteur                    | Seuil défaut         | Logger level  |
|------------------------------|----------------------|---------------|
| `STOCK_BAS`                  | < 2 sacs/kg          | WARNING       |
| `STOCK_ZERO`                 | quantite=0 ET kg=0   | WARNING       |
| `PROJET_DEPASSEMENT`         | dépenses > budget    | WARNING       |
| `CREANCE_ELEVEE`             | restant > 100 000 F  | WARNING       |
| `COLLECTE_NON_DEPOSEE`       | > 3 jours sans dépôt | WARNING       |
| `CONVERSIONS_FREQUENTES`     | > 20/jour            | WARNING       |
| `TICKETS_SANS_IDEMPOTENCY_KEY` | > 0 (STRICT=True)  | ERROR         |

### Notifications (prod uniquement)

Configurer dans les variables d'environnement :

```
SLACK_ALERTS_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
ALERTS_EMAIL_TO=admin@konis.app,daf@konis.app
```

- Slack : POST JSON `{"text": "..."}` via `urllib.request` (pas de dépendance externe).
- Email : `django.core.mail.send_mail` — nécessite `EMAIL_HOST` configuré.
- Si les deux sont vides : alertes dans les logs uniquement.

### Cron recommandé (prod)

```cron
0 * * * * /app/venv/bin/python /app/manage.py check_alerts >> /var/log/konis_alerts.log 2>&1
```

---

## Logging namespaces

| Logger          | Niveau prod | Contenu                                           |
|-----------------|-------------|---------------------------------------------------|
| `konis.alerts`  | WARNING     | Toutes les alertes `check_alerts` + throttle 429  |
| `konis.audit`   | INFO        | Actions métier auditées (ventes, dépenses, etc.)  |
| `konis.perf`    | WARNING     | Requêtes lentes, N+1 détectés                     |
| `django.security` | WARNING   | Tentatives d'intrusion, CSRF, XSS                 |

---

## Throttling

| Scope               | Limite   | ViewSets concernés                              |
|---------------------|----------|-------------------------------------------------|
| `login`             | 5/min    | `LoginView`                                     |
| `ventes_create`     | 30/min   | `VenteBoutiqueViewSet`                          |
| `facture_create`    | 30/min   | `FactureViewSet`                                |
| `usine_create`      | 30/min   | `LotProductionViewSet`, `CessionViewSet`        |
| `finance_create`    | 30/min   | 7 ViewSets finance (créanciers, emprunts, etc.) |
| `user`              | 600/hour | Tous les users authentifiés                     |

Un dépassement de `login` ou `ventes_create` est loggué à `konis.alerts` niveau WARNING.

---

## Intégrité des données

### `on_delete=PROTECT`

- `LigneVente.ticket` → PROTECT (tickets immuables une fois créés)
- `LigneFacture.facture` → PROTECT
- `MouvementStock.transfert` → PROTECT

### CheckConstraints DB (exemples critiques)

- Tous les montants financiers : `> 0`
- `Ticket.montant_total` : `>= 0`
- `LigneVente.quantite` : `> 0`
- `Emprunt.taux_interet` : `<= 100`
- `Produit.poids_par_sac` : `NULL OR > 0`
- `Lieu.prix_mouture_defaut` : `NULL OR > 0`

---

## Migrations — ordre et risques

Toujours appliquer les migrations dans cet ordre en prod :
1. `core` (modèles de base, Lieu, Entreprise, User)
2. `produits`
3. `inventaire`
4. `ventes`
5. `finance`
6. `depenses`, `audit`
7. `usine`

Après chaque déploiement : vérifier `python manage.py showmigrations` avant de
redémarrer Gunicorn.
