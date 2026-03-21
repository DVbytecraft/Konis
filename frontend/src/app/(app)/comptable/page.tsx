"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

// ---- Types ----
interface BoutiqueRapport {
  lieu_id: number;
  lieu_nom: string;
  nb_tickets: number;
  total_ventes: string;
  total_mouture: string;
  total_creances: string;
  cessions_recues_sacs: string;
  cessions_recues_montant: string;
  caisse_reelle: string;
  nb_produits_en_stock: number;
}

interface MPSLRapport {
  lieu_id: number;
  lieu_nom: string;
  nb_achats: number;
  total_achats: string;
  nb_dettes_en_cours: number;
  total_dettes: string;
}

interface Ticket {
  id: number;
  lieu: number;
  lieu_nom?: string;
  numero: string;
  date: string;
  montant_total?: number;
  lignes: { quantite: string; prix_unitaire: string }[];
}

interface BilanData {
  total_ventes: string;
  total_ventes_produits: string;
  total_mouture: string;
  total_achats_mpsl: string;
  total_depenses_operationnelles: string;
  total_charges: string;
  benefice_net: string;
  est_benefice: boolean;
  total_dettes_fournisseurs: string;
  nb_dettes_en_cours: number;
}

// ---- Helpers ----
function fmt(v: string | number) {
  return Number(v).toLocaleString("fr-FR");
}

function ticketTotal(t: Ticket) {
  if (t.montant_total != null) return Number(t.montant_total);
  return t.lignes.reduce((s, l) => s + Number(l.quantite) * Number(l.prix_unitaire), 0);
}

function thisWeekRange() {
  const now = new Date();
  const day = (now.getDay() + 6) % 7;
  const debut = new Date(now);
  debut.setDate(now.getDate() - day);
  const fin = new Date(debut);
  fin.setDate(debut.getDate() + 6);
  return { debut: debut.toISOString().slice(0, 10), fin: fin.toISOString().slice(0, 10) };
}

function thisMonthRange() {
  const now = new Date();
  const debut = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
  const fin = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
  return { debut, fin };
}

type Tab = "boutiques" | "mpsl" | "ventes";

