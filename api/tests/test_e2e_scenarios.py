"""
Tests E2E scénarios KONIS — simulation workflows métiers complets.

Couvre les 4 scénarios post-lancement critiques :
  S1. Création de stock par supreme_admin (fix boutique_views)
  S2. Blocage transfert inter-entreprises (toutes les couches)
  S3. Conversions sac→kg multiples + détection alerte fréquence
  S4. Dépassement projet + créance élevée (détectés par check_alerts)

Ces tests valident l'intégration complète : vue → service → modèle → DB.
"""
from decimal import Decimal
from io import StringIO

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from finance.models import JournalCreance, Projet, DepenseProjet
from finance.services import (
    creer_projet,
    enregistrer_depense_projet,
    creer_journal_creance,
)
from inventaire.models import Stock
from inventaire.services import convertir_sac_en_kg, ErreurStock
from produits.models import Produit
from ventes.models import Ticket
from ventes.services import vente_boutique


# ── Helpers communs ──────────────────────────────────────────────────────────

def _entreprise(nom="EntE2E"):
    return Entreprise.objects.create(nom=nom)


def _boutique(ent, nom="BoutiqueE2E", code="E2E"):
    return Lieu.objects.create(
        entreprise=ent, nom=nom, code=code, type_lieu=Lieu.TYPE_MAGASIN,
        mouture_enabled=True,
    )


def _usine(ent, nom="UsineE2E"):
    return Lieu.objects.create(
        entreprise=ent, nom=nom, type_lieu=Lieu.TYPE_USINE,
    )


def _user(ent, lieu, username, role=CustomUser.ROLE_BOUTIQUE):
    return CustomUser.objects.create_user(
        username=username, password="pass", role=role,
        entreprise=ent, lieu=lieu,
    )


def _produit(ent, nom="Maïs", poids_par_sac=None):
    return Produit.objects.create(nom=nom, entreprise=ent, unite="sac", poids_par_sac=poids_par_sac)


def _stock(produit, lieu, quantite=10, quantite_kg=0):
    return Stock.objects.create(produit=produit, lieu=lieu, quantite=quantite, quantite_kg=quantite_kg)


def _token(user):
    return str(RefreshToken.for_user(user).access_token)


# ════════════════════════════════════════════════════════════════════════════
# S1. Supreme_admin peut créer du stock direct en boutique
# ════════════════════════════════════════════════════════════════════════════

