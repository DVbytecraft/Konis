"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { openTicketPrintWindow } from "@/lib/print";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Ticket58mm } from "@/components/caisse/ticket-58mm";
import { ClipboardList, Copy, Printer, X } from "lucide-react";
import { fmt } from "@/lib/utils";

interface LigneTicket {
  produit_nom: string;
  quantite: number;
  prix_unitaire: number;
  total: number;
}

interface Ticket {
  id: number;
  numero: string;
  date: string;
  lieu_nom: string;
  lignes: LigneTicket[];
  mouture: boolean;
  cout_mouture: number;
  prix_mouture_kg: number | null;
  prix_mouture_tonne: number | null;
  prix_mouture_sac: number | null;
  montant_total: number;
  produit_apporte?: string;
}

type FiltrePeriode = "aujourd_hui" | "hier" | "semaine" | "personnalise";

function dateISO(d: Date): string {
  return d.toISOString().split("T")[0];
}

function getPlage(filtre: FiltrePeriode): { debut: string; fin: string } {
  const today = new Date();
  if (filtre === "aujourd_hui") {
    const s = dateISO(today);
    return { debut: s, fin: s };
  }
  if (filtre === "hier") {
    const h = new Date(today);
    h.setDate(h.getDate() - 1);
    const s = dateISO(h);
    return { debut: s, fin: s };
  }
  if (filtre === "semaine") {
    const lundi = new Date(today);
    lundi.setDate(today.getDate() - ((today.getDay() + 6) % 7));
    return { debut: dateISO(lundi), fin: dateISO(today) };
  }
  return { debut: "", fin: "" };
}