export default function ComptablePage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("boutiques");
  const [debut, setDebut] = useState("");
  const [fin, setFin] = useState("");

  const [boutiques, setBoutiques] = useState<BoutiqueRapport[]>([]);
  const [mpsl, setMpsl] = useState<MPSLRapport[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
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
      const [b, m, t, bl] = await Promise.all([
        apiFetch(`/comptable/rapport-boutiques/${qs}`),
        apiFetch(`/comptable/rapport-mpsl/${qs}`),
        apiFetch(`/comptable/ventes/${qs}`),
        apiFetch(`/comptable/bilan/${qs}`),
      ]);
      setBoutiques(b as BoutiqueRapport[]);
      setMpsl(m as MPSLRapport[]);
      setTickets((t as { results?: Ticket[] }).results ?? (t as Ticket[]));
      setBilan(bl as BilanData);
    } catch {
      // silencieux
    } finally {
      setLoading(false);
    }
  }, [buildQs]);

  useEffect(() => { load(); }, [load]);

  const applyPreset = (preset: "semaine" | "mois" | "tout") => {
    if (preset === "semaine") { const r = thisWeekRange(); setDebut(r.debut); setFin(r.fin); }
    else if (preset === "mois") { const r = thisMonthRange(); setDebut(r.debut); setFin(r.fin); }
    else { setDebut(""); setFin(""); }
  };

  const totalVentes = boutiques.reduce((s, b) => s + Number(b.total_ventes), 0);
  const totalAchatsMpsl = mpsl.reduce((s, m) => s + Number(m.total_achats), 0);
  const totalDettesMpsl = mpsl.reduce((s, m) => s + Number(m.total_dettes), 0);

  const beneficeNet = bilan ? Number(bilan.benefice_net) : 0;
  const estBenefice = bilan ? bilan.est_benefice : true;

  const detailBoutiqueUrl = (id: number) => `/comptable/boutiques/${id}${buildQs()}`;
  const detailMpslUrl = (id: number) => `/comptable/mpsl/${id}${buildQs()}`;

  return (
    <div className="space-y-4 min-w-0">
      <h1 className="text-2xl font-semibold tracking-tight">Rapport comptable</h1>

      {/* Filtres date */}
      <div className="flex flex-wrap items-center gap-2 p-3 rounded-lg border bg-card">
        <div className="flex gap-1 flex-wrap">
          {(["semaine", "mois", "tout"] as const).map((p) => (
            <button
              key={p}
              onClick={() => applyPreset(p)}
              className="px-3 py-1.5 text-xs font-medium rounded-md border hover:bg-muted transition-colors"
            >
              {p === "semaine" ? "Cette semaine" : p === "mois" ? "Ce mois" : "Tout"}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="date"
            value={debut}
            onChange={(e) => setDebut(e.target.value)}
            className="h-8 rounded-md border border-input bg-background px-2 text-xs"
          />
          <span className="text-xs text-muted-foreground">→</span>
          <input
            type="date"
            value={fin}
            onChange={(e) => setFin(e.target.value)}
            className="h-8 rounded-md border border-input bg-background px-2 text-xs"
          />
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
            <div className="rounded-lg border border-l-4 border-l-green-600 bg-green-50 dark:bg-green-950/20 p-3">
              <p className="text-xs text-muted-foreground">Total revenus</p>
              <p className="text-lg font-bold text-green-800 dark:text-green-300">{fmt(bilan.total_ventes)}</p>
              <p className="text-xs text-muted-foreground">dont mouture {fmt(bilan.total_mouture)} FCFA</p>
            </div>
            <div className="rounded-lg border border-l-4 border-l-orange-500 bg-orange-50 dark:bg-orange-950/20 p-3">
              <p className="text-xs text-muted-foreground">Achats MPSL</p>
              <p className="text-lg font-bold text-orange-700 dark:text-orange-400">{fmt(bilan.total_achats_mpsl)}</p>
              <p className="text-xs text-muted-foreground">FCFA</p>
            </div>
            <div className="rounded-lg border border-l-4 border-l-red-400 bg-red-50 dark:bg-red-950/20 p-3">
              <p className="text-xs text-muted-foreground">Charges opér.</p>
              <p className="text-lg font-bold text-red-600 dark:text-red-400">{fmt(bilan.total_depenses_operationnelles)}</p>
              <p className="text-xs text-muted-foreground">FCFA</p>
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
              <p className="text-xs text-muted-foreground">FCFA</p>
            </div>
          </div>
          {Number(bilan.total_dettes_fournisseurs) > 0 && (
            <div className="rounded-lg border border-l-4 border-l-red-500 bg-red-50 dark:bg-red-950/20 p-3 flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-red-700 dark:text-red-400">Dettes fournisseurs en cours</p>
                <p className="text-xs text-muted-foreground">{bilan.nb_dettes_en_cours} dette(s) non soldée(s)</p>
              </div>
              <p className="text-lg font-bold text-red-700 dark:text-red-400">{fmt(bilan.total_dettes_fournisseurs)} FCFA</p>
            </div>
          )}
        </div>
      )}

      {/* Cartes résumé */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <div className="rounded-lg border border-l-4 border-l-green-500 bg-card p-4">
          <p className="text-xs text-muted-foreground">CA boutiques</p>
          <p className="text-xl font-bold text-green-700 dark:text-green-400">{fmt(totalVentes)} <span className="text-sm font-normal text-muted-foreground">FCFA</span></p>
        </div>
        <div className="rounded-lg border border-l-4 border-l-orange-500 bg-card p-4">
          <p className="text-xs text-muted-foreground">Achats MPSL</p>
          <p className="text-xl font-bold text-orange-700 dark:text-orange-400">{fmt(totalAchatsMpsl)} <span className="text-sm font-normal text-muted-foreground">FCFA</span></p>
        </div>
        <div className="rounded-lg border border-l-4 border-l-red-400 bg-card p-4 col-span-2 lg:col-span-1">
          <p className="text-xs text-muted-foreground">Dettes fournisseurs MPSL</p>
          <p className="text-xl font-bold text-red-600 dark:text-red-400">{fmt(totalDettesMpsl)} <span className="text-sm font-normal text-muted-foreground">FCFA</span></p>
        </div>
      </div>

      {/* Tabs */}
      <div className="scrollbar-hidden flex gap-1 border-b overflow-x-auto">
        {([
          ["boutiques", "Boutiques"],
          ["mpsl", "MPSL"],
          ["ventes", "Ventes détail"],
        ] as [Tab, string][]).map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors",
              tab === t ? "border-green-600 text-green-600 dark:border-green-400 dark:text-green-400" : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab Boutiques */}
      {tab === "boutiques" && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs sm:text-sm min-w-[900px]">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="text-left py-2 px-3">Boutique</th>
                <th className="text-right py-2 px-3">Tickets</th>
                <th className="text-right py-2 px-3">CA ventes (FCFA)</th>
                <th className="text-right py-2 px-3">Cash encaissé (FCFA)</th>
                <th className="text-right py-2 px-3">Créances (FCFA)</th>
                <th className="text-right py-2 px-3">Stock (produits)</th>
                <th className="text-right py-2 px-3">Cessions reçues</th>
                <th className="py-2 px-3"></th>
              </tr>
            </thead>
            <tbody>
              {boutiques.length === 0 && <tr><td colSpan={8} className="py-6 text-center text-muted-foreground">Aucune donnée.</td></tr>}
              {boutiques.map((b) => (
                <tr key={b.lieu_id} className="border-b hover:bg-muted/20 cursor-pointer" onClick={() => router.push(detailBoutiqueUrl(b.lieu_id))}>
                  <td className="py-2 px-3 font-medium">{b.lieu_nom}</td>
                  <td className="py-2 px-3 text-right">{b.nb_tickets}</td>
                  <td className="py-2 px-3 text-right font-medium text-green-700 dark:text-green-400">{fmt(b.total_ventes)}</td>
                  <td className="py-2 px-3 text-right text-blue-700 dark:text-blue-400">{fmt(b.caisse_reelle)}</td>
                  <td className="py-2 px-3 text-right text-amber-700 dark:text-amber-400">{fmt(b.total_creances)}</td>
                  <td className="py-2 px-3 text-right">{b.nb_produits_en_stock}</td>
                  <td className="py-2 px-3 text-right text-muted-foreground">{fmt(b.cessions_recues_sacs)} sacs</td>
                  <td className="py-2 px-3 text-right text-xs text-green-600 dark:text-green-400">Détail →</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab MPSL */}
      {tab === "mpsl" && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs sm:text-sm min-w-[640px]">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="text-left py-2 px-3">Dépôt MPSL</th>
                <th className="text-right py-2 px-3">Achats</th>
                <th className="text-right py-2 px-3">Total achats (FCFA)</th>
                <th className="text-right py-2 px-3">Dettes en cours</th>
                <th className="text-right py-2 px-3">Montant dettes (FCFA)</th>
                <th className="py-2 px-3"></th>
              </tr>
            </thead>
            <tbody>
              {mpsl.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-muted-foreground">Aucun dépôt MPSL.</td></tr>}
              {mpsl.map((m) => (
                <tr key={m.lieu_id} className="border-b hover:bg-muted/20 cursor-pointer" onClick={() => router.push(detailMpslUrl(m.lieu_id))}>
                  <td className="py-2 px-3 font-medium">{m.lieu_nom}</td>
                  <td className="py-2 px-3 text-right">{m.nb_achats}</td>
                  <td className="py-2 px-3 text-right font-medium text-orange-700 dark:text-orange-400">{fmt(m.total_achats)}</td>
                  <td className="py-2 px-3 text-right">{m.nb_dettes_en_cours}</td>
                  <td className="py-2 px-3 text-right font-medium text-red-600 dark:text-red-400">{fmt(m.total_dettes)}</td>
                  <td className="py-2 px-3 text-right text-xs text-green-600 dark:text-green-400">Détail →</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab Ventes détail */}
      {tab === "ventes" && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs sm:text-sm min-w-[480px]">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="text-left py-2 px-3">N°</th>
                <th className="text-left py-2 px-3">Boutique</th>
                <th className="text-left py-2 px-3">Date</th>
                <th className="text-right py-2 px-3">Total (FCFA)</th>
              </tr>
            </thead>
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
    </div>
  );
}
