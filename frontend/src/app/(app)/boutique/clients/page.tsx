"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
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
  notes: string;
  created_at: string;
  updated_at: string;
  // Stats (ajoutées par le backend)
  nb_achats: number;
  dernier_achat: string | null;
  total_achats: string;
}

export default function BoutiqueClientsPage() {
  const { user } = useAuth();
  const lieuNom = user?.lieu?.nom ?? "Boutique";

  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [erreur, setErreur] = useState("");
  const [search, setSearch] = useState("");

  const charger = useCallback(async () => {
    try {
      setLoading(true);
      setErreur("");
      const res = await apiFetch<Client[]>("/boutique/clients/");
      setClients(Array.isArray(res) ? res : []);
    } catch {
      setErreur("Impossible de charger la liste des clients.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { charger(); }, [charger]);

  const clientsFiltres = search.trim()
    ? clients.filter(
        (c) =>
          c.nom.toLowerCase().includes(search.toLowerCase()) ||
          c.contact.toLowerCase().includes(search.toLowerCase())
      )
    : clients;

  const formatDate = (iso: string | null) => {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("fr-FR", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  };

  return (
    <div className="space-y-4">
      {/* En-tête impression */}
      <div className="hidden print:block mb-4">
        <h1 className="text-xl font-bold">Liste des clients — {lieuNom}</h1>
        <p className="text-xs text-gray-400">
          {clientsFiltres.length} client{clientsFiltres.length !== 1 ? "s" : ""}
          {search.trim() ? ` · Filtre : "${search}"` : ""}
          {" "}· Imprimé le {new Date().toLocaleString("fr-FR")}
        </p>
      </div>

      <div className="flex items-center justify-between flex-wrap gap-3 print:hidden">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Users className="h-6 w-6 text-blue-500" />
            Clients — {lieuNom}
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {clients.length} client{clients.length !== 1 ? "s" : ""} enregistré{clients.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={charger}>
            <RefreshCw className="h-4 w-4 mr-2" /> Actualiser
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer className="h-4 w-4 mr-2" /> Imprimer
          </Button>
        </div>
      </div>

      {/* Recherche */}
      <div className="relative max-w-xs print:hidden">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          placeholder="Rechercher par nom ou contact…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-8 h-8 text-sm"
        />
      </div>

      {erreur && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{erreur}</p>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement…</p>
      ) : clientsFiltres.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Users className="h-8 w-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">
            {search.trim()
              ? `Aucun client pour "${search}".`
              : "Aucun client enregistré. Les clients sont créés lors des ventes à crédit ou en les associant à une vente."}
          </p>
        </div>
      ) : (
        <>
          {/* Vue impression : tableau compact */}
          <div className="hidden print:block">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b-2 border-black">
                  <th className="text-left py-1 pr-4">Nom</th>
                  <th className="text-left py-1 pr-4">Contact</th>
                  <th className="text-right py-1 pr-4">Achats</th>
                  <th className="text-right py-1 pr-4">Total</th>
                  <th className="text-right py-1">Dernier achat</th>
                </tr>
              </thead>
              <tbody>
                {clientsFiltres.map((c) => (
                  <tr key={c.id} className="border-b border-gray-300">
                    <td className="py-1 pr-4 font-medium">{c.nom}</td>
                    <td className="py-1 pr-4 text-gray-600">{c.contact || "—"}</td>
                    <td className="py-1 pr-4 text-right">{c.nb_achats}</td>
                    <td className="py-1 pr-4 text-right">{fmt(parseFloat(c.total_achats || "0"))} F</td>
                    <td className="py-1 text-right">{formatDate(c.dernier_achat)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Vue normale : cartes */}
          <div className="print:hidden space-y-2">
            {clientsFiltres.map((c) => {
              const totalAchats = parseFloat(c.total_achats || "0");
              const actif = c.dernier_achat
                ? (Date.now() - new Date(c.dernier_achat).getTime()) < 90 * 24 * 60 * 60 * 1000 // 90 jours
                : false;
              return (
                <Card key={c.id} className={`border-l-4 ${actif ? "border-l-green-400" : c.nb_achats === 0 ? "border-l-gray-300" : "border-l-amber-300"}`}>
                  <CardContent className="px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-sm">{c.nom}</p>
                        {c.contact ? (
                          <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                            <Phone className="h-3 w-3 shrink-0" />
                            {c.contact}
                          </p>
                        ) : (
                          <p className="text-xs text-muted-foreground/50 italic mt-0.5">Pas de contact</p>
                        )}
                        {c.notes && (
                          <p className="text-xs text-muted-foreground mt-0.5 truncate">{c.notes}</p>
                        )}
                      </div>
                      <div className="text-right shrink-0 space-y-0.5">
                        <div className="flex items-center gap-1 justify-end text-xs text-muted-foreground">
                          <ShoppingBag className="h-3 w-3" />
                          <span>{c.nb_achats} achat{c.nb_achats !== 1 ? "s" : ""}</span>
                        </div>
                        {totalAchats > 0 && (
                          <p className="text-xs font-semibold text-green-700 dark:text-green-300">
                            {fmt(totalAchats)} F
                          </p>
                        )}
                        <p className="text-xs text-muted-foreground">
                          {c.dernier_achat
                            ? `Dernier : ${formatDate(c.dernier_achat)}`
                            : "Jamais acheté"}
                        </p>
                        {!actif && c.nb_achats > 0 && (
                          <span className="text-[10px] bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 px-1.5 py-0.5 rounded-full">
                            À relancer
                          </span>
                        )}
                        {actif && (
                          <span className="text-[10px] bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-300 px-1.5 py-0.5 rounded-full">
                            Actif
                          </span>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* Résumé */}
          <Card className="bg-muted/30 print:hidden">
            <CardHeader className="pb-1 pt-3 px-4">
              <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Récapitulatif
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-3 grid grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Total clients</p>
                <p className="font-semibold">{clientsFiltres.length}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Actifs (90j)</p>
                <p className="font-semibold text-green-600">
                  {clientsFiltres.filter((c) =>
                    c.dernier_achat &&
                    Date.now() - new Date(c.dernier_achat).getTime() < 90 * 24 * 60 * 60 * 1000
                  ).length}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">À relancer</p>
                <p className="font-semibold text-amber-600">
                  {clientsFiltres.filter((c) =>
                    c.nb_achats > 0 &&
                    (!c.dernier_achat ||
                      Date.now() - new Date(c.dernier_achat).getTime() >= 90 * 24 * 60 * 60 * 1000)
                  ).length}
                </p>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
