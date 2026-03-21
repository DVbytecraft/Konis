"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface TransferRow {
  id: number;
  lot_nom: string;
  boutique_nom: string;
  produit_nom: string;
  quantite_sacs: string | number;
  poids_total: string | number;
  prix_par_sac: string | number;
  montant_cession: string | number;
  created_at: string;
}

interface InterUsineRow {
  id: number;
  lot_nom: string;
  produit_nom: string;
  usine_source_nom: string;
  usine_destination_nom: string;
  quantite_sacs: string | number;
  notes: string;
  created_at: string;
}

interface LotOption {
  id: number;
  nom_lot: string;
  produit_fini_nom: string;
  stock_restant: string | number;
}

interface ShopOption {
  id: number;
  nom: string;
}
type LocationPayload =
  | ShopOption[]
  | { results?: ShopOption[]; items?: ShopOption[]; data?: ShopOption[] }
  | null
  | undefined;

function toLocationList(payload: LocationPayload): ShopOption[] {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== "object") return [];
  return payload.results ?? payload.items ?? payload.data ?? [];
}

export default function FactoryTransfersPage() {
  const [tab, setTab] = useState<"boutiques" | "usines">("boutiques");

  // --- Vers boutiques ---
  const [rows, setRows] = useState<TransferRow[]>([]);
  const [lots, setLots] = useState<LotOption[]>([]);
  const [shops, setShops] = useState<ShopOption[]>([]);
  const [form, setForm] = useState({ lot: "", boutique: "", quantite_sacs: "", poids_total: "", prix_par_sac: "" });
  const [err, setErr] = useState("");

  // --- Vers usines ---
  const [interRows, setInterRows] = useState<InterUsineRow[]>([]);
  const [factories, setFactories] = useState<ShopOption[]>([]);
  const [formU, setFormU] = useState({ lot: "", usine_destination: "", quantite_sacs: "", poids_total: "", notes: "" });
  const [errU, setErrU] = useState("");

  const load = async () => {
    const [list, lotList, shopList, factoryList, interList] = await Promise.all([
      apiFetch("/usine/cessions/"),
      apiFetch("/usine/lots/"),
      apiFetch("/locations/by-type/?type=shop"),
      apiFetch("/locations/by-type/?type=factory"),
      apiFetch("/usine/transferts-inter-usines/"),
    ]);
    setRows((list as { results?: TransferRow[] }).results ?? (list as TransferRow[]));
    setLots((lotList as { results?: LotOption[] }).results ?? (lotList as LotOption[]));
    setShops(toLocationList(shopList as LocationPayload));
    setFactories(toLocationList(factoryList as LocationPayload));
    setInterRows((interList as { results?: InterUsineRow[] }).results ?? (interList as InterUsineRow[]));
  };

  useEffect(() => { load().catch(() => {}); }, []);

  const submitBoutique = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    if (!form.lot) { setErr("Sélectionne un lot."); return; }
    if (!form.boutique) { setErr("Sélectionne une boutique."); return; }
    if (!form.quantite_sacs || Number(form.quantite_sacs) <= 0) { setErr("Nombre de sacs > 0 requis."); return; }
    try {
      await apiFetch("/usine/cessions/", {
        method: "POST",
        body: JSON.stringify({
          lot: Number(form.lot),
          boutique: Number(form.boutique),
          quantite_sacs: form.quantite_sacs,
          poids_total: form.poids_total || "0",
          prix_par_sac: form.prix_par_sac || "0",
        }),
      });
      setForm({ lot: "", boutique: "", quantite_sacs: "", poids_total: "", prix_par_sac: "" });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erreur");
    }
  };

  const submitUsine = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrU("");
    if (!formU.lot) { setErrU("Sélectionne un lot."); return; }
    if (!formU.usine_destination) { setErrU("Sélectionne une usine destination."); return; }
    if (!formU.quantite_sacs || Number(formU.quantite_sacs) <= 0) { setErrU("Nombre de sacs > 0 requis."); return; }
    try {
      await apiFetch("/usine/transferts-inter-usines/", {
        method: "POST",
        body: JSON.stringify({
          lot: Number(formU.lot),
          usine_destination: Number(formU.usine_destination),
          quantite_sacs: formU.quantite_sacs,
          poids_total: formU.poids_total || "0",
          notes: formU.notes,
        }),
      });
      setFormU({ lot: "", usine_destination: "", quantite_sacs: "", poids_total: "", notes: "" });
      await load();
    } catch (e) {
      setErrU(e instanceof Error ? e.message : "Erreur");
    }
  };

  return (
    <div className="space-y-4 min-w-0">
      <h1 className="text-2xl font-semibold tracking-tight">Transferts</h1>

      {/* Tabs */}
      <div className="flex gap-1 border-b scrollbar-hidden overflow-x-auto">
        <button
          onClick={() => setTab("boutiques")}
          className={cn(
            "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap",
            tab === "boutiques"
              ? "border-blue-500 text-blue-600 dark:text-blue-400"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          Vers boutiques
        </button>
        <button
          onClick={() => setTab("usines")}
          className={cn(
            "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap",
            tab === "usines"
              ? "border-purple-500 text-purple-600 dark:text-purple-400"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          Vers usines
        </button>
      </div>

      {/* Tab : Vers boutiques */}
      {tab === "boutiques" && (
        <div className="space-y-4">
          <form onSubmit={submitBoutique} className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-6">
            <select
              className="h-10 rounded-md border border-input bg-background px-2 text-sm lg:col-span-2"
              value={form.lot}
              onChange={(e) => setForm((f) => ({ ...f, lot: e.target.value }))}
            >
              <option value="">Lot de production</option>
              {lots.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.nom_lot} — {l.produit_fini_nom} (stock: {Number(l.stock_restant).toFixed(0)} sacs)
                </option>
              ))}
            </select>
            <select
              className="h-10 rounded-md border border-input bg-background px-2 text-sm"
              value={form.boutique}
              onChange={(e) => setForm((f) => ({ ...f, boutique: e.target.value }))}
            >
              <option value="">Boutique</option>
              {shops.map((s) => (
                <option key={s.id} value={s.id}>{s.nom}</option>
              ))}
            </select>
            <Input placeholder="Nb sacs *" value={form.quantite_sacs} onChange={(e) => setForm((f) => ({ ...f, quantite_sacs: e.target.value }))} />
            <Input placeholder="Prix / sac (FCFA)" value={form.prix_par_sac} onChange={(e) => setForm((f) => ({ ...f, prix_par_sac: e.target.value }))} />
            <Input placeholder="Poids total kg (optionnel)" value={form.poids_total} onChange={(e) => setForm((f) => ({ ...f, poids_total: e.target.value }))} />
            <Button type="submit" className="w-full lg:col-span-6 sm:col-span-2 bg-blue-600 hover:bg-blue-700 text-white">
              Créer transfert vers boutique
            </Button>
          </form>
          {lots.length === 0 && <p className="text-xs text-amber-700">Aucun lot disponible. Crée d&apos;abord une production.</p>}
          {shops.length === 0 && <p className="text-xs text-amber-700">Aucune boutique disponible pour votre entreprise.</p>}
          {err && <p className="text-sm text-destructive">{err}</p>}
          <div className="overflow-x-auto rounded-md border -mx-1 sm:mx-0">
            <table className="w-full text-xs sm:text-sm min-w-[680px]">
              <thead>
                <tr className="border-b bg-blue-50/50 dark:bg-blue-950/20">
                  <th className="text-left py-2 px-3 text-blue-700 dark:text-blue-300">Lot</th>
                  <th className="text-left py-2 px-3">Boutique</th>
                  <th className="text-left py-2 px-3">Produit</th>
                  <th className="text-right py-2 px-3">Sacs</th>
                  <th className="text-right py-2 px-3">Montant (FCFA)</th>
                  <th className="text-left py-2 px-3">Date</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr><td colSpan={5} className="py-4 text-center text-muted-foreground text-sm">Aucun transfert.</td></tr>
                )}
                {rows.map((r) => (
                  <tr key={r.id} className="border-b hover:bg-blue-50/30 dark:hover:bg-blue-950/10">
                    <td className="py-1.5 px-3 font-mono text-blue-700 dark:text-blue-300">{r.lot_nom}</td>
                    <td className="py-1.5 px-3">{r.boutique_nom}</td>
                    <td className="py-1.5 px-3">{r.produit_nom}</td>
                    <td className="py-1.5 px-3 text-right">{Number(r.quantite_sacs).toFixed(0)}</td>
                    <td className="py-1.5 px-3 text-right font-medium text-blue-700 dark:text-blue-400">
                      {Number(r.montant_cession) > 0 ? Number(r.montant_cession).toLocaleString("fr-FR") : "—"}
                    </td>
                    <td className="py-1.5 px-3 text-muted-foreground">{new Date(r.created_at).toLocaleString("fr-FR")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab : Vers usines */}
      {tab === "usines" && (
        <div className="space-y-4">
          <form onSubmit={submitUsine} className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-6">
            <select
              className="h-10 rounded-md border border-input bg-background px-2 text-sm lg:col-span-2"
              value={formU.lot}
              onChange={(e) => setFormU((f) => ({ ...f, lot: e.target.value }))}
            >
              <option value="">Lot de production</option>
              {lots.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.nom_lot} — {l.produit_fini_nom} (stock: {Number(l.stock_restant).toFixed(0)} sacs)
                </option>
              ))}
            </select>
            <select
              className="h-10 rounded-md border border-input bg-background px-2 text-sm"
              value={formU.usine_destination}
              onChange={(e) => setFormU((f) => ({ ...f, usine_destination: e.target.value }))}
            >
              <option value="">Usine destination</option>
              {factories.map((f) => (
                <option key={f.id} value={f.id}>{f.nom}</option>
              ))}
            </select>
            <Input placeholder="Nb sacs" value={formU.quantite_sacs} onChange={(e) => setFormU((f) => ({ ...f, quantite_sacs: e.target.value }))} />
            <Input placeholder="Poids total (optionnel)" value={formU.poids_total} onChange={(e) => setFormU((f) => ({ ...f, poids_total: e.target.value }))} />
            <Input placeholder="Notes (optionnel)" value={formU.notes} onChange={(e) => setFormU((f) => ({ ...f, notes: e.target.value }))} className="lg:col-span-5" />
            <Button type="submit" className="w-full lg:col-span-6 sm:col-span-2 bg-purple-600 hover:bg-purple-700 text-white">
              Créer transfert inter-usines
            </Button>
          </form>
          {lots.length === 0 && <p className="text-xs text-amber-700">Aucun lot disponible. Crée d&apos;abord une production.</p>}
          {factories.length === 0 && <p className="text-xs text-amber-700">Aucune autre usine disponible.</p>}
          {errU && <p className="text-sm text-destructive">{errU}</p>}
          <div className="overflow-x-auto rounded-md border -mx-1 sm:mx-0">
            <table className="w-full text-xs sm:text-sm min-w-[720px]">
              <thead>
                <tr className="border-b bg-purple-50/50 dark:bg-purple-950/20">
                  <th className="text-left py-2 px-3 text-purple-700 dark:text-purple-300">Lot</th>
                  <th className="text-left py-2 px-3">Source</th>
                  <th className="text-left py-2 px-3">Destination</th>
                  <th className="text-left py-2 px-3">Produit</th>
                  <th className="text-right py-2 px-3">Sacs</th>
                  <th className="text-left py-2 px-3">Date</th>
                </tr>
              </thead>
              <tbody>
                {interRows.length === 0 && (
                  <tr><td colSpan={6} className="py-4 text-center text-muted-foreground text-sm">Aucun transfert inter-usines.</td></tr>
                )}
                {interRows.map((r) => (
                  <tr key={r.id} className="border-b hover:bg-purple-50/30 dark:hover:bg-purple-950/10">
                    <td className="py-1.5 px-3 font-mono text-purple-700 dark:text-purple-300">{r.lot_nom}</td>
                    <td className="py-1.5 px-3">{r.usine_source_nom}</td>
                    <td className="py-1.5 px-3">{r.usine_destination_nom}</td>
                    <td className="py-1.5 px-3">{r.produit_nom}</td>
                    <td className="py-1.5 px-3 text-right">{Number(r.quantite_sacs).toFixed(0)}</td>
                    <td className="py-1.5 px-3 text-muted-foreground">{new Date(r.created_at).toLocaleString("fr-FR")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
