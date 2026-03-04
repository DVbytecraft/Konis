#!/bin/bash
# Backup PostgreSQL KONIS V0
# Usage: DATABASE_URL=postgres://... ./scripts/backup_db.sh [output_dir]
# Pas de secrets en dur.

set -e
OUTDIR="${1:-./backups}"
mkdir -p "$OUTDIR"
if [ -z "$DATABASE_URL" ]; then
  echo "DATABASE_URL non défini." >&2
  exit 1
fi
FILE="$OUTDIR/konis_$(date +%Y%m%d_%H%M).dump"
pg_dump "$DATABASE_URL" -F c -f "$FILE"
echo "Backup: $FILE"
