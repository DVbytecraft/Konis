"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RefreshCw, Users, Search, Phone, Printer, ShoppingBag } from "lucide-react";

interface Client {
  id: number;
  nom: string;
  contact: string;
  interet: string;
  notes: string;
  statut: "prospect" | "client";
  lieu_nom: string | null;
  created_at: string;
  nb_achats: number;
  dernier_achat: string | null;
  total_achats: string;
}

const fmt_date = (iso: string | null) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
};

export default function AdminClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [erreur, setErreur] = useState("");
  const [search, setSearch] = useState("");
  const [filtreStatut, setFiltreStatut] = useState<"tous" | "prospect" | "client">("tous");
  const [filtreLieu, setFiltreLieu] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const charger = useCallback(async () => {
    setLoading(true);
    setErreur("");
    try {
      const params = new URLSearchParams();
      if (filtreStatut !== "tous") params.set("statut", filtreStatut);
      if (search.trim()) params.set("search", search.trim());
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const res = await apiFetch<Client[]>(`/admin/clients/?${params.toString()}`);
      setClients(Array.isArray(res) ? res : []);
    } catch {
      setErreur("Impossible de charger la liste.");
    } finally {
      setLoading(false);
    }
  }, [filtreStatut, search, dateFrom, dateTo]);

  useEffect(() => { charger(); }, [charger]);

  const lieux = Array.from(new Set(clients.map(c => c.lieu_nom).filter(Boolean))) as string[];
  const clientsFiltres = filtreLieu ? clients.filter(c => c.lieu_nom === filtreLieu) : clients;
  const nbProspects = clientsFiltres.filter(c => c.statut === "prospect").length;
  const nbClients   = clientsFiltres.filter(c => c.statut === "client").length;

  return (
    <div className="space-y-4">
      {/* En-tête impression */}
      <div className="hidden print:block mb-4">
        <h1 className="text-xl font-bold">Clients &amp; Visiteurs</h1>
        <p className="text-xs text-gray-400">
          {clientsFiltres.length} entrée{clientsFiltres.length !== 1 ? "s" : ""}
          {filtreStatut !== "tous" ? ` · ${filtreStatut === "prospect" ? "Prospects" : "Clients"}` : ""}
          {filtreLieu ? ` · ${filtreLieu}` : ""}
          {dateFrom || dateTo ? ` · Du ${dateFrom || "…"} au ${dateTo || "…"}` : ""}
          {" "}· Imprimé le {new Date().toLocaleString("fr-FR")}
        </p>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3 print:hidden">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Users className="h-6 w-6 text-blue-500" />
            Clients &amp; Visiteurs
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {nbClients} client{nbClients !== 1 ? "s" : ""} · {nbProspects} prospect{nbProspects !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={charger} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} /> Actualiser
          </Button>
          {clients.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => window.print()}>
              <Printer className="h-4 w-4 mr-2" /> Imprimer
            </Button>
          )}
        </div>
      </div>

      {/* Filtres */}
      <div className="flex flex-wrap gap-3 items-center print:hidden">
        {(["tous", "client", "prospect"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFiltreStatut(s)}
            className={`text-xs px-3 py-1 rounded-full border transition-colors ${
              filtreStatut === s
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border text-muted-foreground hover:border-foreground"
            }`}
          >
            {s === "tous" ? "Tous" : s === "client" ? "Clients" : "Prospects"}
          </button>
        ))}
        {lieux.length > 0 && (
          <select
            value={filtreLieu}
            onChange={e => setFiltreLieu(e.target.value)}
            className="text-xs h-7 px-2 rounded border border-border bg-background text-foreground"
          >
            <option value="">Toutes les boutiques</option>
            {lieux.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        )}
        <div className="flex items-center gap-2 ml-auto">
          <label className="text-xs text-muted-foreground">Du</label>
          <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="h-7 text-xs w-36" />
          <label className="text-xs text-muted-foreground">au</label>
          <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="h-7 text-xs w-36" />
          {(dateFrom || dateTo) && (
            <button onClick={() => { setDateFrom(""); setDateTo(""); }} className="text-xs text-muted-foreground hover:text-foreground underline">Effacer</button>
          )}
        </div>
      </div>

      {/* Recherche */}
      <div className="relative max-w-sm print:hidden">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          placeholder="Nom, contact, ce qu'il cherche…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="pl-8 h-8 text-sm"
        />
      </div>

      {erreur && <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{erreur}</p>}

      {/* Tableau impression */}
      {clientsFiltres.length > 0 && (
        <div className="hidden print:block">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="border-b-2 border-black">
                <th className="text-left py-1 pr-3">Nom</th>
                <th className="text-left py-1 pr-3">Contact</th>
                <th className="text-left py-1 pr-3">Statut</th>
                <th className="text-left py-1 pr-3">Boutique</th>
                <th className="text-left py-1 pr-3">Intérêt</th>
                <th className="text-right py-1 pr-3">Achats</th>
                <th className="text-right py-1 pr-3">Total</th>
                <th className="text-right py-1">Enregistré</th>
              </tr>
            </thead>
            <tbody>
              {clientsFiltres.map(c => (
                <tr key={c.id} className="border-b border-gray-300">
                  <td className="py-1 pr-3 font-medium">{c.nom}</td>
                  <td className="py-1 pr-3 text-gray-600">{c.contact || "—"}</td>
                  <td className="py-1 pr-3">{c.statut === "prospect" ? "Prospect" : "Client"}</td>
                  <td className="py-1 pr-3 text-gray-600">{c.lieu_nom || "—"}</td>
                  <td className="py-1 pr-3 text-gray-600">{c.interet || "—"}</td>
                  <td className="py-1 pr-3 text-right">{c.nb_achats}</td>
                  <td className="py-1 pr-3 text-right">{fmt(parseFloat(c.total_achats || "0"))} F</td>
                  <td className="py-1 text-right">{fmt_date(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Liste cartes */}
      {loading ? (
        <p className="text-sm text-muted-foreground print:hidden">Chargement…</p>
      ) : clientsFiltres.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground print:hidden">
          <Users className="h-8 w-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">Aucun résultat.</p>
        </div>
      ) : (
        <>
          <div className="print:hidden space-y-2">
            {clientsFiltres.map(c => {
              const isProspect = c.statut === "prospect";
              const totalAchats = parseFloat(c.total_achats || "0");
              const actif = !isProspect && c.dernier_achat
                ? Date.now() - new Date(c.dernier_achat).getTime() < 90 * 24 * 60 * 60 * 1000
                : false;
              return (
                <Card key={c.id} className={`border-l-4 ${isProspect ? "border-l-blue-300" : actif ? "border-l-green-400" : "border-l-amber-300"}`}>
                  <CardContent className="px-4 py-3">
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="font-semibold text-sm">{c.nom}</p>
                          {isProspect
                            ? <span className="text-[10px] bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 px-1.5 py-0.5 rounded-full">Prospect</span>
                            : <span className="text-[10px] bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300 px-1.5 py-0.5 rounded-full">Client</span>
                          }
                        </div>
                        {c.contact && (
                          <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                            <Phone className="h-3 w-3 shrink-0" />{c.contact}
                          </p>
                        )}
                        {c.interet && (
                          <p className="text-xs text-blue-600 dark:text-blue-400 mt-0.5 truncate">🔍 {c.interet}</p>
                        )}
                        {c.notes && (
                          <p className="text-xs text-muted-foreground mt-0.5 truncate">{c.notes}</p>
                        )}
                        <p className="text-xs text-muted-foreground mt-1">
                          {c.lieu_nom && <span className="font-medium text-foreground">{c.lieu_nom} · </span>}
                          Enregistré le {fmt_date(c.created_at)}
                        </p>
                      </div>
                      {!isProspect && (
                        <div className="text-right shrink-0 space-y-0.5">
                          <div className="flex items-center gap-1 justify-end text-xs text-muted-foreground">
                            <ShoppingBag className="h-3 w-3" />
                            <span>{c.nb_achats} achat{c.nb_achats !== 1 ? "s" : ""}</span>
                          </div>
                          {totalAchats > 0 && (
                            <p className="text-xs font-semibold text-green-700 dark:text-green-300">{fmt(totalAchats)} F</p>
                          )}
                          <p className="text-xs text-muted-foreground">
                            {c.dernier_achat ? `Dernier : ${fmt_date(c.dernier_achat)}` : "Jamais acheté"}
                          </p>
                          {actif && <span className="text-[10px] bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-300 px-1.5 py-0.5 rounded-full">Actif</span>}
                          {!actif && c.nb_achats > 0 && <span className="text-[10px] bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 px-1.5 py-0.5 rounded-full">À relancer</span>}
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          <Card className="bg-muted/30 print:hidden">
            <CardHeader className="pb-1 pt-3 px-4">
              <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Récapitulatif</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-3 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Prospects</p>
                <p className="font-semibold text-blue-600">{nbProspects}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Clients</p>
                <p className="font-semibold">{nbClients}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Actifs (90j)</p>
                <p className="font-semibold text-green-600">
                  {clientsFiltres.filter(c => c.statut === "client" && c.dernier_achat && Date.now() - new Date(c.dernier_achat).getTime() < 90 * 24 * 60 * 60 * 1000).length}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total achats</p>
                <p className="font-semibold">
                  {fmt(clientsFiltres.reduce((a, c) => a + parseFloat(c.total_achats || "0"), 0))} F
                </p>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
