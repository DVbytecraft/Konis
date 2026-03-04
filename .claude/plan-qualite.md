# Plan — Standard qualité professionnelle KONIS

## CONSTATS D'AUDIT (résumé)

### Infrastructure ✅ (très bonne base)
- Docker multi-stage, nginx SSL, rate-limiting : EXCELLENT
- CI/CD absent, pas de secrets manager : à faire
- 10 fichiers de tests, couverture ~70% : à compléter

### Backend — Problèmes réels
| Sévérité | Problème | Fichier |
|---|---|---|
| 🔴 Important | Duplication 98% entre `transfert_usine_vers_boutique()` et `transfert_entre_usines()` | inventaire/services.py |
| 🔴 Important | `float()` au lieu de `Decimal()` dans validate_lignes → risques précision | api/serializers.py |
| 🔴 Important | Aucune pagination sur les ListViews → OOM si données grandissent | boutique/admin views |
| 🟠 Important | `_get_request_data()` workaround DRF inutile (53 lignes) | usine_views.py |
| 🟠 Important | `FactoryDashboardView.get()` : 63 lignes, 6 requêtes séparées sans prefetch | usine_views.py |
| 🟠 Important | Helpers `_get_lieu_boutique` / `_usine_lieu` dupliqués entre views | boutique/usine views |
| 🟠 Important | Audit log manquant dans inventaire/usine services | services.py |
| 🟡 Mineur | `get_stock_restant()` : requête N+1 dans serializer (1 query par lot) | serializers.py |

### Frontend — Problèmes réels
| Sévérité | Problème | Fichier |
|---|---|---|
| 🟠 Important | `auth-context.tsx` : 3 `fetch()` manuels au lieu d'`apiFetch`, silent errors | auth-context.tsx |
| 🟠 Important | Logique métier (calcul KPI, totaux) dans composants page | admin/page.tsx, comptable/page.tsx |
| 🟠 Important | Pattern loading/error/fetch dupliqué dans 17 pages | toutes les pages |
| 🟡 Mineur | `apiFetch()` retourne `Promise<any>` → pas de type safety | api.ts |

### Tests — Gaps identifiés
- Tests des services : 0 test sur `ventes/services.py`, `inventaire/services.py`, `usine/services.py`
- Tests des nouvelles validations (prix=0, poids incohérent) : 0
- Tests de régression sur `montant_total` : 0

---

## PLAN D'ACTION — 4 TIERS ORDONNÉS

### TIER 1 — Corrections qualité backend (sans risque de casse)

**T1.1** — `inventaire/services.py` : extraire `_transfert_interne()` pour éliminer la duplication 98%

**T1.2** — `api/serializers.py` : remplacer `float()` par `Decimal()` dans `validate_lignes` (boutique + facture)

**T1.3** — Pagination DRF globale : ajouter `DEFAULT_PAGINATION_CLASS` dans `settings/base.py` + `PAGE_SIZE=50`

**T1.4** — `api/utils.py` : créer helpers partagés (`get_lieu_for_user`, `filter_by_date`, `filter_by_lieu`)

**T1.5** — `usine_views.py` : supprimer `_get_request_data()` inutile, décomposer `FactoryDashboardView.get()`

**T1.6** — Audit log dans `inventaire/services.py` et `usine/services.py` : tracer les transferts

### TIER 2 — Tests unitaires (couverture services core)

**T2.1** — `api/tests/test_services_vente.py` : vente simple, vente+mouture, mouture-seule, montant_total

**T2.2** — `api/tests/test_services_inventaire.py` : transfert, stock négatif bloqué, stock multi-produits

**T2.3** — `api/tests/test_validations.py` : prix=0 bloqué, poids incohérent bloqué, quantite<=0 bloqué

**T2.4** — `api/tests/test_services_usine.py` : creer_lot, transfert_vers_boutique, transfert_inter_usine

### TIER 3 — Qualité frontend

**T3.1** — `frontend/src/hooks/use-fetch.ts` : hook `useFetch<T>(url)` → `{data, loading, error, refetch}`

**T3.2** — `frontend/src/lib/api.ts` : typer `apiFetch<T>()` en générique

**T3.3** — `frontend/src/contexts/auth-context.tsx` : remplacer les 3 `fetch()` par `apiFetch`

**T3.4** — `frontend/src/hooks/use-kpi.ts` : extraire calculs KPI de `admin/page.tsx`

### TIER 4 — Documentation architecture

**T4.1** — `ARCHITECTURE.md` : diagramme textuel, description des apps, conventions, flux data

---

## PÉRIMÈTRE NON INCLUS (trop risqué ou hors scope immédiat)
- CI/CD GitHub Actions (infrastructure externe, pas de dépôt git remote connu)
- Secrets manager (Render/AWS, infrastructure externe)
- Monitoring Sentry (infrastructure externe)
- Celery/Redis (changement d'architecture trop lourd)
- Tests E2E frontend (no test framework frontend actuellement)

Ces points sont documentés dans ARCHITECTURE.md comme "Phase suivante".

---

## GARANTIES
- Aucune migration DB nécessaire
- Aucun changement d'API (rétrocompatibilité totale)
- Tests exécutés après chaque tier pour valider
- Fonctionnalités existantes préservées

## FICHIERS MODIFIÉS (liste attendue)
### Backend
- `inventaire/services.py`
- `api/serializers.py`
- `konis/settings/base.py`
- `api/utils.py` (nouveau)
- `api/views/usine_views.py`
- `api/tests/test_services_vente.py` (nouveau)
- `api/tests/test_services_inventaire.py` (nouveau)
- `api/tests/test_validations.py` (nouveau)
- `api/tests/test_services_usine.py` (nouveau)

### Frontend
- `frontend/src/hooks/use-fetch.ts` (nouveau)
- `frontend/src/lib/api.ts`
- `frontend/src/contexts/auth-context.tsx`
- `frontend/src/hooks/use-kpi.ts` (nouveau)

### Docs
- `ARCHITECTURE.md` (nouveau)
