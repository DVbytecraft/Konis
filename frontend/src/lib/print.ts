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
  // Unified formula fields (new tickets)
  prix_par_kg?: number | null;
  quantite_apportee_kg?: number;
  quantite_achetee_kg?: number;
  total_mouture_kg?: number;
  // Legacy display fields (old tickets — not used in calculation)
  prix_mouture_kg?: number | null;
  prix_mouture_tonne?: number | null;
  prix_mouture_sac?: number | null;
  produit_apporte?: string;
  copie?: boolean;
}

export interface FacturePrintLine {
  description: string;
  quantite: number | string;
  prix_unitaire: number | string;
  total: number | string;
}

export interface FacturePrintData {
  numero: string;
  date: string;
  lieu_nom: string;
  client_nom?: string;
  client_contact?: string;
  notes?: string;
  lignes: FacturePrintLine[];
  total: number | string;
}

// ── Utilitaires ────────────────────────────────────────────────────────────

function escapeHtml(value: string): string {
  return String(value ?? "").replace(/[&<>"']/g, (char) => {
    switch (char) {
      case "&": return "&amp;";
      case "<": return "&lt;";
      case ">": return "&gt;";
      case "\"": return "&quot;";
      case "'": return "&#39;";
      default: return char;
    }
  });
}

function formatNumber(value: number | string | null | undefined): string {
  const num = typeof value === "number" ? value : Number(value ?? 0);
  if (!Number.isFinite(num)) return "0.00";
  return num.toFixed(2);
}

/**
 * Imprime un HTML dans un iframe caché injecté dans le document courant.
 * Fiable : pas de popup blocker, fonctionne dans tous les navigateurs modernes.
 */
function printViaIframe(html: string): void {
  const iframe = document.createElement("iframe");
  iframe.setAttribute("aria-hidden", "true");
  iframe.style.cssText =
    "position:absolute;width:0;height:0;border:0;left:-9999px;top:-9999px;visibility:hidden;";
  document.body.appendChild(iframe);

  const doc = iframe.contentDocument ?? iframe.contentWindow?.document;
  if (!doc) {
    document.body.removeChild(iframe);
    return;
  }

  doc.open();
  doc.write(html);
  doc.close();

  const doprint = () => {
    try {
      iframe.contentWindow?.focus();
      iframe.contentWindow?.print();
    } catch {
      // Silencieux — l'impression peut échouer si la fenêtre est fermée.
    }
    setTimeout(() => {
      try { document.body.removeChild(iframe); } catch { /* déjà retiré */ }
    }, 2000);
  };

  // On attend le load de l'iframe avant d'imprimer
  iframe.onload = doprint;
  // Fallback si l'événement load ne se déclenche pas (iframe déjà chargé)
  setTimeout(doprint, 800);
}

// ── HTML tickets 58mm ──────────────────────────────────────────────────────

