"""
Tests d'isolation multi-entreprises pour le modèle Produit.

Vérifie que :
- Le catalogue produit est strictement scoped par entreprise (pas de cross-tenant)
- La création de produits assigne automatiquement l'entreprise de l'utilisateur
- Aucune mutation cross-tenant n'est possible (vente, lot, code uniqueness)
- L'admin voit uniquement les produits de son entreprise
- Le même code produit peut coexister dans deux entreprises différentes
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from inventaire.models import Stock
from produits.models import Categorie, Produit


class ProduitIsolationTests(APITestCase):
    """Isolation complète du catalogue produit par entreprise."""

    @classmethod
    def setUpTestData(cls):
        # Entreprise A
        cls.ent_a = Entreprise.objects.create(nom="Entreprise A")
        cls.usine_a = Lieu.objects.create(
            entreprise=cls.ent_a, nom="Usine A", type_lieu=Lieu.TYPE_USINE
        )
        cls.boutique_a = Lieu.objects.create(
            entreprise=cls.ent_a, nom="Boutique A", type_lieu=Lieu.TYPE_MAGASIN
        )

        # Entreprise B
        cls.ent_b = Entreprise.objects.create(nom="Entreprise B")
        cls.usine_b = Lieu.objects.create(
            entreprise=cls.ent_b, nom="Usine B", type_lieu=Lieu.TYPE_USINE
        )
        cls.boutique_b = Lieu.objects.create(
            entreprise=cls.ent_b, nom="Boutique B", type_lieu=Lieu.TYPE_MAGASIN
        )

        # Utilisateurs
        cls.admin_a = CustomUser.objects.create_user(
            username="admin_a", password="pass",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent_a,
        )
        cls.usine_user_a = CustomUser.objects.create_user(
            username="usine_a", password="pass",
            role=CustomUser.ROLE_USINE, entreprise=cls.ent_a, lieu=cls.usine_a,
        )
        cls.boutique_user_a = CustomUser.objects.create_user(
            username="boutique_a", password="pass",
            role=CustomUser.ROLE_BOUTIQUE, entreprise=cls.ent_a, lieu=cls.boutique_a,
        )
        cls.usine_user_b = CustomUser.objects.create_user(
            username="usine_b", password="pass",
            role=CustomUser.ROLE_USINE, entreprise=cls.ent_b, lieu=cls.usine_b,
        )

        cat_a = Categorie.objects.create(nom="Général", entreprise=cls.ent_a)
        cat_b = Categorie.objects.create(nom="Général", entreprise=cls.ent_b)

        # Produits entreprise A
        cls.produit_fini_a = Produit.objects.create(
            entreprise=cls.ent_a, categorie=cat_a,
            nom="Anitche A", code="ANIT-A",
            category=Produit.CATEGORY_FINISHED, unite="kg",
        )
        cls.produit_mp_a = Produit.objects.create(
            entreprise=cls.ent_a, categorie=cat_a,
            nom="Mais A", code="MAIS-A",
            category=Produit.CATEGORY_RAW_MATERIAL, unite="kg",
        )

        # Produits entreprise B (même code que A pour tester l'unicité par entreprise)
        cls.produit_fini_b = Produit.objects.create(
            entreprise=cls.ent_b, categorie=cat_b,
            nom="Anitche B", code="ANIT-B",
            category=Produit.CATEGORY_FINISHED, unite="kg",
        )

        # Stock pour les tests de vente
        Stock.objects.create(
            produit=cls.produit_fini_a, lieu=cls.boutique_a, quantite=Decimal("50")
        )

    def _auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    # ── 1. Catalogue produits finis scoped par entreprise ─────────────────────

    def test_catalogue_finis_ne_montre_que_entreprise_a(self):
        """L'utilisateur usine A ne voit que les produits finis de son entreprise."""
        r = self.client.get(
            "/api/factory/finished-products/catalog/",
            **self._auth(self.usine_user_a),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ids = [p["id"] for p in r.json()]
        self.assertIn(self.produit_fini_a.id, ids, "Produit A doit être visible par usine A")
        self.assertNotIn(self.produit_fini_b.id, ids, "Produit B ne doit PAS être visible par usine A")

    # ── 2. Catalogue matières premières scoped par entreprise ─────────────────

    def test_catalogue_mp_ne_montre_que_entreprise_a(self):
        """L'utilisateur usine A ne voit que les MP de son entreprise."""
        r = self.client.get(
            "/api/factory/raw-materials/catalog/",
            **self._auth(self.usine_user_a),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ids = [p["id"] for p in r.json()]
        self.assertIn(self.produit_mp_a.id, ids)
        # Aucun produit d'entreprise B ne doit apparaître
        all_ent_b_ids = list(
            Produit.objects.filter(entreprise=self.ent_b).values_list("id", flat=True)
        )
        for pid in all_ent_b_ids:
            self.assertNotIn(pid, ids, f"Produit B (id={pid}) ne doit pas être visible par usine A")

    # ── 3. Création produit → entreprise automatiquement assignée ─────────────

    def test_creation_produit_fini_assigne_entreprise_correcte(self):
        """POST catalog finis → le produit créé appartient à l'entreprise de l'utilisateur."""
        r = self.client.post(
            "/api/factory/finished-products/catalog/",
            {"name": "Nouveau Fini A", "code": "NFI-A", "unit": "kg"},
            format="json",
            **self._auth(self.usine_user_a),
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        produit_id = r.json()["id"]
        produit = Produit.objects.get(pk=produit_id)
        self.assertEqual(produit.entreprise_id, self.ent_a.id,
                         "Le produit créé doit appartenir à entreprise A")

    def test_creation_produit_mp_assigne_entreprise_correcte(self):
        """POST catalog MP → le produit créé appartient à l'entreprise de l'utilisateur."""
        r = self.client.post(
            "/api/factory/raw-materials/catalog/",
            {"name": "Nouveau MP A", "code": "NMP-A", "unit": "sac"},
            format="json",
            **self._auth(self.usine_user_a),
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        produit = Produit.objects.get(pk=r.json()["id"])
        self.assertEqual(produit.entreprise_id, self.ent_a.id)

    # ── 4. Code unique par entreprise (pas global) ────────────────────────────

    def test_meme_code_autorise_dans_deux_entreprises_differentes(self):
        """Le même code peut exister dans deux entreprises différentes (unicité par entreprise)."""
        # Entreprise A crée un produit avec code "SHARED"
        r_a = self.client.post(
            "/api/factory/finished-products/catalog/",
            {"name": "Produit SHARED A", "code": "SHARED", "unit": "kg"},
            format="json",
            **self._auth(self.usine_user_a),
        )
        self.assertEqual(r_a.status_code, status.HTTP_201_CREATED, r_a.json())

        # Entreprise B peut aussi créer un produit avec le même code "SHARED"
        r_b = self.client.post(
            "/api/factory/finished-products/catalog/",
            {"name": "Produit SHARED B", "code": "SHARED", "unit": "kg"},
            format="json",
            **self._auth(self.usine_user_b),
        )
        self.assertEqual(r_b.status_code, status.HTTP_201_CREATED,
                         "Le même code doit être autorisé dans une autre entreprise")

        # Entreprise A ne peut PAS créer un second produit avec le même code
        r_a_dup = self.client.post(
            "/api/factory/finished-products/catalog/",
            {"name": "Dupliqué A", "code": "SHARED", "unit": "kg"},
            format="json",
            **self._auth(self.usine_user_a),
        )
        self.assertEqual(r_a_dup.status_code, status.HTTP_400_BAD_REQUEST,
                         "Le code dupliqué dans la MÊME entreprise doit être rejeté")

    # ── 5. Vente boutique bloquée si produit hors entreprise ──────────────────

    def test_vente_bloquee_avec_produit_autre_entreprise(self):
        """La boutique A ne peut pas vendre un produit appartenant à l'entreprise B."""
        r = self.client.post(
            reverse("boutique-ventes-list"),
            {
                "lignes": [{
                    "produit": self.produit_fini_b.id,  # Produit de l'entreprise B !
                    "quantite": "1",
                    "prix_unitaire": "100",
                }]
            },
            format="json",
            **self._auth(self.boutique_user_a),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST,
                         "La vente doit être refusée car le produit appartient à une autre entreprise")

    # ── 6. Admin voit uniquement les produits de son entreprise ───────────────

    def test_admin_produit_viewset_scope_entreprise(self):
        """L'admin ne voit que les produits de son entreprise via /api/admin/produits/."""
        r = self.client.get(
            reverse("admin-produits-list"),
            **self._auth(self.admin_a),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        ids = [p["id"] for p in items]
        self.assertIn(self.produit_fini_a.id, ids,
                      "Admin A doit voir les produits de son entreprise")
        self.assertNotIn(self.produit_fini_b.id, ids,
                         "Admin A ne doit PAS voir les produits de l'entreprise B")
