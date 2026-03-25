"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Store,
  TrendingUp,
  AlertCircle,
  Wallet,
  Users,
  Package,
  RefreshCw,
  Wheat,
  Truck,
  Printer,
} from "lucide-react";
import Link from "next/link";

interface DerniereCollecte {
  date: string;
  montant_trouve: string;
  montant_pris: string;
  montant_laisse: string;
  collecteur: string | null;
}

interface DashboardData {
  total_ventes: string;
  total_cash: string;
  total_credit: string;
  total_creances: string;
  total_paiements_creances: string;
  caisse_reelle: string;
  caisse_physique: string;
  total_collectes_prises: string;
  argent_theorique: string;
  montant_fictif: string;
  total_depenses: string;
  nb_produits_en_stock: number;
  total_mouture: string;
  total_ventes_produits: string;
  derniere_collecte: DerniereCollecte | null;
}

interface Ticket {
  id: number;
  numero: string;
  date: string;
  type_vente: string;
  type_vente_label: string;
  montant_total: string;
  montant_cash: string;
  montant_credit: string;
  client_nom: string | null;
  mouture: boolean;
  cout_mouture: string;
  lignes_count: number;
}

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

export default function BoutiqueDashboardPage() {
  const { user } = useAuth();
  const lieuNom = user?.lieu?.nom ?? "Boutique";

  const [dateDebut, setDateDebut] = useState(todayStr());
  const [dateFin, setDateFin] = useState(todayStr());

  const [data, setData] = useState<DashboardData | null>(null);
  const [ventes, setVentes] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [erreur, setErreur] = useState("");

  const charger = useCallback(async () => {
    try {
      setLoading(true);
      setErreur("");
      const params = `?date_debut=${dateDebut}&date_fin=${dateFin}`;
      const ventesParams = `?debut=${dateDebut}&fin=${dateFin}`;
      const [dashRes, ventesRes] = await Promise.all([
        apiFetch<DashboardData>(`/boutique/dashboard/${params}`),
        apiFetch<{ results?: Ticket[] } | Ticket[]>(`/boutique/ventes/${ventesParams}`),
      ]);
      setData(dashRes);
      setVentes(Array.isArray(ventesRes) ? ventesRes : (ventesRes.results ?? []));
    } catch {
      setErreur("Impossible de charger le tableau de bord.");
    } finally {
      setLoading(false);
    }
  }, [dateDebut, dateFin]);

  useEffect(() => {
    charger();
  }, [charger]);

  if (loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Tableau de bord — {lieuNom}</h1>
        <p className="text-sm text-muted-foreground">Chargement…</p>
      </div>
    );
  }

  if (erreur || !data) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Tableau de bord — {lieuNom}</h1>
        <p className="text-sm text-destructive">{erreur || "Données indisponibles."}</p>
        <Button variant="outline" size="sm" onClick={charger}>
          <RefreshCw className="h-4 w-4 mr-2" /> Réessayer
        </Button>
      </div>
    );
  }

  const tv   = parseFloat(data.total_ventes);
  const tc   = parseFloat(data.total_cash);
  const tcr  = parseFloat(data.total_credit);
  const cre  = parseFloat(data.total_creances);
  const cais = parseFloat(data.caisse_reelle);
  const cp   = parseFloat(data.caisse_physique   || "0");
  const tcp  = parseFloat(data.total_collectes_prises || "0");
  const at   = parseFloat(data.argent_theorique);
  const mf   = parseFloat(data.montant_fictif || "0");
  const dep  = parseFloat(data.total_depenses);
  const mout = parseFloat(data.total_mouture || "0");
  const tvp  = parseFloat(data.total_ventes_produits || "0");

  const periodLabel = dateDebut === dateFin
    ? new Date(dateDebut + "T12:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })
    : `${new Date(dateDebut + "T12:00:00").toLocaleDateString("fr-FR")} – ${new Date(dateFin + "T12:00:00").toLocaleDateString("fr-FR")}`;

  return (
    <div className="space-y-6">
      {/* En-tête impression uniquement */}
      <div className="hidden print:block mb-4">
        <h1 className="text-xl font-bold">{lieuNom} — Tableau de bord</h1>
        <p className="text-sm text-gray-600">Période : {periodLabel}</p>
        <p className="text-xs text-gray-400">Imprimé le {new Date().toLocaleString("fr-FR")}</p>
      </div>

      <div className="flex items-start justify-between gap-4 print:hidden">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Store className="h-6 w-6 text-green-600" />
            Tableau de bord — {lieuNom}
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Synthèse financière · {periodLabel}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <Button variant="outline" size="sm" onClick={charger}>
            <RefreshCw className="h-4 w-4 mr-2" /> Actualiser
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer className="h-4 w-4 mr-2" /> Imprimer
          </Button>
        </div>
      </div>

      {/* Filtre par date */}
      <div className="flex items-end gap-3 flex-wrap print:hidden">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Du</label>
          <Input
            type="date"
            value={dateDebut}
            onChange={(e) => setDateDebut(e.target.value)}
            className="h-8 text-sm w-36"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Au</label>
          <Input
            type="date"
            value={dateFin}
            onChange={(e) => setDateFin(e.target.value)}
            className="h-8 text-sm w-36"
          />
        </div>
      </div>

      {/* KPI principaux */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-green-500">
          <CardHeader className="pb-1 pt-4 px-4">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
              <TrendingUp className="h-3.5 w-3.5 text-green-500" />
              Ventes totales
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <p className="text-2xl font-bold text-green-700 dark:text-green-300">{fmt(tv)}</p>
            <p className="text-xs text-muted-foreground mt-0.5">FCFA enregistrés</p>
            <div className="mt-2 flex gap-3 text-xs text-muted-foreground">
              <span className="text-green-600">Cash : {fmt(tc)}</span>
              <span className="text-red-500">Crédit : {fmt(tcr)}</span>
            </div>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-blue-500">
          <CardHeader className="pb-1 pt-4 px-4">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
              <Wallet className="h-3.5 w-3.5 text-blue-500" />
              En caisse (physique)
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">{fmt(cp)}</p>
            <p className="text-xs text-muted-foreground mt-0.5">FCFA dans le tiroir</p>
            <div className="mt-2 flex flex-col gap-0.5 text-xs text-muted-foreground">
              <span>Encaissé : {fmt(cais)} F</span>
              {tcp > 0 && <span className="text-amber-600">Collecté : −{fmt(tcp)} F</span>}
            </div>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-amber-500">
          <CardHeader className="pb-1 pt-4 px-4">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
              <AlertCircle className="h-3.5 w-3.5 text-amber-500" />
              Créances en cours
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <p className="text-2xl font-bold text-amber-700 dark:text-amber-300">{fmt(cre)}</p>
            <p className="text-xs text-muted-foreground mt-0.5">FCFA à encaisser</p>
            <Link
              href="/boutique/creances"
              className="text-xs text-blue-600 hover:underline mt-1 block print:hidden"
            >
              Voir les créances →
            </Link>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-purple-500">
          <CardHeader className="pb-1 pt-4 px-4">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
              <Users className="h-3.5 w-3.5 text-purple-500" />
              Argent théorique
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <p className="text-2xl font-bold text-purple-700 dark:text-purple-300">{fmt(at)}</p>
            <p className="text-xs text-muted-foreground mt-0.5">FCFA</p>
            <p className="text-xs text-muted-foreground mt-1">Caisse + créances</p>
          </CardContent>
        </Card>
      </div>

      {/* Mouture */}
      {mout > 0 && (
        <div className="rounded-xl border-2 border-dashed border-green-200 dark:border-green-800 p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3 flex items-center gap-1.5">
            <Wheat className="h-3.5 w-3.5 text-green-600" />
            Revenus mouture (inclus dans les ventes)
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Card className="border-l-4 border-l-green-400">
              <CardContent className="pt-3 pb-3 px-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Mouture</p>
                <p className="text-xl font-bold text-green-700 dark:text-green-300 mt-0.5">{fmt(mout)} F</p>
              </CardContent>
            </Card>
            <Card className="border-l-4 border-l-blue-400">
              <CardContent className="pt-3 pb-3 px-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Ventes produits</p>
                <p className="text-xl font-bold text-blue-700 dark:text-blue-300 mt-0.5">{fmt(tvp)} F</p>
              </CardContent>
            </Card>
            <Card className="bg-muted/30">
              <CardContent className="pt-3 pb-3 px-4 text-xs text-muted-foreground space-y-0.5">
                <p>Total ventes = produits + mouture</p>
                <p className="font-medium text-foreground">{fmt(tvp)} + {fmt(mout)} = {fmt(tv)} FCFA</p>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Ligne secondaire */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-1 pt-4 px-4">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Dépenses
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <p className="text-xl font-semibold text-red-600 dark:text-red-400">{fmt(dep)}</p>
            <p className="text-xs text-muted-foreground mt-0.5">FCFA</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-1 pt-4 px-4">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
              <Package className="h-3.5 w-3.5" />
              Stock disponible
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <p className="text-xl font-semibold">{data.nb_produits_en_stock}</p>
            <p className="text-xs text-muted-foreground mt-0.5">produits en stock</p>
          </CardContent>
        </Card>

        <Card className="bg-muted/30">
          <CardHeader className="pb-1 pt-4 px-4">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Formule caisse
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-1 text-xs text-muted-foreground">
            <p>Caisse réelle = cash ventes + paiements créances reçus</p>
            <p>Argent théorique = caisse + créances restantes</p>
            <p className="text-green-600 font-medium">
              {fmt(cais)} + {fmt(cre)} = {fmt(at)} FCFA
            </p>
            <p className="mt-1 pt-1 border-t">Montant fictif = argent théorique − dépenses</p>
            <p className={mf >= 0 ? "text-emerald-600 font-medium" : "text-red-600 font-medium"}>
              {fmt(at)} − {fmt(dep)} = {fmt(mf)} FCFA
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Liste des ventes */}
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3">
          Ventes de la période ({ventes.length})
        </h2>
        {ventes.length === 0 ? (
          <p className="text-sm text-muted-foreground bg-muted/30 rounded p-4 text-center">
            Aucune vente pour cette période.
          </p>
        ) : (
          <div className="overflow-x-auto print:overflow-visible rounded-md border">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40">
                <tr>
                  <th className="text-left px-3 py-2 font-medium text-xs">N°</th>
                  <th className="text-left px-3 py-2 font-medium text-xs">Date / Heure</th>
                  <th className="text-left px-3 py-2 font-medium text-xs">Type</th>
                  <th className="text-left px-3 py-2 font-medium text-xs">Client</th>
                  <th className="text-right px-3 py-2 font-medium text-xs">Total</th>
                  <th className="text-right px-3 py-2 font-medium text-xs">Cash</th>
                  <th className="text-right px-3 py-2 font-medium text-xs">Crédit</th>
                  <th className="text-right px-3 py-2 font-medium text-xs print:hidden">Mouture</th>
                </tr>
              </thead>
              <tbody>
                {ventes.map((t) => {
                  const dt = new Date(t.date);
                  return (
                    <tr key={t.id} className="border-b last:border-0 hover:bg-muted/20">
                      <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{t.numero || `#${t.id}`}</td>
                      <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                        {dt.toLocaleDateString("fr-FR")} {dt.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
                          t.type_vente === "credit"
                            ? "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300"
                            : t.type_vente === "partiel"
                            ? "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                            : "bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-300"
                        }`}>
                          {t.type_vente_label}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">{t.client_nom || "—"}</td>
                      <td className="px-3 py-2 text-right tabular-nums font-semibold">{fmt(parseFloat(t.montant_total))}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-green-600">{fmt(parseFloat(t.montant_cash))}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-red-500">
                        {parseFloat(t.montant_credit) > 0 ? fmt(parseFloat(t.montant_credit)) : "—"}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-xs text-muted-foreground print:hidden">
                        {t.mouture && parseFloat(t.cout_mouture) > 0 ? fmt(parseFloat(t.cout_mouture)) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot className="border-t bg-muted/20">
                <tr>
                  <td colSpan={4} className="px-3 py-2 text-xs font-semibold">Total période</td>
                  <td className="px-3 py-2 text-right tabular-nums font-bold">{fmt(tv)}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold text-green-600">{fmt(tc)}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold text-red-500">{fmt(tcr)}</td>
                  <td className="px-3 py-2 print:hidden" />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>

      {/* Dernière collecte */}
      {data.derniere_collecte && (() => {
        const dc = data.derniere_collecte!;
        const laisse = parseFloat(dc.montant_laisse);
        // Construire la date en heure locale pour éviter le décalage UTC (new Date("YYYY-MM-DD") = UTC midnight)
        const [dy, dm, dd] = dc.date.split("-").map(Number);
        const dateCollecte = new Date(dy, dm - 1, dd);
        return (
          <Card className={laisse > 0 ? "border-l-4 border-l-amber-400" : "border-l-4 border-l-gray-300"}>
            <CardHeader className="pb-1 pt-4 px-4">
              <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                <Truck className="h-3.5 w-3.5 text-amber-500" />
                Dernier passage collecteur
                <span className="ml-auto font-normal normal-case text-xs">
                  {dateCollecte.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" })}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div>
                  <p className="text-xs text-muted-foreground">Trouvé</p>
                  <p className="font-semibold">{fmt(dc.montant_trouve)} F</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Prélevé</p>
                  <p className="font-semibold text-blue-700 dark:text-blue-300">{fmt(dc.montant_pris)} F</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Laissé en boutique</p>
                  <p className={`font-bold ${laisse > 0 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"}`}>
                    {fmt(dc.montant_laisse)} F
                  </p>
                </div>
              </div>
              {dc.collecteur && (
                <p className="text-xs text-muted-foreground mt-2">Collecteur : {dc.collecteur}</p>
              )}
            </CardContent>
          </Card>
        );
      })()}

      {/* Actions rapides */}
      <div className="flex flex-wrap gap-3 print:hidden">
        <Link href="/boutique/caisse" className="inline-flex items-center justify-center rounded-md text-sm font-medium h-9 px-4 py-2 bg-green-600 hover:bg-green-700 text-white transition-colors">
          Aller à la caisse
        </Link>
        <Link href="/boutique/creances" className="inline-flex items-center justify-center rounded-md text-sm font-medium h-9 px-4 py-2 border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground transition-colors">
          Gérer les créances
        </Link>
        <Link href="/boutique/tickets" className="inline-flex items-center justify-center rounded-md text-sm font-medium h-9 px-4 py-2 border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground transition-colors">
          Voir les tickets
        </Link>
      </div>
    </div>
  );
}
