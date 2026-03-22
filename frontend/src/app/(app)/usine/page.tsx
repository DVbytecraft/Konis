"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface LotRow {
  lot_id: number;
  nom_lot: string;
  produit_fini: string;
  quantite_produite: string;
  quantite_cedee: string;
  cout_total: string;
  total_cession: string;
  benefice: string;
}

interface StockRow {
  id: number;
  produit_nom: string;
  lieu_nom: string;
  quantite: string;
}

export default function UsinePage() {
  const [loading, setLoading] = useState(true);
  const [lots, setLots] = useState<LotRow[]>([]);
  const [stocks, setStocks] = useState<StockRow[]>([]);

  const charger = useCallback(async () => {
    try {
      setLoading(true);
      interface Paginated<T> { results: T[] }
      const [rapport, stocksRes] = await Promise.all([
        apiFetch<Paginated<LotRow>>("/usine/rapports/benefices/"),
        apiFetch<Paginated<StockRow> | StockRow[]>("/usine/stocks-boutiques/"),
      ]);
      setLots(rapport.results ?? []);
      setStocks((Array.isArray(stocksRes) ? stocksRes : stocksRes.results).slice(0, 30));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    charger();
  }, [charger]);

  return (
    <div className="space-y-6 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Usine</h1>
          <p className="text-sm text-muted-foreground">Lots de production, cessions et stocks boutiques.</p>
        </div>
        <Link href="/usine/stock" className="text-sm text-emerald-600 dark:text-emerald-400 hover:underline font-medium">
          Stock usine
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Bénéfices par lot</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement...</p>
          ) : lots.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun lot.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[640px]">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2">Lot</th>
                    <th className="text-left py-2">Produit</th>
                    <th className="text-right py-2">Coût</th>
                    <th className="text-right py-2">Cession</th>
                    <th className="text-right py-2">Bénéfice</th>
                  </tr>
                </thead>
                <tbody>
                  {lots.map((l) => (
                    <tr key={l.lot_id} className="border-b">
                      <td className="py-1.5 font-mono">{l.nom_lot}</td>
                      <td className="py-1.5">{l.produit_fini}</td>
                      <td className="py-1.5 text-right">{Number(l.cout_total).toFixed(2)}</td>
                      <td className="py-1.5 text-right">{Number(l.total_cession).toFixed(2)}</td>
                      <td className="py-1.5 text-right font-semibold">{Number(l.benefice).toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Stocks boutiques (produits finis)</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement...</p>
          ) : stocks.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucune ligne de stock.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[520px]">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2">Produit</th>
                    <th className="text-left py-2">Boutique</th>
                    <th className="text-right py-2">Quantité</th>
                  </tr>
                </thead>
                <tbody>
                  {stocks.map((s) => (
                    <tr key={s.id} className="border-b">
                      <td className="py-1.5">{s.produit_nom}</td>
                      <td className="py-1.5">{s.lieu_nom}</td>
                      <td className="py-1.5 text-right">{Number(s.quantite).toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
