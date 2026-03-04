"""
Commande de vérification de l'état de la base de données.

Usage :
    python manage.py check_db                  # vérifie l'état actuel
    python manage.py check_db --after-reset    # vérifie qu'un full_reset s'est bien passé
    python manage.py check_db --sequences      # affiche l'état des séquences PostgreSQL

Cette commande est en LECTURE SEULE : elle ne modifie rien.
Idéale pour valider l'état après un full_reset ou après un déploiement.

Codes de retour :
    0 → tout est OK
    1 → au moins une vérification a échoué (utilisable dans les scripts CI/CD)
"""
import sys

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection


# ── Tables métier à contrôler ─────────────────────────────────────────────────
# (app_label, model_name, description courte)
TABLES_METIER = [
    ("ventes",      "Ticket",             "Tickets de vente"),
    ("ventes",      "LigneVente",         "Lignes de vente"),
    ("ventes",      "Facture",            "Factures"),
    ("ventes",      "LigneFacture",       "Lignes de facture"),
    ("inventaire",  "Stock",              "Stocks"),
    ("inventaire",  "AchatUsine",         "Achats usine"),
    ("inventaire",  "Transfert",          "Transferts inventaire"),
    ("inventaire",  "MouvementStock",     "Mouvements de stock"),
    ("usine",       "LotProduction",      "Lots de production"),
    ("usine",       "TransfertCession",   "Cessions usine→boutique"),
    ("usine",       "TransfertInterUsine","Transferts inter-usines"),
    ("depenses",    "Depense",            "Dépenses"),
    ("depenses",    "CategorieDepense",   "Catégories de dépenses"),
    ("produits",    "Produit",            "Produits"),
    ("produits",    "Categorie",          "Catégories de produits"),
    ("core",        "Lieu",               "Lieux (boutiques / usines)"),
    ("core",        "Entreprise",         "Entreprises"),
    ("audit",       "AuditLog",           "Logs d'audit"),
]

TABLES_TOKENS = [
    ("token_blacklist", "OutstandingToken",  "Tokens JWT actifs"),
    ("token_blacklist", "BlacklistedToken",  "Tokens JWT blacklistés"),
]

TABLES_USERS = [
    ("core", "CustomUser", "Utilisateurs"),
]


