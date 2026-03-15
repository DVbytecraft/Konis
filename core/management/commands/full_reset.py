"""
Commande de réinitialisation TOTALE avant déploiement en production.

Usage :
    python manage.py full_reset [--superuser=USERNAME] [--confirm] [--dry-run]

Différence avec reset_for_production :
    reset_for_production → conserve lieux, produits, utilisateurs (reset partiel)
    full_reset           → supprime TOUT sauf un seul superadministrateur (reset total)

Ce que cette commande supprime :
    - Tous les tokens JWT (invalide toutes les sessions immédiatement)
    - Toutes les ventes, tickets, factures et lignes
    - Tous les stocks et mouvements de stock
    - Tous les achats usine et transferts
    - Tous les lots de production
    - Toutes les dépenses et catégories de dépenses
    - Tous les produits et catégories de produits
    - Tous les logs d'audit
    - Tous les utilisateurs SAUF le superadministrateur désigné
    - Tous les lieux (usines et boutiques)
    - Toutes les entreprises

    Puis réinitialise toutes les séquences PostgreSQL à 1.

Ce que cette commande conserve :
    - Le seul compte superadministrateur (is_superuser=True) que vous désignez

Invalidation JWT immédiate (TokenRevocationEpoch) :
    Après le reset, un enregistrement TokenRevocationEpoch est créé avec
    revoked_before = maintenant(). JWTCookieAuthentication rejette immédiatement
    tout token émis avant cet instant, sans attendre son expiration naturelle.
    Cela couvre aussi les access tokens stateless qui ne sont pas trackés en DB.

ATTENTION : Cette opération est irréversible. Effectuez un backup complet avant.
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone


# ──────────────────────────────────────────────────────────────────────────────
# Ordre de suppression strict — respecte les contraintes FK PostgreSQL
# Toujours supprimer les enfants avant les parents (PROTECT bloque sinon)
# ──────────────────────────────────────────────────────────────────────────────
DELETION_ORDER = [
    # 0. Anciennes époques de révocation JWT (nettoyage des resets précédents)
    #    La nouvelle époque est créée APRÈS la transaction (voir handle())
    ("core", "TokenRevocationEpoch"),

    # 1. Logs d'audit (FK user SET_NULL : pas bloquant mais propre de vider d'abord)
    ("audit", "AuditLog"),

    # 2. Tokens JWT — invalide TOUTES les sessions actives en premier
    #    BlacklistedToken a une FK CASCADE vers OutstandingToken → supprimer avant
    ("token_blacklist", "BlacklistedToken"),
    ("token_blacklist", "OutstandingToken"),   # FK CASCADE vers User

    # 3. Ventes (lignes avant entêtes, entêtes avant tickets)
    ("ventes", "LigneFacture"),               # FK → Facture (CASCADE)
    ("ventes", "LigneVente"),                 # FK → Ticket (CASCADE), Produit (PROTECT)
    ("ventes", "Facture"),                    # FK → Ticket (CASCADE)
    ("ventes", "TicketReprint"),              # FK → Ticket (PROTECT) — doit précéder Ticket
    ("ventes", "Ticket"),                     # FK → Lieu (PROTECT)

    # 4. Mouvements de stock (FK → Transfert : supprimer avant Transfert)
    ("inventaire", "MouvementStock"),         # FK → Produit (PROTECT), Transfert

    # 5. Transferts usine (TransfertCession référence LotProduction ET inventaire.Transfert)
    ("usine", "TransfertInterUsine"),         # FK → LotProduction (PROTECT), Lieu (PROTECT)
    ("usine", "TransfertCession"),            # FK → LotProduction (PROTECT), Lieu (PROTECT)
    ("usine", "LotProduction"),               # FK → Lieu (PROTECT), Produit (PROTECT)

    # 6. Transferts inventaire (après MouvementStock et TransfertCession)
    ("inventaire", "Transfert"),              # FK → Lieu from/to (PROTECT)

    # 7. Achats et stocks
    ("inventaire", "AchatUsine"),             # FK → Lieu (PROTECT)
    ("inventaire", "Stock"),                  # FK → Lieu (CASCADE), Produit (CASCADE)

    # 8. Dépenses
    ("depenses", "Depense"),                  # FK → Lieu (PROTECT), CategorieDepense (PROTECT)
    ("depenses", "CategorieDepense"),         # pas de FK sortante

    # 9. Produits (après Stock, LotProduction, LigneVente, AchatUsine)
    ("produits", "Produit"),                  # FK → Categorie (PROTECT)
    ("produits", "Categorie"),                # pas de FK sortante

    # 10. Core : utilisateurs (sauf superadmin), lieux, entreprises
    #     → traités séparément dans handle() pour la logique superadmin
]


class Command(BaseCommand):
    help = "Reset TOTAL avant production : supprime tout sauf le superadministrateur désigné."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirme l'exécution sans prompt interactif (pour scripts CI/CD).",
        )
        parser.add_argument(
            "--superuser",
            type=str,
            default=None,
            metavar="USERNAME",
            help=(
                "Username du superadministrateur à conserver. "
                "Si omis, le premier compte is_superuser=True (par date de création) est utilisé."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simule le reset sans modifier la base (affiche ce qui serait supprimé).",
        )

    def handle(self, *args, **options):
        CustomUser = apps.get_model("core", "CustomUser")
        dry_run = options["dry_run"]

        # ── Identifier le superadmin à conserver ─────────────────────────────
        username_arg = options.get("superuser")
        if username_arg:
            try:
                superadmin = CustomUser.objects.get(
                    username=username_arg, is_superuser=True
                )
            except CustomUser.DoesNotExist:
                raise CommandError(
                    f"Aucun superuser avec username='{username_arg}' trouvé.\n"
                    "Vérifiez avec : python manage.py shell -c "
                    "\"from core.models import CustomUser; "
                    "print(list(CustomUser.objects.filter(is_superuser=True).values('username')))\""
                )
        else:
            superadmin = (
                CustomUser.objects.filter(is_superuser=True)
                .order_by("date_joined")
                .first()
            )
            if not superadmin:
                raise CommandError(
                    "Aucun superadministrateur (is_superuser=True) trouvé dans la base.\n"
                    "Créez-en un d'abord avec : python manage.py createsuperuser\n"
                    "Puis relancez cette commande."
                )

        # ── Compter ce qui va être supprimé ──────────────────────────────────
        counts = self._count_all(superadmin)
        total = sum(counts.values())

        # ── Afficher le récapitulatif ─────────────────────────────────────────
        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING("══ MODE DRY-RUN (aucune donnée supprimée) ══"))
        else:
            self.stdout.write(self.style.ERROR("══ RESET TOTAL — OPÉRATION IRRÉVERSIBLE ══"))
        self.stdout.write("")
        self.stdout.write(f"  Superadmin conservé    : {superadmin.username} (id={superadmin.pk})")
        self.stdout.write(f"  Autres utilisateurs    : {counts['users_autres']} à supprimer")
        self.stdout.write(f"  Lieux (boutiques/usines): {counts['lieux']} à supprimer")
        self.stdout.write(f"  Entreprises            : {counts['entreprises']} à supprimer")
        self.stdout.write(f"  Produits               : {counts['produits']} à supprimer")
        self.stdout.write(f"  Données opérationnelles: {counts['operationnel']} entrées à supprimer")
        self.stdout.write(f"  Tokens JWT             : {counts['tokens']} à invalider")
        self.stdout.write(f"  TOTAL                  : {total} entrées concernées")
        self.stdout.write("")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry-run terminé. Aucune modification effectuée."))
            self.stdout.write("Relancez sans --dry-run (avec --confirm) pour exécuter le reset.")
            return

        # ── Confirmation ─────────────────────────────────────────────────────
        if not options["confirm"]:
            self.stdout.write(self.style.WARNING(
                "⚠️  Effectuez un backup complet AVANT de continuer :\n"
                "  docker exec konis_db pg_dump -U konis_user -d konis_db "
                "-F c -f /tmp/backup.dump\n"
                "  docker cp konis_db:/tmp/backup.dump ./backup_$(date +%Y%m%d_%H%M%S).dump\n"
            ))
            confirm = input("Tapez 'RESET-TOTAL' pour confirmer : ")
            if confirm.strip() != "RESET-TOTAL":
                raise CommandError("Opération annulée.")

        self.stdout.write("\nDébut du reset total...")

        # ── Horodatage de révocation — capturé AVANT la transaction ──────────
        # On capture now() ici pour que les tokens émis pendant la transaction
        # (edge case improbable) soient aussi couverts par la révocation.
        revocation_ts = timezone.now()

        # ── Exécution dans une transaction atomique ───────────────────────────
        with transaction.atomic():
            # Étape 1 : données opérationnelles + tokens + anciennes époques
            for app_label, model_name in DELETION_ORDER:
                self._delete_model(app_label, model_name)

            # Étape 2 : supprimer tous les utilisateurs sauf le superadmin
            Lieu = apps.get_model("core", "Lieu")
            Entreprise = apps.get_model("core", "Entreprise")

            # Détacher le superadmin de son lieu et entreprise AVANT de les supprimer.
            # On utilise QuerySet.update() et non instance.save() pour contourner le
            # override CustomUser.save() qui, en mode SINGLE_ENTREPRISE, réassignerait
            # immédiatement l'entreprise primaire (→ ProtectedError à l'étape 4).
            CustomUser.objects.filter(pk=superadmin.pk).update(lieu=None, entreprise=None)

            # Supprimer tous les autres utilisateurs
            deleted_users, _ = CustomUser.objects.exclude(pk=superadmin.pk).delete()
            if deleted_users:
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ core.CustomUser : {deleted_users} supprimé(s)")
                )
            else:
                self.stdout.write("  — core.CustomUser : aucun autre utilisateur")

            # Étape 3 : supprimer tous les lieux
            count, _ = Lieu.objects.all().delete()
            if count:
                self.stdout.write(self.style.SUCCESS(f"  ✓ core.Lieu : {count} supprimé(s)"))
            else:
                self.stdout.write("  — core.Lieu : vide")

            # Étape 4 : supprimer toutes les entreprises
            count, _ = Entreprise.objects.all().delete()
            if count:
                self.stdout.write(self.style.SUCCESS(f"  ✓ core.Entreprise : {count} supprimée(s)"))
            else:
                self.stdout.write("  — core.Entreprise : vide")

            # Étape 5 : réinitialiser les séquences PostgreSQL
            self._reset_sequences()

            # Étape 6 : repositionner la séquence des utilisateurs au-delà du superadmin.
            # _reset_sequences() remet tout à 1, mais le superadmin conserve son id
            # (ex : id=3). Sans cette correction, le 3ème nouvel utilisateur créé
            # obtiendrait id=3 → conflit de clé unique → IntegrityError.
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT setval(
                            pg_get_serial_sequence('core_customuser', 'id'),
                            (SELECT MAX(id) FROM core_customuser),
                            true
                        )
                    """)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Séquence utilisateurs repositionnée après superadmin (id={superadmin.pk})"
                    )
                )

        # ── Révocation JWT immédiate — HORS transaction ───────────────────────
        # Créé APRÈS le commit de la transaction principale pour être visible
        # immédiatement de toutes les connexions PostgreSQL.
        # JWTCookieAuthentication rejette maintenant tout token avec iat <= revocation_ts.
        TokenRevocationEpoch = apps.get_model("core", "TokenRevocationEpoch")
        TokenRevocationEpoch.objects.create(revoked_before=revocation_ts)
        self.stdout.write(
            self.style.SUCCESS(
                f"  ✓ TokenRevocationEpoch créé : révocation de tous les tokens "
                f"émis avant {revocation_ts.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
        )

        # ── Résumé final ──────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("═" * 55))
        self.stdout.write(self.style.SUCCESS("  ✅ Reset total terminé avec succès"))
        self.stdout.write(self.style.SUCCESS("═" * 55))
        self.stdout.write(f"  Superadmin conservé : {superadmin.username}")
        self.stdout.write("")
        self.stdout.write("  Invalidation JWT :")
        self.stdout.write("    ✓ OutstandingToken/BlacklistedToken supprimés (refresh invalides)")
        self.stdout.write(f"    ✓ TokenRevocationEpoch créé (access tokens révoqués immédiatement)")
        self.stdout.write("")
        self.stdout.write("  Prochaines étapes :")
        self.stdout.write("  1. Connectez-vous avec le superadmin")
        self.stdout.write("  2. Créez l'entreprise via Admin Django ou l'API")
        self.stdout.write("  3. Créez les usines et boutiques")
        self.stdout.write("  4. Créez les comptes utilisateurs opérationnels")
        self.stdout.write("  5. Saisissez les catégories et produits")
        self.stdout.write("")
        self.stdout.write(
            "  Vérification base : python manage.py check_db --after-reset --sequences"
        )
        self.stdout.write("")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _delete_model(self, app_label, model_name):
        """Supprime toutes les entrées d'un modèle. Ignore si introuvable."""
        try:
            model = apps.get_model(app_label, model_name)
            count, _ = model.objects.all().delete()
            if count:
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ {app_label}.{model_name} : {count} supprimé(s)")
                )
            else:
                self.stdout.write(f"  — {app_label}.{model_name} : vide")
        except LookupError:
            self.stdout.write(
                self.style.WARNING(f"  ⚠ {app_label}.{model_name} : modèle introuvable (ignoré)")
            )

    def _count_all(self, superadmin):
        """Compte ce qui sera supprimé (pour le récapitulatif dry-run / confirmation)."""
        CustomUser = apps.get_model("core", "CustomUser")
        Lieu = apps.get_model("core", "Lieu")
        Entreprise = apps.get_model("core", "Entreprise")

        operationnel = 0
        for app_label, model_name in DELETION_ORDER:
            try:
                model = apps.get_model(app_label, model_name)
                operationnel += model.objects.count()
            except LookupError:
                pass

        # Séparer tokens du reste pour affichage
        tokens = 0
        for app_label, model_name in [
            ("token_blacklist", "BlacklistedToken"),
            ("token_blacklist", "OutstandingToken"),
        ]:
            try:
                model = apps.get_model(app_label, model_name)
                tokens += model.objects.count()
            except LookupError:
                pass
        operationnel -= tokens  # éviter le double comptage

        return {
            "users_autres": CustomUser.objects.exclude(pk=superadmin.pk).count(),
            "lieux": Lieu.objects.count(),
            "entreprises": Entreprise.objects.count(),
            "produits": sum(
                apps.get_model(a, m).objects.count()
                for a, m in [("produits", "Produit"), ("produits", "Categorie")]
                if self._model_exists(a, m)
            ),
            "tokens": tokens,
            "operationnel": operationnel,
        }

    def _model_exists(self, app_label, model_name):
        try:
            apps.get_model(app_label, model_name)
            return True
        except LookupError:
            return False

    def _reset_sequences(self):
        """
        Réinitialise toutes les séquences PostgreSQL du schéma public à 1.
        N'a d'effet que sur PostgreSQL (ignoré silencieusement pour SQLite).
        """
        vendor = connection.vendor
        if vendor != "postgresql":
            self.stdout.write(
                self.style.WARNING(
                    f"  ⚠ Réinitialisation des séquences ignorée (moteur : {vendor}, PostgreSQL requis)"
                )
            )
            return

        self.stdout.write("  Réinitialisation des séquences PostgreSQL...")
        with connection.cursor() as cursor:
            cursor.execute("""
                DO $$
                DECLARE
                    seq_rec RECORD;
                    seq_count INTEGER := 0;
                BEGIN
                    FOR seq_rec IN
                        SELECT sequence_name
                        FROM information_schema.sequences
                        WHERE sequence_schema = 'public'
                        ORDER BY sequence_name
                    LOOP
                        EXECUTE format('ALTER SEQUENCE %I RESTART WITH 1', seq_rec.sequence_name);
                        seq_count := seq_count + 1;
                    END LOOP;
                    RAISE NOTICE 'Séquences réinitialisées : %', seq_count;
                END $$;
            """)
        self.stdout.write(self.style.SUCCESS("  ✓ Toutes les séquences réinitialisées à 1"))
