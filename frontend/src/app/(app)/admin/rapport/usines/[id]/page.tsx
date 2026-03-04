"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";

interface Achat { id: number; produit_nom: string; quantite: string; unite: string; prix_total: string; date: string }
interface Cession { id: number; lot_nom: string; produit_nom: string; boutique_nom: string; quantite_sacs: string; prix_par_sac: string; montant_cession: string; created_at: string }
interface InterUsine { id: number; lot_nom: string; produit_nom: string; usine_source_nom: string; usine_destination_nom: string; quantite_sacs: string; prix_par_sac: string; montant_transfert: string; created_at: string }
interface DetailUsine {
  lieu_id: number; lieu_nom: string;
  total_achats: string; total_transferts_boutiques: string; total_transferts_inter_usines_sortants: string; total_transferts: string;
  achats: Achat[]; cessions_vers_boutiques: Cession[];
  transferts_inter_usines_sortants: InterUsine[]; transferts_inter_usines_entrants: InterUsine[];
}

function fmt(v: string | number) { return Number(v).toLocaleString("fr-FR"); }
type Tab = "achats" | "boutiques" | "inter_sortants" | "inter_entrants";

export default function AdminDetailUsinePage() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [data, setData] = useState<DetailUsine | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState<Tab>("achats");

  const debut = searchParams.get("debut") ?? "";
  const fin = searchParams.get("fin") ?? "";

  useEffect(() => {
    const qs = new URLSearchParams();
    if (debut) qs.set("debut", debut);
    if (fin) qs.set("fin", fin);
    const q = qs.toString() ? `?${qs.toString()}` : "";
    apiFetch(`/comptable/rapport-usines/${id}/${q}`)
      .then((d) => setData(d as DetailUsine))
      .catch((e) => setErr(e instanceof Error ? e.message : "Erreur"))
      .finally(() => setLoading(false));
  }, [id, debut, fin]);

  if (loading) return <div className="p-6 text-muted-foreground">Chargement…</div>;
  if (err) return <div className="p-6 text-destructive">{err}</div>;
  if (!data) return null;

  const periode = debut && fin ? `${debut} → ${fin}` : debut ? `depuis ${debut}` : fin ? `jusqu'au ${fin}` : "toute période";
  const tabs: [Tab, string, number][] = [
    ["achats", "Achats", data.achats.length],
    ["boutiques", "Vers boutiques", data.cessions_vers_boutiques.length],
    ["inter_sortants", "Inter-usines sortants", data.transferts_inter_usines_sortants.length],
    ["inter_entrants", "Inter-usines entrants", data.transferts_inter_usines_entrants.length],
  ];

  return (
    <div className="space-y-6 min-w-0">
      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={() => router.back()} className="text-sm text-muted-foreground hover:text-foreground">← Retour</button>
        <h1 className="text-2xl font-semibold tracking-tight">{data.lieu_nom}</h1>
        <span className="text-sm text-muted-foreground">{periode}</span>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="rounded-lg border border-l-4 border-l-orange-500 bg-orange-50 dark:bg-orange-950/20 p-4">
          <p className="text-xs text-muted-foreground">Total achats</p>
          <p className="text-lg font-bold text-orange-700 dark:text-orange-400">{fmt(data.total_achats)} <span className="text-xs font-normal text-muted-foreground">FCFA</span></p>
        </div>
        <div className="rounded-lg border border-l-4 border-l-green-500 bg-green-50 dark:bg-green-950/20 p-4">
          <p className="text-xs text-muted-foreground">→ Boutiques</p>
          <p className="text-lg font-bold text-green-700 dark:text-green-400">{fmt(data.total_transferts_boutiques)} <span className="text-xs font-normal text-muted-foreground">FCFA</span></p>
        </div>
        <div className="rounded-lg border border-l-4 border-l-purple-500 bg-purple-50 dark:bg-purple-950/20 p-4">
          <p className="text-xs text-muted-foreground">Inter-usines</p>
          <p className="text-lg font-bold text-purple-700 dark:text-purple-400">{fmt(data.total_transferts_inter_usines_sortants)} <span className="text-xs font-normal text-muted-foreground">FCFA</span></p>
        </div>
        <div className="rounded-lg border border-l-4 border-l-slate-500 bg-slate-50 dark:bg-slate-950/20 p-4">
          <p className="text-xs text-muted-foreground">Total transferts</p>
          <p className="text-lg font-bold text-slate-700 dark:text-slate-300">{fmt(data.total_transferts)} <span className="text-xs font-normal text-muted-foreground">FCFA</span></p>
        </div>
      </div>
      <div className="scrollbar-hidden flex gap-1 border-b overflow-x-auto">
        {tabs.map(([t, label, count]) => (
          <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${tab === t ? "border-green-600 text-green-600 dark:border-green-400 dark:text-green-400" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {label} ({count})
          </button>
        ))}
      </div>

      {tab === "achats" && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs sm:text-sm min-w-[480px]">
            <thead><tr className="border-b bg-muted/40">
              <th className="text-left py-2 px-3">Date</th><th className="text-left py-2 px-3">Produit</th>
              <th className="text-right py-2 px-3">Qté</th><th className="text-left py-2 px-3">Unité</th><th className="text-right py-2 px-3">Total (FCFA)</th>
            </tr></thead>
            <tbody>
              {data.achats.length === 0 && <tr><td colSpan={5} className="py-4 text-center text-muted-foreground">Aucun achat.</td></tr>}
              {data.achats.map((a) => (
                <tr key={a.id} className="border-b hover:bg-muted/20">
                  <td className="py-1.5 px-3 text-muted-foreground">{new Date(a.date).toLocaleDateString("fr-FR")}</td>
                  <td className="py-1.5 px-3">{a.produit_nom}</td>
                  <td className="py-1.5 px-3 text-right">{fmt(a.quantite)}</td>
                  <td className="py-1.5 px-3">{a.unite}</td>
                  <td className="py-1.5 px-3 text-right font-medium text-orange-700 dark:text-orange-400">{fmt(a.prix_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "boutiques" && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs sm:text-sm min-w-[640px]">
            <thead><tr className="border-b bg-muted/40">
              <th className="text-left py-2 px-3">Lot</th><th className="text-left py-2 px-3">Produit</th><th className="text-left py-2 px-3">Boutique</th>
              <th className="text-right py-2 px-3">Sacs</th><th className="text-right py-2 px-3">Prix/sac</th><th className="text-right py-2 px-3">Montant (FCFA)</th><th className="text-left py-2 px-3">Date</th>
            </tr></thead>
            <tbody>
              {data.cessions_vers_boutiques.length === 0 && <tr><td colSpan={7} className="py-4 text-center text-muted-foreground">Aucune cession.</td></tr>}
              {data.cessions_vers_boutiques.map((c) => (
                <tr key={c.id} className="border-b hover:bg-muted/20">
                  <td className="py-1.5 px-3 font-mono">{c.lot_nom}</td><td className="py-1.5 px-3">{c.produit_nom}</td><td className="py-1.5 px-3">{c.boutique_nom}</td>
                  <td className="py-1.5 px-3 text-right">{fmt(c.quantite_sacs)}</td><td className="py-1.5 px-3 text-right">{fmt(c.prix_par_sac)}</td>
                  <td className="py-1.5 px-3 text-right font-medium text-green-700 dark:text-green-400">{fmt(c.montant_cession)}</td>
                  <td className="py-1.5 px-3 text-muted-foreground">{new Date(c.created_at).toLocaleDateString("fr-FR")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(tab === "inter_sortants" || tab === "inter_entrants") && (() => {
        const rows = tab === "inter_sortants" ? data.transferts_inter_usines_sortants : data.transferts_inter_usines_entrants;
        const dir = tab === "inter_sortants" ? "sortant" : "entrant";
        return (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-xs sm:text-sm min-w-[640px]">
              <thead><tr className="border-b bg-muted/40">
                <th className="text-left py-2 px-3">Lot</th><th className="text-left py-2 px-3">Produit</th>
                <th className="text-left py-2 px-3">{dir === "sortant" ? "Destination" : "Source"}</th>
                <th className="text-right py-2 px-3">Sacs</th><th className="text-right py-2 px-3">Prix/sac</th><th className="text-right py-2 px-3">Montant (FCFA)</th><th className="text-left py-2 px-3">Date</th>
              </tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={7} className="py-4 text-center text-muted-foreground">Aucun transfert.</td></tr>}
                {rows.map((r) => (
                  <tr key={r.id} className="border-b hover:bg-muted/20">
                    <td className="py-1.5 px-3 font-mono">{r.lot_nom}</td><td className="py-1.5 px-3">{r.produit_nom}</td>
                    <td className="py-1.5 px-3">{dir === "sortant" ? r.usine_destination_nom : r.usine_source_nom}</td>
                    <td className="py-1.5 px-3 text-right">{fmt(r.quantite_sacs)}</td><td className="py-1.5 px-3 text-right">{fmt(r.prix_par_sac)}</td>
                    <td className="py-1.5 px-3 text-right font-medium text-purple-700 dark:text-purple-400">{fmt(r.montant_transfert)}</td>
                    <td className="py-1.5 px-3 text-muted-foreground">{new Date(r.created_at).toLocaleDateString("fr-FR")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })()}
    </div>
  );
}
