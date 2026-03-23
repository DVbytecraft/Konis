"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RefreshCw, Users, Search, Phone, Printer, ShoppingBag, UserPlus, X } from "lucide-react";

interface Client {
  id: number;
  nom: string;
  contact: string;
  interet: string;
  notes: string;
  statut: "prospect" | "client";
  created_at: string;
  updated_at: string;
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
  const [filtreStatut, setFiltreStatut] = useState<"tous" | "prospect" | "client">("tous");

  // Formulaire nouveau visiteur
  const [showForm, setShowForm] = useState(false);
  const [formNom, setFormNom] = useState("");
  const [formContact, setFormContact] = useState("");
  const [formInteret, setFormInteret] = useState("");
  const [formNotes, setFormNotes] = useState("");
  const [formSaving, setFormSaving] = useState(false);
  const [formErreur, setFormErreur] = useState("");

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

  const enregistrerVisiteur = async () => {
    if (!formNom.trim()) { setFormErreur("Le nom est requis."); return; }
    setFormSaving(true);
    setFormErreur("");
    try {
      await apiFetch("/boutique/clients/", {
        method: "POST",
        body: JSON.stringify({
          nom: formNom.trim(),
          contact: formContact.trim(),
          interet: formInteret.trim(),
          notes: formNotes.trim(),
          statut: "prospect",
        }),
      });
      setShowForm(false);
      setFormNom(""); setFormContact(""); setFormInteret(""); setFormNotes("");
      charger();
    } catch (e) {
      setFormErreur(e instanceof Error ? e.message : "Erreur lors de l'enregistrement.");
    } finally {
      setFormSaving(false);
    }
  };

  const clientsFiltres = clients.filter((c) => {
    const matchSearch = !search.trim() ||
      c.nom.toLowerCase().includes(search.toLowerCase()) ||
      c.contact.toLowerCase().includes(search.toLowerCase()) ||
      c.interet.toLowerCase().includes(search.toLowerCase());
    const matchStatut = filtreStatut === "tous" || c.statut === filtreStatut;
    return matchSearch && matchStatut;
  });

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
        <h1 className="text-xl font-bold">Clients &amp; Visiteurs — {lieuNom}</h1>
        <p className="text-xs text-gray-400">
          {clientsFiltres.length} entrée{clientsFiltres.length !== 1 ? "s" : ""}
          {filtreStatut !== "tous" ? ` · ${filtreStatut === "prospect" ? "Prospects" : "Clients"}` : ""}
          {search.trim() ? ` · Recherche : "${search}"` : ""}
          {" "}· Imprimé le {new Date().toLocaleString("fr-FR")}
        </p>
      </div>

