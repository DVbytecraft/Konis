"""
Commande de réinitialisation avant déploiement en production.

Usage :
    python manage.py reset_for_production [--confirm]

Cette commande supprime toutes les données opérationnelles (ventes, stocks,
productions, dépenses, logs d'audit, etc.) tout en conservant les données de
configuration essentielles :
    - Entreprises
    - Lieux (usines et magasins)
    - Utilisateurs et groupes
    - Catégories de produits et produits
    - Catégories de dépenses

ATTENTION : Cette opération est irréversible. Faites un backup avant de l'exécuter.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


OPERATIONAL_MODELS = [
    # Ordre respectant les contraintes FK (enfants avant parents)
    ("ventes", "LigneFacture"),
    ("ventes", "LigneVente"),
    ("ventes", "Facture"),
    ("ventes", "Ticket"),
    ("inventaire", "MouvementStock"),
    ("usine", "TransfertInterUsine"),
    ("usine", "TransfertCession"),
    ("usine", "LotProduction"),
    ("inventaire", "Transfert"),
    ("inventaire", "AchatUsine"),
    ("inventaire", "Stock"),
    ("depenses", "Depense"),
    ("audit", "AuditLog"),
]


class Command(BaseCommand):
    help = "Supprime les données de test/dev avant déploiement en production."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirme l'exécution sans prompt interactif.",
        )

    def handle(self, *args, **options):
        if not options["confirm"]:
            self.stdout.write(self.style.WARNING(
                "\n⚠️  ATTENTION : Cette commande supprime définitivement toutes les données opérationnelles.\n"
                "Données conservées : Entreprises, Lieux, Utilisateurs, Groupes, Produits, Catégories.\n"
                "Données supprimées : Ventes, Tickets, Factures, Stocks, Productions, Dépenses, Logs d'audit.\n\n"
                "Effectuez un backup complet avant de continuer.\n"
            ))
            confirm = input("Tapez 'CONFIRMER' pour continuer : ")
            if confirm.strip() != "CONFIRMER":
                raise CommandError("Opération annulée.")

        self.stdout.write("Début de la réinitialisation...")

        with transaction.atomic():
            for app_label, model_name in OPERATIONAL_MODELS:
                from django.apps import apps
                try:
                    model = apps.get_model(app_label, model_name)
                    count, _ = model.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ {app_label}.{model_name} : {count} entrée(s) supprimée(s)")
                    )
                except LookupError:
                    self.stdout.write(
                        self.style.WARNING(f"  ⚠ Modèle introuvable : {app_label}.{model_name} (ignoré)")
                    )

        self.stdout.write(self.style.SUCCESS(
            "\n✅ Réinitialisation terminée. Base de données prête pour la production.\n"
            "Données conservées : Entreprises, Lieux, Utilisateurs, Groupes, Produits, Catégories.\n"
        ))
