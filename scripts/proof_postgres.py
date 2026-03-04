#!/usr/bin/env python
"""
Preuve DB Postgres - affiche ENGINE, HOST, DB name (sans secrets) et comptages.
Usage: cd konis && DATABASE_URL=postgres://... python scripts/proof_postgres.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "konis.settings.dev")
django.setup()
from django.conf import settings
from django.db import connection

db = settings.DATABASES["default"]
engine = db.get("ENGINE", "")
name = db.get("NAME", "")
host = db.get("HOST", "")
port = db.get("PORT", "")

print("=== PREUVE DB ===")
print("ENGINE:", engine)
print("HOST:", host or "localhost")
print("PORT:", port or "5433")
print("DB name:", name)
is_postgres = "postgresql" in engine
print("PostgreSQL:", "OUI" if is_postgres else "NON")
if not is_postgres:
    exit(1)

# Comptages (sans exposer de données sensibles)
from core.models import Entreprise, Lieu
from produits.models import Produit
from inventaire.models import Stock
from ventes.models import Ticket
from depenses.models import Depense

print("\n=== NOMBRE DE LIGNES ===")
print("entreprises:", Entreprise.objects.count())
print("lieux:", Lieu.objects.count())
print("produits:", Produit.objects.count())
print("stock:", Stock.objects.count())
print("tickets:", Ticket.objects.count())
print("depenses:", Depense.objects.count())
print("\nOK")
