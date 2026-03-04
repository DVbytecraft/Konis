"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { apiFetch, djangoUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Ticket58mm } from "@/components/caisse/ticket-58mm";
import {
  Search,
  Plus,
  Trash2,
  CreditCard,
  Receipt,
  Keyboard,
  Package,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface ProduitWithStock {
  id: number;
  nom: string;
  code: string | null;
  unite: string;
  quantite_dispo: number;
}

interface LignePanier {
  produit_id: number;
  produit_nom: string;
  produit_unite: string;
  quantite: number;
  prix_unitaire: number;
}

interface TicketReponse {
  id: number;
  numero: string;
  date: string;
  lieu_nom: string;
  lignes: Array<{
    produit_nom: string;
    quantite: number;
    prix_unitaire: number;
    total: number;
  }>;
  mouture: boolean;
  cout_mouture: number;
  prix_mouture_kg: number | null;
  prix_mouture_tonne: number | null;
  prix_mouture_sac: number | null;
  montant_total: number;
  produit_apporte?: string;
}

export default function BoutiqueCaissePage() {
  const { user } = useAuth();
  const lieuNom = user?.lieu?.nom ?? "Boutique";

  const [produits, setProduits] = useState<ProduitWithStock[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [panier, setPanier] = useState<LignePanier[]>([]);
  const [paiementEnCours, setPaiementEnCours] = useState(false);
  const [erreur, setErreur] = useState("");
  const [ticketImprimer, setTicketImprimer] = useState<TicketReponse | null>(null);
  const [mouture, setMouture] = useState(false);
  const [prixMoutureKg, setPrixMoutureKg] = useState("");
  const [prixMoutureTonne, setPrixMoutureTonne] = useState("");
  const [prixMoutureSac, setPrixMoutureSac] = useState("");
  const [ventesDuJour, setVentesDuJour] = useState<
    Array<{ id: number; numero: string; date: string; total: number }>
  >([]);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const isPayingRef = useRef(false); // Guard synchrone anti double-submit (F4 répété)

  const produitsFiltres = produits.filter(
    (p) =>
      p.nom.toLowerCase().includes(search.toLowerCase()) ||
      (p.code && p.code.toLowerCase().includes(search.toLowerCase()))
  );

  const chargerDonnees = useCallback(async () => {
    try {
      setLoading(true);
      const [produitsRes, stockRes, ventesRes] = await Promise.all([
        apiFetch("/boutique/produits/"),
        apiFetch("/boutique/stock/"),
        apiFetch("/boutique/ventes/").catch(() => []),
      ]);
      const stockByProduit: Record<number, number> = {};
      (stockRes.results || stockRes).forEach((s: { produit: number; quantite: string }) => {
        stockByProduit[s.produit] = parseFloat(s.quantite);
      });
      const liste = (produitsRes.results || produitsRes).map(
        (p: { id: number; nom: string; code: string | null; unite: string }) => ({
          ...p,
          quantite_dispo: stockByProduit[p.id] ?? 0,
        })
      );
      setProduits(liste);

      const ventesList = ventesRes.results ?? (Array.isArray(ventesRes) ? ventesRes : []);
      const aujourdhui = new Date().toDateString();
      const duJour = ventesList
        .filter((t: { date: string }) => new Date(t.date).toDateString() === aujourdhui)
        .map((t: {
          id: number;
          numero: string;
          date: string;
          montant_total?: number;
          lignes?: Array<{ quantite: number; prix_unitaire: number }>;
        }) => {
          const total = t.montant_total != null
            ? Number(t.montant_total)
            : (t.lignes ?? []).reduce(
                (a: number, l: { quantite: number; prix_unitaire: number }) =>
                  a + l.quantite * l.prix_unitaire,
                0
              );
          return { id: t.id, numero: t.numero, date: t.date, total };
        });
      setVentesDuJour(duJour);
    } catch {
      setErreur("Impossible de charger produits / stock");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    chargerDonnees();
  }, [chargerDonnees]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [search]);

  const ajouterAuPanier = useCallback(
    (p: ProduitWithStock, qte: number = 1, prix: number = 0) => {
      if (p.quantite_dispo < 1) return;
      const existant = panier.find((l) => l.produit_id === p.id);
      if (existant) {
        setPanier((prev) =>
          prev.map((l) =>
            l.produit_id === p.id
              ? {
                  ...l,
                  quantite: Math.min(l.quantite + qte, p.quantite_dispo),
                  prix_unitaire: l.prix_unitaire || prix,
                }
              : l
          )
        );
      } else {
        setPanier((prev) => [
          ...prev,
          {
            produit_id: p.id,
            produit_nom: p.nom,
            produit_unite: p.unite,
            quantite: Math.min(qte, p.quantite_dispo),
            prix_unitaire: prix,
          },
        ]);
      }
      setSearch("");
      searchInputRef.current?.focus();
    },
    [panier]
  );

  const modifierLigne = useCallback(
    (produit_id: number, field: "quantite" | "prix_unitaire", value: number) => {
      setPanier((prev) =>
        prev.map((l) =>
          l.produit_id === produit_id ? { ...l, [field]: value } : l
        )
      );
    },
    []
  );

  const retirerLigne = useCallback((produit_id: number) => {
    setPanier((prev) => prev.filter((l) => l.produit_id !== produit_id));
  }, []);

  const totalPanier = panier.reduce(
    (acc, l) => acc + l.quantite * l.prix_unitaire,
    0
  );

  // Calcul mouture en temps réel selon unité du produit
  const coutMouture = panier.reduce((acc, l) => {
    const unite = (l.produit_unite || "").toLowerCase();
    if (unite.includes("kg") && prixMoutureKg) return acc + l.quantite * +prixMoutureKg;
    if (unite.includes("tonne") && prixMoutureTonne) return acc + l.quantite * +prixMoutureTonne;
    if (unite.includes("sac") && prixMoutureSac) return acc + l.quantite * +prixMoutureSac;
    return acc;
  }, 0);

  const totalGeneral = totalPanier + (mouture ? coutMouture : 0);

  const payer = useCallback(async () => {
    // Guard synchrone : évite le double-submit si F4 est pressé rapidement avant re-render
    if (isPayingRef.current) return;
    if (panier.length === 0) {
      setErreur("Panier vide");
      return;
    }
    const sansPrix = panier.filter((l) => l.prix_unitaire === undefined || l.prix_unitaire === null || String(l.prix_unitaire) === "");
    if (sansPrix.length > 0) {
      setErreur("Saisir le prix pour : " + sansPrix.map((l) => l.produit_nom).join(", "));
      return;
    }
    const lignesZero = panier.filter((l) => l.prix_unitaire === 0);
    if (lignesZero.length > 0) {
      setErreur("Prix à 0 FCFA non autorisé : " + lignesZero.map((l) => l.produit_nom).join(", ") + ". Saisissez le prix réel.");
      return;
    }
    setErreur("");
    isPayingRef.current = true;
    setPaiementEnCours(true);
    try {
      const ticket = await apiFetch("/boutique/ventes/", {
        method: "POST",
        body: JSON.stringify({
          lignes: panier.map((l) => ({
            produit: l.produit_id,
            quantite: l.quantite,
            prix_unitaire: l.prix_unitaire,
          })),
          mouture,
          prix_mouture_kg: mouture && prixMoutureKg ? prixMoutureKg : null,
          prix_mouture_tonne: mouture && prixMoutureTonne ? prixMoutureTonne : null,
          prix_mouture_sac: mouture && prixMoutureSac ? prixMoutureSac : null,
        }),
      });
      setTicketImprimer(ticket);
      setPanier([]);
      chargerDonnees();
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "Erreur paiement");
    } finally {
      isPayingRef.current = false;
      setPaiementEnCours(false);
    }
  }, [panier, mouture, prixMoutureKg, prixMoutureTonne, prixMoutureSac, chargerDonnees]);

  const fermerTicket = useCallback(() => setTicketImprimer(null), []);

  const nouvelleVente = useCallback(() => {
    setPanier([]);
    setTicketImprimer(null);
    setErreur("");
    setMouture(false);
    setPrixMoutureKg("");
    setPrixMoutureTonne("");
    setPrixMoutureSac("");
    searchInputRef.current?.focus();
  }, []);

  // Raccourcis clavier
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (ticketImprimer) {
        if (e.key === "Escape") fermerTicket();
        return;
      }
      // F4 : Payer
      if (e.key === "F4") {
        e.preventDefault();
        payer();
        return;
      }
      // F2 ou Ctrl+N : Nouvelle vente
      if (e.key === "F2" || (e.ctrlKey && e.key === "n")) {
        e.preventDefault();
        nouvelleVente();
        return;
      }
      // Entrée : ajouter le produit sélectionné au panier
      if (e.key === "Enter" && !(e.target as HTMLElement).closest("input[type=\"number\"]")) {
        e.preventDefault();
        const p = produitsFiltres[selectedIndex];
        if (p && p.quantite_dispo > 0) ajouterAuPanier(p);
        return;
      }
      // Flèches : changer sélection dans la liste produits
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, produitsFiltres.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
        return;
      }
      // Échap : vider recherche ou nouvelle vente si panier vide
      if (e.key === "Escape") {
        if (search) setSearch("");
        else if (panier.length === 0) nouvelleVente();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    ticketImprimer,
    produitsFiltres,
    selectedIndex,
    search,
    panier.length,
    ajouterAuPanier,
    payer,
    nouvelleVente,
    fermerTicket,
  ]);

  const lancerImpression = useCallback(() => {
    window.print();
  }, []);

  if (user?.role !== "boutique") {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">Caisse boutique</h1>
        <p className="text-sm text-muted-foreground">
          Acces reserve aux utilisateurs boutique.
        </p>
      </div>
    );
  }

  if (ticketImprimer) {
    const totalGen = ticketImprimer.montant_total != null
      ? Number(ticketImprimer.montant_total)
      : ticketImprimer.lignes.reduce(
          (a, l) => a + Number(l.total ?? l.quantite * l.prix_unitaire),
          0
        ) + Number(ticketImprimer.cout_mouture ?? 0);
    const lignesTicket = ticketImprimer.lignes.map((l) => {
      const total = l.total ?? l.quantite * l.prix_unitaire;
      return { ...l, total: Number(total) };
    });
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 print:bg-transparent p-4">
        <div className="print:block">
          <Ticket58mm
            lieuNom={ticketImprimer.lieu_nom}
            numero={ticketImprimer.numero}
            date={new Date(ticketImprimer.date).toLocaleString("fr-FR")}
            lignes={lignesTicket}
            totalGeneral={totalGen}
            mouture={ticketImprimer.mouture}
            coutMouture={Number(ticketImprimer.cout_mouture ?? 0)}
            prixMoutureKg={ticketImprimer.prix_mouture_kg != null ? Number(ticketImprimer.prix_mouture_kg) : undefined}
            prixMoutureTonne={ticketImprimer.prix_mouture_tonne != null ? Number(ticketImprimer.prix_mouture_tonne) : undefined}
            prixMoutureSac={ticketImprimer.prix_mouture_sac != null ? Number(ticketImprimer.prix_mouture_sac) : undefined}
            produitApporte={ticketImprimer.produit_apporte}
          />
        </div>
        <Card className="print:hidden absolute bottom-4 left-1/2 -translate-x-1/2 max-w-sm w-full flex flex-col gap-3 p-4">
          <div className="text-center space-y-1">
            <p className="font-medium">Vente réussie</p>
            <p className="text-sm text-muted-foreground">
              Ticket {ticketImprimer.numero} · Total {Number(totalGen).toFixed(2)} FCFA
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <Button variant="default" className="w-full" onClick={lancerImpression}>
              Imprimer ticket thermique 80mm
            </Button>
            <a
              href={djangoUrl(`/ventes/ticket/${ticketImprimer.id}/print/`)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex"
            >
              <Button variant="outline" type="button" className="w-full">
                Ouvrir page impression (Ctrl+P pour imprimer)
              </Button>
            </a>
            <Button
              className="w-full"
              onClick={() => {
                fermerTicket();
                nouvelleVente();
              }}
            >
              Nouvelle vente
            </Button>
          </div>
          <Button variant="ghost" size="sm" onClick={fermerTicket}>
            Fermer
          </Button>
        </Card>
      </div>
    );
  }

  const caDuJour = ventesDuJour.reduce((a, t) => a + t.total, 0);

  return (
    <div className="space-y-4 min-w-0">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Caisse – {lieuNom}
          </h1>
          <p className="text-sm text-muted-foreground flex items-center gap-2 mt-0.5">
            <Keyboard className="h-3.5 w-3.5" />
            Entrée = ajouter · F4 = Payer · F2 = Nouvelle vente
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="border-l-4 border-l-green-500 bg-green-50/40 dark:bg-green-950/20">
          <CardHeader className="py-3">
            <CardTitle className="text-sm flex items-center gap-2 text-green-700 dark:text-green-300">
              <Receipt className="h-4 w-4 text-green-500" />
              Ventes du jour
            </CardTitle>
          </CardHeader>
          <CardContent className="py-0 pb-3">
            <div className="flex items-baseline gap-4 mb-2">
              <span className="text-2xl font-bold text-green-800 dark:text-green-200">{ventesDuJour.length}</span>
              <span className="text-muted-foreground">tickets</span>
              <span className="text-lg font-semibold text-green-700 dark:text-green-300">{caDuJour.toFixed(2)} FCFA</span>
            </div>
            {ventesDuJour.length > 0 && (
              <ul className="text-sm max-h-24 overflow-y-auto space-y-0.5">
                {ventesDuJour.slice(0, 8).map((t) => (
                  <li key={t.id} className="flex justify-between">
                    <span className="font-mono text-green-700 dark:text-green-300">{t.numero}</span>
                    <span className="font-medium">{t.total.toFixed(2)}</span>
                  </li>
                ))}
                {ventesDuJour.length > 8 && (
                  <li className="text-muted-foreground">…</li>
                )}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-green-400">
          <CardHeader className="py-3">
            <CardTitle className="text-sm flex items-center gap-2 text-green-700 dark:text-green-300">
              <Package className="h-4 w-4 text-green-500" />
              Stock local
            </CardTitle>
          </CardHeader>
          <CardContent className="py-0 pb-3">
            <div className="max-h-32 overflow-y-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="text-left py-1">Produit</th>
                    <th className="text-right py-1">Qté</th>
                  </tr>
                </thead>
                <tbody>
                  {produits
                    .filter((p) => p.quantite_dispo > 0)
                    .slice(0, 10)
                    .map((p) => (
                      <tr key={p.id} className="border-b">
                        <td className="py-0.5 truncate max-w-[140px]">{p.nom}</td>
                        <td className={`py-0.5 text-right font-mono font-medium ${p.quantite_dispo < 5 ? "text-red-600 dark:text-red-400" : "text-green-700 dark:text-green-300"}`}>
                          {p.quantite_dispo} {p.unite}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
              {produits.filter((p) => p.quantite_dispo > 0).length > 10 && (
                <p className="text-xs text-muted-foreground mt-1">
                  + {produits.filter((p) => p.quantite_dispo > 0).length - 10} autres
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Colonne gauche : recherche + liste produits */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Search className="h-4 w-4" />
              Recherche produit
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              ref={searchInputRef}
              placeholder="Nom ou code produit..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-10"
              autoFocus
            />
            {loading ? (
              <p className="text-sm text-muted-foreground">Chargement...</p>
            ) : (
              <ul
                className="border rounded-md divide-y max-h-[320px] overflow-y-auto"
                role="listbox"
                aria-activedescendant={produitsFiltres[selectedIndex]?.id?.toString()}
              >
                {produitsFiltres.length === 0 ? (
                  <li className="px-3 py-4 text-sm text-muted-foreground text-center">
                    Aucun produit
                  </li>
                ) : (
                  produitsFiltres.map((p, i) => (
                    <li
                      key={p.id}
                      id={p.id.toString()}
                      role="option"
                      aria-selected={i === selectedIndex}
                      className={cn(
                        "flex items-center justify-between px-3 py-2 cursor-pointer transition-colors",
                        i === selectedIndex
                          ? "bg-primary text-primary-foreground"
                          : "hover:bg-muted",
                        p.quantite_dispo < 1 && "opacity-50"
                      )}
                      onClick={() => p.quantite_dispo >= 1 && ajouterAuPanier(p)}
                    >
                      <span className="font-medium truncate flex-1">
                        {p.nom}
                        {p.code && (
                          <span className="text-muted-foreground ml-1">
                            ({p.code})
                          </span>
                        )}
                      </span>
                      <span className="text-sm shrink-0 ml-2">
                        Stock: {p.quantite_dispo} {p.unite}
                      </span>
                      {p.quantite_dispo >= 1 && (
                        <Plus className="h-4 w-4 shrink-0 ml-1 opacity-70" />
                      )}
                    </li>
                  ))
                )}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Colonne droite : panier + mouture + paiement */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Receipt className="h-4 w-4" />
              Panier
            </CardTitle>
            {panier.length > 0 && (
              <Button variant="ghost" size="sm" onClick={nouvelleVente}>
                Nouvelle vente (F2)
              </Button>
            )}
          </CardHeader>
          <CardContent className="space-y-3">
            {erreur && (
              <p className="text-sm text-destructive bg-destructive/10 px-2 py-1 rounded">
                {erreur}
              </p>
            )}

            {/* Lignes panier */}
            {panier.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                Panier vide. Recherchez un produit et appuyez sur Entrée ou cliquez.
              </p>
            ) : (
              <ul className="space-y-2 max-h-[240px] overflow-y-auto">
                {panier.map((l) => (
                  <li
                    key={l.produit_id}
                    className="flex items-center gap-2 text-sm border-b pb-2"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">
                        {l.produit_nom}{" "}
                        <span className="text-xs font-normal text-muted-foreground bg-muted px-1.5 py-0.5 rounded-full">
                          {l.produit_unite}
                        </span>
                      </p>
                      <div className="flex gap-2 mt-0.5">
                        <input
                          type="number"
                          min={0.01}
                          step={0.01}
                          value={l.quantite}
                          onChange={(e) =>
                            modifierLigne(
                              l.produit_id,
                              "quantite",
                              parseFloat(e.target.value) || 0
                            )
                          }
                          className="w-14 rounded border border-input px-1.5 py-0.5 text-xs"
                        />
                        <input
                          type="number"
                          min={0}
                          step={0.01}
                          placeholder="Prix"
                          value={l.prix_unitaire || ""}
                          onChange={(e) =>
                            modifierLigne(
                              l.produit_id,
                              "prix_unitaire",
                              parseFloat(e.target.value) || 0
                            )
                          }
                          className="w-20 rounded border border-input px-1.5 py-0.5 text-xs"
                        />
                        <span className="text-muted-foreground">
                          = {(l.quantite * l.prix_unitaire).toFixed(2)}
                        </span>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="shrink-0 h-8 w-8 text-destructive hover:text-destructive"
                      onClick={() => retirerLigne(l.produit_id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}

            {/* Section Mouture — toujours visible */}
            <div className="border rounded-md p-3 space-y-2 bg-orange-50/30 dark:bg-orange-950/10">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={mouture}
                  onChange={(e) => setMouture(e.target.checked)}
                  className="h-4 w-4 rounded border-input"
                />
                <span className="text-sm font-semibold">Mouture demandée</span>
              </label>
              {mouture && (
                <div className="grid grid-cols-1 gap-1.5 pl-6">
                  <Input
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="Prix mouture/kg (FCFA)"
                    value={prixMoutureKg}
                    onChange={(e) => setPrixMoutureKg(e.target.value)}
                    className="h-8 text-xs"
                  />
                  <Input
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="Prix mouture/tonne (FCFA)"
                    value={prixMoutureTonne}
                    onChange={(e) => setPrixMoutureTonne(e.target.value)}
                    className="h-8 text-xs"
                  />
                  <Input
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="Prix mouture/sac (FCFA)"
                    value={prixMoutureSac}
                    onChange={(e) => setPrixMoutureSac(e.target.value)}
                    className="h-8 text-xs"
                  />
                  {coutMouture > 0 && (
                    <>
                      <p className="text-xs text-orange-700 dark:text-orange-300 font-semibold">
                        Coût mouture calculé : {coutMouture.toFixed(2)} FCFA
                      </p>
                      {panier.length > 0 && (
                        <div className="border-t border-orange-200 dark:border-orange-800 pt-1.5 mt-1 space-y-0.5">
                          <p className="text-xs font-semibold text-orange-600 dark:text-orange-400 mb-1">
                            Détail par produit :
                          </p>
                          {panier.map((l) => {
                            const u = (l.produit_unite || "").toLowerCase();
                            let prix = 0;
                            let label = "";
                            if (u.includes("kg") && prixMoutureKg) { prix = +prixMoutureKg; label = "kg"; }
                            else if (u.includes("tonne") && prixMoutureTonne) { prix = +prixMoutureTonne; label = "tonne"; }
                            else if (u.includes("sac") && prixMoutureSac) { prix = +prixMoutureSac; label = "sac"; }
                            if (!prix) return null;
                            return (
                              <div key={l.produit_id} className="flex justify-between text-xs text-orange-700 dark:text-orange-300">
                                <span className="truncate flex-1 mr-2">
                                  {l.produit_nom} ({l.quantite} {l.produit_unite} × {prix}/{label})
                                </span>
                                <span className="shrink-0 font-medium">
                                  {(l.quantite * prix).toFixed(2)} F
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>

            {/* Totaux + bouton payer */}
            {panier.length > 0 && (
              <>
                <div className="border-t pt-2 space-y-1">
                  {mouture && coutMouture > 0 && (
                    <>
                      <div className="flex justify-between text-sm text-muted-foreground">
                        <span>Sous-total produits</span>
                        <span>{totalPanier.toFixed(2)} FCFA</span>
                      </div>
                      <div className="flex justify-between text-sm text-orange-600 dark:text-orange-400">
                        <span>Mouture</span>
                        <span>+{coutMouture.toFixed(2)} FCFA</span>
                      </div>
                    </>
                  )}
                  <div className="flex items-center justify-between font-semibold bg-green-50/50 dark:bg-green-950/20 -mx-3 px-3 py-2 rounded-b">
                    <span>TOTAL</span>
                    <span className="text-lg text-green-700 dark:text-green-300">{totalGeneral.toFixed(2)} FCFA</span>
                  </div>
                </div>
                <Button
                  className="w-full h-11 bg-green-600 hover:bg-green-700 text-white"
                  onClick={payer}
                  disabled={paiementEnCours}
                >
                  <CreditCard className="h-4 w-4 mr-2" />
                  {paiementEnCours ? "Enregistrement…" : "Payer (F4)"}
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
