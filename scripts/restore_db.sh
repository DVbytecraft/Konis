#!/bin/bash
# Restore PostgreSQL KONIS V0
# Usage: DATABASE_URL=postgres://... ./scripts/restore_db.sh <fichier.dump>
# Pas de secrets en dur.

set -e
if [ -z "$DATABASE_URL" ]; then
  echo "DATABASE_URL non défini." >&2
  exit 1
fi
if [ -z "$1" ] || [ ! -f "$1" ]; then
  echo "Usage: $0 <fichier.dump>" >&2
  exit 1
fi
pg_restore -d "$DATABASE_URL" -c --if-exists "$1"
echo "Restauration terminée: $1"
