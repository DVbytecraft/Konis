"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { apiFetch } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Receipt,
  Package,
  AlertTriangle,
  TrendingUp,
  MapPin,
} from "lucide-react";

const SEUIL_ALERTE_STOCK = 10;

interface Kpi {
  ventesAujourdhui: number;
  caAujourdhui: number;
  totalStocks: number;
  produitsEnAlerte: number;
}

interface Ticket {
  id: number;
  numero: string;
  date: string;
  lieu_nom: string;
  lignes?: Array<{ quantite: number; prix_unitaire: number; total?: number }>;
}

interface StockItem {
  id: number;
  produit_nom: string;
  lieu_nom: string;
  quantite: string;
}

export default function AdminPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [kpi, setKpi] = useState<Kpi>({
    ventesAujourdhui: 0,
    caAujourdhui: 0,
    totalStocks: 0,
    produitsEnAlerte: 0,
  });
  const [ventes, setVentes] = useState<Ticket[]>([]);
  const [stocks, setStocks] = useState<StockItem[]>([]);
  const [alertes, setAlertes] = useState<StockItem[]>([]);

  const charger = useCallback(async () => {
    try {
      setLoading(true);
      interface Paginated<T> { results: T[] }
      const [ticketsRes, stocksRes] = await Promise.all([
        apiFetch<Paginated<Ticket> | Ticket[]>("/admin/tickets/"),
        apiFetch<Paginated<StockItem> | StockItem[]>("/admin/stocks/"),
      ]);
      const tickets: Ticket[] = Array.isArray(ticketsRes) ? ticketsRes : ticketsRes.results;
      const stocksList: StockItem[] = Array.isArray(stocksRes) ? stocksRes : stocksRes.results;

      const aujourdhui = new Date().toDateString();
      const ventesJour = tickets.filter(
        (t) => new Date(t.date).toDateString() === aujourdhui
      );
      let ca = 0;
      ventesJour.forEach((t) => {
        (t.lignes ?? []).forEach((l) => {
          ca += l.quantite * (l.prix_unitaire ?? 0);
        });
      });

      const totalStocks = stocksList.reduce(
        (acc, s) => acc + parseFloat(s.quantite ?? "0"),
        0
      );
      const enAlerte = stocksList.filter(
        (s) => parseFloat(s.quantite ?? "0") < SEUIL_ALERTE_STOCK
      );

      setKpi({
        ventesAujourdhui: ventesJour.length,
        caAujourdhui: ca,
        totalStocks: Math.round(totalStocks * 100) / 100,
        produitsEnAlerte: enAlerte.length,
      });
      setVentes(tickets.slice(0, 10));
      setStocks(stocksList.slice(0, 15));
      setAlertes(enAlerte.slice(0, 10));
    } catch {
      setKpi((k) => ({ ...k, produitsEnAlerte: 0 }));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    charger();
  }, [charger]);

  return (
    <div className="space-y-8 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Administration
        </h1>
        <p className="mt-1 text-muted-foreground">
          KPI, ventes, stocks et alertes. Connecté : {user?.username}
        </p>
      </div>

      {/* KPI */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="border-l-4 border-l-green-500 bg-green-50/50 dark:bg-green-950/20">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-green-700 dark:text-green-300">Ventes du jour</CardTitle>
            <Receipt className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-2xl font-bold text-muted-foreground">—</p>
            ) : (
              <p className="text-2xl font-bold text-green-800 dark:text-green-200">{kpi.ventesAujourdhui}</p>
            )}
            <p className="text-xs text-green-600/70 dark:text-green-400/70">Tickets du jour</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-green-500 bg-green-50/50 dark:bg-green-950/20">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-green-700 dark:text-green-300">CA du jour</CardTitle>
            <TrendingUp className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-2xl font-bold text-muted-foreground">—</p>
            ) : (
              <p className="text-2xl font-bold text-green-800 dark:text-green-200">{kpi.caAujourdhui.toFixed(2)}</p>
            )}
            <p className="text-xs text-green-600/70 dark:text-green-400/70">Chiffre d&apos;affaires</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-slate-400 bg-slate-50/50 dark:bg-slate-950/20">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-slate-700 dark:text-slate-300">Stock total</CardTitle>
            <Package className="h-4 w-4 text-slate-500" />
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-2xl font-bold text-muted-foreground">—</p>
            ) : (
              <p className="text-2xl font-bold text-slate-800 dark:text-slate-200">{kpi.totalStocks}</p>
            )}
            <p className="text-xs text-slate-600/70 dark:text-slate-400/70">Quantité tous lieux</p>
          </CardContent>
        </Card>
        <Card className={`border-l-4 ${kpi.produitsEnAlerte > 0 ? "border-l-red-500 bg-red-50/50 dark:bg-red-950/20" : "border-l-emerald-400 bg-emerald-50/50 dark:bg-emerald-950/20"}`}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className={`text-sm font-medium ${kpi.produitsEnAlerte > 0 ? "text-red-700 dark:text-red-300" : "text-emerald-700 dark:text-emerald-300"}`}>
              Alertes stock
            </CardTitle>
            <AlertTriangle className={`h-4 w-4 ${kpi.produitsEnAlerte > 0 ? "text-red-500" : "text-emerald-500"}`} />
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-2xl font-bold text-muted-foreground">—</p>
            ) : (
              <p className={`text-2xl font-bold ${kpi.produitsEnAlerte > 0 ? "text-red-700 dark:text-red-300" : "text-emerald-700 dark:text-emerald-300"}`}>
                {kpi.produitsEnAlerte}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              &lt; {SEUIL_ALERTE_STOCK} unités
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Ventes récentes */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Receipt className="h-4 w-4 text-green-500" />
              Ventes récentes
            </CardTitle>
            <CardDescription>Derniers tickets enregistrés</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Chargement…</p>
            ) : ventes.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucune vente</p>
            ) : (
              <div className="overflow-x-auto -mx-1 min-w-0">
                <table className="w-full min-w-[280px] text-sm">
                  <thead>
                    <tr className="border-b bg-muted/30">
                      <th className="text-left py-2 px-1">N°</th>
                      <th className="text-left py-2 px-1">Lieu</th>
                      <th className="text-left py-2 px-1">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ventes.map((t) => (
                      <tr key={t.id} className="border-b hover:bg-muted/20">
                        <td className="py-1.5 px-1 font-mono text-green-700 dark:text-green-300">{t.numero}</td>
                        <td className="py-1.5 px-1">{t.lieu_nom}</td>
                        <td className="py-1.5 px-1 text-muted-foreground">
                          {new Date(t.date).toLocaleString("fr-FR")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Alertes stock */}
        <Card className={alertes.length > 0 ? "border-red-200 dark:border-red-900" : ""}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className={`h-4 w-4 ${alertes.length > 0 ? "text-red-500" : "text-muted-foreground"}`} />
              <span className={alertes.length > 0 ? "text-red-700 dark:text-red-300" : ""}>
                Alertes stock (&lt; {SEUIL_ALERTE_STOCK})
              </span>
            </CardTitle>
            <CardDescription>Produits à réapprovisionner</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Chargement…</p>
            ) : alertes.length === 0 ? (
              <p className="text-sm text-emerald-600 dark:text-emerald-400 font-medium">
                ✓ Aucune alerte — stocks suffisants
              </p>
            ) : (
              <div className="overflow-x-auto -mx-1 min-w-0">
                <table className="w-full min-w-[280px] text-sm">
                  <thead>
                    <tr className="border-b bg-red-50/50 dark:bg-red-950/20">
                      <th className="text-left py-2 px-1">Produit</th>
                      <th className="text-left py-2 px-1">Lieu</th>
                      <th className="text-right py-2 px-1">Qté</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alertes.map((s) => (
                      <tr key={s.id} className="border-b hover:bg-red-50/30 dark:hover:bg-red-950/10">
                        <td className="py-1.5 px-1">{s.produit_nom}</td>
                        <td className="py-1.5 px-1">{s.lieu_nom}</td>
                        <td className="py-1.5 px-1 text-right font-mono text-red-600 dark:text-red-400 font-semibold">
                          {parseFloat(s.quantite).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Stocks */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MapPin className="h-4 w-4 text-slate-500" />
            Stocks par lieu
          </CardTitle>
          <CardDescription>Aperçu des stocks (15 premiers)</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement…</p>
          ) : stocks.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun stock</p>
          ) : (
            <div className="overflow-x-auto -mx-1 min-w-0">
              <table className="w-full min-w-[280px] text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="text-left py-2 px-1">Produit</th>
                    <th className="text-left py-2 px-1">Lieu</th>
                    <th className="text-right py-2 px-1">Quantité</th>
                  </tr>
                </thead>
                <tbody>
                  {stocks.map((s) => {
                    const qte = parseFloat(s.quantite);
                    const enAlerte = qte < SEUIL_ALERTE_STOCK;
                    return (
                      <tr key={s.id} className="border-b hover:bg-muted/20">
                        <td className="py-1.5 px-1">{s.produit_nom}</td>
                        <td className="py-1.5 px-1">{s.lieu_nom}</td>
                        <td className={`py-1.5 px-1 text-right font-mono font-medium ${enAlerte ? "text-red-600 dark:text-red-400" : "text-emerald-700 dark:text-emerald-300"}`}>
                          {qte.toFixed(2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
