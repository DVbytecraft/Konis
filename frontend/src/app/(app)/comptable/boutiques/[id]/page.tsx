"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";

interface LigneVente { quantite: string; prix_unitaire: string; produit?: { nom: string } }
interface Ticket {
  id: number;
  numero: string;
  date: string;
  montant_total?: number | string;
  cout_mouture?: number | string;
  lignes: LigneVente[];
}
interface Cession {
  id: number;
  lot_nom: string;
  produit_nom: string;
  usine_source_nom?: string;
  quantite_sacs: string;
  prix_par_sac: string;
  montant_cession: string;
  created_at: string;
}
interface StockItem { produit_nom: string; produit_code: string; quantite: string }
interface CreanceItem { id: number; client_nom: string; montant_initial: string; montant_paye: string; montant_restant: string }
interface CollecteItem { date: string; montant_trouve: string; montant_pris: string; montant_laisse: string; collecteur: string | null }
interface DetailBoutique {
  lieu_id: number;
  lieu_nom: string;
  total_ventes: string;
  total_ventes_produits: string;
  total_mouture: string;
  total_cash: string;
  total_credit: string;
  total_creances: string;
  total_cessions_recues: string;
  tickets: Ticket[];
  cessions_recues: Cession[];
  stock: StockItem[];
  creances_en_cours: CreanceItem[];
  collectes_recentes: CollecteItem[];
}

function fmt(v: string | number) { return Number(v).toLocaleString("fr-FR"); }
function ticketTotal(t: Ticket) {
  if (t.montant_total != null) return Number(t.montant_total);
  const produits = t.lignes.reduce((s, l) => s + Number(l.quantite) * Number(l.prix_unitaire), 0);
  return produits + Number(t.cout_mouture ?? 0);
}