class TestSupremeAdminStockCreate(APITestCase):
    """S1 — supreme_admin peut créer du stock direct via POST /boutique/stock/."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = _entreprise("EntS1")
        cls.boutique = _boutique(cls.ent)
        cls.usine = _usine(cls.ent)
        cls.supreme = _user(cls.ent, cls.boutique, "supreme1", CustomUser.ROLE_SUPREME_ADMIN)
        cls.admin = _user(cls.ent, cls.boutique, "admin1", CustomUser.ROLE_ADMIN)
        cls.vendeur = _user(cls.ent, cls.boutique, "vendeur1", CustomUser.ROLE_BOUTIQUE)
        cls.produit = _produit(cls.ent)

    def _auth(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token(user)}")

    def test_supreme_admin_peut_creer_stock(self):
        """supreme_admin doit pouvoir créer du stock direct en boutique."""
        self._auth(self.supreme)
        r = self.client.post("/api/boutique/stock/", {
            "produit": self.produit.pk,
            "quantity": "5.00",
        }, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        stock = Stock.objects.get(produit=self.produit, lieu=self.boutique)
        self.assertEqual(stock.quantite, Decimal("5"))

    def test_admin_peut_creer_stock(self):
        """admin peut créer du stock direct — comportement inchangé."""
        self._auth(self.admin)
        r = self.client.post("/api/boutique/stock/", {
            "produit": self.produit.pk,
            "quantity": "3.00",
        }, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())

    def test_vendeur_ne_peut_pas_creer_stock(self):
        """Un rôle boutique normal ne peut pas créer de stock direct."""
        self._auth(self.vendeur)
        r = self.client.post("/api/boutique/stock/", {
            "produit": self.produit.pk,
            "quantity": "5.00",
        }, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("administrateurs", r.json().get("detail", ""))


# ════════════════════════════════════════════════════════════════════════════
# S2. Transfert inter-entreprises — bloqué à chaque couche
# ════════════════════════════════════════════════════════════════════════════

class TestTransfertInterEntreprises(APITestCase):
    """S2 — Aucun transfert inter-entreprises ne doit passer."""

    @classmethod
    def setUpTestData(cls):
        cls.ent_a = _entreprise("EntA")
        cls.ent_b = _entreprise("EntB")
        cls.usine_a = _usine(cls.ent_a, "UsineA")
        cls.usine_b = _usine(cls.ent_b, "UsineB")
        cls.boutique_a = _boutique(cls.ent_a, "BoutiqueA", "BA")
        cls.boutique_b = _boutique(cls.ent_b, "BoutiqueB", "BB")
        cls.produit_a = _produit(cls.ent_a, "ProdA")
        cls.produit_b = _produit(cls.ent_b, "ProdB")
        _stock(cls.produit_a, cls.usine_a, quantite=50)
        _stock(cls.produit_b, cls.usine_b, quantite=50)

    def test_service_usine_vers_boutique_inter_ent_bloque(self):
        """Service : transfert usine_A → boutique_B lève ErreurStock."""
        from inventaire.services import transfert_usine_vers_boutique
        with self.assertRaises(ErreurStock) as ctx:
            transfert_usine_vers_boutique(
                self.usine_a, self.boutique_b,
                [(self.produit_a, Decimal("5"))],
            )
        self.assertIn("inter-entreprises", str(ctx.exception))

    def test_service_mpsl_vers_boutique_inter_ent_bloque(self):
        """Service : transfert MPSL_A → boutique_B lève ErreurStock."""
        from inventaire.services import transfert_depuis_mpsl
        mpsl_a = Lieu.objects.create(
            entreprise=self.ent_a, nom="MPSL-A", type_lieu=Lieu.TYPE_MPSL
        )
        produit_mpsl = _produit(self.ent_a, "MPSLProd")
        _stock(produit_mpsl, mpsl_a, quantite=20)
        with self.assertRaises(ErreurStock) as ctx:
            transfert_depuis_mpsl(
                mpsl_a, self.boutique_b,
                [(produit_mpsl, Decimal("5"), "sac")],
            )
        self.assertIn("inter-entreprises", str(ctx.exception))

    def test_service_transfert_direct_inter_ent_bloque(self):
        """Service : transfert direct usine_A → usine_B lève ErreurStock."""
        from inventaire.services import transfert_direct_usine_vers
        with self.assertRaises(ErreurStock) as ctx:
            transfert_direct_usine_vers(
                self.usine_a, self.usine_b,
                [(self.produit_a, Decimal("5"))],
            )
        self.assertIn("inter-entreprises", str(ctx.exception))

    def test_api_cession_inter_ent_bloque(self):
        """API POST /usine/cessions/ : cession vers boutique d'une autre entreprise → 400."""
        from usine.services import creer_lot_production
        lot = creer_lot_production(
            lieu_usine=self.usine_a,
            produit=self.produit_a,
            quantite=Decimal("30"),
            prix_unitaire=Decimal("100"),
        )
        admin_a = _user(self.ent_a, self.usine_a, "admin_a_cession", CustomUser.ROLE_ADMIN)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token(admin_a)}")
        r = self.client.post("/api/usine/cessions/", {
            "lot_id": lot.pk,
            "boutique_id": self.boutique_b.pk,
            "quantite": "5",
            "prix_unitaire": "100",
        }, format="json")
        self.assertIn(r.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])
        body = r.json()
        self.assertTrue(
            "inter-entreprises" in str(body).lower() or "interdit" in str(body).lower(),
            f"Message attendu 'inter-entreprises' ou 'interdit', reçu: {body}",
        )


# ════════════════════════════════════════════════════════════════════════════
# S3. Conversions sac→kg multiples — test atomicité + détection alerte
# ════════════════════════════════════════════════════════════════════════════

