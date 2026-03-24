"""
Tests pour le module Admin Corrections.
"""
from decimal import Decimal
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from audit.models import AuditLog
from core.models import CustomUser, Entreprise, Lieu
from finance.models import CaisseSupremeTransaction
from inventaire.models import Stock
from produits.models import Produit, Categorie
from ventes.models import Ticket, LigneVente


class AdminCorrectionsPermissionTests(APITestCase):
    """Tests des permissions pour les corrections admin."""

    @classmethod
    def setUpTestData(cls):
        cls.entreprise = Entreprise.objects.create(nom="Test_Enterprise")

        # Créer les utilisateurs
        cls.supreme_admin = CustomUser.objects.create_user(
            username="supreme_admin",
            email="supreme@test.local",
            password="pass123",
            role=CustomUser.ROLE_SUPREME_ADMIN,
            entreprise=cls.entreprise,
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin",
            email="admin@test.local",
            password="pass123",
            role=CustomUser.ROLE_ADMIN,
            entreprise=cls.entreprise,
        )
        cls.comptable = CustomUser.objects.create_user(
            username="comptable",
            email="comptable@test.local",
            password="pass123",
            role=CustomUser.ROLE_COMPTABLE,
            entreprise=cls.entreprise,
        )
        cls.collecteur = CustomUser.objects.create_user(
            username="collecteur",
            email="collecteur@test.local",
            password="pass123",
            role=CustomUser.ROLE_COLLECTEUR,
            entreprise=cls.entreprise,
        )

        # Créer les lieux
        cls.boutique = Lieu.objects.create(
            nom="Boutique Test",
            type_lieu=Lieu.TYPE_MAGASIN,
            entreprise=cls.entreprise,
        )

        # Créer les produits
        cls.categorie = Categorie.objects.create(
            nom="Catégorie Test",
            entreprise=cls.entreprise,
        )
        cls.produit = Produit.objects.create(
            nom="Produit Test",
            code="PROD001",
            categorie=cls.categorie,
            entreprise=cls.entreprise,
            poids_par_sac=50,
        )

    def _auth_token(self, user):
        """Générer un token JWT pour l'utilisateur."""
        return f"Bearer {str(RefreshToken.for_user(user).access_token)}"

    # ────────────────────────────────────────────────────────────────────────
    # TESTS PERMISSION - CAISSE
    # ────────────────────────────────────────────────────────────────────────

    def test_caisse_supreme_admin_allowed(self):
        """Supreme admin peut corriger la caisse."""
        payload = {
            "lieu_id": self.boutique.id,
            "montant": "10000",
            "operation": "ajouter",
            "motif": "Correction de caisse"
        }
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.supreme_admin)
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.json()["success"])

    def test_caisse_admin_allowed(self):
        """Admin peut corriger la caisse."""
        payload = {
            "lieu_id": self.boutique.id,
            "montant": "5000",
            "operation": "retrancher",
            "motif": "Correction de caisse"
        }
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.json()["success"])

    def test_caisse_comptable_forbidden(self):
        """Comptable ne peut pas corriger la caisse."""
        payload = {
            "lieu_id": self.boutique.id,
            "montant": "10000",
            "operation": "ajouter",
            "motif": "Correction de caisse"
        }
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.comptable)
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_caisse_collecteur_forbidden(self):
        """Collecteur ne peut pas corriger la caisse."""
        payload = {
            "lieu_id": self.boutique.id,
            "montant": "10000",
            "operation": "ajouter",
            "motif": "Correction de caisse"
        }
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.collecteur)
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    # ────────────────────────────────────────────────────────────────────────
    # TESTS PERMISSION - STOCK
    # ────────────────────────────────────────────────────────────────────────

    def test_stock_admin_allowed(self):
        """Admin peut corriger le stock."""
        payload = {
            "lieu_id": self.boutique.id,
            "produit_id": self.produit.id,
            "quantite": "10",
            "operation": "ajouter",
            "motif": "Correction de stock"
        }
        r = self.client.post(
            "/api/admin/corrections/stock/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.json()["success"])

    def test_stock_comptable_forbidden(self):
        """Comptable ne peut pas corriger le stock."""
        payload = {
            "lieu_id": self.boutique.id,
            "produit_id": self.produit.id,
            "quantite": "10",
            "operation": "ajouter",
            "motif": "Correction de stock"
        }
        r = self.client.post(
            "/api/admin/corrections/stock/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.comptable)
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    # ────────────────────────────────────────────────────────────────────────
    # TESTS VALIDATION
    # ────────────────────────────────────────────────────────────────────────

    def test_caisse_motif_required(self):
        """Motif obligatoire pour corriger la caisse."""
        payload = {
            "lieu_id": self.boutique.id,
            "montant": "10000",
            "operation": "ajouter",
            "motif": ""  # Empty motif
        }
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("motif", r.json())

    def test_caisse_montant_positive(self):
        """Montant doit être positif."""
        payload = {
            "lieu_id": self.boutique.id,
            "montant": "-5000",
            "operation": "ajouter",
            "motif": "Correction"
        }
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("montant", r.json())

    def test_stock_quantite_required_for_add(self):
        """Quantité requise pour 'ajouter' au stock."""
        payload = {
            "lieu_id": self.boutique.id,
            "produit_id": self.produit.id,
            "operation": "ajouter",
            "motif": "Correction"
            # Missing quantite
        }
        r = self.client.post(
            "/api/admin/corrections/stock/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # ────────────────────────────────────────────────────────────────────────
    # TESTS BUSINESS LOGIC - CAISSE
    # ────────────────────────────────────────────────────────────────────────

    def test_caisse_ajouter_creates_depot(self):
        """'ajouter' crée un dépôt dans la caisse supreme."""
        payload = {
            "lieu_id": self.boutique.id,
            "montant": "25000",
            "operation": "ajouter",
            "motif": "Dépôt de correction"
        }
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        # Vérifier que la transaction a été créée
        tx = CaisseSupremeTransaction.objects.filter(
            type_transaction="depot",
            montant=Decimal("25000")
        ).first()
        self.assertIsNotNone(tx)
        self.assertIn("CORRECTION CAISSE", tx.description)

    def test_caisse_retrancher_creates_retrait(self):
        """'retrancher' crée un retrait dans la caisse supreme."""
        payload = {
            "lieu_id": self.boutique.id,
            "montant": "15000",
            "operation": "retrancher",
            "motif": "Retrait réconciliation"
        }
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        # Vérifier que la transaction a été créée
        tx = CaisseSupremeTransaction.objects.filter(
            type_transaction="retrait",
            montant=Decimal("15000")
        ).first()
        self.assertIsNotNone(tx)

    # ────────────────────────────────────────────────────────────────────────
    # TESTS BUSINESS LOGIC - STOCK
    # ────────────────────────────────────────────────────────────────────────

    def test_stock_ajouter(self):
        """'ajouter' augmente le stock."""
        payload = {
            "lieu_id": self.boutique.id,
            "produit_id": self.produit.id,
            "quantite": "50",
            "operation": "ajouter",
            "motif": "Correction stock ajout"
        }
        r = self.client.post(
            "/api/admin/corrections/stock/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # Les décimales sont sérialisées avec .00 par DRF
        self.assertIn(r.json()["quantite_apres"], ["50", "50.00"])

        # Vérifier le stock en DB
        stock = Stock.objects.get(lieu=self.boutique, produit=self.produit)
        self.assertEqual(stock.quantite, Decimal("50"))

    def test_stock_retrancher(self):
        """'retrancher' diminue le stock."""
        # Créer un stock initial
        Stock.objects.create(
            lieu=self.boutique,
            produit=self.produit,
            quantite=Decimal("100")
        )

        payload = {
            "lieu_id": self.boutique.id,
            "produit_id": self.produit.id,
            "quantite": "30",
            "operation": "retrancher",
            "motif": "Correction stock retrait"
        }
        r = self.client.post(
            "/api/admin/corrections/stock/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # Les décimales sont sérialisées avec .00 par DRF
        self.assertIn(r.json()["quantite_apres"], ["70", "70.00"])

    def test_stock_supprimer(self):
        """'supprimer' vide le stock."""
        Stock.objects.create(
            lieu=self.boutique,
            produit=self.produit,
            quantite=Decimal("100")
        )

        payload = {
            "lieu_id": self.boutique.id,
            "produit_id": self.produit.id,
            "operation": "supprimer",
            "motif": "Suppression stock"
        }
        r = self.client.post(
            "/api/admin/corrections/stock/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["quantite_apres"], "0")

        stock = Stock.objects.get(lieu=self.boutique, produit=self.produit)
        self.assertEqual(stock.quantite, Decimal("0"))

    # ────────────────────────────────────────────────────────────────────────
    # TESTS AUDIT LOGGING
    # ────────────────────────────────────────────────────────────────────────

    def test_caisse_audit_logged(self):
        """Correction de caisse est tracée dans l'audit."""
        payload = {
            "lieu_id": self.boutique.id,
            "montant": "10000",
            "operation": "ajouter",
            "motif": "Test audit"
        }
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        # Vérifier l'audit log
        audit = AuditLog.objects.filter(
            user=self.admin,
            action="caisse_correction_depot"
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.object_type, "CaisseSupremeTransaction")
        self.assertIn("motif", audit.extra)
        self.assertEqual(audit.extra["motif"], "Test audit")

    def test_stock_audit_logged(self):
        """Correction de stock est tracée dans l'audit."""
        payload = {
            "lieu_id": self.boutique.id,
            "produit_id": self.produit.id,
            "quantite": "25",
            "operation": "ajouter",
            "motif": "Test audit stock"
        }
        r = self.client.post(
            "/api/admin/corrections/stock/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        # Vérifier l'audit log
        audit = AuditLog.objects.filter(
            user=self.admin,
            action="stock_correction_ajouter"
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.object_type, "Stock")
        self.assertIn("quantite_avant", audit.extra)
        self.assertIn("quantite_apres", audit.extra)
        self.assertIn("motif", audit.extra)


class AdminCorrectionTicketTests(APITestCase):
    """Tests pour la suppression de tickets."""

    @classmethod
    def setUpTestData(cls):
        cls.entreprise = Entreprise.objects.create(nom="Test_Enterprise")

        cls.admin = CustomUser.objects.create_user(
            username="admin",
            email="admin@test.local",
            password="pass123",
            role=CustomUser.ROLE_ADMIN,
            entreprise=cls.entreprise,
        )
        cls.comptable = CustomUser.objects.create_user(
            username="comptable",
            email="comptable@test.local",
            password="pass123",
            role=CustomUser.ROLE_COMPTABLE,
            entreprise=cls.entreprise,
        )

        cls.boutique = Lieu.objects.create(
            nom="Boutique Test",
            type_lieu=Lieu.TYPE_MAGASIN,
            entreprise=cls.entreprise,
        )

        cls.categorie = Categorie.objects.create(
            nom="Catégorie Test",
            entreprise=cls.entreprise,
        )
        cls.produit = Produit.objects.create(
            nom="Produit Test",
            code="PROD001",
            categorie=cls.categorie,
            entreprise=cls.entreprise,
            poids_par_sac=50,
        )

        # Créer un ticket avec lignes de vente
        cls.ticket = Ticket.objects.create(
            lieu=cls.boutique,
            numero="TEST001",
            montant_total=Decimal("100000"),
            montant_cash=Decimal("100000"),
            montant_credit=Decimal("0"),
        )
        LigneVente.objects.create(
            ticket=cls.ticket,
            produit=cls.produit,
            quantite=Decimal("10"),
            prix_unitaire=Decimal("10000"),
        )

    def _auth_token(self, user):
        return f"Bearer {str(RefreshToken.for_user(user).access_token)}"

    def test_admin_can_delete_ticket(self):
        """Admin peut supprimer un ticket."""
        payload = {"motif": "Erreur de paiement"}
        r = self.client.post(
            f"/api/admin/corrections/ticket/{self.ticket.id}/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.json()["success"])

        # Vérifier que le ticket existe toujours (pas suppression, juste retour du stock)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket)

    def test_non_admin_cannot_delete_ticket(self):
        """Comptable ne peut pas supprimer un ticket."""
        payload = {"motif": "Erreur de paiement"}
        r = self.client.post(
            f"/api/admin/corrections/ticket/{self.ticket.id}/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.comptable)
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_ticket_deletion_motif_required(self):
        """Motif obligatoire pour supprimer un ticket."""
        payload = {"motif": ""}
        r = self.client.post(
            f"/api/admin/corrections/ticket/{self.ticket.id}/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ticket_deletion_audit_logged(self):
        """Suppression de ticket est tracée dans l'audit."""
        payload = {"motif": "Annulation pour test"}
        r = self.client.post(
            f"/api/admin/corrections/ticket/{self.ticket.id}/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=self._auth_token(self.admin)
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["motif"], "Annulation pour test")

        # Vérifier l'audit log
        audit = AuditLog.objects.filter(
            user=self.admin,
            action="ticket_annule"
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.object_type, "Ticket")
        self.assertEqual(audit.extra["ticket_numero"], "TEST001")
