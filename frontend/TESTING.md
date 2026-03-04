# KONIS Frontend — Guide de test

## Tests automatisés

### Installation (première fois)

```bash
cd frontend
npm install
```

### Lancer les tests

```bash
npm test               # run + watch
npm run test:run       # run une fois (CI)
npm run test:ui        # interface graphique Vitest
```

### Couverture

```bash
npm run test:coverage
```

---

## Validation manuelle — flux d'authentification

À faire après toute modification de `auth-context.tsx`, des routes `/api/auth/*`, ou du middleware.

### Prérequis
- `docker compose up` (backend + DB + Redis)
- `npm run dev` (frontend)

---

### 1. Connexion nominale

1. Ouvrir `http://localhost:3000`
2. Se connecter avec un utilisateur valide
3. **Vérifier dans DevTools → Application → Cookies :**
   - `access_token` présent, `httpOnly`, `SameSite=Lax`
   - `refresh_token` présent, `httpOnly`, `SameSite=Lax`
   - `csrftoken` présent, **non** `httpOnly` (lu par le JS pour X-CSRFToken)
4. Naviguer sur quelques pages — pas de 401 dans la console

---

### 2. Refresh silencieux au bootstrap (cas critique)

Simule le retour d'un utilisateur après 10+ minutes d'inactivité.

1. Se connecter
2. Dans DevTools → Application → Cookies → **Supprimer uniquement `access_token`** (garder `refresh_token`)
3. Rafraîchir la page (F5)
4. **Résultat attendu :** La page se charge normalement, sans redirection vers `/login`
5. **Vérifier en console :** Un 401 sur `/api/auth/me` suivi d'un appel à `/api/auth/refresh` puis d'un second `/api/auth/me` — c'est le refresh silencieux, c'est normal.
6. Vérifier que `access_token` est de nouveau présent dans les cookies

---

### 3. Session vraiment expirée

1. Se connecter
2. Dans DevTools → Cookies → **Supprimer `access_token` ET `refresh_token`**
3. Rafraîchir la page
4. **Résultat attendu :** Redirection vers `/login`
5. Vérifier qu'aucune boucle de requêtes ne se produit (max 2 appels : `/me` + `/refresh`)

---

### 4. Timeout serveur

1. Couper le backend : `docker compose stop backend`
2. Rafraîchir la page
3. **Résultat attendu :** Après ~10 secondes, redirection vers `/login` avec log de timeout en console
4. Redémarrer le backend : `docker compose start backend`

---

### 5. Vérification "aucune requête fantôme"

1. Ouvrir DevTools → Network
2. Faire les scénarios 2 et 3 ci-dessus
3. **Vérifier :** Après redirection vers `/login`, aucune nouvelle requête vers `/api/auth/*` ne s'envoie en arrière-plan.

---

### 6. Validation DO App Platform spec

```bash
# Valider le fichier de spec avant tout déploiement
doctl apps spec validate .do/app.yaml

# Si doctl non installé :
# brew install doctl  (macOS)
# ou https://docs.digitalocean.com/reference/doctl/how-to/install/
```

---

## Checklist avant merge

- [ ] `npm test` → tous les tests passent
- [ ] Scénario 1 (connexion nominale) validé manuellement
- [ ] Scénario 2 (refresh silencieux) validé manuellement
- [ ] Scénario 3 (session expirée) validé manuellement
- [ ] `doctl apps spec validate .do/app.yaml` → aucune erreur
- [ ] Aucun `console.log` de debug dans les fichiers modifiés