      <div className="flex items-start justify-between flex-wrap gap-3 print:hidden">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Users className="h-6 w-6 text-blue-500" />
            Clients &amp; Visiteurs — {lieuNom}
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {clients.filter(c => c.statut === "client").length} client{clients.filter(c => c.statut === "client").length !== 1 ? "s" : ""} ·{" "}
            {clients.filter(c => c.statut === "prospect").length} prospect{clients.filter(c => c.statut === "prospect").length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => { setShowForm(true); setFormErreur(""); }}>
            <UserPlus className="h-4 w-4 mr-2" /> Enregistrer un visiteur
          </Button>
          <Button variant="outline" size="sm" onClick={charger}>
            <RefreshCw className="h-4 w-4 mr-2" /> Actualiser
          </Button>
          {clientsFiltres.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => window.print()}>
              <Printer className="h-4 w-4 mr-2" /> Imprimer
            </Button>
          )}
        </div>
      </div>

      {/* Filtres */}
      <div className="flex flex-wrap gap-2 print:hidden">
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
      </div>

      {/* Recherche */}
      <div className="relative max-w-sm print:hidden">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          placeholder="Nom, contact, ce qu'il cherche…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-8 h-8 text-sm"
        />
      </div>

      {/* Modal nouveau visiteur */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white dark:bg-card rounded-lg shadow-xl w-full max-w-md space-y-4 p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Enregistrer un visiteur</h2>
              <button onClick={() => setShowForm(false)} className="text-muted-foreground hover:text-foreground">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium">Nom <span className="text-red-500">*</span></label>
                <Input value={formNom} onChange={(e) => setFormNom(e.target.value)} placeholder="Nom complet" autoFocus />
              </div>
              <div>
                <label className="text-sm font-medium">Contact (téléphone / email)</label>
                <Input value={formContact} onChange={(e) => setFormContact(e.target.value)} placeholder="Ex : 07 00 00 00 00" />
              </div>
              <div>
                <label className="text-sm font-medium">Ce qu&apos;il cherche / demande</label>
                <Input value={formInteret} onChange={(e) => setFormInteret(e.target.value)} placeholder="Ex : farine basse protéine, prix en gros…" />
              </div>
              <div>
                <label className="text-sm font-medium">Notes</label>
                <Input value={formNotes} onChange={(e) => setFormNotes(e.target.value)} placeholder="Remarques supplémentaires…" />
              </div>
            </div>
            {formErreur && <p className="text-sm text-destructive">{formErreur}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => setShowForm(false)} disabled={formSaving}>Annuler</Button>
              <Button onClick={enregistrerVisiteur} disabled={formSaving || !formNom.trim()}>
                {formSaving ? "Enregistrement…" : "Enregistrer"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {erreur && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{erreur}</p>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement…</p>
      ) : clientsFiltres.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Users className="h-8 w-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">
            {search.trim() || filtreStatut !== "tous"
              ? "Aucun résultat pour ce filtre."
              : "Aucun client enregistré. Utilisez « Enregistrer un visiteur » ou créez un client lors d'une vente à crédit."}
          </p>
        </div>
      ) : (
        <>
          {/* Vue impression : tableau compact */}
          <div className="hidden print:block">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b-2 border-black">
                  <th className="text-left py-1 pr-3">Nom</th>
                  <th className="text-left py-1 pr-3">Contact</th>
                  <th className="text-left py-1 pr-3">Statut</th>
                  <th className="text-left py-1 pr-3">Intérêt</th>
                  <th className="text-right py-1 pr-3">Achats</th>
                  <th className="text-right py-1">Dernier achat</th>
                </tr>
              </thead>
              <tbody>
                {clientsFiltres.map((c) => (
                  <tr key={c.id} className="border-b border-gray-300">
                    <td className="py-1 pr-3 font-medium">{c.nom}</td>
                    <td className="py-1 pr-3 text-gray-600">{c.contact || "—"}</td>
                    <td className="py-1 pr-3">{c.statut === "prospect" ? "Prospect" : "Client"}</td>
                    <td className="py-1 pr-3 text-gray-600">{c.interet || "—"}</td>
                    <td className="py-1 pr-3 text-right">{c.nb_achats}</td>
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
              const isProspect = c.statut === "prospect";
              const actif = !isProspect && c.dernier_achat
                ? (Date.now() - new Date(c.dernier_achat).getTime()) < 90 * 24 * 60 * 60 * 1000
                : false;
              return (
                <Card key={c.id} className={`border-l-4 ${isProspect ? "border-l-blue-300" : actif ? "border-l-green-400" : c.nb_achats === 0 ? "border-l-gray-300" : "border-l-amber-300"}`}>
                  <CardContent className="px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="font-semibold text-sm">{c.nom}</p>
                          {isProspect ? (
                            <span className="text-[10px] bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 px-1.5 py-0.5 rounded-full">Prospect</span>
                          ) : (
                            <span className="text-[10px] bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300 px-1.5 py-0.5 rounded-full">Client</span>
                          )}
                        </div>
                        {c.contact ? (
                          <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                            <Phone className="h-3 w-3 shrink-0" />{c.contact}
                          </p>
                        ) : (
                          <p className="text-xs text-muted-foreground/50 italic mt-0.5">Pas de contact</p>
                        )}
                        {c.interet && (
                          <p className="text-xs text-blue-600 dark:text-blue-400 mt-0.5 truncate">
                            🔍 {c.interet}
                          </p>
                        )}
                        {c.notes && (
                          <p className="text-xs text-muted-foreground mt-0.5 truncate">{c.notes}</p>
                        )}
                      </div>
                      <div className="text-right shrink-0 space-y-0.5">
                        {!isProspect && (
                          <>
                            <div className="flex items-center gap-1 justify-end text-xs text-muted-foreground">
                              <ShoppingBag className="h-3 w-3" />
                              <span>{c.nb_achats} achat{c.nb_achats !== 1 ? "s" : ""}</span>
                            </div>
                            {totalAchats > 0 && (
                              <p className="text-xs font-semibold text-green-700 dark:text-green-300">{fmt(totalAchats)} F</p>
                            )}
                            <p className="text-xs text-muted-foreground">
                              {c.dernier_achat ? `Dernier : ${formatDate(c.dernier_achat)}` : "Jamais acheté"}
                            </p>
                            {actif && <span className="text-[10px] bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-300 px-1.5 py-0.5 rounded-full">Actif</span>}
                            {!actif && c.nb_achats > 0 && <span className="text-[10px] bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 px-1.5 py-0.5 rounded-full">À relancer</span>}
                          </>
                        )}
                        {isProspect && (
                          <p className="text-xs text-muted-foreground">
                            Enregistré le {formatDate(c.created_at)}
                          </p>
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
              <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Récapitulatif</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-3 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Prospects</p>
                <p className="font-semibold text-blue-600">{clientsFiltres.filter(c => c.statut === "prospect").length}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Clients</p>
                <p className="font-semibold">{clientsFiltres.filter(c => c.statut === "client").length}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Actifs (90j)</p>
                <p className="font-semibold text-green-600">
                  {clientsFiltres.filter(c => c.statut === "client" && c.dernier_achat && Date.now() - new Date(c.dernier_achat).getTime() < 90 * 24 * 60 * 60 * 1000).length}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">À relancer</p>
                <p className="font-semibold text-amber-600">
                  {clientsFiltres.filter(c => c.statut === "client" && c.nb_achats > 0 && (!c.dernier_achat || Date.now() - new Date(c.dernier_achat).getTime() >= 90 * 24 * 60 * 60 * 1000)).length}
                </p>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
