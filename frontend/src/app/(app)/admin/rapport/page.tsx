"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

interface BoutiqueRapport {
  lieu_id: number; lieu_nom: string; nb_tickets: number;
  total_ventes: string; total_mouture: string; total_creances: string;
  cessions_recues_sacs: string; cessions_recues_montant: string;
  caisse_reelle: string; nb_produits_en_stock: number;
}
interface UsineRapport {
  lieu_id: number; lieu_nom: string; nb_achats: number; total_achats: string;
  transferts_boutiques_montant: string; transferts_inter_usines_montant: string; total_transferts_montant: string;
}
interface Ticket {
  id: number;
  lieu: number;
  lieu_nom?: string;
  numero: string;
  date: string;
  montant_total?: number | string;
  cout_mouture?: number | string;
  lignes: { quantite: string; prix_unitaire: string }[];
}
interface AchatMPSL { id: number; lieu_nom: string; produit_nom: string; quantite: string; unite: string; prix_unitaire: string; prix_total: string; fournisseur_nom: string | null; type_paiement_label: string; date: string; }
interface BilanData {
  total_ventes: string;
  total_achats_mpsl: string;
  total_depenses_operationnelles: string;
  total_charges: string;
  benefice_net: string;
  est_benefice: boolean;
  total_dettes_fournisseurs: string;
  nb_dettes_en_cours: number;
}

function fmt(v: string | number) { return Number(v).toLocaleString("fr-FR"); }
function ticketTotal(t: Ticket) {
  if (t.montant_total != null) return Number(t.montant_total);
  const produits = t.lignes.reduce((s, l) => s + Number(l.quantite) * Number(l.prix_unitaire), 0);
  return produits + Number(t.cout_mouture ?? 0);
}

function thisWeekRange() {
  const now = new Date();
  const day = (now.getDay() + 6) % 7;
  const debut = new Date(now); debut.setDate(now.getDate() - day);
  const fin = new Date(debut); fin.setDate(debut.getDate() + 6);
  return { debut: debut.toISOString().slice(0, 10), fin: fin.toISOString().slice(0, 10) };
}
function thisMonthRange() {
  const now = new Date();
  return {
    debut: new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10),
    fin: new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10),
  };
}

type Tab = "boutiques" | "usines" | "ventes" | "mpsl";

