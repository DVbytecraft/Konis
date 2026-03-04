"""
Script seed KONIS V0 :
- 1 entreprise KONIS
- 1 usine, 3 boutiques
- 1 admin, 1 comptable, 3 comptes boutique
- 20 produits (catégories + produits provenderie)
- Stocks initiaux (usine)
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import CustomUser, Entreprise, Lieu
from depenses.models import CategorieDepense, Depense
from inventaire.models import AchatUsine, MouvementStock, Stock, Transfert
from produits.models import Categorie, Produit
from ventes.models import LigneVente, Ticket


class Command(BaseCommand):
    help = "Seed KONIS : entreprise, lieux, utilisateurs, produits, stocks initiaux."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Ne pas demander de confirmation si des données existent.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        no_input = options["no_input"]

        if Entreprise.objects.exists() and not no_input:
            if input("Entreprise déjà présente. Continuer et tout recréer ? (y/N) ").lower() != "y":
                self.stdout.write("Annulé.")
                return

        self.stdout.write("Suppression des données existantes (hors migrations)...")
        LigneVente.objects.all().delete()
        Ticket.objects.all().delete()
        MouvementStock.objects.all().delete()
        Transfert.objects.all().delete()
        AchatUsine.objects.all().delete()
        Depense.objects.all().delete()
        Stock.objects.all().delete()
        CustomUser.objects.all().delete()
        Lieu.objects.all().delete()
        Entreprise.objects.all().delete()
        Produit.objects.all().delete()
        Categorie.objects.all().delete()
        CategorieDepense.objects.all().delete()

        # 1. Entreprise
        self.stdout.write("Création entreprise KONIS...")
        entreprise = Entreprise.objects.create(nom="KONIS")

        # 2. Lieux : 1 usine, 3 boutiques (code pour numéros ticket KONIS-CODE-YYYYMMDD-SEQ)
        self.stdout.write("Création lieux...")
        usine = Lieu.objects.create(
            entreprise=entreprise,
            nom="Usine KONIS",
            code="USINE",
            type_lieu=Lieu.TYPE_USINE,
        )
        b1 = Lieu.objects.create(
            entreprise=entreprise,
            nom="Boutique Centre",
            code="CENTRE",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        b2 = Lieu.objects.create(
            entreprise=entreprise,
            nom="Boutique Nord",
            code="NORD",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        b3 = Lieu.objects.create(
            entreprise=entreprise,
            nom="Boutique Sud",
            code="SUD",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        boutiques = [b1, b2, b3]

        # 3. Utilisateurs
        self.stdout.write("Création utilisateurs...")
        admin_user = CustomUser.objects.create_user(
            username="admin",
            password="admin123",
            email="admin@konis.local",
            first_name="Admin",
            last_name="KONIS",
            role=CustomUser.ROLE_ADMIN,
            entreprise=entreprise,
            is_staff=True,
            is_superuser=True,
        )
        CustomUser.objects.create_user(
            username="comptable",
            password="comptable123",
            email="comptable@konis.local",
            first_name="Comptable",
            last_name="KONIS",
            role=CustomUser.ROLE_COMPTABLE,
            entreprise=entreprise,
        )
        CustomUser.objects.create_user(
            username="usine",
            password="usine123",
            email="usine@konis.local",
            first_name="Responsable",
            last_name="Usine",
            role=CustomUser.ROLE_USINE,
            entreprise=entreprise,
            lieu=usine,
        )
        for i, lieu in enumerate(boutiques, 1):
            CustomUser.objects.create_user(
                username=f"boutique{i}",
                password="boutique123",
                email=f"boutique{i}@konis.local",
                first_name=f"Boutique {lieu.nom}",
                last_name="",
                role=CustomUser.ROLE_BOUTIQUE,
                entreprise=entreprise,
                lieu=lieu,
            )

        # 4. Catégories et 20 produits (provenderie)
        self.stdout.write("Création catégories et produits...")
        categories_data = [
            ("Aliments volailles", ["Aliment poulet démarrage", "Aliment poulet croissance", "Aliment ponte", "Aliment dinde"]),
            ("Aliments bétail", ["Aliment veau", "Aliment bovin engraissement", "Aliment vache laitière", "Aliment mouton"]),
            ("Aliments porcins", ["Aliment porcelet", "Aliment porc croissance", "Aliment truie"]),
            ("Aliments lapins", ["Aliment lapin croissance", "Aliment lapin reproducteur"]),
            ("Compléments", ["Minéraux bétail", "Vitamines volailles", "Prémélange porc", "Levure digestive", "Sel bloc"]),
        ]
        noms_plats = []
        for _cat_nom, noms in categories_data:
            noms_plats.extend(noms)
        # Exactement 20 noms (compléter si < 20)
        while len(noms_plats) < 20:
            noms_plats.append(f"Produit complémentaire {len(noms_plats) + 1}")
        noms_20 = noms_plats[:20]

        produits_created = []
        idx = 0
        for cat_nom, noms in categories_data:
            cat = Categorie.objects.create(nom=cat_nom)
            for _ in noms:
                if idx >= 20:
                    break
                p = Produit.objects.create(
                    categorie=cat,
                    nom=noms_20[idx],
                    code=f"P{idx + 1:03d}",
                    unite="kg",
                )
                produits_created.append(p)
                idx += 1
        cat_default = Categorie.objects.first()
        while len(produits_created) < 20:
            p = Produit.objects.create(
                categorie=cat_default,
                nom=noms_20[len(produits_created)],
                code=f"P{len(produits_created) + 1:03d}",
                unite="kg",
            )
            produits_created.append(p)

        # 4b. Catégories dépenses (par défaut)
        self.stdout.write("Création catégories dépenses...")
        categories_depense = [
            "Fournitures",
            "Transport",
            "Entretien",
            "Salaires",
            "Autres",
        ]
        for nom in categories_depense:
            CategorieDepense.objects.get_or_create(nom=nom)

        # 5. Stocks initiaux (usine uniquement)
        self.stdout.write("Création stocks initiaux à l'usine...")
        quantites_init = [100, 200, 150, 80, 120, 250, 180, 90, 110, 160, 140, 170, 130, 95, 210, 75, 190, 220, 165, 145]
        for produit, qte in zip(produits_created, quantites_init[: len(produits_created)]):
            Stock.objects.create(
                produit=produit,
                lieu=usine,
                quantite=Decimal(str(qte)),
            )

        self.stdout.write(self.style.SUCCESS("Seed terminé."))
        self.stdout.write(f"  - Entreprise : {entreprise.nom}")
        self.stdout.write(f"  - Usine : {usine.nom}, Boutiques : {[b.nom for b in boutiques]}")
        self.stdout.write(f"  - Utilisateurs : admin, comptable, usine, boutique1, boutique2, boutique3")
        self.stdout.write(f"  - Produits : {Produit.objects.count()}, Stocks usine : {Stock.objects.count()}")
        self.stdout.write("  - Mots de passe : admin123 / comptable123 / usine123 / boutique123")