function buildTicketHtml(ticket: TicketPrintData): string {
  const lignes = ticket.lignes ?? [];
  const lignesHtml = lignes.length
    ? lignes
        .map((ligne) => {
          const total = ligne.total ?? ligne.quantite * ligne.prix_unitaire;
          const libelle = `${ligne.produit_nom} x${ligne.quantite} @ ${formatNumber(ligne.prix_unitaire)}`;
          return `<div class="ligne"><span>${escapeHtml(libelle)}</span><span>${formatNumber(total)}</span></div>`;
        })
        .join("")
    : `<div class="ligne"><span>${escapeHtml(ticket.produit_apporte || "Mouture seule")}</span><span></span></div>`;

  const prixKg = ticket.prix_par_kg ?? ticket.prix_mouture_kg ?? null;
  const apporteeKg = ticket.quantite_apportee_kg ?? 0;
  const acheteeKg = ticket.quantite_achetee_kg ?? 0;
  const totalKg = (ticket.total_mouture_kg ?? (apporteeKg + acheteeKg)) || null;
  const hasBreakdown = (apporteeKg + acheteeKg) > 0;

  const moutureSection = ticket.mouture
    ? `<div class="lignes">
        <div class="section-title">MOUTURE</div>
        ${ticket.produit_apporte ? `<div class="ligne"><span>${escapeHtml(ticket.produit_apporte)}</span></div>` : ""}
        ${hasBreakdown ? `
          <div class="ligne"><span>Apporté</span><span>${formatNumber(apporteeKg)} kg</span></div>
          <div class="ligne"><span>Acheté</span><span>${formatNumber(acheteeKg)} kg</span></div>
          <div class="ligne ligne-sep"><span><b>Total moudre</b></span><span><b>${formatNumber(totalKg ?? 0)} kg</b></span></div>
        ` : ""}
        ${prixKg != null ? `<div class="ligne"><span>Prix/kg</span><span>${formatNumber(prixKg)} FCFA</span></div>` : ""}
        <div class="ligne"><span><b>Coût mouture</b></span><span><b>${formatNumber(ticket.cout_mouture)} FCFA</b></span></div>
      </div>`
    : `<div class="muted">MOUTURE : NON</div>`;

  return `<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <title>Ticket ${escapeHtml(ticket.numero)}</title>
  <style>
    @page { size: 80mm auto; margin: 2mm 4mm; }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { width: 72mm; max-width: 72mm; font-family: "Courier New", Courier, monospace; font-size: 11px; line-height: 1.3; padding: 1mm 0; }
    .header { text-align: center; border-bottom: 1px dashed #000; padding-bottom: 4px; margin-bottom: 4px; }
    .ticket-num { font-weight: bold; font-size: 12px; }
    .copie { font-size: 10px; font-weight: bold; color: #b91c1c; margin-top: 2px; }
    .lieu { font-size: 10px; }
    .date { font-size: 9px; }
    .ligne { display: flex; justify-content: space-between; margin: 2px 0; gap: 8px; }
    .lignes { border-bottom: 1px dashed #000; padding-bottom: 4px; margin-bottom: 4px; }
    .section-title { text-align: center; font-weight: bold; margin: 2px 0; }
    .ligne-sep { border-top: 1px dashed #000; margin-top: 2px; padding-top: 2px; }
    .total { font-weight: bold; text-align: right; font-size: 12px; }
    .footer { text-align: center; font-size: 9px; margin-top: 8px; }
    .muted { font-size: 9px; margin: 2px 0; }
    @media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
  </style>
</head>
<body>
  <div class="header">
    <div class="ticket-num">${escapeHtml(ticket.numero)}</div>
    ${ticket.copie ? `<div class="copie">★ COPIE ★</div>` : ""}
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

// ── HTML facture A4 ────────────────────────────────────────────────────────

function buildFactureHtml(facture: FacturePrintData): string {
  const lignesHtml = facture.lignes
    .map(
      (l) => `
      <tr>
        <td class="p-left">${escapeHtml(String(l.description))}</td>
        <td class="p-right">${formatNumber(l.quantite)}</td>
        <td class="p-right">${formatNumber(l.prix_unitaire)}</td>
        <td class="p-right">${formatNumber(l.total)}</td>
      </tr>`
    )
    .join("");

  return `<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <title>Facture ${escapeHtml(facture.numero)}</title>
  <style>
    @page { size: A4; margin: 15mm 20mm; }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: Arial, sans-serif; font-size: 12px; color: #111; background: #fff; }
    .header { display: flex; justify-content: space-between; border-bottom: 2px solid #16a34a; padding-bottom: 12px; margin-bottom: 16px; }
    .header-left h1 { font-size: 24px; font-weight: 700; color: #16a34a; margin-bottom: 4px; }
    .header-left p { font-size: 11px; color: #555; }
    .header-right { text-align: right; font-size: 11px; }
    .header-right .numero { font-family: monospace; font-size: 14px; font-weight: 700; }
    .meta { display: flex; gap: 32px; margin-bottom: 20px; }
    .meta-block { flex: 1; }
    .meta-block .label { font-size: 10px; text-transform: uppercase; color: #888; margin-bottom: 3px; letter-spacing: 0.5px; }
    .meta-block .value { font-size: 12px; font-weight: 600; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
    thead tr { background: #16a34a; color: #fff; }
    thead th { padding: 7px 8px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
    tbody tr:nth-child(even) { background: #f0fdf4; }
    tbody td { padding: 6px 8px; border-bottom: 1px solid #e5e7eb; font-size: 11px; }
    .p-left { text-align: left; }
    .p-right { text-align: right; }
    .total-row { margin-top: 8px; text-align: right; }
    .total-row .total-label { font-size: 13px; font-weight: 700; margin-right: 16px; }
    .total-row .total-value { font-size: 16px; font-weight: 700; color: #16a34a; }
    .notes { margin-top: 20px; font-size: 11px; color: #555; border-top: 1px solid #e5e7eb; padding-top: 8px; }
    .footer { margin-top: 32px; text-align: center; font-size: 10px; color: #aaa; border-top: 1px dashed #e5e7eb; padding-top: 8px; }
    @media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
  </style>
</head>
<body>
  <div class="header">
    <div class="header-left">
      <h1>FACTURE</h1>
      <p>${escapeHtml(facture.lieu_nom)}</p>
    </div>
    <div class="header-right">
      <div class="numero">${escapeHtml(facture.numero)}</div>
      <div style="margin-top:4px">${escapeHtml(facture.date)}</div>
    </div>
  </div>
  <div class="meta">
    <div class="meta-block">
      <div class="label">Client</div>
      <div class="value">${escapeHtml(facture.client_nom || "—")}</div>
    </div>
    ${facture.client_contact ? `
    <div class="meta-block">
      <div class="label">Contact</div>
      <div class="value">${escapeHtml(facture.client_contact)}</div>
    </div>` : ""}
  </div>
  <table>
    <thead>
      <tr>
        <th class="p-left" style="width:50%">Description</th>
        <th class="p-right">Qté</th>
        <th class="p-right">Prix unitaire</th>
        <th class="p-right">Total</th>
      </tr>
    </thead>
    <tbody>
      ${lignesHtml}
    </tbody>
  </table>
  <div class="total-row">
    <span class="total-label">TOTAL</span>
    <span class="total-value">${formatNumber(facture.total)} FCFA</span>
  </div>
  ${facture.notes ? `<div class="notes"><b>Notes :</b> ${escapeHtml(facture.notes)}</div>` : ""}
  <div class="footer">Document généré par KONIS</div>
</body>
</html>`;
}

// ── Exports publics ────────────────────────────────────────────────────────

/**
 * Imprime un ticket thermique 58mm.
 * autoPrint=true (défaut) : impression immédiate via iframe (sans popup blocker).
 * autoPrint=false : ouvre dans un nouvel onglet pour aperçu sans impression auto.
 */
export function openTicketPrintWindow(
  ticket: TicketPrintData,
  options: { autoPrint?: boolean } = {},
): void {
  const { autoPrint = true } = options;
  const html = buildTicketHtml(ticket);

  if (autoPrint) {
    printViaIframe(html);
    return;
  }

  // Mode aperçu : ouvrir dans un nouvel onglet sans déclencher l'impression
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const popup = window.open(url, "_blank");
  if (popup) {
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } else {
    // Popup bloqué → fallback iframe sans auto-print (inutile mais silencieux)
    URL.revokeObjectURL(url);
  }
}

export function printFacture(facture: FacturePrintData): void {
  printViaIframe(buildFactureHtml(facture));
}
