#!/usr/bin/env python
"""
Diagnostic UnicodeDecodeError psycopg2 - KONIS backend.
Affiche : ENGINE, host/port/dbname, encodage DATABASE_URL, version psycopg.
"""
import os
import sys

# 1) Version psycopg2 / psycopg
print("=== VERSIONS ===")
try:
    import psycopg2
    print("psycopg2:", getattr(psycopg2, "__version__", "N/A"))
except ImportError as e:
    print("psycopg2: IMPORT ERROR:", e)

try:
    import psycopg
    print("psycopg:", getattr(psycopg, "__version__", "N/A"))
except ImportError:
    print("psycopg: non installé")

# 2) DATABASE_URL - présence et analyse
_db_url = os.environ.get("DATABASE_URL")
print("\n=== DATABASE_URL ===")
if not _db_url:
    print("DATABASE_URL: non défini")
    sys.exit(1)
print("DATABASE_URL défini: OUI (longueur:", len(_db_url), ")")

# Encodage / caractères non ASCII
try:
    ascii_only = _db_url.encode("ascii")
    print("ASCII uniquement: OUI")
except UnicodeEncodeError as e:
    print("ASCII uniquement: NON - contient des caractères non-ASCII")
    print("  Premier problème autour de:", repr(_db_url[max(0, e.start - 5):e.end + 5]))

# Bytes raw (pour debug encodage Windows)
_raw = _db_url.encode("utf-8")
print("Encodage UTF-8 valide: OUI" if _raw else "N/A")

# Structure masquée (sans user/pass)
# Format typique: postgres://user:pass@host:port/dbname
parts = _db_url.split("@")
if len(parts) >= 2:
    after_at = parts[-1]
    # after_at = host:port/dbname ou host:port/dbname?params
    if "/" in after_at:
        host_port, db_part = after_at.split("/", 1)
        dbname = db_part.split("?")[0] if "?" in db_part else db_part
        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
        else:
            host, port = host_port, "5432"
    else:
        host, port, dbname = "?", "?", "?"
else:
    host, port, dbname = "?", "?", "?"

print("\n=== STRUCTURE MASQUÉE (sans user/pass) ===")
print("HOST:", host)
print("PORT:", port)
print("DB name:", dbname)

# 3) Django DATABASES (si possible)
print("\n=== DJANGO DATABASES (via dj_database_url) ===")
try:
    import dj_database_url
    db = dj_database_url.parse(_db_url)
    print("ENGINE:", db.get("ENGINE", "N/A"))
    print("HOST:", db.get("HOST", "N/A"))
    print("PORT:", db.get("PORT", "N/A"))
    print("NAME:", db.get("NAME", "N/A"))
except Exception as e:
    print("Erreur parse:", type(e).__name__, str(e))

# 4) Test connexion directe psycopg2 (sans afficher secrets)
print("\n=== TEST CONNEXION psycopg2 ===")
try:
    conn = psycopg2.connect(_db_url)
    conn.close()
    print("Connexion: OK")
except Exception as e:
    print("Connexion: FAIL")
    print("Type:", type(e).__name__)
    print("Message:", str(e))

print("\n=== FIN DIAGNOSTIC ===")
