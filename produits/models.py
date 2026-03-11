from django.db import models


def _default_entreprise_id():
    from core.models import Entreprise

    ent = Entreprise.objects.order_by("id").first()
    if ent:
        return ent.id
    # Ne pas créer silencieusement : un produit sans entreprise est une erreur.
    raise ValueError(
        "Aucune entreprise trouvée. Créez une entreprise avant de créer des produits."
    )


class Categorie(models.Model):
    """Catégorie de produit."""
    nom = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"


class Produit(models.Model):
    """Produit vendu (provenderie)."""
    CATEGORY_RAW_MATERIAL = "raw_material"
    CATEGORY_FINISHED = "finished"
    CATEGORY_CHOICES = [
        (CATEGORY_RAW_MATERIAL, "Matière première"),
        (CATEGORY_FINISHED, "Produit fini"),
    ]

    entreprise = models.ForeignKey(
        "core.Entreprise",
        on_delete=models.PROTECT,
        related_name="produits",
        default=_default_entreprise_id,
        db_index=True,
    )
    categorie = models.ForeignKey(
        Categorie, on_delete=models.PROTECT, related_name="produits",
        null=True, blank=True,
    )
    nom = models.CharField(max_length=255)
    code = models.CharField(max_length=50, null=True, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_FINISHED)
    unite = models.CharField(max_length=20, default="kg", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nom or self.code or str(self.pk)

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ["-id"]  # Évite UnorderedObjectListWarning lors de la pagination
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise", "code"],
                name="unique_produit_code_par_entreprise",
            )
        ]
        indexes = [
            models.Index(fields=["nom"]),
            models.Index(fields=["entreprise", "nom"]),
        ]