class Command(BaseCommand):
    help = "Vérifie l'état de la base de données (lecture seule). Utiliser après full_reset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--after-reset",
            action="store_true",
            help=(
                "Mode strict : attend 0 entrée dans toutes les tables métier "
                "et exactement 1 superadministrateur. Retourne exit code 1 si "
                "la base n'est pas propre."
            ),
        )
        parser.add_argument(
            "--sequences",
            action="store_true",
            help="Affiche également l'état des séquences PostgreSQL.",
        )

    def handle(self, *args, **options):
        after_reset = options["after_reset"]
        show_sequences = options["sequences"]
        errors = []

        self.stdout.write("")
        if after_reset:
            self.stdout.write(self.style.WARNING("══ VÉRIFICATION POST-RESET ══"))
        else:
            self.stdout.write(self.style.HTTP_INFO("══ ÉTAT DE LA BASE DE DONNÉES ══"))
        self.stdout.write("")

        # ── Utilisateurs ──────────────────────────────────────────────────────
        self.stdout.write("  Comptes utilisateurs :")
        CustomUser = apps.get_model("core", "CustomUser")
        total_users = CustomUser.objects.count()
        superadmins = CustomUser.objects.filter(is_superuser=True)
        superadmin_count = superadmins.count()
        autres_count = total_users - superadmin_count

        for su in superadmins:
            self.stdout.write(
                self.style.SUCCESS(
                    f"    ✓ Superadmin conservé : {su.username} (id={su.pk}, "
                    f"lieu={'∅' if su.lieu_id is None else su.lieu_id}, "
                    f"entreprise={'∅' if su.entreprise_id is None else su.entreprise_id})"
                )
            )

        if superadmin_count == 0:
            msg = "    ✗ Aucun superadministrateur trouvé !"
            self.stdout.write(self.style.ERROR(msg))
            errors.append(msg)
        elif superadmin_count > 1 and after_reset:
            msg = f"    ✗ {superadmin_count} superadmins trouvés (attendu : 1)"
            self.stdout.write(self.style.ERROR(msg))
            errors.append(msg)

        if autres_count == 0:
            self.stdout.write("    — Aucun autre utilisateur")
        elif after_reset:
            msg = f"    ✗ {autres_count} utilisateur(s) non-superadmin encore présent(s)"
            self.stdout.write(self.style.ERROR(msg))
            errors.append(msg)
        else:
            self.stdout.write(f"    · {autres_count} autre(s) utilisateur(s)")

        self.stdout.write("")

        # ── Tables métier ─────────────────────────────────────────────────────
        self.stdout.write("  Tables métier :")
        for app_label, model_name, description in TABLES_METIER:
            count = self._count(app_label, model_name)
            if count is None:
                self.stdout.write(
                    self.style.WARNING(f"    ⚠ {description:35s} — modèle introuvable (app non installée ?)")
                )
            elif count == 0:
                self.stdout.write(f"    — {description:35s} 0")
            else:
                line = f"    · {description:35s} {count}"
                if after_reset:
                    self.stdout.write(self.style.ERROR(f"    ✗ {description:35s} {count} (attendu : 0)"))
                    errors.append(f"{app_label}.{model_name} : {count} entrée(s) résiduelle(s)")
                else:
                    self.stdout.write(line)

        self.stdout.write("")

        # ── Tokens JWT ────────────────────────────────────────────────────────
        self.stdout.write("  Tokens JWT :")
        for app_label, model_name, description in TABLES_TOKENS:
            count = self._count(app_label, model_name)
            if count is None:
                self.stdout.write(
                    self.style.WARNING(f"    ⚠ {description:35s} — token_blacklist non installé")
                )
            elif count == 0:
                self.stdout.write(f"    — {description:35s} 0 (invalidés)")
            else:
                line = f"    · {description:35s} {count}"
                if after_reset and app_label == "token_blacklist" and model_name == "OutstandingToken":
                    self.stdout.write(self.style.WARNING(
                        f"    ⚠ {description:35s} {count} (tokens actifs résiduels — expirent dans max 10 min)"
                    ))
                else:
                    self.stdout.write(line)

        self.stdout.write("")

        # ── Séquences PostgreSQL ──────────────────────────────────────────────
        if show_sequences or after_reset:
            self._check_sequences(errors, after_reset)

        # ── Résumé ────────────────────────────────────────────────────────────
        self.stdout.write("─" * 55)
        if not errors:
            if after_reset:
                self.stdout.write(self.style.SUCCESS("  ✅ Base PROPRE — reset validé avec succès."))
            else:
                self.stdout.write(self.style.SUCCESS("  ✅ Vérification terminée — aucun problème détecté."))
        else:
            self.stdout.write(self.style.ERROR(f"  ✗ {len(errors)} problème(s) détecté(s) :"))
            for e in errors:
                self.stdout.write(self.style.ERROR(f"      - {e}"))
            if after_reset:
                self.stdout.write(self.style.ERROR(
                    "\n  Relancez : python manage.py full_reset --dry-run\n"
                    "  puis     : python manage.py full_reset --superuser=<username> --confirm"
                ))
            sys.exit(1)

        self.stdout.write("")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _count(self, app_label, model_name):
        """Retourne le count ou None si le modèle n'existe pas."""
        try:
            model = apps.get_model(app_label, model_name)
            return model.objects.count()
        except LookupError:
            return None

    def _check_sequences(self, errors, strict):
        """Affiche l'état des séquences PostgreSQL et vérifie qu'elles sont à 1 en mode strict."""
        vendor = connection.vendor
        if vendor != "postgresql":
            self.stdout.write(
                self.style.WARNING(
                    f"  ⚠ Séquences : non applicable (moteur {vendor}, PostgreSQL requis)"
                )
            )
            return

        self.stdout.write("  Séquences PostgreSQL :")
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT s.sequence_name, p.last_value, p.start_value
                FROM information_schema.sequences s
                JOIN pg_sequences p ON p.sequencename = s.sequence_name
                WHERE s.sequence_schema = 'public'
                ORDER BY s.sequence_name
            """)
            rows = cursor.fetchall()

        if not rows:
            self.stdout.write("    — Aucune séquence trouvée dans le schéma public.")
            return

        non_reset = [(name, last_val) for name, last_val, _ in rows if last_val != 1]

        if not non_reset:
            self.stdout.write(
                self.style.SUCCESS(f"    ✓ {len(rows)} séquence(s) toutes à 1")
            )
        else:
            for name, last_val in non_reset:
                line = f"    · {name[:50]:50s} last_value={last_val}"
                if strict:
                    self.stdout.write(self.style.ERROR(f"    ✗ {name[:50]:50s} last_value={last_val} (attendu : 1)"))
                    errors.append(f"Séquence {name} : last_value={last_val}")
                else:
                    self.stdout.write(line)

            reset_count = len(rows) - len(non_reset)
            if reset_count:
                self.stdout.write(f"    — {reset_count} séquence(s) déjà à 1")

        self.stdout.write("")
