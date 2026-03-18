"""
Configuration Gunicorn KONIS — serveur 4 vCPU / 8 GB RAM.

Dimensionnement :
  Serveur cible : 4 vCPU, 8 GB RAM, SSD NVMe
  Workers       : (2 × 4) + 1 = 9  (formule Gunicorn recommandée pour I/O bound)
  Threads       : 2 par worker (gthread) → 18 connexions simultanées max
  RAM estimée   : ~100-150 MB/worker × 9 = ~1.2 GB (Django + preload copy-on-write)
  Connexions DB : 9 × 2 = 18 max → PostgreSQL max_connections=50 confortable

  Capacité : ~50–100 requêtes/seconde (pic 20–50 ventes simultanées OK).
"""

import multiprocessing
import os

# ── Bind ──────────────────────────────────────────────────────────────────────
bind = "0.0.0.0:8000"

# ── Workers ───────────────────────────────────────────────────────────────────
# Pour 4 vCPU : (2 × 4) + 1 = 9 workers. Surcharge via GUNICORN_WORKERS.
_default_workers = multiprocessing.cpu_count() * 2 + 1
workers = int(os.environ.get("GUNICORN_WORKERS", _default_workers))

# gthread : threads légers pour I/O Django (DB, cache Redis)
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", 2))

# ── Timeouts ──────────────────────────────────────────────────────────────────
# 30s : toute requête web normale doit répondre en < 30s.
# Les migrations sont gérées dans entrypoint.sh AVANT le démarrage de Gunicorn.
timeout          = 60    # Worker tué si pas de réponse après 60s (PDF ReportLab + lente DB)
graceful_timeout = 20    # Temps pour finir les requêtes en cours au restart
keepalive        = 5     # HTTP keep-alive (secondes)

# ── Recyclage des workers (anti-fuite mémoire) ────────────────────────────────
max_requests        = 1000   # Worker redémarré après 1000 requêtes
max_requests_jitter = 150    # ±150 → évite le restart simultané (jitter > nb_workers)

# ── Optimisation mémoire ──────────────────────────────────────────────────────
# preload_app=True : Django chargé UNE FOIS dans le master process.
# Workers forké après → copy-on-write → économie RAM significative.
# Attention : incompatible avec certains signaux de rechargement (--reload).
preload_app = True

# ── Logging ───────────────────────────────────────────────────────────────────
# Stdout/stderr → capturés par Docker → accessibles via docker logs
accesslog  = "-"
errorlog   = "-"
loglevel   = "warning"  # info = trop verbeux en prod ; warning = erreurs seulement

# Format logs d'accès (durée en µs pour détection requêtes lentes)
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'
