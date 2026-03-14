export interface TicketPrintLine {
  produit_nom: string;
  quantite: number;
  prix_unitaire: number;
  total?: number;
}

export interface TicketPrintData {
  numero: string;
  date: string;
  lieu_nom: string;
  lignes: TicketPrintLine[];
  montant_total: number;
  mouture?: boolean;
  cout_mouture?: number;
  prix_mouture_kg?: number | null;
  prix_mouture_tonne?: number | null;
  prix_mouture_sac?: number | null;
  produit_apporte?: string;
  copie?: boolean;
}

interface PrintOptions {
  autoPrint?: boolean;
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => {
    switch (char) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case "\"":
        return "&quot;";
      case "'":
        return "&#39;";
      default:
        return char;
    }
  });
}

function formatNumber(value: number | null | undefined): string {
  const num = typeof value === "number" ? value : Number(value ?? 0);
  if (!Number.isFinite(num)) return "0.00";
  return num.toFixed(2);
}

function buildTicketHtml(ticket: TicketPrintData): string {
  const lignesHtml = ticket.lignes.length
    ? ticket.lignes
        .map((ligne) => {
          const total = ligne.total ?? ligne.quantite * ligne.prix_unitaire;
          const libelle = `${ligne.produit_nom} x${ligne.quantite} @ ${formatNumber(
            ligne.prix_unitaire
          )}`;
          return `
            <div class="ligne">
              <span>${escapeHtml(libelle)}</span>
              <span>${formatNumber(total)}</span>
            </div>`;
        })
        .join("")
    : `
        <div class="ligne">
          <span>${escapeHtml(ticket.produit_apporte || "Mouture seule")}</span>
          <span></span>
        </div>`;

  const moutureSection = ticket.mouture
    ? `
        <div class="lignes">
          <div class="section-title">MOUTURE</div>
          <div class="ligne"><span><b>MOUTURE : OUI</b></span></div>
          ${
            ticket.prix_mouture_kg != null
              ? `<div class="ligne"><span>Mouture/kg</span><span>${formatNumber(
                  ticket.prix_mouture_kg
                )} FCFA/kg</span></div>`
              : ""
          }
          ${
            ticket.prix_mouture_tonne != null
              ? `<div class="ligne"><span>Mouture/tonne</span><span>${formatNumber(
                  ticket.prix_mouture_tonne
                )} FCFA/t</span></div>`
              : ""
          }
          ${
            ticket.prix_mouture_sac != null
              ? `<div class="ligne"><span>Mouture/sac</span><span>${formatNumber(
                  ticket.prix_mouture_sac
                )} FCFA/sac</span></div>`
              : ""
          }
          <div class="ligne"><span>Coût mouture</span><span>${formatNumber(
            ticket.cout_mouture
          )} FCFA</span></div>
        </div>`
    : `<div class="muted">MOUTURE : NON</div>`;

  return `<!DOCTYPE html>
<html lang="fr">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=80mm, initial-scale=1.0" />
    <title>Ticket ${escapeHtml(ticket.numero)}</title>
    <style>
      @page { size: 80mm auto; margin: 2mm 4mm; }
      * { margin: 0; padding: 0; box-sizing: border-box; }
      body {
        width: 72mm;
        max-width: 72mm;
        font-family: "Courier New", Courier, monospace;
        font-size: 11px;
        line-height: 1.3;
        padding: 1mm 0;
      }
      .header { text-align: center; border-bottom: 1px dashed #000; padding-bottom: 4px; margin-bottom: 4px; }
      .ticket-num { font-weight: bold; font-size: 12px; }
      .copie { font-size: 10px; font-weight: bold; color: #b91c1c; margin-top: 2px; }
      .lieu { font-size: 10px; }
      .date { font-size: 9px; }
      .ligne { display: flex; justify-content: space-between; margin: 2px 0; gap: 8px; }
      .lignes { border-bottom: 1px dashed #000; padding-bottom: 4px; margin-bottom: 4px; }
      .section-title { text-align: center; font-weight: bold; margin: 2px 0; }
      .total { font-weight: bold; text-align: right; font-size: 12px; }
      .footer { text-align: center; font-size: 9px; margin-top: 8px; }
      .muted { font-size: 9px; margin: 2px 0; }
      @media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
    </style>
  </head>
  <body>
    <div class="header">
      <div class="ticket-num">${escapeHtml(ticket.numero)}</div>
      ${ticket.copie ? `<div class="copie">COPIE</div>` : ""}
      <div class="lieu">${escapeHtml(ticket.lieu_nom)}</div>
      <div class="date">${escapeHtml(ticket.date)}</div>
    </div>
    <div class="lignes">${lignesHtml}</div>
    ${moutureSection}
    <div class="total">TOTAL: ${formatNumber(ticket.montant_total)} FCFA</div>
    <div class="footer">Merci de votre visite</div>
  </body>
</html>`;
}

export function openTicketPrintWindow(ticket: TicketPrintData, options: PrintOptions = {}) {
  const { autoPrint = true } = options;
  const html = buildTicketHtml(ticket);
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const popup = window.open(url, "_blank", "noopener,noreferrer");

  if (!popup) {
    try {
      window.open(url, "_blank");
    } catch {
      // Ignore popup errors.
    }
    try {
      window.print();
    } catch {
      // Ignore print errors.
    }
    return;
  }

  const triggerPrint = () => {
    if (!autoPrint) return;
    try {
      popup.focus();
      popup.print();
    } catch {
      // Ignore print errors (popup still opened).
    }
  };

  popup.addEventListener?.("load", triggerPrint);
  // Fallback in case load event doesn't fire.
  setTimeout(triggerPrint, 600);

  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
