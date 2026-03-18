"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface Produit {
  id: number;
  nom: string;
  code: string | null;
  unite: string;
  categorie_nom: string;
  category: string;
}

export default function AdminProduitsPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [produits, setProduits] = useState<Produit[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        interface Paginated<T> { results: T[] }
        const res = await apiFetch<Paginated<Produit> | Produit[]>("/admin/produits/");
        setProduits(Array.isArray(res) ? res : res.results);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur de chargement");
      } finally {
        setLoading(false);
      }
    };
    load().catch(() => null);
  }, []);

  if (user?.role !== "admin" && user?.role !== "supreme_admin") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Produits</h1>
        <p className="text-sm text-muted-foreground">Acces reserve au role administrateur.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Produits</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Vue de supervision uniquement. La creation des produits est reservee aux usines et aux boutiques.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Catalogue produits</CardTitle>
          <CardDescription>Produits actuellement utilises par le systeme.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement...</p>
          ) : error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : produits.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun produit.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[280px] text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="text-left py-2 px-1">Nom</th>
                    <th className="text-left py-2 px-1">Code</th>
                    <th className="text-left py-2 px-1">Unité</th>
                  </tr>
                </thead>
                <tbody>
                  {produits.map((p) => (
                    <tr key={p.id} className="border-b hover:bg-muted/20">
                      <td className="py-1.5 px-1 font-medium">{p.nom}</td>
                      <td className="py-1.5 px-1 font-mono text-muted-foreground">{p.code || "—"}</td>
                      <td className="py-1.5 px-1 text-muted-foreground">{p.unite}</td>
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