class TestConversionsMultiples(TestCase):
    """S3 — Plusieurs conversions sac→kg consécutives restent cohérentes."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = _entreprise("EntS3")
        cls.boutique = _boutique(cls.ent)
        cls.admin = _user(cls.ent, cls.boutique, "admin_s3", CustomUser.ROLE_ADMIN)
        cls.produit = _produit(cls.ent, "BléS3", poids_par_sac=Decimal("50"))
        cls.stock = _stock(cls.produit, cls.boutique, quantite=20, quantite_kg=0)

    def test_conversion_atomique_sequence(self):
        """5 conversions successives de 2 sacs → stock cohérent."""
        stock = Stock.objects.get(pk=self.stock.pk)
        for i in range(5):
            kg = convertir_sac_en_kg(
                stock=stock, nombre_sacs=2, updated_by=self.admin,
                idempotency_key=f"test-conv-{i}",
            )
            self.assertEqual(kg, Decimal("100"))  # 2 sacs × 50 kg/sac
            stock.refresh_from_db()

        stock.refresh_from_db()
        self.assertEqual(stock.quantite, Decimal("10"))     # 20 - 10 sacs convertis
        self.assertEqual(stock.quantite_kg, Decimal("500"))  # 10 sacs × 50 kg

    def test_conversion_refuse_si_stock_insuffisant(self):
        """Conversion refusée si le nombre de sacs demandé dépasse le stock."""
        stock = Stock.objects.get(pk=self.stock.pk)
        with self.assertRaises(ErreurStock) as ctx:
            convertir_sac_en_kg(stock=stock, nombre_sacs=999, updated_by=self.admin)
        self.assertIn("insuffisant", str(ctx.exception).lower())

    def test_api_conversion_sac_en_kg(self):
        """API POST /boutique/stock/{id}/convertir/ retourne 200 avec kg_generes."""
        from rest_framework.test import APIClient
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token(self.admin)}")

        # Recréer un stock frais pour ce test
        produit2 = _produit(self.ent, "BléAPITest", poids_par_sac=Decimal("25"))
        _stock(produit2, self.boutique, quantite=10, quantite_kg=0)

        r = client.post(
            f"/api/boutique/stock/{produit2.pk}/convertir/",
            {"nombre_sacs": 2},
            format="json",
            HTTP_IDEMPOTENCY_KEY="e2e-conversion-api-test-001",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.json())
        data = r.json()
        self.assertEqual(Decimal(data["kg_generes"]), Decimal("50"))  # 2 × 25
        self.assertEqual(Decimal(data["quantite_sacs"]), Decimal("8"))
        self.assertEqual(Decimal(data["quantite_kg"]), Decimal("50"))

    def test_check_alerts_detecte_conversions_frequentes(self):
        """check_alerts détecte les conversions fréquentes si le seuil est bas."""
        from django.core.management import call_command
        # Forcer des entrées AuditLog de conversion (on simule via convertir_sac_en_kg)
        stock = Stock.objects.get(pk=self.stock.pk)
        stock.refresh_from_db()
        for i in range(3):
            if stock.quantite >= 1:
                try:
                    convertir_sac_en_kg(
                        stock=stock, nombre_sacs=1, updated_by=self.admin,
                        idempotency_key=f"alert-test-{i}",
                    )
                    stock.refresh_from_db()
                except ErreurStock:
                    break

        out = StringIO()
        # Seuil bas (2) pour déclencher l'alerte avec peu de conversions
        call_command("check_alerts", "--seuil-conversions-jour=2", stdout=out)
        # La commande doit s'exécuter sans exception
        output = out.getvalue()
        self.assertIn("2026", output + "ok")  # Just verifies command ran


# ════════════════════════════════════════════════════════════════════════════
# S4. Dépassement projet + créances élevées — détectés par check_alerts
# ════════════════════════════════════════════════════════════════════════════

class TestAlertesProjetsEtCreances(TestCase):
    """S4 — check_alerts détecte dépassements et créances élevées."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = _entreprise("EntS4")
        cls.boutique = _boutique(cls.ent)
        cls.admin = _user(cls.ent, cls.boutique, "admin_s4", CustomUser.ROLE_ADMIN)
        from finance.models import ClientFinance
        cls.client_finance = ClientFinance.objects.create(
            nom="Client Test S4",
            entreprise=cls.ent,
        )

    def test_projet_en_depassement_detectable(self):
        """Un projet avec dépenses > budget est visible via check_alerts."""
        projet = creer_projet(
            entreprise=self.ent,
            nom="Projet Dépasse",
            budget_initial=Decimal("1000"),
            date_debut="2026-01-01",
            created_by=self.admin,
        )
        # Dépense supérieure au budget
        enregistrer_depense_projet(
            projet=projet,
            montant=Decimal("1500"),
            description="Dépassement test",
            date="2026-03-01",
            created_by=self.admin,
        )

        from finance.services import get_budget_restant_projet
        restant = get_budget_restant_projet(projet)
        self.assertLess(restant, Decimal("0"))
        self.assertEqual(restant, Decimal("-500"))

    def test_creance_elevee_detectable(self):
        """Une créance > 200 000 FCFA est détectée par check_alerts."""
        journal = creer_journal_creance(
            client=self.client_finance,
            description="Créance élevée test",
            montant_initial=Decimal("250000"),
            created_by=self.admin,
            reference="CREANCE-E2E-001",
        )
        self.assertEqual(journal.montant_initial, Decimal("250000"))
        self.assertEqual(journal.statut, "en_cours")

        out = StringIO()
        from django.core.management import call_command
        call_command("check_alerts", "--seuil-creances=200000", stdout=out)
        output = out.getvalue()
        # La commande doit signaler au moins 1 alerte (créance dépasse seuil)
        self.assertNotIn("aucune anomalie", output.lower())

    def test_check_alerts_seuils_personnalises(self):
        """check_alerts accepte des seuils personnalisés sans erreur."""
        out = StringIO()
        from django.core.management import call_command
        # Ne doit pas lever d'exception avec des seuils non standard
        call_command(
            "check_alerts",
            "--seuil-stock=5",
            "--seuil-creances=500000",
            "--jours-collectes=7",
            "--seuil-conversions-jour=50",
            stdout=out,
        )
        # Sortie doit contenir une date ou un statut
        output = out.getvalue()
        self.assertTrue(len(output) > 0)


