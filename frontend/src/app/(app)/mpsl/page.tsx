"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface StockItem {
  produit: string;
  unite: string;
  quantite: string;
  poids_par_sac: string | null;
}

interface LastAchat {
  id: number;
  produit: string;
  quantite: string;
  unite: string;
  poids_par_sac: string | null;
  prix_total: string;
  date: string;
}

interface LastTransfert {
  id: number;
  to_lieu: string;
  to_lieu_type: string;
  nb_produits: number;
  date: string;
}

interface DashboardData {
  lieu: string;
  stock_mpsl: StockItem[];
  total_achats_fcfa: string;
  total_transferts: number;
  last_achats: LastAchat[];
  last_transferts: LastTransfert[];
}

export default function MpslDashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    apiFetch("/mpsl/dashboard/")
      .then((res) => setData(res as DashboardData))
      .catch(() => setData(null));
  }, []);

  return (
    <div className="space-y-6 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Tableau de bord — {data?.lieu ?? "MPSL"}
          </h1>
          <p className="text-sm text-muted-foreground">Centre logistique d&apos;approvisionnement.</p>
        </div>
        <div className="flex flex-wrap gap-3 text-sm">
          <Link href="/mpsl/achats" className="text-orange-600 dark:text-orange-400 hover:underline font-medium">Achats</Link>
          <Link href="/mpsl/transferts" className="text-blue-600 dark:text-blue-400 hover:underline font-medium">Transferts</Link>
          <Link href="/mpsl/stock" className="text-emerald-600 dark:text-emerald-400 hover:underline font-medium">Stock</Link>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
            <CardTitle className="text-sm font-medium text-blue-700 dark:text-blue-300">Transferts sortants</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-blue-800 dark:text-blue-200">
              {data ? data.total_transferts : "…"}
            </p>
            <p className="text-xs text-blue-600/70 dark:text-blue-400/70">vers usines &amp; magasins</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-emerald-500 bg-emerald-50/50 dark:bg-emerald-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-emerald-700 dark:text-emerald-300">Produits en stock</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-emerald-800 dark:text-emerald-200">
              {data ? data.stock_mpsl.length : "…"}
            </p>
            <p className="text-xs text-emerald-600/70 dark:text-emerald-400/70">références</p>
          </CardContent>
        </Card>
      </div>

      {data && data.stock_mpsl.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-500" />
              Stock actuel du dépôt
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
                    <th className="text-right py-1.5 px-2">Poids/sac</th>
                  </tr>
                </thead>
                <tbody>
                  {data.stock_mpsl.map((s, i) => (
                    <tr key={i} className="border-b hover:bg-muted/20">
                      <td className="py-1.5 px-2 font-medium">{s.produit}</td>
                      <td className="py-1.5 px-2 text-right font-mono text-emerald-700 dark:text-emerald-300 font-semibold">
                        {Number(s.quantite).toLocaleString("fr-FR", { maximumFractionDigits: 3 })}
                      </td>
                      <td className="py-1.5 px-2 text-muted-foreground">{s.unite}</td>
                      <td className="py-1.5 px-2 text-right text-muted-foreground tabular-nums">
                        {s.poids_par_sac ? `${s.poids_par_sac} kg` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
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
                    <span className="truncate max-w-[160px]">
                      {a.produit}
                      {a.unite === "sacs" && a.poids_par_sac && (
                        <span className="ml-1 text-xs text-muted-foreground">({a.poids_par_sac} kg/sac)</span>
                      )}
                    </span>
                    <span className="text-orange-700 dark:text-orange-300 font-medium">
                      {Number(a.prix_total).toLocaleString("fr-FR")} F
                    </span>
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
            {(!data || data.last_transferts.length === 0) ? (
              <p className="text-sm text-muted-foreground">Aucun transfert.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {data.last_transferts.map((t) => (
                  <li key={t.id} className="flex justify-between border-b pb-1 last:border-0">
                    <span className="truncate max-w-[160px]">{t.to_lieu}</span>
                    <span className="text-xs text-muted-foreground capitalize">
                      {t.to_lieu_type === "usine" ? "Usine" : "Magasin"}
                    </span>
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
