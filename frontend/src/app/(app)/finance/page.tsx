"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Banknote, FolderKanban, TrendingDown, TrendingUp,
  RefreshCw, ArrowUpCircle, ArrowDownCircle, DollarSign, Wheat, Truck, Printer,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Resume {
  total_creances_restantes: string;
  total_payables_restants: string;
  total_emprunts_restants: string;
  solde_caisse: string;
  projets_en_cours: number;
  projets_en_depassement: number;
}

interface CollecteParBoutique {
  lieu_id: number;
  lieu_nom: string;
  total_pris: string;
  total_laisse: string;
}

interface VenteBoutique {
  lieu_id: number;
  lieu_nom: string;
  nb_tickets: number;
  total_ventes: string;
  total_mouture: string;
  total_creances: string;
  caisse_reelle: string;
  nb_produits_en_stock: number;
}

interface DashboardGlobal {
  total_ventes: string;
  total_cash: string;
  total_credit: string;
  total_creances: string;
  total_dettes_fourn: string;
  total_depenses: string;
  solde_caisse: string;
  caisse_reelle: string;
  argent_theorique: string;
  montant_fictif: string;
  benefice_brut: string;
  benefice_net: string;
  total_mouture: string;
  total_ventes_produits: string;
  total_collecte_pris: string;
  total_collecte_laisse: string;
  collectes_par_boutique: CollecteParBoutique[];
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function FinanceDashboardPage() {
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [resume, setResume]       = useState<Resume | null>(null);
  const [global, setGlobal]       = useState<DashboardGlobal | null>(null);
  const [ventesBoutiques, setVentesBoutiques] = useState<VenteBoutique[]>([]);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [resumeData, globalData, boutiquesData] = await Promise.all([
        apiFetch<Resume>("/finance/resume/"),
        apiFetch<DashboardGlobal>("/finance/dashboard/"),
        apiFetch<VenteBoutique[]>("/comptable/rapport-boutiques/").catch(() => [] as VenteBoutique[]),
      ]);
      setResume(resumeData);
      setGlobal(globalData);
      setVentesBoutiques(Array.isArray(boutiquesData) ? boutiquesData : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const benBrut  = global ? parseFloat(global.benefice_brut)  : 0;
  const benNet   = global ? parseFloat(global.benefice_net)   : 0;
  const isProfit = benNet >= 0;

  return (
    <div className="space-y-6 min-w-0">
      <div className="hidden print:block mb-4">
        <h1 className="text-xl font-bold">Finance — Tableau de bord</h1>
        <p className="text-sm text-gray-500">Vue d&apos;ensemble complète de la situation financière</p>
      </div>
      <div className="flex items-center justify-between flex-wrap gap-3 print:hidden">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Finance — Tableau de bord</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Vue d&apos;ensemble complète de la situation financière
          </p>
        </div>
        <div className="flex gap-2 print:hidden">
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer className="h-4 w-4 mr-2" />
            Imprimer
          </Button>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4 mr-2", loading && "animate-spin")} />
            Actualiser
          </Button>
        </div>
      </div>

      {error && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{error}</p>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement…</p>
      ) : (
        <>
          {/* ── Bénéfice — section principale ──────────────────────────────── */}
          {global && (
            <div className="rounded-xl border-2 border-dashed p-5 space-y-4"
              style={{ borderColor: isProfit ? "#22c55e" : "#ef4444" }}
            >
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Calcul du bénéfice
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Card className="border-l-4 border-l-green-400">
                  <CardHeader className="pb-1 pt-4 px-4">
                    <CardTitle className="text-xs text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                      <TrendingUp className="h-3.5 w-3.5 text-green-500" />
                      Total ventes
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <p className="text-xl font-bold text-green-700 dark:text-green-300">
                      {fmt(global.total_ventes)} F
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Cash: {fmt(global.total_cash)} · Crédit: {fmt(global.total_credit)}
                    </p>
                  </CardContent>
                </Card>

                <Card className="border-l-4 border-l-orange-400">
                  <CardHeader className="pb-1 pt-4 px-4">
                    <CardTitle className="text-xs text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                      <ArrowDownCircle className="h-3.5 w-3.5 text-orange-500" />
                      Bénéfice brut
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <p className={cn(
                      "text-xl font-bold",
                      benBrut >= 0 ? "text-orange-600 dark:text-orange-300" : "text-red-600"
                    )}>
                      {fmt(global.benefice_brut)} F
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Ventes − achats fournisseurs
                    </p>
                  </CardContent>
                </Card>

                <Card className={cn(
                  "border-l-4",
                  isProfit ? "border-l-emerald-500" : "border-l-red-500"
                )}>
                  <CardHeader className="pb-1 pt-4 px-4">
                    <CardTitle className="text-xs text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                      {isProfit
                        ? <ArrowUpCircle className="h-3.5 w-3.5 text-emerald-500" />
                        : <ArrowDownCircle className="h-3.5 w-3.5 text-red-500" />
                      }
                      Bénéfice net
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <p className={cn(
                      "text-2xl font-bold",
                      isProfit ? "text-emerald-700 dark:text-emerald-300" : "text-red-600"
                    )}>
                      {isProfit ? "+" : ""}{fmt(global.benefice_net)} F
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Brut − dépenses ({fmt(global.total_depenses)} F)
                    </p>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          {/* ── Mouture ─────────────────────────────────────────────────────── */}
          {global && parseFloat(global.total_mouture) > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Card className="border-l-4 border-l-green-400">
                <CardContent className="pt-4 pb-4 px-4">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                    <Wheat className="h-3.5 w-3.5 text-green-500" /> Revenus mouture
                  </p>
                  <p className="text-lg font-bold text-green-700 dark:text-green-300 mt-1">
                    {fmt(global.total_mouture)} F
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">Toutes boutiques</p>
                </CardContent>
              </Card>
              <Card className="border-l-4 border-l-blue-400">
                <CardContent className="pt-4 pb-4 px-4">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">
                    Ventes produits
                  </p>
                  <p className="text-lg font-bold text-blue-700 dark:text-blue-300 mt-1">
                    {fmt(global.total_ventes_produits)} F
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">Hors mouture</p>
                </CardContent>
              </Card>
              <Card className="bg-muted/30">
                <CardContent className="pt-4 pb-4 px-4 text-xs text-muted-foreground space-y-0.5">
                  <p className="font-medium">Décomposition des ventes</p>
                  <p>Produits : {fmt(global.total_ventes_produits)} F</p>
                  <p>Mouture : {fmt(global.total_mouture)} F</p>
                  <p className="text-green-600 font-semibold">
                    Total : {fmt(global.total_ventes)} F
                  </p>
                </CardContent>
              </Card>
            </div>
          )}

          {/* ── Trésorerie ──────────────────────────────────────────────────── */}
          {global && (() => {
            const mf = parseFloat(global.montant_fictif);
            const mfPositif = mf >= 0;
            return (
              <div className="space-y-3">
                {/* Trésorerie (caisse suprême) — source unique de vérité */}
                <div className="rounded-lg border-2 border-emerald-400 bg-emerald-50 dark:bg-emerald-950/20 p-3 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-400 flex items-center gap-1">
                      <Banknote className="h-3.5 w-3.5" /> Trésorerie (banque / caisse suprême)
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Σ dépôts − Σ retraits · inclut les collectes boutiques
                    </p>
                  </div>
                  <p className="text-2xl font-bold text-emerald-700 dark:text-emerald-400 tabular-nums shrink-0">
                    {fmt(global.solde_caisse)} F
                  </p>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <Card className="border-l-4 border-l-blue-600">
                    <CardContent className="pt-4 pb-4 px-4">
                      <p className="text-xs text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                        <Banknote className="h-3.5 w-3.5" /> Cash encaissé (boutiques)
                      </p>
                      <p className="text-lg font-bold text-blue-700 dark:text-blue-300 mt-1">
                        {fmt(global.caisse_reelle)} F
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">Cash ventes + paiements créances</p>
                    </CardContent>
                  </Card>
                  <Card className="border-l-4 border-l-purple-400">
                    <CardContent className="pt-4 pb-4 px-4">
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">
                        Argent théorique
                      </p>
                      <p className="text-lg font-bold text-purple-700 dark:text-purple-300 mt-1">
                        {fmt(global.argent_theorique)} F
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">Cash + créances restantes</p>
                    </CardContent>
                  </Card>
                  <Card className="border-l-4 border-l-amber-400">
                    <CardContent className="pt-4 pb-4 px-4">
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">
                        Créances clients
                      </p>
                      <p className="text-lg font-bold text-amber-700 dark:text-amber-300 mt-1">
                        {fmt(global.total_creances)} F
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">non encore encaissées</p>
                    </CardContent>
                  </Card>
                  <Card className="border-l-4 border-l-red-400">
                    <CardContent className="pt-4 pb-4 px-4">
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">
                        Dettes fourn.
                      </p>
                      <p className="text-lg font-bold text-red-600 dark:text-red-400 mt-1">
                        {fmt(global.total_dettes_fourn)} F
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">à payer aux fournisseurs</p>
                    </CardContent>
                  </Card>
                </div>
                {/* Montant fictif */}
                <div className={cn(
                  "rounded-lg border p-3 flex items-center justify-between gap-3",
                  mfPositif ? "border-emerald-200 bg-emerald-50 dark:bg-emerald-950/20" : "border-red-200 bg-red-50 dark:bg-red-950/20"
                )}>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Montant net attendu
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Cash encaissé + créances − dettes fournisseurs − dépenses
                    </p>
                  </div>
                  <p className={cn(
                    "text-2xl font-bold tabular-nums shrink-0",
                    mfPositif ? "text-emerald-700 dark:text-emerald-400" : "text-red-600"
                  )}>
                    {mfPositif ? "+" : ""}{fmt(global.montant_fictif)} F
                  </p>
                </div>
              </div>
            );
          })()}

          {/* ── Ventes par boutique ─────────────────────────────────────────── */}
          {ventesBoutiques.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
                <TrendingUp className="h-3.5 w-3.5 text-green-500" />
                Ventes par boutique
              </h2>
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full text-xs sm:text-sm">
                  <thead>
                    <tr className="border-b bg-muted/40">
                      <th className="text-left py-2 px-3 font-medium">Boutique</th>
                      <th className="text-right py-2 px-3 font-medium">Tickets</th>
                      <th className="text-right py-2 px-3 font-medium">Total ventes (FCFA)</th>
                      <th className="text-right py-2 px-3 font-medium">Cash (FCFA)</th>
                      <th className="text-right py-2 px-3 font-medium">Créances (FCFA)</th>
                      <th className="text-right py-2 px-3 font-medium hidden sm:table-cell">Mouture (FCFA)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ventesBoutiques.map((b) => (
                      <tr key={b.lieu_id} className="border-b hover:bg-muted/20">
                        <td className="py-1.5 px-3 font-medium">{b.lieu_nom}</td>
                        <td className="py-1.5 px-3 text-right text-muted-foreground">{b.nb_tickets}</td>
                        <td className="py-1.5 px-3 text-right font-semibold text-green-700 dark:text-green-400">
                          {fmt(b.total_ventes)}
                        </td>
                        <td className="py-1.5 px-3 text-right text-blue-700 dark:text-blue-400">
                          {fmt(b.caisse_reelle)}
                        </td>
                        <td className={cn(
                          "py-1.5 px-3 text-right",
                          parseFloat(b.total_creances) > 0 ? "text-amber-600 dark:text-amber-400 font-medium" : "text-muted-foreground"
                        )}>
                          {fmt(b.total_creances)}
                        </td>
                        <td className="py-1.5 px-3 text-right text-muted-foreground hidden sm:table-cell">
                          {parseFloat(b.total_mouture) > 0 ? fmt(b.total_mouture) : "—"}
                        </td>
                      </tr>
                    ))}
                    <tr className="bg-muted/30 font-semibold text-xs">
                      <td className="py-2 px-3">Total</td>
                      <td className="py-2 px-3 text-right">
                        {ventesBoutiques.reduce((s, b) => s + b.nb_tickets, 0)}
                      </td>
                      <td className="py-2 px-3 text-right text-green-700 dark:text-green-400">
                        {fmt(ventesBoutiques.reduce((s, b) => s + parseFloat(b.total_ventes), 0))}
                      </td>
                      <td className="py-2 px-3 text-right text-blue-700 dark:text-blue-400">
                        {fmt(ventesBoutiques.reduce((s, b) => s + parseFloat(b.caisse_reelle), 0))}
                      </td>
                      <td className="py-2 px-3 text-right text-amber-600 dark:text-amber-400">
                        {fmt(ventesBoutiques.reduce((s, b) => s + parseFloat(b.total_creances), 0))}
                      </td>
                      <td className="py-2 px-3 text-right text-muted-foreground hidden sm:table-cell">
                        {fmt(ventesBoutiques.reduce((s, b) => s + parseFloat(b.total_mouture), 0))}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── Collectes ────────────────────────────────────────────────────── */}
          {global && ((Array.isArray(global.collectes_par_boutique) && global.collectes_par_boutique.length > 0) || parseFloat(global.total_collecte_pris) > 0) && (() => {
            const totalPris   = parseFloat(global.total_collecte_pris);
            const totalLaisse = parseFloat(global.total_collecte_laisse);
            return (
              <div className="space-y-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
                  <Truck className="h-3.5 w-3.5 text-amber-500" />
                  Collectes argent (toutes boutiques)
                </h2>
                <div className="grid grid-cols-2 gap-3">
                  <Card className="border-l-4 border-l-blue-500">
                    <CardContent className="pt-4 pb-4 px-4">
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">Total prélevé</p>
                      <p className="text-lg font-bold text-blue-700 dark:text-blue-300 mt-1">{fmt(totalPris)} F</p>
                      <p className="text-xs text-muted-foreground mt-0.5">Argent collecté (retiré des boutiques)</p>
                    </CardContent>
                  </Card>
                  <Card className={cn("border-l-4", totalLaisse > 0 ? "border-l-amber-400" : "border-l-gray-300")}>
                    <CardContent className="pt-4 pb-4 px-4">
                      <p className="text-xs text-muted-foreground uppercase tracking-wide">Total laissé en boutique</p>
                      <p className={cn("text-lg font-bold mt-1", totalLaisse > 0 ? "text-amber-700 dark:text-amber-300" : "text-muted-foreground")}>
                        {fmt(totalLaisse)} F
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">Fonds restants cumulés</p>
                    </CardContent>
                  </Card>
                </div>
                {Array.isArray(global.collectes_par_boutique) && global.collectes_par_boutique.length > 0 && (
                  <div className="overflow-x-auto rounded-md border">
                    <table className="w-full text-xs sm:text-sm">
                      <thead>
                        <tr className="border-b bg-muted/40">
                          <th className="text-left py-2 px-3 font-medium">Boutique</th>
                          <th className="text-right py-2 px-3 font-medium">Prélevé (FCFA)</th>
                          <th className="text-right py-2 px-3 font-medium">Laissé (FCFA)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {global.collectes_par_boutique.map((row) => (
                          <tr key={row.lieu_id} className="border-b hover:bg-muted/20">
                            <td className="py-1.5 px-3">{row.lieu_nom}</td>
                            <td className="py-1.5 px-3 text-right font-medium text-blue-700 dark:text-blue-300">
                              {fmt(row.total_pris)}
                            </td>
                            <td className={cn(
                              "py-1.5 px-3 text-right font-medium",
                              parseFloat(row.total_laisse) > 0 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"
                            )}>
                              {fmt(row.total_laisse)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })()}

          {/* ── Résumé étendu (emprunts, projets) ───────────────────────────── */}
          {resume && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {[
                {
                  label: "Emprunts restants",
                  value: `${fmt(resume.total_emprunts_restants)} FCFA`,
                  icon: TrendingDown, iconClass: "text-red-500", border: "border-red-200",
                },
                {
                  label: "Projets en cours",
                  value: String(resume.projets_en_cours),
                  icon: FolderKanban, iconClass: "text-blue-600", border: "border-blue-200",
                },
                {
                  label: "Projets en dépassement",
                  value: String(resume.projets_en_depassement),
                  icon: DollarSign, iconClass: "text-orange-500", border: "border-orange-200",
                },
              ].map((kpi) => {
                const Icon = kpi.icon;
                return (
                  <Card key={kpi.label} className={kpi.border}>
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                      <CardTitle className="text-sm font-medium text-muted-foreground">
                        {kpi.label}
                      </CardTitle>
                      <Icon className={cn("h-5 w-5", kpi.iconClass)} />
                    </CardHeader>
                    <CardContent>
                      <p className="text-2xl font-bold">{kpi.value}</p>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