export default function AdminRapportPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("boutiques");
  const [debut, setDebut] = useState("");
  const [fin, setFin] = useState("");
  const [boutiques, setBoutiques] = useState<BoutiqueRapport[]>([]);
  const [usines, setUsines] = useState<UsineRapport[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [achatsMpsl, setAchatsMpsl] = useState<AchatMPSL[]>([]);
  const [bilan, setBilan] = useState<BilanData | null>(null);
  const [loading, setLoading] = useState(false);

  const buildQs = useCallback(() => {
    const p = new URLSearchParams();
    if (debut) p.set("debut", debut);
    if (fin) p.set("fin", fin);
    return p.toString() ? `?${p.toString()}` : "";
  }, [debut, fin]);

  const load = useCallback(async () => {
    setLoading(true);
    const qs = buildQs();
    try {
      interface Paginated<T> { results: T[] }
      const [b, u, t, bl, am] = await Promise.all([
        apiFetch<BoutiqueRapport[]>(`/comptable/rapport-boutiques/${qs}`),
        apiFetch<UsineRapport[]>(`/comptable/rapport-usines/${qs}`),
        apiFetch<Paginated<Ticket> | Ticket[]>(`/comptable/ventes/${qs}`),
        apiFetch<BilanData>(`/comptable/bilan/${qs}`),
        apiFetch<Paginated<AchatMPSL> | AchatMPSL[]>(`/mpsl/achats/${qs}`).catch(() => [] as AchatMPSL[]),
      ]);
      setBoutiques(b);
      setUsines(u);
      setTickets(Array.isArray(t) ? t : t.results);
      setBilan(bl);
      setAchatsMpsl(Array.isArray(am) ? am : (am as Paginated<AchatMPSL>).results);
    } catch { /* silencieux */ }
    finally { setLoading(false); }
  }, [buildQs]);

  useEffect(() => { load(); }, [load]);

  const applyPreset = (preset: "semaine" | "mois" | "tout") => {
    if (preset === "semaine") { const r = thisWeekRange(); setDebut(r.debut); setFin(r.fin); }
    else if (preset === "mois") { const r = thisMonthRange(); setDebut(r.debut); setFin(r.fin); }
    else { setDebut(""); setFin(""); }
  };

  const totalVentes = boutiques.reduce((s, b) => s + Number(b.total_ventes), 0);
  const totalMouture = boutiques.reduce((s, b) => s + Number(b.total_mouture ?? "0"), 0);
  const totalCreances = boutiques.reduce((s, b) => s + Number(b.total_creances ?? "0"), 0);
  const totalCaisse = boutiques.reduce((s, b) => s + Number(b.caisse_reelle ?? "0"), 0);
  const totalTransferts = usines.reduce((s, u) => s + Number(u.total_transferts_montant), 0);

  const detailUrl = (type: "boutiques" | "usines", id: number) => {
    const qs = buildQs();
    return `/admin/rapport/${type}/${id}${qs}`;
  };

  const beneficeNet = bilan ? Number(bilan.benefice_net) : 0;
  const estBenefice = bilan ? bilan.est_benefice : true;

  return (
    <div className="space-y-4 min-w-0">
      <h1 className="text-2xl font-semibold tracking-tight">Rapport général</h1>

      {/* Filtres */}
      <div className="flex flex-wrap items-center gap-2 p-3 rounded-lg border bg-card">
        <div className="flex gap-1 flex-wrap">
          {(["semaine", "mois", "tout"] as const).map((p) => (
            <button key={p} onClick={() => applyPreset(p)} className="px-3 py-1.5 text-xs font-medium rounded-md border hover:bg-muted transition-colors">
              {p === "semaine" ? "Cette semaine" : p === "mois" ? "Ce mois" : "Tout"}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input type="date" value={debut} onChange={(e) => setDebut(e.target.value)} className="h-8 rounded-md border border-input bg-background px-2 text-xs" />
          <span className="text-xs text-muted-foreground">→</span>
          <input type="date" value={fin} onChange={(e) => setFin(e.target.value)} className="h-8 rounded-md border border-input bg-background px-2 text-xs" />
        </div>
        {loading && <span className="text-xs text-muted-foreground">Chargement…</span>}
      </div>

      {/* Bilan financier */}
      {bilan && (
        <div className="rounded-lg border bg-card p-4 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h2 className="text-base font-semibold">Bilan financier</h2>
            <span className={cn(
              "inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-semibold",
              estBenefice
                ? "bg-green-100 text-green-700 dark:bg-green-950/50 dark:text-green-400"
                : "bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-400"
            )}>
              {estBenefice ? "✓ Bénéfice" : "✗ Perte"}
            </span>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="rounded-lg border border-l-4 border-l-green-500 bg-green-50 dark:bg-green-950/20 p-3">
              <p className="text-xs text-muted-foreground">Revenus (ventes)</p>
              <p className="text-lg font-bold text-green-700 dark:text-green-400">{fmt(bilan.total_ventes)}</p>
              <p className="text-xs text-muted-foreground">dont mouture : {fmt(totalMouture)} F</p>
            </div>
            <div className="rounded-lg border border-l-4 border-l-orange-500 bg-orange-50 dark:bg-orange-950/20 p-3">
              <p className="text-xs text-muted-foreground">Achats MPSL (matières)</p>
              <p className="text-lg font-bold text-orange-700 dark:text-orange-400">{fmt(bilan.total_achats_mpsl)}</p>
              <p className="text-xs text-muted-foreground">coût d&apos;achat fournisseurs</p>
            </div>
            <div className="rounded-lg border border-l-4 border-l-red-400 bg-red-50 dark:bg-red-950/20 p-3">
              <p className="text-xs text-muted-foreground">Charges opér.</p>
              <p className="text-lg font-bold text-red-600 dark:text-red-400">{fmt(bilan.total_depenses_operationnelles)}</p>
              <p className="text-xs text-muted-foreground">dépenses de fonctionnement</p>
            </div>
            <div className={cn(
              "rounded-lg border border-l-4 p-3",
              estBenefice
                ? "border-l-green-600 bg-green-50 dark:bg-green-950/20"
                : "border-l-red-600 bg-red-50 dark:bg-red-950/20"
            )}>
              <p className="text-xs text-muted-foreground">Bénéfice net</p>
              <p className={cn(
                "text-lg font-bold",
                estBenefice ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"
              )}>
                {estBenefice ? "+" : ""}{fmt(beneficeNet)}
              </p>
              <p className="text-xs text-muted-foreground">ventes − achats MPSL − dépenses</p>
            </div>
          </div>
          {/* Dettes fournisseurs en cours */}
          {bilan.nb_dettes_en_cours > 0 && (
            <div className="rounded-lg border border-l-4 border-l-red-500 bg-red-50 dark:bg-red-950/20 p-3">
              <p className="text-xs text-muted-foreground">
                Dettes fournisseurs en cours — {bilan.nb_dettes_en_cours} dette{bilan.nb_dettes_en_cours > 1 ? "s" : ""} non soldée{bilan.nb_dettes_en_cours > 1 ? "s" : ""}
              </p>
              <p className="text-lg font-bold text-red-700 dark:text-red-400">{fmt(bilan.total_dettes_fournisseurs)} F</p>
              <p className="text-xs text-muted-foreground">montants restants à payer aux fournisseurs MPSL</p>
            </div>
          )}
          {/* Créances clients en cours */}
          {totalCreances > 0 && (
            <div className="rounded-lg border border-l-4 border-l-amber-400 bg-amber-50 dark:bg-amber-950/20 p-3">
              <p className="text-xs text-muted-foreground">Créances clients en cours (toutes boutiques)</p>
              <p className="text-lg font-bold text-amber-700 dark:text-amber-400">{fmt(totalCreances)} F</p>
              <p className="text-xs text-muted-foreground">montants non encore encaissés</p>
            </div>
          )}
        </div>
      )}

      {/* Cartes */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="rounded-lg border border-l-4 border-l-green-500 bg-card p-4">
          <p className="text-xs text-muted-foreground">CA boutiques</p>
          <p className="text-xl font-bold text-green-700 dark:text-green-400">{fmt(totalVentes)} <span className="text-sm font-normal text-muted-foreground">FCFA</span></p>
        </div>
        <div className="rounded-lg border border-l-4 border-l-blue-500 bg-card p-4">
          <p className="text-xs text-muted-foreground">Cash encaissé (toutes boutiques)</p>
          <p className="text-xl font-bold text-blue-700 dark:text-blue-400">{fmt(totalCaisse)} <span className="text-sm font-normal text-muted-foreground">FCFA</span></p>
        </div>
        <div className="rounded-lg border border-l-4 border-l-orange-500 bg-card p-4">
          <p className="text-xs text-muted-foreground">Achats MPSL</p>
          <p className="text-xl font-bold text-orange-700 dark:text-orange-400">{fmt(bilan?.total_achats_mpsl ?? 0)} <span className="text-sm font-normal text-muted-foreground">FCFA</span></p>
        </div>
        <div className="rounded-lg border border-l-4 border-l-green-500 bg-card p-4">
          <p className="text-xs text-muted-foreground">Valeur transferts</p>
          <p className="text-xl font-bold text-green-700 dark:text-green-400">{fmt(totalTransferts)} <span className="text-sm font-normal text-muted-foreground">FCFA</span></p>
        </div>
      </div>

      {/* Tabs */}
      <div className="scrollbar-hidden flex gap-1 border-b overflow-x-auto">
        {([["boutiques", "Boutiques"], ["usines", "Usines"], ["ventes", "Ventes détail"], ["mpsl", "Achats MPSL"]] as [Tab, string][]).map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)} className={cn("px-4 py-2 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors", tab === t ? "border-green-600 text-green-600 dark:border-green-400 dark:text-green-400" : "border-transparent text-muted-foreground hover:text-foreground")}>
            {label}
          </button>
        ))}
      </div>

      {tab === "boutiques" && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs sm:text-sm min-w-[960px]">
            <thead><tr className="border-b bg-muted/40">
              <th className="text-left py-2 px-3">Boutique</th>
              <th className="text-right py-2 px-3">Tickets</th>
              <th className="text-right py-2 px-3">Ventes totales</th>
              <th className="text-right py-2 px-3">Cash encaissé</th>
              <th className="text-right py-2 px-3">Créances en cours</th>
              <th className="text-right py-2 px-3">Stock (produits)</th>
              <th className="text-right py-2 px-3">Cessions (sacs)</th>
              <th className="py-2 px-3"></th>
            </tr></thead>
            <tbody>
              {boutiques.length === 0 && <tr><td colSpan={8} className="py-6 text-center text-muted-foreground">Aucune donnée.</td></tr>}
              {boutiques.map((b) => (
                <tr key={b.lieu_id} className="border-b hover:bg-muted/20 cursor-pointer" onClick={() => router.push(detailUrl("boutiques", b.lieu_id))}>
                  <td className="py-2 px-3 font-medium">{b.lieu_nom}</td>
                  <td className="py-2 px-3 text-right">{b.nb_tickets}</td>
                  <td className="py-2 px-3 text-right font-medium text-green-700 dark:text-green-400">{fmt(b.total_ventes)} F</td>
                  <td className="py-2 px-3 text-right font-medium text-blue-700 dark:text-blue-400">{fmt(b.caisse_reelle ?? "0")} F</td>
                  <td className="py-2 px-3 text-right text-amber-600 dark:text-amber-400">{fmt(b.total_creances ?? "0")} F</td>
                  <td className="py-2 px-3 text-right">{b.nb_produits_en_stock ?? 0}</td>
                  <td className="py-2 px-3 text-right">{fmt(b.cessions_recues_sacs)}</td>
                  <td className="py-2 px-3 text-right text-xs text-green-600 dark:text-green-400">Détail →</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "usines" && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs sm:text-sm min-w-[600px]">
            <thead><tr className="border-b bg-muted/40">
              <th className="text-left py-2 px-3">Usine</th>
              <th className="text-right py-2 px-3">Vers boutiques (FCFA)</th>
              <th className="text-right py-2 px-3">Inter-usines (FCFA)</th>
              <th className="text-right py-2 px-3">Total transferts (FCFA)</th>
              <th className="py-2 px-3"></th>
            </tr></thead>
            <tbody>
              {usines.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-muted-foreground">Aucune donnée.</td></tr>}
              {usines.map((u) => (
                <tr key={u.lieu_id} className="border-b hover:bg-muted/20 cursor-pointer" onClick={() => router.push(detailUrl("usines", u.lieu_id))}>
                  <td className="py-2 px-3 font-medium">{u.lieu_nom}</td>
                  <td className="py-2 px-3 text-right">{fmt(u.transferts_boutiques_montant)}</td>
                  <td className="py-2 px-3 text-right">{fmt(u.transferts_inter_usines_montant)}</td>
                  <td className="py-2 px-3 text-right font-medium text-green-700 dark:text-green-400">{fmt(u.total_transferts_montant)}</td>
                  <td className="py-2 px-3 text-right text-xs text-green-600 dark:text-green-400">Détail →</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "ventes" && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs sm:text-sm min-w-[480px]">
            <thead><tr className="border-b bg-muted/40">
              <th className="text-left py-2 px-3">N°</th>
              <th className="text-left py-2 px-3">Boutique</th>
              <th className="text-left py-2 px-3">Date</th>
              <th className="text-right py-2 px-3">Total (FCFA)</th>
            </tr></thead>
            <tbody>
              {tickets.length === 0 && <tr><td colSpan={4} className="py-6 text-center text-muted-foreground">Aucune vente.</td></tr>}
              {tickets.map((t) => (
                <tr key={t.id} className="border-b hover:bg-muted/20">
                  <td className="py-1.5 px-3 font-mono">{t.numero}</td>
                  <td className="py-1.5 px-3">{(t as unknown as Record<string, string>)["lieu_nom"] ?? String(t.lieu)}</td>
                  <td className="py-1.5 px-3 text-muted-foreground">{new Date(t.date).toLocaleDateString("fr-FR")}</td>
                  <td className="py-1.5 px-3 text-right font-medium text-green-700 dark:text-green-400">{fmt(ticketTotal(t))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "mpsl" && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs sm:text-sm min-w-[700px]">
            <thead><tr className="border-b bg-muted/40">
              <th className="text-left py-2 px-3">Date</th>
              <th className="text-left py-2 px-3">Dépôt</th>
              <th className="text-left py-2 px-3">Produit</th>
              <th className="text-right py-2 px-3">Qté</th>
              <th className="text-left py-2 px-3">Unité</th>
              <th className="text-right py-2 px-3">Prix unit.</th>
              <th className="text-right py-2 px-3">Total (FCFA)</th>
              <th className="text-left py-2 px-3">Fournisseur</th>
              <th className="text-left py-2 px-3">Paiement</th>
            </tr></thead>
            <tbody>
              {achatsMpsl.length === 0 && <tr><td colSpan={9} className="py-6 text-center text-muted-foreground">Aucun achat MPSL.</td></tr>}
              {achatsMpsl.map((a) => (
                <tr key={a.id} className="border-b hover:bg-muted/20">
                  <td className="py-1.5 px-3 text-muted-foreground">{new Date(a.date).toLocaleDateString("fr-FR")}</td>
                  <td className="py-1.5 px-3">{a.lieu_nom}</td>
                  <td className="py-1.5 px-3 font-medium">{a.produit_nom}</td>
                  <td className="py-1.5 px-3 text-right">{Number(a.quantite).toLocaleString("fr-FR")}</td>
                  <td className="py-1.5 px-3">{a.unite}</td>
                  <td className="py-1.5 px-3 text-right text-muted-foreground">{fmt(a.prix_unitaire)}</td>
                  <td className="py-1.5 px-3 text-right font-medium text-orange-700 dark:text-orange-400">{fmt(a.prix_total)}</td>
                  <td className="py-1.5 px-3">{a.fournisseur_nom ?? "—"}</td>
                  <td className="py-1.5 px-3 text-muted-foreground">{a.type_paiement_label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