export default function BoutiqueTicketsPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(false);
  const [erreur, setErreur] = useState("");
  const [filtre, setFiltre] = useState<FiltrePeriode>("aujourd_hui");
  const [debut, setDebut] = useState(dateISO(new Date()));
  const [fin, setFin] = useState(dateISO(new Date()));
  const [ticketDetail, setTicketDetail] = useState<Ticket | null>(null);
  const [ticketReimpression, setTicketReimpression] = useState<Ticket | null>(null);
  const [reimpLoading, setReimpLoading] = useState(false);
  const [reimpErreur, setReimpErreur] = useState("");
  const imprimerTicket = useCallback((ticket: Ticket, copie: boolean = false) => {
    openTicketPrintWindow({
      numero: ticket.numero,
      date: new Date(ticket.date).toLocaleString("fr-FR"),
      lieu_nom: ticket.lieu_nom,
      lignes: ticket.lignes,
      montant_total: Number(ticket.montant_total),
      mouture: ticket.mouture,
      cout_mouture: Number(ticket.cout_mouture ?? 0),
      prix_mouture_kg: ticket.prix_mouture_kg ?? null,
      prix_mouture_tonne: ticket.prix_mouture_tonne ?? null,
      prix_mouture_sac: ticket.prix_mouture_sac ?? null,
      produit_apporte: ticket.produit_apporte,
      copie,
    });
  }, []);

  const charger = useCallback(async (d: string, f: string) => {
    if (!d || !f) return;
    setLoading(true);
    setErreur("");
    try {
      const params = new URLSearchParams({ debut: d, fin: f });
      interface Paginated<T> { results: T[] }
      const res = await apiFetch<Paginated<Ticket> | Ticket[]>(`/boutique/ventes/?${params}`);
      const liste: Ticket[] = Array.isArray(res) ? res : res.results;
      setTickets(liste);
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "Erreur chargement tickets");
    } finally {
      setLoading(false);
    }
  }, []);

  // Chargement initial (aujourd'hui)
  useEffect(() => {
    const { debut: d, fin: f } = getPlage("aujourd_hui");
    charger(d, f);
  }, [charger]);

  const appliquerFiltre = useCallback(
    (f: FiltrePeriode) => {
      setFiltre(f);
      if (f !== "personnalise") {
        const { debut: d, fin: fi } = getPlage(f);
        setDebut(d);
        setFin(fi);
        charger(d, fi);
      }
    },
    [charger]
  );

  const appliquerPersonnalise = useCallback(() => {
    charger(debut, fin);
  }, [debut, fin, charger]);

  const reimprimer = useCallback(async (ticket: Ticket) => {
    setReimpLoading(true);
    setReimpErreur("");
    try {
      const data = await apiFetch<Ticket>(
        `/boutique/tickets/${ticket.id}/reimprimer/`,
        { method: "POST", body: JSON.stringify({ motif: "" }) }
      );
      setTicketDetail(null);
      setTicketReimpression(data);
    } catch (e) {
      setReimpErreur(e instanceof Error ? e.message : "Erreur réimpression");
    } finally {
      setReimpLoading(false);
    }
  }, []);

  const totalPeriode = tickets.reduce(
    (acc, t) => acc + (t.montant_total != null ? Number(t.montant_total) : 0),
    0
  );

  const FILTRES: { key: FiltrePeriode; label: string }[] = [
    { key: "aujourd_hui", label: "Aujourd'hui" },
    { key: "hier", label: "Hier" },
    { key: "semaine", label: "Cette semaine" },
    { key: "personnalise", label: "Personnalisé" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <ClipboardList className="h-6 w-6" />
          Historique des tickets
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Consultez et filtrez vos ventes par période.
        </p>
      </div>

      {/* Filtres période */}
      <Card>
        <CardContent className="pt-4 pb-3 space-y-3">
          <div className="flex flex-wrap gap-2">
            {FILTRES.map(({ key, label }) => (
              <Button
                key={key}
                variant={filtre === key ? "default" : "outline"}
                size="sm"
                onClick={() => appliquerFiltre(key)}
              >
                {label}
              </Button>
            ))}
          </div>
          {filtre === "personnalise" && (
            <div className="flex flex-wrap items-center gap-2">
              <Input
                type="date"
                value={debut}
                onChange={(e) => setDebut(e.target.value)}
                className="w-full sm:w-36 h-8 text-sm"
              />
              <span className="text-muted-foreground text-sm">→</span>
              <Input
                type="date"
                value={fin}
                onChange={(e) => setFin(e.target.value)}
                className="w-full sm:w-36 h-8 text-sm"
              />
              <Button size="sm" onClick={appliquerPersonnalise}>
                Appliquer
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Résumé période */}
      {!loading && tickets.length > 0 && (
        <div className="flex items-center gap-4 px-1">
          <span className="text-sm text-muted-foreground">
            {tickets.length} ticket{tickets.length > 1 ? "s" : ""}
          </span>
          <span className="font-semibold text-green-700 dark:text-green-300">
            Total période : {fmt(totalPeriode)} FCFA
          </span>
        </div>
      )}

      {/* Erreur */}
      {erreur && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">
          {erreur}
        </p>
      )}

      {/* Table tickets */}
      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm">Liste des tickets</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <p className="text-sm text-muted-foreground px-4 py-6 text-center">
              Chargement…
            </p>
          ) : tickets.length === 0 ? (
            <p className="text-sm text-muted-foreground px-4 py-6 text-center">
              Aucun ticket sur cette période.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/40">
                    <th className="text-left px-4 py-2 font-medium">Numéro</th>
                    <th className="text-left px-4 py-2 font-medium">Date / Heure</th>
                    <th className="text-center px-4 py-2 font-medium">Mouture</th>
                    <th className="text-right px-4 py-2 font-medium">Total</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {tickets.map((t) => (
                    <tr
                      key={t.id}
                      className="border-b hover:bg-muted/30 transition-colors cursor-pointer"
                      onClick={() => setTicketDetail(t)}
                    >
                      <td className="px-4 py-2 font-mono text-green-700 dark:text-green-300">
                        {t.numero}
                      </td>
                      <td className="px-4 py-2 text-muted-foreground">
                        {new Date(t.date).toLocaleString("fr-FR", {
                          day: "2-digit",
                          month: "2-digit",
                          year: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td className="px-4 py-2 text-center">
                        {t.mouture ? (
                          <span className="text-xs bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300 px-1.5 py-0.5 rounded font-medium">
                            OUI
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right font-semibold">
                        {Number(t.montant_total).toFixed(2)} FCFA
                      </td>
                      <td className="px-4 py-2 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-xs"
                            onClick={(e) => {
                              e.stopPropagation();
                              setTicketDetail(t);
                            }}
                          >
                            Détail
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 px-2 text-xs gap-1"
                            disabled={reimpLoading}
                            onClick={(e) => {
                              e.stopPropagation();
                              reimprimer(t);
                            }}
                          >
                            <Copy className="h-3 w-3" />
                            Réimprimer
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Erreur réimpression */}
      {reimpErreur && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">
          {reimpErreur}
        </p>
      )}

      {/* Modal détail ticket */}
      {ticketDetail && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setTicketDetail(null)}
        >
          <Card
            className="w-full max-w-lg max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <CardHeader className="flex flex-row items-start justify-between pb-3">
              <div>
                <CardTitle className="text-base font-mono">
                  Ticket {ticketDetail.numero}
                </CardTitle>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {ticketDetail.lieu_nom} ·{" "}
                  {new Date(ticketDetail.date).toLocaleString("fr-FR")}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0"
                onClick={() => setTicketDetail(null)}
              >
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Lignes produits */}
              <div>
                <p className="text-xs font-semibold uppercase text-muted-foreground mb-1">
                  Produits
                </p>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/30">
                      <th className="text-left py-1 pr-2">Produit</th>
                      <th className="text-right py-1 px-2">Qté</th>
                      <th className="text-right py-1 px-2">P.U.</th>
                      <th className="text-right py-1 pl-2">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ticketDetail.lignes.map((l, i) => (
                      <tr key={i} className="border-b">
                        <td className="py-1 pr-2 truncate max-w-[160px]">
                          {l.produit_nom}
                        </td>
                        <td className="py-1 px-2 text-right">{l.quantite}</td>
                        <td className="py-1 px-2 text-right">
                          {Number(l.prix_unitaire).toFixed(2)}
                        </td>
                        <td className="py-1 pl-2 text-right font-medium">
                          {Number(l.total ?? l.quantite * l.prix_unitaire).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Section mouture */}
              {ticketDetail.mouture ? (
                <div className="border rounded-md p-3 space-y-1 bg-orange-50/50 dark:bg-orange-950/20">
                  <p className="text-xs font-semibold uppercase text-orange-700 dark:text-orange-300 mb-2">
                    Mouture
                  </p>
                  {ticketDetail.prix_mouture_kg != null &&
                    Number(ticketDetail.prix_mouture_kg) > 0 && (
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Prix/kg</span>
                        <span>{Number(ticketDetail.prix_mouture_kg).toFixed(2)} FCFA/kg</span>
                      </div>
                    )}
                  {ticketDetail.prix_mouture_tonne != null &&
                    Number(ticketDetail.prix_mouture_tonne) > 0 && (
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Prix/tonne</span>
                        <span>
                          {Number(ticketDetail.prix_mouture_tonne).toFixed(2)} FCFA/t
                        </span>
                      </div>
                    )}
                  {ticketDetail.prix_mouture_sac != null &&
                    Number(ticketDetail.prix_mouture_sac) > 0 && (
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Prix/sac</span>
                        <span>
                          {Number(ticketDetail.prix_mouture_sac).toFixed(2)} FCFA/sac
                        </span>
                      </div>
                    )}
                  <div className="flex justify-between text-sm font-medium border-t pt-1 mt-1">
                    <span>Coût mouture</span>
                    <span className="text-orange-700 dark:text-orange-300">
                      {Number(ticketDetail.cout_mouture).toFixed(2)} FCFA
                    </span>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Mouture : NON</p>
              )}

              {/* Totaux */}
              <div className="border-t pt-3 space-y-1">
                {ticketDetail.mouture && Number(ticketDetail.cout_mouture) > 0 && (
                  <div className="flex justify-between text-sm text-muted-foreground">
                    <span>Sous-total produits</span>
                    <span>
                      {fmt(
                        Number(ticketDetail.montant_total) -
                        Number(ticketDetail.cout_mouture)
                      )}{" "}
                      FCFA
                    </span>
                  </div>
                )}
                <div className="flex justify-between font-semibold text-base">
                  <span>TOTAL</span>
                  <span className="text-green-700 dark:text-green-300">
                    {Number(ticketDetail.montant_total).toFixed(2)} FCFA
                  </span>
                </div>
              </div>

              {/* Bouton réimpression depuis le modal détail */}
              <Button
                className="w-full gap-2"
                variant="outline"
                disabled={reimpLoading}
                onClick={() => reimprimer(ticketDetail)}
              >
                <Copy className="h-4 w-4" />
                {reimpLoading ? "Chargement…" : "Réimprimer ce ticket"}
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Modal réimpression — preview ticket + window.print() */}
      {ticketReimpression && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setTicketReimpression(null)}
        >
          <Card
            className="w-auto max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <CardHeader className="flex flex-row items-start justify-between pb-2">
              <CardTitle className="text-sm font-mono">
                Réimpression — {ticketReimpression.numero}
              </CardTitle>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0"
                onClick={() => setTicketReimpression(null)}
              >
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              <Ticket58mm
                lieuNom={ticketReimpression.lieu_nom}
                numero={ticketReimpression.numero}
                date={new Date(ticketReimpression.date).toLocaleString("fr-FR")}
                lignes={ticketReimpression.lignes}
                totalGeneral={Number(ticketReimpression.montant_total)}
                mouture={ticketReimpression.mouture}
                coutMouture={Number(ticketReimpression.cout_mouture)}
                prixMoutureKg={ticketReimpression.prix_mouture_kg ?? undefined}
                prixMoutureTonne={ticketReimpression.prix_mouture_tonne ?? undefined}
                prixMoutureSac={ticketReimpression.prix_mouture_sac ?? undefined}
                produitApporte={ticketReimpression.produit_apporte}
                copie={true}
              />
              <Button
                className="w-full gap-2 bg-green-600 hover:bg-green-700 text-white"
                onClick={() => imprimerTicket(ticketReimpression, true)}
              >
                <Printer className="h-4 w-4" />
                Imprimer
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
