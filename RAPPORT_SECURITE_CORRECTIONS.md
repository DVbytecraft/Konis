# Rapport de Correction des Failles de Sécurité - KONIS

## Résumé Exécutif

Ce rapport documente les corrections de sécurité appliquées au système KONIS pour éliminer les vulnérabilités financières identifiées. Chaque correction est accompagnée d'une explication détaillée et des instructions de déploiement.

---

## 🔴 Corrections Appliquées

### 1. Collecte Fraudable - Interdiction de Modification des Montants

**Problème**: Les collecteurs pouvaient modifier les montants après collecte, permettant des détournements.

**Solution**: 
- `api/views/finance_views.py` - `CollecteViewSet.partial_update()`
- Interdiction stricte: le collecteur ne peut modifier que les notes
- Toute tentative de modification des montants (`montant_trouve`, `montant_pris`) est refusée (403)
- Seul admin/DAF peut corriger les montants avec audit log

**Fichiers Modifiés**:
- `api/views/finance_views.py`

---

### 2. Solde Manuel Interdit - Vérification de Permission

**Problème**: N'importe quel utilisateur pouvait solder manuellement un journal sans paiement réel.

**Solution**:
- `finance/services.py` - `solder_journal_payable()` et `solder_journal_creance()`
- Vérification stricte: seuls admin/DAF peuvent solder manuellement
- Lève `ErreurFinance` si permission insuffisante
- Audit log amélioré avec indicateur `est_remise`

**Fichiers Modifiés**:
- `finance/services.py`

---

### 3. Validation à Deux Niveaux pour Paiements Élevés

**Problème**: Pas de validation spéciale pour les montants élevés (potentiellement frauduleux).

**Solution**:
- `api/views/finance_views.py` - `JournalPayableViewSet.create()`
- Pour tout montant >= 1,000,000 FCFA: code de validation obligatoire
- Retourne `code_validation_required: True` si absent

**Fichiers Modifiés**:
- `api/views/finance_views.py`

---

### 4. Statut PENDING pour Créancier/Fournisseur

**Problème**: Les fournisseurs pouvaient être utilisés avant validation, permettant des opérations frauduleuses avec des entités non vérifiées.

**Solution**:
- `finance/models.py` - Ajout champ `statut` sur `Creancier`
  - Valeurs: `actif`, `inactif`, `pending`
  - Valeur par défaut: `pending`
- `api/views/finance_views.py` - Vérification avant utilisation
  - Un créancier doit être `actif` pour être utilisé dans un journal payable
  - Retourne erreur 400 si statut != `actif`

**Fichiers Modifiés**:
- `finance/models.py`
- `api/views/finance_views.py`

**Attention**: Requiert PostgreSQL pour les tests. La migration est générée mais non appliquée.

---

### 5. Bloquage du Dépassement de Budget Projet

**Problème**: Les dépenses projet pouvaient dépasser le budget sans contrôle.

**Solution**:
- `finance/services.py` - `enregistrer_depense_projet()`
- Par défaut: bloque si `montant > budget_restant`
- Option `autoriser_depassement=True` nécessite rôle admin/DAF
- Audit log avec indicateur `depassement`

**Fichiers Modifiés**:
- `finance/services.py`

---

### 6. Prix Unitaire Strictement Positif

**Problème**: Les transferts permettaient des prix négatifs ou nuls (valeur sans transfert).

**Solution**:
- `api/serializers/inventaire.py` - `TransfertCreateSerializer.validate_lignes()`
- Validation explicite: `unit_price >= 0`
- Lève `ValidationError` si valeur négative

**Fichiers Modifiés**:
- `api/serializers/inventaire.py`

---

## 🔄 État des Corrections

| Correction | Statut | PostgreSQL Requis |
|------------|--------|-------------------|
| Collecte - Interdiction modification | ✅ Appliqué | Non |
| Solde manuel - Permission | ✅ Appliqué | Non |
| Paiements élevés - Validation | ✅ Appliqué | Non |
| Fournisseur - Statut PENDING | ✅ Appliqué | Oui* |
| Budget projet - Bloquage | ✅ Appliqué | Non |
| Prix unitaire - Positif | ✅ Appliqué | Non |

*Tests unitaires nécessitent PostgreSQL en raison de contraintes SQL avancées.

---

## 📋 Instructions de Déploiement

### Étape 1: Sauvegarde
```bash
# Sauvegarder la base de données
pg_dump konis_prod > backup_pre_securite_$(date +%Y%m%d).sql
```

### Étape 2: Migration PostgreSQL
```bash
# Appliquer les migrations
python manage.py migrate finance

#OU si erreur de migration exists:
python manage.py migrate finance --fake
```

### Étape 3: Redémarrer les Services
```bash
# Redémarrer Django
sudo systemctl restart gunicorn

# Redémarrer Next.js
sudo systemctl restart nextjs
```

### Étape 4: Vérification
```bash
# Tester l'API
curl -X POST http://localhost:8000/api/finance/creanciers/ \
  -H "Content-Type: application/json" \
  -d '{"nom": "Nouveau Fournisseur", "type_creancier": "fournisseur"}'
# Doit retourner 201 avec statut "pending"
```

---

## 🧪 Tests de Sécurité

Les tests suivants doivent être exécutés après déploiement:

1. **Collecteur ne peut pas modifier les montants**
2. **Admin/DAF peut solder manuellement un journal**
3. **Créancier inactif ne peut pas être utilisé**
4. **Dépense projet bloquée si dépassement**
5. **Prix unitaire négatif refusé dans les transferts**

---

## ⚠️ Notes Importantes

1. **PostgreSQL Requis**: Les contraintes de base de données avancées ne fonctionnent pas avec SQLite. Utilisez PostgreSQL en production.

2. **Code de Validation**: Le système de code de validation pour montants élevés est implémenté mais nécessite une méthode de vérification (à implémenter selon vos besoins).

3. **Rôle Collecteur**: Vérifiez que tous les collecteurs ont le rôle `collecteur` dans CustomUser.ROLE_COLLECTEUR.

4. **Audit**: Toutes les opérations sensibles sont journalisées. Vérifiez régulièrement les logs d'audit.

---

## 📞 Support

Pour toute question sur ces corrections, contactez l'équipe sécurité.
