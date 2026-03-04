"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

interface ProductionRow {
  id: number;
  nom_lot: string;
  produit_fini_nom: string;
  quantite_sacs: string | number;
  poids: string | number;
  unite_poids: string;
  stock_restant: string | number;
  created_at: string;
}

export default function FactoryProductionPage() {
  const [rows, setRows] = useState<ProductionRow[]>([]);

  useEffect(() => {
    apiFetch("/usine/lots/")
      .then((res) => {
        const list = (res as { results?: ProductionRow[] }).results ?? (res as ProductionRow[]);
        setRows(list);
      })
      .catch(() => setRows([]));
  }, []);

  return (
    <div className="space-y-4 min-w-0">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <span className="inline-block w-3 h-3 rounded-full bg-purple-500"></span>
          Lots de production
        </h1>
        <Link href="/factory/production/new" className="text-sm font-medium text-purple-600 dark:text-purple-400 hover:underline">
          + Nouveau lot
        </Link>
      </div>
      <div className="overflow-x-auto rounded-md border -mx-1 sm:mx-0">
        <table className="w-full text-xs sm:text-sm min-w-[600px]">
          <thead>
            <tr className="border-b bg-purple-50/50 dark:bg-purple-950/20">
              <th className="text-left py-2 px-3 text-purple-700 dark:text-purple-300">Lot</th>
              <th className="text-left py-2 px-3">Produit</th>
              <th className="text-right py-2 px-3">Sacs produits</th>
              <th className="text-right py-2 px-3">Poids</th>
              <th className="text-right py-2 px-3 text-emerald-700 dark:text-emerald-300">Stock restant</th>
              <th className="text-left py-2 px-3">Date</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="py-4 text-center text-muted-foreground text-sm">
                  Aucun lot de production.
                </td>
              </tr>
            )}
            {rows.map((r) => {
              const stockRestant = Number(r.stock_restant);
              const stockFaible = stockRestant < 10;
              return (
                <tr key={r.id} className="border-b hover:bg-purple-50/30 dark:hover:bg-purple-950/10">
                  <td className="py-1.5 px-3 font-mono text-purple-700 dark:text-purple-300 font-medium">{r.nom_lot}</td>
                  <td className="py-1.5 px-3">{r.produit_fini_nom}</td>
                  <td className="py-1.5 px-3 text-right font-medium">{Number(r.quantite_sacs).toFixed(0)}</td>
                  <td className="py-1.5 px-3 text-right text-muted-foreground">
                    {Number(r.poids) > 0 ? `${Number(r.poids).toFixed(2)} ${r.unite_poids}` : "—"}
                  </td>
                  <td className={`py-1.5 px-3 text-right font-semibold ${stockFaible ? "text-red-600 dark:text-red-400" : "text-emerald-700 dark:text-emerald-300"}`}>
                    {stockRestant.toFixed(0)}
                  </td>
                  <td className="py-1.5 px-3 text-muted-foreground">
                    {new Date(r.created_at).toLocaleString("fr-FR")}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
