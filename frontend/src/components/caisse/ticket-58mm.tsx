"use client";

import { fmt } from "@/lib/utils";

export interface LigneTicket {
  produit_nom: string;
  quantite: number;
  prix_unitaire: number;
  total: number;
  unite?: string;
}

interface Ticket58mmProps {
  lieuNom: string;
  numero: string;
  date: string;
  lignes: LigneTicket[];
  totalGeneral: number;
  /** Mouture demandée ? */
  mouture?: boolean;
  /** Coût total de la mouture (en FCFA) */
  coutMouture?: number;
  /** Prix mouture par kg (formule unifiée) */
  prixParKg?: number;
  /** Quantité apportée par le client (kg, normalisé) */
  quantiteApporteeKg?: number;
  /** Quantité achetée / supplémentaire (kg, normalisé) */
  quantiteAcheteeKg?: number;
  /** Produit apporté par le client (mouture-seule) */
  produitApporte?: string;
  /** Si true, applique les styles d'impression thermique 80mm */
  printStyle?: boolean;
  /** Si true, affiche un bandeau "COPIE" (ticket réimprimé) */
  copie?: boolean;
  // Legacy props — kept for backward compat (old tickets)
  prixMoutureKg?: number;
  prixMoutureTonne?: number;
  prixMoutureSac?: number;
  /** Client (optionnel) */
  clientNom?: string | null;
  clientContact?: string | null;
}

export function Ticket58mm({
  lieuNom,
  numero,
  date,
  lignes,
  totalGeneral,
  mouture = false,
  coutMouture = 0,
  prixParKg,
  quantiteApporteeKg = 0,
  quantiteAcheteeKg = 0,
  produitApporte,
  printStyle = true,
  copie = false,
  prixMoutureKg,
  clientNom,
  clientContact,
}: Ticket58mmProps) {
  const moutureSeule = mouture && lignes.length === 0;
  const totalProduits = lignes.reduce((a, l) => a + Number(l.total), 0);
  // Unified: use prix_par_kg; fall back to legacy prixMoutureKg for old tickets
  const prixKgDisplay = prixParKg ?? prixMoutureKg ?? null;
  const totalMoudreKg = quantiteApporteeKg + quantiteAcheteeKg;
  const hasBreakdown = totalMoudreKg > 0;

  return (
    <div
      className="ticket-thermal-print bg-white text-black p-1 border border-border"
      style={
        printStyle
          ? {
              width: "72mm",
              minHeight: "40mm",
              fontSize: "10px",
              fontFamily: "monospace",
              lineHeight: 1.2,
            }
          : undefined
      }
    >
      {/* En-tête — le logo est volontairement absent des tickets (application uniquement) */}
      <div className="text-center font-semibold text-xs uppercase tracking-wider">
        {lieuNom}
      </div>
      <div className="text-center text-[10px] mt-0.5">
        Ticket {numero}
      </div>
      <div className="text-center text-[9px] opacity-80">
        {date}
      </div>
      {clientNom && (
        <div className="text-[9px] border-t border-dashed border-black mt-1 pt-1">
          <span className="font-semibold">Client :</span> {clientNom}
          {clientContact && <div><span className="font-semibold">Tél :</span> {clientContact}</div>}
        </div>
      )}
      {copie && (
        <div className="text-center text-[9px] font-bold tracking-widest border border-dashed border-black py-0.5 mt-1">
          ── COPIE ──
        </div>
      )}

      {/* Lignes produits */}
      <hr className="border-black border-dashed my-1" />
      {moutureSeule ? (
        <div className="space-y-0.5">
          <div className="text-center text-[9px] font-bold">─── SERVICE MOUTURE ───</div>
          {produitApporte && (
            <div className="flex justify-between text-[10px]">
              <span>Produit</span>
              <span className="font-medium">{produitApporte}</span>
            </div>
          )}
        </div>
      ) : (
        lignes.map((l, i) => (
          <div key={i} className="flex justify-between text-[10px]">
            <span className="flex-1 truncate">
              {l.unite ? `${l.quantite} ${l.unite} x ${l.produit_nom}` : `${l.quantite} x ${l.produit_nom}`}
            </span>
            <span className="ml-1">{fmt(l.total)}</span>
          </div>
        ))
      )}

      {/* Section mouture */}
      <hr className="border-black border-dashed my-1" />
      {mouture ? (
        <div className="space-y-0.5">
          {!moutureSeule && (
            <div className="text-center text-[9px] font-bold">─── MOUTURE ───</div>
          )}
          {hasBreakdown && (
            <>
              <div className="flex justify-between text-[9px]">
                <span>Apporté</span>
                <span>{fmt(quantiteApporteeKg, 3)} kg</span>
              </div>
              <div className="flex justify-between text-[9px]">
                <span>Acheté</span>
                <span>{fmt(quantiteAcheteeKg, 3)} kg</span>
              </div>
              <div className="flex justify-between text-[9px] font-semibold border-t border-dashed border-black pt-0.5 mt-0.5">
                <span>Total moudre</span>
                <span>{fmt(totalMoudreKg, 3)} kg</span>
              </div>
            </>
          )}
          {prixKgDisplay != null && prixKgDisplay > 0 && (
            <div className="flex justify-between text-[9px]">
              <span>Prix/kg</span>
              <span>{fmt(prixKgDisplay)} FCFA</span>
            </div>
          )}
          <div className="flex justify-between text-[10px] font-semibold">
            <span>Coût mouture</span>
            <span>{fmt(coutMouture)} FCFA</span>
          </div>
        </div>
      ) : (
        <div className="text-[9px] opacity-70">MOUTURE : NON</div>
      )}

      {/* Totaux */}
      <hr className="border-black border-dashed my-1" />
      {mouture && coutMouture > 0 && !moutureSeule && (
        <div className="flex justify-between text-[9px]">
          <span>Sous-total produits</span>
          <span>{fmt(totalProduits)}</span>
        </div>
      )}
      <div className="flex justify-between font-semibold text-[11px]">
        <span>TOTAL</span>
        <span>{fmt(totalGeneral)} FCFA</span>
      </div>

      <div className="text-center text-[9px] mt-2">
        Merci de votre achat
      </div>
    </div>
  );
}
