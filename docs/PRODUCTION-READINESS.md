# Production readiness minimum – KONIS V0

## Backups

### Stratégie PostgreSQL (pg_dump)

- **Fréquence** : quotidien (volume faible) ou hebdomadaire (selon volume).
- **Rétention** : 7 jours minimum.
- **Rappel** : activer les backups automatiques du provider (Render, Supabase, etc.).

### Backup

```bash
# Via DATABASE_URL (variable d'environnement, jamais en dur)
pg_dump "$DATABASE_URL" -F c -f konis_backup_$(date +%Y%m%d_%H%M).dump
```

Ou avec `scripts/backup_db.sh` (utilise `$DATABASE_URL`).

### Restore

```bash
# Restauration (remplace les données existantes)
pg_restore -d "$DATABASE_URL" -c --if-exists konis_backup_YYYYMMDD_HHMM.dump
```

Ou avec `scripts/restore_db.sh` (utilise `$DATABASE_URL` et le fichier passé en argument).

---

## Monitoring

### Uptime check

- **Endpoint** : `GET /api/health/`
- **Réponse** : `{ "status": "ok", "db": "ok", "version": "v0" }`
- **Vérifier** : `db === "ok"` pour confirmer la connexion Postgres.

**Exemple** (cron ou service externe) :

```bash
curl -s https://votre-api.com/api/health/ | jq -e '.db == "ok"' || exit 1
```

---

## Logs – Sentry

### Backend (Django)

1. Installer : `pip install sentry-sdk`
2. Dans `konis/settings/prod.py` :

```python
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[DjangoIntegration()],
    traces_sample_rate=0.1,
    send_default_pii=False,
    environment="production",
)
```

3. Variable d'environnement : `SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx`

---

## Checklist rapide

- [ ] Backups pg_dump planifiés
- [ ] Health check configuré (uptime)
- [ ] Sentry configuré (optionnel)
- [ ] `DEBUG=False`, `SECRET_KEY` et `DATABASE_URL` en prod
