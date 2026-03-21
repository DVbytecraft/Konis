"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Package, RefreshCw, Store } from "lucide-react";
import { cn } from "@/lib/utils";

interface StockItem {
  id: number;
  produit: number;
  produit_nom: string;
  produit_code: string;
  produit_unite: string;
  poids_par_sac: string | null;
  lieu: number;
  lieu_nom: string;
  quantite: string;
  quantite_kg: string;
}

interface GroupedBoutique {
  lieu_nom: string;
  lieu_id: number;
  items: StockItem[];
  total_produits: number;
}

export default function AdminStockPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stocks, setStocks] = useState<StockItem[]>([]);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await apiFetch<StockItem[]>("/admin/stocks/");
      setStocks(Array.isArray(data) ? data : (data as { results: StockItem[] }).results ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = stocks.filter(s =>
    s.produit_nom.toLowerCase().includes(search.toLowerCase()) ||
    s.lieu_nom.toLowerCase().includes(search.toLowerCase()) ||
    s.produit_code?.toLowerCase().includes(search.toLowerCase())
  );

  // Group by boutique
  const grouped: GroupedBoutique[] = filtered.reduce<GroupedBoutique[]>((acc, item) => {
    const existing = acc.find(g => g.lieu_id === item.lieu);
    if (existing) {
      existing.items.push(item);
      if (parseFloat(item.quantite) > 0) existing.total_produits += 1;
    } else {
      acc.push({
        lieu_nom: item.lieu_nom,
        lieu_id: item.lieu,
        items: [item],
        total_produits: parseFloat(item.quantite) > 0 ? 1 : 0,
      });
    }
    return acc;
  }, []).sort((a, b) => a.lieu_nom.localeCompare(b.lieu_nom));

  const totalGlobal = filtered.reduce((s, i) => s + parseFloat(i.quantite), 0);
  const totalProduits = filtered.filter(i => parseFloat(i.quantite) > 0).length;

  return (
    <div className="space-y-6 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Stock global — toutes boutiques</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Vue consolidée du stock par boutique et par produit
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={cn("h-4 w-4 mr-2", loading && "animate-spin")} />
          Actualiser
        </Button>
      </div>

      {error && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{error}</p>
      )}

      {/* KPIs globaux */}
      {!loading && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <Card className="border-l-4 border-l-blue-500">
            <CardContent className="pt-4 pb-4 px-4">
              <p className="text-xs text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                <Package className="h-3.5 w-3.5" /> Lignes de stock actives
              </p>
              <p className="text-2xl font-bold text-blue-700 dark:text-blue-300 mt-1">{totalProduits}</p>
              <p className="text-xs text-muted-foreground mt-0.5">produits en stock (toutes boutiques)</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-green-500">
            <CardContent className="pt-4 pb-4 px-4">
              <p className="text-xs text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                <Store className="h-3.5 w-3.5" /> Boutiques
              </p>
              <p className="text-2xl font-bold text-green-700 dark:text-green-300 mt-1">{grouped.length}</p>
              <p className="text-xs text-muted-foreground mt-0.5">emplacements avec du stock</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-amber-400">
            <CardContent className="pt-4 pb-4 px-4">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Quantité totale</p>
              <p className="text-2xl font-bold text-amber-700 dark:text-amber-300 mt-1">{fmt(totalGlobal)}</p>
              <p className="text-xs text-muted-foreground mt-0.5">unités (toutes unités confondues)</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filtre */}
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Filtrer par produit, code ou boutique…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 w-full max-w-sm rounded-md border border-input bg-background px-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement…</p>
      ) : grouped.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aucun stock trouvé.</p>
      ) : (
        <div className="space-y-5">
          {grouped.map((g) => (
            <Card key={g.lieu_id}>
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <Store className="h-4 w-4 text-green-600" />
                  {g.lieu_nom}
                  <span className="ml-auto text-xs font-normal text-muted-foreground">
                    {g.total_produits} produit{g.total_produits !== 1 ? "s" : ""} en stock
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-xs text-muted-foreground uppercase tracking-wide">
                        <th className="text-left pb-1.5 font-medium">Produit</th>
                        <th className="text-left pb-1.5 font-medium">Code</th>
                        <th className="text-right pb-1.5 font-medium">Sacs / Unités</th>
                        <th className="text-right pb-1.5 font-medium">Kg conv.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {g.items
                        .sort((a, b) => parseFloat(b.quantite) - parseFloat(a.quantite))
                        .map((item) => (
                          <tr key={item.id} className={cn(
                            "border-b last:border-0",
                            parseFloat(item.quantite) === 0 && parseFloat(item.quantite_kg) === 0 && "opacity-40"
                          )}>
                            <td className="py-1.5 font-medium">{item.produit_nom}</td>
                            <td className="py-1.5 text-muted-foreground text-xs">{item.produit_code || "—"}</td>
                            <td className="py-1.5 text-right font-mono font-semibold">
                              <span className={cn(
                                parseFloat(item.quantite) > 0
                                  ? "text-green-700 dark:text-green-400"
                                  : "text-red-500"
                              )}>
                                {fmt(item.quantite)}
                              </span>
                            </td>
                            <td className="py-1.5 text-right font-mono text-muted-foreground text-xs">
                              {parseFloat(item.quantite_kg) > 0 ? `${item.quantite_kg} kg` : "—"}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