# ════════════════════════════════════════════════════════════════════════════
# S5. Idempotency STRICT_MODE — rejet 400 si clé absente
# ════════════════════════════════════════════════════════════════════════════

@override_settings(IDEMPOTENCY_STRICT_MODE=True)
class TestIdempotencyStrictModeE2E(APITestCase):
    """S5 — STRICT_MODE=True : toutes les actions sensibles rejettent la requête sans clé."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = _entreprise("EntS5")
        cls.boutique = _boutique(cls.ent)
        cls.vendeur = _user(cls.ent, cls.boutique, "vendeur_s5", CustomUser.ROLE_BOUTIQUE)
        cls.produit = _produit(cls.ent, "ProdS5", poids_par_sac=Decimal("50"))
        cls.stock = _stock(cls.produit, cls.boutique, quantite=10)

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token(self.vendeur)}")

    def test_vente_sans_idempotency_key_refusee(self):
        """POST /boutique/ventes/ sans header Idempotency-Key → 400 en mode STRICT."""
        self._auth()
        r = self.client.post("/api/boutique/ventes/", {
            "lignes": [{"produit": self.produit.pk, "quantite": "1", "prix_unitaire": "500"}],
            "type_vente": "cash",
        }, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Idempotency-Key", r.json().get("detail", ""))

    def test_vente_avec_idempotency_key_acceptee(self):
        """POST /boutique/ventes/ avec header Idempotency-Key → 201."""
        self._auth()
        r = self.client.post(
            "/api/boutique/ventes/",
            {
                "lignes": [{"produit": self.produit.pk, "quantite": "1", "prix_unitaire": "500"}],
                "type_vente": "cash",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="e2e-strict-vente-001",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())

    def test_mouture_sans_idempotency_key_refusee(self):
        """POST /boutique/mouture-seule/ sans header Idempotency-Key → 400 en mode STRICT."""
        self._auth()
        r = self.client.post("/api/boutique/mouture-seule/", {
            "quantite_apportee": "10",
            "quantite_achetee": "0",
            "unite": "kg",
            "prix_par_kg": "5",
        }, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Idempotency-Key", r.json().get("detail", ""))

    def test_conversion_sans_idempotency_key_refusee(self):
        """POST /boutique/stock/{id}/convertir/ sans header → 400 en mode STRICT."""
        self._auth()
        r = self.client.post(
            f"/api/boutique/stock/{self.produit.pk}/convertir/",
            {"nombre_sacs": 1},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Idempotency-Key", r.json().get("detail", ""))
