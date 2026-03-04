"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface StockItem {
  produit: string;
  quantite: string;
  unite: string;
}

interface LastProduction {
  id: number;
  nom_lot: string;
  produit: string;
  quantite_sacs: string;
  created_at: string;
}

interface LastTransfer {
  id: number;
  lot: string;
  boutique: string;
  quantite_sacs: string;
  montant: string;
  created_at: string;
}

interface LastAchat {
  id: number;
  produit_nom: string;
  quantite: string;
  unite: string;
  prix_total: string;
  date: string;
}

interface DashboardData {
  lieu: string;
  stock_usine: StockItem[];
  total_achats_fcfa: string;
  total_sacs_transferes: string;
  last_productions: LastProduction[];
  last_transfers: LastTransfer[];
  last_achats: LastAchat[];
}

export default function FactoryDashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    apiFetch("/factory/dashboard/")
      .then((res) => setData(res as DashboardData))
      .catch(() => setData(null));
  }, []);

  return (
    <div className="space-y-6 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Tableau de bord — {data?.lieu ?? "Usine"}
          </h1>
          <p className="text-sm text-muted-foreground">Suivi opérationnel usine.</p>
        </div>
        <div className="flex flex-wrap gap-3 text-sm">
          <Link href="/factory/raw-materials" className="text-orange-600 dark:text-orange-400 hover:underline font-medium">Achats</Link>
          <Link href="/factory/production" className="text-purple-600 dark:text-purple-400 hover:underline font-medium">Production</Link>
          <Link href="/factory/transfers" className="text-blue-600 dark:text-blue-400 hover:underline font-medium">Transferts</Link>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="border-l-4 border-l-orange-500 bg-orange-50/50 dark:bg-orange-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-orange-700 dark:text-orange-300">Total achats</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-orange-800 dark:text-orange-200">
              {data ? Number(data.total_achats_fcfa).toLocaleString("fr-FR") : "…"}
            </p>
            <p className="text-xs text-orange-600/70 dark:text-orange-400/70">FCFA</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-blue-500 bg-blue-50/50 dark:bg-blue-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-blue-700 dark:text-blue-300">Sacs transférés</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-blue-800 dark:text-blue-200">
              {data ? Number(data.total_sacs_transferes).toLocaleString("fr-FR") : "…"}
            </p>
            <p className="text-xs text-blue-600/70 dark:text-blue-400/70">vers boutiques</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-purple-500 bg-purple-50/50 dark:bg-purple-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-purple-700 dark:text-purple-300">Lots produits</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-purple-800 dark:text-purple-200">{data ? data.last_productions.length : "…"}</p>
            <p className="text-xs text-purple-600/70 dark:text-purple-400/70">5 derniers</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-emerald-500 bg-emerald-50/50 dark:bg-emerald-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-emerald-700 dark:text-emerald-300">Produits en stock</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-emerald-800 dark:text-emerald-200">{data ? data.stock_usine.length : "…"}</p>
            <p className="text-xs text-emerald-600/70 dark:text-emerald-400/70">références</p>
          </CardContent>
        </Card>
      </div>

      {data && data.stock_usine.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
              Stock usine actuel
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[360px]">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="text-left py-1.5 px-2">Produit</th>
                    <th className="text-right py-1.5 px-2">Quantité</th>
                    <th className="text-left py-1.5 px-2">Unité</th>
                  </tr>
                </thead>
                <tbody>
                  {data.stock_usine.map((s, i) => (
                    <tr key={i} className="border-b hover:bg-muted/20">
                      <td className="py-1.5 px-2 font-medium">{s.produit}</td>
                      <td className="py-1.5 px-2 text-right font-mono text-emerald-700 dark:text-emerald-300 font-semibold">
                        {Number(s.quantite).toFixed(2)}
                      </td>
                      <td className="py-1.5 px-2 text-muted-foreground">{s.unite}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="border-t-2 border-t-purple-400">
          <CardHeader>
            <CardTitle className="text-base text-purple-700 dark:text-purple-300">Dernières productions</CardTitle>
          </CardHeader>
          <CardContent>
            {(!data || data.last_productions.length === 0) ? (
              <p className="text-sm text-muted-foreground">Aucune production.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {data.last_productions.map((l) => (
                  <li key={l.id} className="flex justify-between border-b pb-1 last:border-0">
                    <span className="font-mono truncate max-w-[140px] text-purple-800 dark:text-purple-200">{l.nom_lot}</span>
                    <span className="text-muted-foreground">{Number(l.quantite_sacs).toFixed(0)} sacs</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card className="border-t-2 border-t-blue-400">
          <CardHeader>
            <CardTitle className="text-base text-blue-700 dark:text-blue-300">Derniers transferts</CardTitle>
          </CardHeader>
          <CardContent>
            {(!data || data.last_transfers.length === 0) ? (
              <p className="text-sm text-muted-foreground">Aucun transfert.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {data.last_transfers.map((t) => (
                  <li key={t.id} className="flex justify-between border-b pb-1 last:border-0">
                    <span className="truncate max-w-[120px]">{t.boutique}</span>
                    <span className="text-blue-700 dark:text-blue-300 font-medium">{Number(t.montant).toLocaleString("fr-FR")} F</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card className="border-t-2 border-t-orange-400">
          <CardHeader>
            <CardTitle className="text-base text-orange-700 dark:text-orange-300">Derniers achats</CardTitle>
          </CardHeader>
          <CardContent>
            {(!data || data.last_achats.length === 0) ? (
              <p className="text-sm text-muted-foreground">Aucun achat.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {data.last_achats.map((a) => (
                  <li key={a.id} className="flex justify-between border-b pb-1 last:border-0">
                    <span className="truncate max-w-[140px]">{a.produit_nom}</span>
                    <span className="text-orange-700 dark:text-orange-300 font-medium">{Number(a.prix_total).toLocaleString("fr-FR")} F</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
