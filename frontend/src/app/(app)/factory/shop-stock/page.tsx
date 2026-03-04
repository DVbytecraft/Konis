"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

interface StockRow {
  id: number;
  produit_id: number;
  produit_nom: string;
  produit_code: string;
  lieu: number;
  lieu_nom: string;
  quantite: string | number;
  unite: string;
}

interface CessionRow {
  id: number;
  lot_nom: string;
  boutique_nom: string;
  produit_nom: string;
  quantite_sacs: string | number;
  prix_par_sac: string | number;
  montant_cession: string | number;
  created_at: string;
}

export default function FactoryShopStockPage() {
  const [stocks, setStocks] = useState<StockRow[]>([]);
  const [cessions, setCessions] = useState<CessionRow[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([
      apiFetch("/usine/stocks-boutiques/"),
      apiFetch("/usine/cessions/"),
    ])
      .then(([stockRes, cessionsRes]) => {
        const stockList = (stockRes as { results?: StockRow[] }).results ?? (stockRes as StockRow[]);
        const cessionList = (cessionsRes as { results?: CessionRow[] }).results ?? (cessionsRes as CessionRow[]);
        setStocks(stockList);
        setCessions(cessionList.slice(0, 30));
      })
      .catch((e) => setErr(e instanceof Error ? e.message : "Erreur de chargement"));
  }, []);

  return (
    <div className="space-y-6 min-w-0">
      <h1 className="text-2xl font-semibold tracking-tight">Stocks boutiques</h1>
      {err && <p className="text-sm text-destructive">{err}</p>}

      <div className="overflow-x-auto rounded-md border -mx-1 sm:mx-0">
        <p className="text-sm font-medium p-3 border-b">Stock produits finis dans les boutiques</p>
        <table className="w-full text-xs sm:text-sm min-w-[480px]">
          <thead>
            <tr className="border-b bg-muted/40">
              <th className="text-left py-2 px-3">Produit</th>
              <th className="text-left py-2 px-3">Boutique</th>
              <th className="text-right py-2 px-3">Quantité</th>
              <th className="text-left py-2 px-3">Unité</th>
            </tr>
          </thead>
          <tbody>
            {stocks.length === 0 && (
              <tr>
                <td colSpan={4} className="py-4 text-center text-muted-foreground text-sm">
                  Aucun stock en boutique pour vos produits.
                </td>
              </tr>
            )}
            {stocks.map((s) => (
              <tr key={s.id} className="border-b hover:bg-muted/20">
                <td className="py-1.5 px-3">{s.produit_nom}</td>
                <td className="py-1.5 px-3">{s.lieu_nom}</td>
                <td className="py-1.5 px-3 text-right">{Number(s.quantite).toFixed(2)}</td>
                <td className="py-1.5 px-3">{s.unite}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="overflow-x-auto rounded-md border -mx-1 sm:mx-0">
        <p className="text-sm font-medium p-3 border-b">Dernières cessions vers boutiques</p>
        <table className="w-full text-xs sm:text-sm min-w-[640px]">
          <thead>
            <tr className="border-b bg-muted/40">
              <th className="text-left py-2 px-3">Lot</th>
              <th className="text-left py-2 px-3">Boutique</th>
              <th className="text-left py-2 px-3">Produit</th>
              <th className="text-right py-2 px-3">Sacs</th>
              <th className="text-right py-2 px-3">Prix/sac</th>
              <th className="text-right py-2 px-3">Montant</th>
              <th className="text-left py-2 px-3">Date</th>
            </tr>
          </thead>
          <tbody>
            {cessions.length === 0 && (
              <tr>
                <td colSpan={7} className="py-4 text-center text-muted-foreground text-sm">
                  Aucune cession enregistrée.
                </td>
              </tr>
            )}
            {cessions.map((c) => (
              <tr key={c.id} className="border-b hover:bg-muted/20">
                <td className="py-1.5 px-3 font-mono">{c.lot_nom}</td>
                <td className="py-1.5 px-3">{c.boutique_nom}</td>
                <td className="py-1.5 px-3">{c.produit_nom}</td>
                <td className="py-1.5 px-3 text-right">{Number(c.quantite_sacs).toFixed(0)}</td>
                <td className="py-1.5 px-3 text-right">{Number(c.prix_par_sac).toFixed(2)}</td>
                <td className="py-1.5 px-3 text-right font-medium">{Number(c.montant_cession).toFixed(2)}</td>
                <td className="py-1.5 px-3 text-muted-foreground">
                  {new Date(c.created_at).toLocaleString("fr-FR")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