export default function DetailBoutiquePage() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [data, setData] = useState<DetailBoutique | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const debut = searchParams.get("debut") ?? "";
  const fin = searchParams.get("fin") ?? "";

  useEffect(() => {
    const qs = new URLSearchParams();
    if (debut) qs.set("debut", debut);
    if (fin) qs.set("fin", fin);
    const q = qs.toString() ? `?${qs.toString()}` : "";
    apiFetch(`/comptable/rapport-boutiques/${id}/${q}`)
      .then((d) => setData(d as DetailBoutique))
      .catch((e) => setErr(e instanceof Error ? e.message : "Erreur"))
      .finally(() => setLoading(false));
  }, [id, debut, fin]);

  if (loading) return <div className="p-6 text-muted-foreground">Chargement…</div>;
  if (err) return <div className="p-6 text-destructive">{err}</div>;
  if (!data) return null;

  const periode = debut && fin ? `${debut} → ${fin}` : debut ? `depuis ${debut}` : fin ? `jusqu'au ${fin}` : "toute période";

  return (
    <div className="space-y-6 min-w-0">
      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={() => router.back()} className="text-sm text-muted-foreground hover:text-foreground">← Retour</button>
        <h1 className="text-2xl font-semibold tracking-tight">{data.lieu_nom}</h1>
        <span className="text-sm text-muted-foreground">{periode}</span>
      </div>

      {/* KPIs ventes */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="rounded-lg border border-l-4 border-l-green-500 bg-green-50 dark:bg-green-950/20 p-4">
          <p className="text-xs text-muted-foreground">CA ventes total</p>
          <p className="text-xl font-bold text-green-700 dark:text-green-400">{fmt(data.total_ventes)} <span className="text-sm font-normal text-muted-foreground">F</span></p>
          <p className="text-xs text-muted-foreground mt-1">Cash : {fmt(data.total_cash)} · Crédit : {fmt(data.total_credit)}</p>
        </div>
        {parseFloat(data.total_mouture) > 0 && (
          <div className="rounded-lg border border-l-4 border-l-teal-400 p-4">
            <p className="text-xs text-muted-foreground">dont Mouture</p>
            <p className="text-xl font-bold text-teal-700 dark:text-teal-300">{fmt(data.total_mouture)} <span className="text-sm font-normal text-muted-foreground">F</span></p>
            <p className="text-xs text-muted-foreground mt-1">Produits : {fmt(data.total_ventes_produits)} F</p>
          </div>
        )}
        <div className="rounded-lg border border-l-4 border-l-amber-400 p-4">
          <p className="text-xs text-muted-foreground">Créances en cours</p>
          <p className="text-xl font-bold text-amber-700 dark:text-amber-300">{fmt(data.total_creances)} <span className="text-sm font-normal text-muted-foreground">F</span></p>
        </div>
        <div className="rounded-lg border border-l-4 border-l-blue-400 p-4">
          <p className="text-xs text-muted-foreground">Cessions reçues</p>
          <p className="text-xl font-bold text-blue-700 dark:text-blue-300">{fmt(data.total_cessions_recues)} <span className="text-sm font-normal text-muted-foreground">F</span></p>
        </div>
      </div>

      {/* Stock actuel */}
      {data.stock.length > 0 && (
        <div>
          <h2 className="text-base font-semibold mb-2">Stock actuel ({data.stock.length} produits)</h2>
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-xs sm:text-sm">
              <thead><tr className="border-b bg-muted/40">
                <th className="text-left py-2 px-3">Produit</th>
                <th className="text-left py-2 px-3">Code</th>
                <th className="text-right py-2 px-3">Quantité</th>
              </tr></thead>
              <tbody>
                {data.stock.map((s, i) => (
                  <tr key={i} className="border-b hover:bg-muted/20">
                    <td className="py-1.5 px-3">{s.produit_nom}</td>
                    <td className="py-1.5 px-3 font-mono text-muted-foreground">{s.produit_code || "—"}</td>
                    <td className="py-1.5 px-3 text-right font-medium">{fmt(s.quantite)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Créances en cours */}
      {data.creances_en_cours.length > 0 && (
        <div>
          <h2 className="text-base font-semibold mb-2">Créances en cours ({data.creances_en_cours.length})</h2>
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-xs sm:text-sm">
              <thead><tr className="border-b bg-muted/40">
                <th className="text-left py-2 px-3">Client</th>
                <th className="text-right py-2 px-3">Montant initial</th>
                <th className="text-right py-2 px-3">Déjà payé</th>
                <th className="text-right py-2 px-3">Restant</th>
              </tr></thead>
              <tbody>
                {data.creances_en_cours.map((c) => (
                  <tr key={c.id} className="border-b hover:bg-muted/20">
                    <td className="py-1.5 px-3">{c.client_nom}</td>
                    <td className="py-1.5 px-3 text-right">{fmt(c.montant_initial)}</td>
                    <td className="py-1.5 px-3 text-right text-green-600">{fmt(c.montant_paye)}</td>
                    <td className="py-1.5 px-3 text-right font-bold text-amber-600 dark:text-amber-400">{fmt(c.montant_restant)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Collectes récentes */}
      {data.collectes_recentes.length > 0 && (
        <div>
          <h2 className="text-base font-semibold mb-2">Collectes récentes</h2>
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-xs sm:text-sm">
              <thead><tr className="border-b bg-muted/40">
                <th className="text-left py-2 px-3">Date</th>
                <th className="text-right py-2 px-3">Trouvé</th>
                <th className="text-right py-2 px-3">Prélevé</th>
                <th className="text-right py-2 px-3">Laissé</th>
                <th className="text-left py-2 px-3">Collecteur</th>
              </tr></thead>
              <tbody>
                {data.collectes_recentes.map((c, i) => (
                  <tr key={i} className="border-b hover:bg-muted/20">
                    <td className="py-1.5 px-3 text-muted-foreground">{new Date(c.date).toLocaleDateString("fr-FR")}</td>
                    <td className="py-1.5 px-3 text-right">{fmt(c.montant_trouve)}</td>
                    <td className="py-1.5 px-3 text-right text-blue-700 dark:text-blue-300 font-medium">{fmt(c.montant_pris)}</td>
                    <td className={`py-1.5 px-3 text-right font-bold ${parseFloat(c.montant_laisse) > 0 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"}`}>
                      {fmt(c.montant_laisse)}
                    </td>
                    <td className="py-1.5 px-3 text-muted-foreground">{c.collecteur ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tickets */}
      <div>
        <h2 className="text-base font-semibold mb-2">Ventes ({data.tickets.length} tickets)</h2>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs sm:text-sm min-w-[480px]">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="text-left py-2 px-3">N°</th>
                <th className="text-left py-2 px-3">Date</th>
                <th className="text-right py-2 px-3">Total (FCFA)</th>
              </tr>
            </thead>
            <tbody>
              {data.tickets.length === 0 && <tr><td colSpan={3} className="py-4 text-center text-muted-foreground">Aucune vente.</td></tr>}
              {data.tickets.map((t) => (
                <tr key={t.id} className="border-b hover:bg-muted/20">
                  <td className="py-1.5 px-3 font-mono">{t.numero}</td>
                  <td className="py-1.5 px-3 text-muted-foreground">{new Date(t.date).toLocaleString("fr-FR")}</td>
                  <td className="py-1.5 px-3 text-right font-medium text-green-700 dark:text-green-400">{fmt(ticketTotal(t))}</td>
                </tr>
              ))}
              {data.tickets.length > 0 && (
                <tr className="bg-green-50 dark:bg-green-950/20 font-semibold">
                  <td colSpan={2} className="py-2 px-3">Total</td>
                  <td className="py-2 px-3 text-right text-green-700 dark:text-green-400">{fmt(data.total_ventes)}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cessions */}
      <div>
        <h2 className="text-base font-semibold mb-2">Cessions reçues ({data.cessions_recues.length})</h2>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs sm:text-sm min-w-[640px]">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="text-left py-2 px-3">Lot</th>
                <th className="text-left py-2 px-3">Produit</th>
                <th className="text-right py-2 px-3">Sacs</th>
                <th className="text-right py-2 px-3">Prix/sac</th>
                <th className="text-right py-2 px-3">Montant (FCFA)</th>
                <th className="text-left py-2 px-3">Date</th>
              </tr>
            </thead>
            <tbody>
              {data.cessions_recues.length === 0 && <tr><td colSpan={6} className="py-4 text-center text-muted-foreground">Aucune cession reçue.</td></tr>}
              {data.cessions_recues.map((c) => (
                <tr key={c.id} className="border-b hover:bg-muted/20">
                  <td className="py-1.5 px-3 font-mono">{c.lot_nom}</td>
                  <td className="py-1.5 px-3">{c.produit_nom}</td>
                  <td className="py-1.5 px-3 text-right">{fmt(c.quantite_sacs)}</td>
                  <td className="py-1.5 px-3 text-right">{fmt(c.prix_par_sac)}</td>
                  <td className="py-1.5 px-3 text-right font-medium text-green-700 dark:text-green-400">{fmt(c.montant_cession)}</td>
                  <td className="py-1.5 px-3 text-muted-foreground">{new Date(c.created_at).toLocaleDateString("fr-FR")}</td>
                </tr>
              ))}
              {data.cessions_recues.length > 0 && (
                <tr className="bg-green-50 dark:bg-green-950/20 font-semibold">
                  <td colSpan={4} className="py-2 px-3">Total</td>
                  <td className="py-2 px-3 text-right text-green-700 dark:text-green-400">{fmt(data.total_cessions_recues)}</td>
                  <td />
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
