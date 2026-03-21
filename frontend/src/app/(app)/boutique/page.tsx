"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
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
  argent_theorique: string;
  montant_fictif: string;
  total_depenses: string;
  nb_produits_en_stock: number;
  total_mouture: string;
  total_ventes_produits: string;
  derniere_collecte: DerniereCollecte | null;
}

export default function BoutiqueDashboardPage() {
  const { user } = useAuth();
  const lieuNom = user?.lieu?.nom ?? "Boutique";
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [erreur, setErreur] = useState("");

  const charger = useCallback(async () => {
    try {
      setLoading(true);
      setErreur("");
      const res = await apiFetch<DashboardData>("/boutique/dashboard/");
      setData(res);
    } catch {
      setErreur("Impossible de charger le tableau de bord.");
    } finally {
      setLoading(false);
    }
  }, []);

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
  const at   = parseFloat(data.argent_theorique);
  const mf   = parseFloat(data.montant_fictif || "0");
  const dep  = parseFloat(data.total_depenses);
  const mout = parseFloat(data.total_mouture || "0");
  const tvp  = parseFloat(data.total_ventes_produits || "0");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Store className="h-6 w-6 text-green-600" />
            Tableau de bord — {lieuNom}
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Synthèse financière de votre boutique
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={charger}>
          <RefreshCw className="h-4 w-4 mr-2" /> Actualiser
        </Button>
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
            <p className="text-xs text-muted-foreground mt-0.5">FCFA enregistrés (encaissé + crédit)</p>
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
              Caisse réelle
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">{fmt(cais)}</p>
            <p className="text-xs text-muted-foreground mt-0.5">FCFA encaissés</p>
            <p className="text-xs text-muted-foreground mt-1">
              Cash ventes + paiements créances
            </p>
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
              className="text-xs text-blue-600 hover:underline mt-1 block"
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

      {/* Dernière collecte */}
      {data.derniere_collecte && (() => {
        const dc = data.derniere_collecte!;
        const laisse = parseFloat(dc.montant_laisse);
        return (
          <Card className={laisse > 0 ? "border-l-4 border-l-amber-400" : "border-l-4 border-l-gray-300"}>
            <CardHeader className="pb-1 pt-4 px-4">
              <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                <Truck className="h-3.5 w-3.5 text-amber-500" />
                Dernier passage collectionneur
                <span className="ml-auto font-normal normal-case text-xs">
                  {new Date(dc.date).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" })}
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
      <div className="flex flex-wrap gap-3">
        <Button asChild className="bg-green-600 hover:bg-green-700">
          <Link href="/boutique/caisse">Aller à la caisse</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/boutique/creances">Gérer les créances</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/boutique/tickets">Voir les tickets</Link>
        </Button>
      </div>
    </div>
  );
}
