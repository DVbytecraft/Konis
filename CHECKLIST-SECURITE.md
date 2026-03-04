# Checklist sécurité KONIS V0

Document de référence pour la sécurité de niveau production (V0).

---

## 1) Authentification robuste

| Élément | Implémentation | Fichier / réglage |
|--------|----------------|-------------------|
| JWT access + refresh (SimpleJWT) | ✅ | `rest_framework_simplejwt`, cookies httpOnly |
| Expiration courte access (5–15 min) | ✅ 10 min | `konis/settings/base.py` → `SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]` |
| Rotation refresh token | ✅ | `SIMPLE_JWT["ROTATE_REFRESH_TOKENS"] = True` |
| Blacklist refresh après logout | ✅ | `rest_framework_simplejwt.token_blacklist`, `LogoutView` appelle `RefreshToken(token).blacklist()` |
| Hash mots de passe (Django default) | ✅ | PBKDF2 par défaut, `AUTH_PASSWORD_VALIDATORS` activés |

---

## 2) Permissions serveur strictes

| Règle | Implémentation |
|-------|----------------|
| IsAdminUser / IsComptableUser / IsBoutiqueUser | ✅ Classes dans `api/permissions.py` (IsAdminRole, IsComptableRole, IsBoutiqueRole + aliases IsAdminUser, IsComptableUser, IsBoutiqueUser) |
| Boutique voit UNIQUEMENT ses données | ✅ Filtrage par `request.user.lieu` dans `get_queryset()` (stock, ventes) ; pas d’accès aux autres boutiques |
| Admin voit tout | ✅ IsAdminRole sur vues admin |
| Comptable lecture + dépenses | ✅ IsComptableRole sur API comptable (lecture seule) |
| Interdire accès croisé boutiques | ✅ API boutique filtre strictement par `user.lieu` |
| Pas de modification stock hors API métier | ✅ Pas d’édition directe du modèle Stock ; uniquement via ventes, transferts, achats usine (services métier) |

---

## 3) Sécurité API

| Élément | Implémentation |
|--------|----------------|
| Validation systématique (serializers) | ✅ Tous les create/update passent par des serializers avec `validate_*` |
| Rejet quantités négatives | ✅ `TransfertCreateSerializer`, `VenteBoutiqueCreateSerializer`, `AchatUsineCreateSerializer` ; contraintes DB (CheckConstraint) |
| Rejet prix négatifs | ✅ `VenteBoutiqueCreateSerializer.validate_lignes` (prix_unitaire >= 0) ; `DepenseSerializer.validate_montant` |
| Rejet stock insuffisant | ✅ `ventes.services.vente_boutique` + `inventaire.services` lèvent `ErreurStock` → 400 |
| Transactions atomiques ventes/transferts | ✅ `transaction.atomic()` dans `vente_boutique` et `transfert_usine_vers_boutique` |

---

## 4) Protection web

| Élément | Implémentation |
|--------|----------------|
| CSRF | ✅ `CsrfViewMiddleware` activé (cookies utilisés pour JWT) |
| CORS propre | ✅ `CORS_ALLOWED_ORIGINS` en dev/prod (frontend uniquement), `CORS_ALLOW_CREDENTIALS = True` |
| X-Frame-Options | ✅ `SecurityHeadersMiddleware` → `DENY` |
| X-Content-Type-Options | ✅ `nosniff` |
| Referrer-Policy | ✅ `strict-origin-when-cross-origin` |
| Content-Security-Policy (basique) | ✅ Politique restrictive (default-src 'self', script-src 'self', etc.) |

Fichier : `api/middleware.py` (SecurityHeadersMiddleware).

---

## 5) Sécurité base de données

| Élément | Implémentation |
|--------|----------------|
| Pas de SQL brut non sécurisé | ✅ Requêtes via ORM Django uniquement |
| Index champs critiques | ✅ Stock (produit, lieu ; lieu), Transfert (date, from_lieu+date, to_lieu+date), Ticket (lieu+date, date), Depense (lieu+date, date), AuditLog (user+created_at, action+created_at, object_type+object_id) |

---

## 6) Logs & audit

| Action | Enregistrée |
|--------|-------------|
| Connexion utilisateur | ✅ `audit_log(action="connexion", object_type="user")` dans `LoginView` |
| Vente créée | ✅ `audit_log(action="vente_creée", object_type="ticket", ...)` dans `VenteBoutiqueViewSet.create` |
| Transfert effectué | ✅ `audit_log(action="transfert_effectue", object_type="transfert", ...)` dans `TransfertViewSet.create` |
| Dépense ajoutée | ✅ `audit_log(action="depense_ajoutee", object_type="depense", ...)` dans `DepenseViewSet.perform_create` |

Modèle : `audit.AuditLog` (user, action, object_type, object_id, extra, created_at).  
Service : `audit.services.audit_log()`.

---

## 7) Rate limiting (anti-abus)

| Endpoint | Limite | Classe |
|----------|--------|--------|
| Login API | 10 / minute (par IP) | `api.throttling.LoginRateThrottle` |
| Création de ventes | 60 / minute (par utilisateur) | `api.throttling.VenteCreateRateThrottle` |

Réglages : `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` dans `konis/settings/base.py`.

---

## 8) Tests sécurité

| Test | Fichier | Description |
|------|--------|-------------|
| Refus accès non autorisé | `api/tests/test_security.py` | Sans token → 401 sur admin et boutique |
| Boutique ne voit pas l’API admin | id. | Cookie boutique → GET admin/stocks/ → 403 |
| Boutique ne voit que son stock | id. | boutique1 ne voit que le stock de son lieu |
| Impossibilité stock négatif | id. | Vente avec qty > stock → 400 + message "Stock insuffisant" |
| Refus accès autre boutique | id. | Ticket d’une autre boutique absent de la liste boutique1 |
| Token invalide / expiré refusé | id. | Bearer token invalide → 401 |

Commande : `python manage.py test api.tests.test_security`

---

## 9) Configuration sécurité (résumé)

- **base.py** : SIMPLE_JWT (lifetime, rotation, blacklist), REST_FRAMEWORK (auth, throttle_rates), SecurityHeadersMiddleware, CORS, AUTH_PASSWORD_VALIDATORS.
- **prod.py** : DEBUG=False, ALLOWED_HOSTS/SECRET_KEY obligatoires, HTTPS (SSL redirect, HSTS, secure cookies), CORS_ALLOWED_ORIGINS depuis l’env.

---

## Validation

- [x] Authentification JWT robuste (expiration, rotation, blacklist)
- [x] Permissions strictes par rôle (admin, comptable, boutique)
- [x] Boutique isolée (données de son lieu uniquement)
- [x] Validation API (quantités, prix, stock) et transactions atomiques
- [x] En-têtes de sécurité et CORS
- [x] ORM uniquement, index sur champs critiques
- [x] Audit (connexion, vente, transfert, dépense)
- [x] Rate limiting (login, création ventes)
- [x] Tests sécurité (accès, stock, isolement, token)

*Checklist sécurité KONIS V0 – validée pour un usage réel en entreprise.*
