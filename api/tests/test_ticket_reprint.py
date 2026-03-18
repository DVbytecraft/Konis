"""
Tests endpoint réimpression de ticket.
POST /api/boutique/tickets/{ticket_id}/reimprimer/

Cas couverts :
  1. Réimpression crée un enregistrement TicketReprint en base
  2. La réponse retourne les données complètes du ticket
  3. Le montant_total n'est pas recalculé (valeur DB inchangée)
  4. Une boutique ne peut pas réimprimer un ticket d'un autre lieu → 404
  5. Un ticket inexistant retourne 404
  6. Sans authentification → 401
"""
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from inventaire.models import Stock
from produits.models import Produit
from ventes.models import Ticket, TicketReprint
from ventes.services import vente_boutique

URL = "/api/boutique/tickets/{ticket_id}/reimprimer/"


class TestTicketReprint(APITestCase):
    """Tests de l'endpoint POST /api/boutique/tickets/{id}/reimprimer/"""

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="KONIS Test")

        cls.boutique_a = Lieu.objects.create(
            entreprise=cls.ent,
            nom="Boutique A",
            code="BA",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.boutique_b = Lieu.objects.create(
            entreprise=cls.ent,
            nom="Boutique B",
            code="BB",
            type_lieu=Lieu.TYPE_MAGASIN,
        )

        cls.user_a = CustomUser.objects.create_user(
            username="vendeur_a",
            email="vendeur_a@konis.local",
            password="pass123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=cls.ent,
            lieu=cls.boutique_a,
        )
        cls.user_b = CustomUser.objects.create_user(
            username="vendeur_b",
            email="vendeur_b@konis.local",
            password="pass123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=cls.ent,
            lieu=cls.boutique_b,
        )

        cls.produit = Produit.objects.create(nom="Maïs", code="MAIS", unite="kg", entreprise=cls.ent)
        Stock.objects.create(produit=cls.produit, lieu=cls.boutique_a, quantite=Decimal("500"))

        # Ticket appartenant à boutique_a
        cls.ticket, _ = vente_boutique(
            cls.boutique_a,
            [(cls.produit, Decimal("10"), Decimal("500"))],
        )

    def _auth(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    # ── Test 1 ────────────────────────────────────────────────────────────────

    def test_reimpression_cree_log_en_base(self):
        """Un POST valide crée exactement un TicketReprint en base."""
        before = TicketReprint.objects.filter(ticket=self.ticket).count()
        r = self.client.post(
            URL.format(ticket_id=self.ticket.pk),
            {"motif": "Client a perdu son ticket"},
            format="json",
            **self._auth(self.user_a),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.json())
        self.assertEqual(
            TicketReprint.objects.filter(ticket=self.ticket).count(),
            before + 1,
        )

    # ── Test 2 ────────────────────────────────────────────────────────────────

    def test_reimpression_retourne_ticket_complet(self):
        """La réponse inclut le numéro du ticket et ses lignes."""
        r = self.client.post(
            URL.format(ticket_id=self.ticket.pk),
            {},
            format="json",
            **self._auth(self.user_a),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        self.assertEqual(data["id"], self.ticket.pk)
        self.assertEqual(data["numero"], self.ticket.numero)
        self.assertIn("lignes", data)

    # ── Test 3 ────────────────────────────────────────────────────────────────

    def test_montants_non_recalcules(self):
        """montant_total dans la réponse = valeur stockée en DB (pas recalculé)."""
        r = self.client.post(
            URL.format(ticket_id=self.ticket.pk),
            {},
            format="json",
            **self._auth(self.user_a),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # DRF sérialise les Decimal avec decimal_places=2 — on compare en Decimal
        self.assertEqual(
            Decimal(r.json()["montant_total"]),
            self.ticket.montant_total,
        )

    def test_reimpression_ticket_mouture_conserve_total_et_cout(self):
        """Un ticket avec mouture garde exactement les montants persistés."""
        ticket_mouture, _ = vente_boutique(
            self.boutique_a,
            [(self.produit, Decimal("5"), Decimal("500"))],
            mouture=True,
            prix_mouture_kg=Decimal("75"),
        )
        r = self.client.post(
            URL.format(ticket_id=ticket_mouture.pk),
            {},
            format="json",
            **self._auth(self.user_a),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        self.assertEqual(Decimal(data["cout_mouture"]), ticket_mouture.cout_mouture)
        self.assertEqual(Decimal(data["montant_total"]), ticket_mouture.montant_total)

    # ── Test 4 ────────────────────────────────────────────────────────────────

    def test_boutique_ne_peut_pas_reimprimer_autre_lieu(self):
        """user_b (boutique_b) ne peut pas réimprimer un ticket de boutique_a → 404."""
        r = self.client.post(
            URL.format(ticket_id=self.ticket.pk),
            {},
            format="json",
            **self._auth(self.user_b),
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
        # Aucun log ne doit avoir été créé
        self.assertFalse(
            TicketReprint.objects.filter(
                ticket=self.ticket, utilisateur=self.user_b
            ).exists()
        )

    # ── Test 5 ────────────────────────────────────────────────────────────────

    def test_ticket_inexistant_retourne_404(self):
        """Un ticket_id qui n'existe pas retourne 404."""
        r = self.client.post(
            URL.format(ticket_id=99999),
            {},
            format="json",
            **self._auth(self.user_a),
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    # ── Test 6 ────────────────────────────────────────────────────────────────

    def test_permission_refusee_sans_auth(self):
        """Sans JWT → 401 Unauthorized."""
        r = self.client.post(
            URL.format(ticket_id=self.ticket.pk),
            {},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)
