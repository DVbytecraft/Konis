from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from core.branding import KONIS_BRAND
from ventes.models import Facture


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value))


def _fmt_amount(value: Decimal) -> str:
    return f"{value:,.2f} FCFA".replace(",", " ")


def _is_mouture_line(description: str) -> bool:
    text = (description or "").strip().lower()
    return "mouture" in text or "broyage" in text


def build_facture_pdf(facture: Facture) -> bytes:
    """
    Build official KONIS A4 invoice PDF from persisted DB data only.
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4, pageCompression=0, invariant=1)
    width, height = A4

    margin = 36  # 0.5in
    content_width = width - (margin * 2)
    y = height - margin

    primary = colors.HexColor(KONIS_BRAND["primary_color"])
    primary_dark = colors.HexColor(KONIS_BRAND["primary_dark_color"])
    text_color = colors.HexColor(KONIS_BRAND["text_color"])
    muted = colors.HexColor(KONIS_BRAND["muted_text_color"])
    border = colors.HexColor(KONIS_BRAND["border_color"])
    panel_bg = colors.HexColor(KONIS_BRAND["panel_bg_color"])

    lignes = list(facture.lignes.all())
    subtotal = sum((_to_decimal(l.total) for l in lignes), Decimal("0"))
    total_mouture = sum((_to_decimal(l.total) for l in lignes if _is_mouture_line(l.description)), Decimal("0"))
    total_produits = subtotal - total_mouture

    company_name = facture.lieu.entreprise.nom if facture.lieu and facture.lieu.entreprise else KONIS_BRAND["name"]
    logo_text = "".join([part[0] for part in company_name.split() if part][:3]).upper() or "KON"

    # Header line
    c.setStrokeColor(primary)
    c.setLineWidth(2)
    c.line(margin, y - 4, margin + content_width, y - 4)

    # Logo
    logo_x = margin
    logo_y = y - 52
    logo_w = 44
    logo_h = 44
    c.setFillColor(panel_bg)
    c.setStrokeColor(primary_dark)
    c.roundRect(logo_x, logo_y, logo_w, logo_h, 6, fill=1, stroke=1)

    logo_path = (KONIS_BRAND.get("logo_path") or "").strip()
    if logo_path:
        try:
            c.drawImage(ImageReader(logo_path), logo_x + 3, logo_y + 3, logo_w - 6, logo_h - 6, preserveAspectRatio=True, mask="auto")
        except Exception:
            c.setFillColor(primary_dark)
            c.setFont("Helvetica-Bold", 11)
            c.drawCentredString(logo_x + logo_w / 2, logo_y + 16, logo_text)
    else:
        c.setFillColor(primary_dark)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(logo_x + logo_w / 2, logo_y + 16, logo_text)

    # Company block
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(logo_x + 56, y - 18, company_name)
    c.setFont("Helvetica", 10)
    c.setFillColor(muted)
    c.drawString(logo_x + 56, y - 32, facture.lieu.nom or "-")
    c.drawString(logo_x + 56, y - 45, (facture.lieu.adresse or "-")[:72])

    # Invoice meta panel
    panel_w = 240
    panel_h = 74
    panel_x = margin + content_width - panel_w
    panel_y = y - panel_h
    c.setFillColor(panel_bg)
    c.setStrokeColor(border)
    c.roundRect(panel_x, panel_y, panel_w, panel_h, 6, fill=1, stroke=1)

    c.setFillColor(primary_dark)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(panel_x + 12, panel_y + panel_h - 18, "FACTURE OFFICIELLE")
    c.setFillColor(text_color)
    c.setFont("Helvetica", 9.5)
    c.drawString(panel_x + 12, panel_y + panel_h - 34, f"Numero : {facture.numero}")
    c.drawString(panel_x + 12, panel_y + panel_h - 47, f"Date : {facture.date.strftime('%d/%m/%Y %H:%M')}")
    c.drawString(panel_x + 12, panel_y + panel_h - 60, f"Source : {facture.get_source_role_display()}")
    c.drawRightString(panel_x + panel_w - 12, panel_y + panel_h - 60, f"Emetteur : {facture.created_by.username if facture.created_by else '-'}")

    # Client panel
    y = panel_y - 14
    client_h = 54
    c.setFillColor(colors.white)
    c.setStrokeColor(border)
    c.roundRect(margin, y - client_h, content_width, client_h, 6, fill=1, stroke=1)
    c.setFillColor(primary_dark)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 10, y - 14, "CLIENT")
    c.setFillColor(text_color)
    c.setFont("Helvetica", 9.5)
    c.drawString(margin + 80, y - 14, f"Nom: {facture.client_nom or '-'}")
    c.drawString(margin + 80, y - 28, f"Contact: {facture.client_contact or '-'}")
    c.drawString(margin + 80, y - 42, f"Notes: {(facture.notes or '-')[:82]}")

    # Table
    y = y - client_h - 14
    row_h = 18
    header_h = 20
    col_desc = margin + 8
    col_qty = margin + content_width - 210
    col_pu = margin + content_width - 135
    col_total = margin + content_width - 52

    c.setFillColor(panel_bg)
    c.setStrokeColor(border)
    c.rect(margin, y - header_h, content_width, header_h, fill=1, stroke=1)
    c.setFillColor(primary_dark)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col_desc, y - 13, "DESCRIPTION")
    c.drawRightString(col_qty, y - 13, "QTE")
    c.drawRightString(col_pu, y - 13, "PU")
    c.drawRightString(col_total, y - 13, "TOTAL")

    y = y - header_h
    c.setFont("Helvetica", 9)
    c.setFillColor(text_color)
    for ligne in lignes:
        if y - row_h < margin + 120:
            c.showPage()
            y = height - margin
        c.setStrokeColor(border)
        c.line(margin, y - row_h, margin + content_width, y - row_h)
        c.drawString(col_desc, y - 12, (ligne.description or "-")[:70])
        c.drawRightString(col_qty, y - 12, f"{_to_decimal(ligne.quantite):.2f}")
        c.drawRightString(col_pu, y - 12, f"{_to_decimal(ligne.prix_unitaire):.2f}")
        c.drawRightString(col_total, y - 12, f"{_to_decimal(ligne.total):.2f}")
        y -= row_h

    # Totals box
    totals_w = 230
    totals_h = 78
    totals_x = margin + content_width - totals_w
    totals_y = y - totals_h - 10
    c.setFillColor(colors.white)
    c.setStrokeColor(border)
    c.roundRect(totals_x, totals_y, totals_w, totals_h, 6, fill=1, stroke=1)

    c.setFillColor(text_color)
    c.setFont("Helvetica", 9.5)
    c.drawString(totals_x + 10, totals_y + totals_h - 16, "Sous-total produits")
    c.drawRightString(totals_x + totals_w - 10, totals_y + totals_h - 16, _fmt_amount(total_produits))
    c.drawString(totals_x + 10, totals_y + totals_h - 32, "Services mouture")
    c.drawRightString(totals_x + totals_w - 10, totals_y + totals_h - 32, _fmt_amount(total_mouture))
    c.setStrokeColor(border)
    c.line(totals_x + 10, totals_y + totals_h - 40, totals_x + totals_w - 10, totals_y + totals_h - 40)
    c.setFillColor(primary_dark)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(totals_x + 10, totals_y + totals_h - 56, "TOTAL GENERAL")
    c.drawRightString(totals_x + totals_w - 10, totals_y + totals_h - 56, _fmt_amount(_to_decimal(facture.total)))

    # Footer legal note
    c.setFillColor(muted)
    c.setFont("Helvetica", 8.5)
    c.drawString(margin, margin - 2, KONIS_BRAND["legal_note"])

    c.showPage()
    c.save()
    return buffer.getvalue()

