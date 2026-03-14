"""
Merge all enterprises into a single primary enterprise.

Usage:
  python manage.py merge_single_entreprise --confirm
  python manage.py merge_single_entreprise --primary-id 3 --confirm
  python manage.py merge_single_entreprise --primary-name "KONIS" --confirm
  python manage.py merge_single_entreprise --confirm --rename-product-codes
"""
from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Entreprise, Lieu, CustomUser
from produits.models import Produit


class Command(BaseCommand):
    help = "Merge all enterprises into a single primary enterprise."

    def add_arguments(self, parser):
        parser.add_argument(
            "--primary-id",
            type=int,
            default=None,
            help="ID of the enterprise to keep.",
        )
        parser.add_argument(
            "--primary-name",
            type=str,
            default=None,
            help="Case-insensitive name of the enterprise to keep.",
        )
        parser.add_argument(
            "--rename-product-codes",
            action="store_true",
            help="Auto-rename conflicting product codes during merge.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm execution without interactive prompt.",
        )

    def _resolve_primary(self, primary_id: int | None, primary_name: str | None) -> Entreprise:
        if primary_id is not None:
            ent = Entreprise.objects.filter(pk=primary_id).first()
            if not ent:
                raise CommandError(f"No enterprise with id={primary_id}.")
            return ent
        if primary_name:
            ent = Entreprise.objects.filter(nom__iexact=primary_name.strip()).first()
            if not ent:
                raise CommandError(f"No enterprise with name='{primary_name}'.")
            return ent
        ent = Entreprise.objects.order_by("id").first()
        if not ent:
            ent = Entreprise.objects.create(nom="Entreprise principale")
        return ent

    def _build_product_conflicts(self):
        by_code: dict[str, list[Produit]] = defaultdict(list)
        for p in Produit.objects.exclude(code__isnull=True):
            by_code[p.code].append(p)
        conflicts = {code: items for code, items in by_code.items() if len(items) > 1}
        return conflicts

    def _rename_conflicts(self, primary: Entreprise, conflicts: dict[str, list[Produit]]):
        if not conflicts:
            return 0
        existing_codes = set(Produit.objects.exclude(code__isnull=True).values_list("code", flat=True))
        renamed = 0
        for code, items in conflicts.items():
            # Prefer to keep the code on a product already in the primary enterprise.
            items_sorted = sorted(items, key=lambda p: (p.entreprise_id != primary.id, p.id))
            for p in items_sorted[1:]:
                base = (code or "PROD").strip() or "PROD"
                suffix = f"-E{p.entreprise_id}-P{p.id}"
                max_len = 50
                if len(base) + len(suffix) > max_len:
                    base = base[: max_len - len(suffix)]
                new_code = f"{base}{suffix}"
                while new_code in existing_codes:
                    base = base[: max_len - len(suffix) - 2]
                    new_code = f"{base}{suffix}"
                p.code = new_code
                p.save(update_fields=["code"])
                existing_codes.add(new_code)
                renamed += 1
        return renamed

    def handle(self, *args, **options):
        primary = self._resolve_primary(options["primary_id"], options["primary_name"])
        others = Entreprise.objects.exclude(pk=primary.pk)

        if not others.exists():
            with transaction.atomic():
                users_updated = CustomUser.objects.filter(entreprise__isnull=True).update(entreprise=primary)
            if users_updated:
                self.stdout.write(self.style.SUCCESS("Single enterprise found; assigned users with no enterprise."))
                self.stdout.write(f"Users reassigned: {users_updated}")
            else:
                self.stdout.write(self.style.SUCCESS("Only one enterprise found. No merge needed."))
            return

        if not options["confirm"]:
            self.stdout.write(self.style.WARNING(
                "\nWARNING: This command merges all enterprises into one.\n"
                "It reassigns Places, Users, and Products, then deletes other enterprises.\n"
                "This is irreversible. Please backup before continuing.\n"
            ))
            confirm = input("Type 'CONFIRM' to continue: ")
            if confirm.strip() != "CONFIRM":
                raise CommandError("Operation cancelled.")

        with transaction.atomic():
            conflicts = self._build_product_conflicts()
            if conflicts and not options["rename_product_codes"]:
                sample = ", ".join(list(conflicts.keys())[:10])
                raise CommandError(
                    "Product code conflicts detected. "
                    "Rerun with --rename-product-codes to auto-rename. "
                    f"Examples: {sample}"
                )
            renamed = self._rename_conflicts(primary, conflicts) if options["rename_product_codes"] else 0

            lieux_updated = Lieu.objects.exclude(entreprise=primary).update(entreprise=primary)
            users_updated = CustomUser.objects.filter(entreprise__isnull=True).update(entreprise=primary)
            users_updated += CustomUser.objects.exclude(entreprise=primary).update(entreprise=primary)
            produits_updated = Produit.objects.exclude(entreprise=primary).update(entreprise=primary)

            deleted_count, _ = others.delete()

        self.stdout.write(self.style.SUCCESS("Merge complete."))
        self.stdout.write(f"Primary enterprise: {primary.id} - {primary.nom}")
        self.stdout.write(f"Places reassigned: {lieux_updated}")
        self.stdout.write(f"Users reassigned: {users_updated}")
        self.stdout.write(f"Products reassigned: {produits_updated}")
        if renamed:
            self.stdout.write(f"Product codes renamed: {renamed}")
        self.stdout.write(f"Enterprises deleted: {deleted_count}")
