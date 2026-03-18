from __future__ import annotations

import os

# Logo stocké dans core/static/img/ (versionné) — collecté dans staticfiles/ par collectstatic
_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_LOGO = os.path.join(_CORE_DIR, "static", "img", "logo-konis.png")

KONIS_BRAND = {
    "name": os.getenv("KONIS_COMPANY_NAME", "AGRO KONIS"),
    "primary_color": os.getenv("KONIS_PRIMARY_COLOR", "#0B8F3A"),
    "primary_dark_color": os.getenv("KONIS_PRIMARY_DARK_COLOR", "#0A6B2D"),
    "text_color": os.getenv("KONIS_TEXT_COLOR", "#101828"),
    "muted_text_color": os.getenv("KONIS_MUTED_TEXT_COLOR", "#475467"),
    "border_color": os.getenv("KONIS_BORDER_COLOR", "#D0D5DD"),
    "panel_bg_color": os.getenv("KONIS_PANEL_BG_COLOR", "#F7FAF8"),
    "logo_path": os.getenv("KONIS_LOGO_PATH", _DEFAULT_LOGO if os.path.exists(_DEFAULT_LOGO) else ""),
    "legal_note": os.getenv(
        "KONIS_LEGAL_NOTE",
        "Document officiel AGRO KONIS - Conservez cette facture pour votre comptabilite.",
    ),
}

