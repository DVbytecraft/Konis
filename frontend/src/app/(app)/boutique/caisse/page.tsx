"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/contexts/auth-context";
import { apiFetch } from "@/lib/api";
import { openTicketPrintWindow } from "@/lib/print";
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
import { buildIdempotencyKey, cn, fmt } from "@/lib/utils";

interface ProduitWithStock {
  id: number;
  nom: string;
  code: string | null;
  unite: string;
  quantite_sac: number;
  quantite_kg: number;
  quantite_kg_total: number;
  poids_par_sac: number | null;
  has_stock: boolean;
  stock_label: string;
}

interface LignePanier {
  produit_id: number;
  produit_nom: string;
  produit_unite: string;
  unite_vente: string;
  quantite: number;
  prix_unitaire: number;
  poids_par_sac: number | null;
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
    unite?: string;
  }>;
  mouture: boolean;
  cout_mouture: number;
  prix_mouture_kg: number | null;
  prix_mouture_tonne: number | null;
  montant_total: number;
  montant_cash: number;
  montant_credit: number;
  type_vente: "cash" | "credit" | "partiel";
  client_nom: string | null;
  client_contact: string | null;
  produit_apporte?: string;
}

type TypeVente = "cash" | "credit" | "partiel";

interface ClientFinance {
  id: number;
  nom: string;
  contact: string;
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
  const [poidsSacManuel, setPoidsSacManuel] = useState<Record<number, string>>({});
  // ── Type de vente ─────────────────────────────────────────────────────────
  const [typeVente, setTypeVente] = useState<TypeVente>("cash");
  const [montantCash, setMontantCash] = useState(""); // acompte si partiel
  const [quantiteTotaleMouture, setQuantiteTotaleMouture] = useState("");
  const [uniteMouture, setUniteMouture] = useState("kg");
  const [clientId, setClientId] = useState<number | null>(null);
  const [clientSearch, setClientSearch] = useState("");
  const [clientContact, setClientContact] = useState("");
  const [clients, setClients] = useState<ClientFinance[]>([]);
  const [clientsLoading, setClientsLoading] = useState(false);
  const [showClientDropdown, setShowClientDropdown] = useState(false);
  const [showContactField, setShowContactField] = useState(false);
  const [showClientForCash, setShowClientForCash] = useState(false);

  const [ventesDuJour, setVentesDuJour] = useState<
    Array<{ id: number; numero: string; date: string; total: number }>
  >([]);

  // ── Conversion sacs → kg (depuis le stock local de la caisse) ─────────────
  const [stockConvertTarget, setStockConvertTarget] = useState<ProduitWithStock | null>(null);
  const [stockNombreSacs, setStockNombreSacs] = useState("");
  const [stockConverting, setStockConverting] = useState(false);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const isPayingRef = useRef(false); // Guard synchrone anti double-submit (F4 répété)

  const produitsFiltres = produits.filter(
    (p) =>
      p.nom.toLowerCase().includes(search.toLowerCase()) ||
      (p.code && p.code.toLowerCase().includes(search.toLowerCase()))
  );

  const getDefaultUnite = useCallback((p: ProduitWithStock) => {
    const isSac = (p.unite || "").toLowerCase().includes("sac");
    if (isSac) {
      if (p.quantite_sac > 0) return "sac";
      if (p.quantite_kg > 0) return "kg";
      return "sac";
    }
    return p.unite || "kg";
  }, []);

  const getMaxDispo = useCallback((p: ProduitWithStock, unite: string) => {
    const u = (unite || "").toLowerCase();
    if (u.includes("kg")) return p.quantite_kg_total || 0;
    if (u.includes("sac")) return p.quantite_sac || 0;
    return p.quantite_sac || 0;
  }, []);

  const chargerDonnees = useCallback(async () => {
    try {
      setLoading(true);
      interface Paginated<T> { results: T[] }
      type StockEntry = { produit: number; quantite: string; quantite_kg?: string; poids_par_sac?: string | null };
      type ProduitEntry = { id: number; nom: string; code: string | null; unite: string };
      type VenteEntry = { id: number; numero: string; date: string; montant_total?: number; lignes?: Array<{ quantite: number; prix_unitaire: number }> };
      const [produitsRes, stockRes, ventesRes] = await Promise.all([
        apiFetch<Paginated<ProduitEntry> | ProduitEntry[]>("/boutique/produits/"),
        apiFetch<Paginated<StockEntry> | StockEntry[]>("/boutique/stock/"),
        apiFetch<Paginated<VenteEntry> | VenteEntry[]>("/boutique/ventes/").catch(() => [] as VenteEntry[]),
      ]);
      const stockByProduit: Record<number, { quantite_sac: number; quantite_kg: number; poids_par_sac: number | null }> = {};
      const stockArray = Array.isArray(stockRes) ? stockRes : stockRes.results;
      stockArray.forEach((s) => {
        const quantiteSac = parseFloat(s.quantite);
        const quantiteKg = parseFloat((s.quantite_kg ?? "0") as string);
        const pps = s.poids_par_sac !== null && s.poids_par_sac !== undefined
          ? parseFloat(String(s.poids_par_sac))
          : null;
        stockByProduit[s.produit] = { quantite_sac: quantiteSac, quantite_kg: quantiteKg, poids_par_sac: pps };
      });
      const produitArray = Array.isArray(produitsRes) ? produitsRes : produitsRes.results;
      const liste = produitArray.map((p) => {
        const stock = stockByProduit[p.id] ?? { quantite_sac: 0, quantite_kg: 0, poids_par_sac: null };
        const isSac = (p.unite || "").toLowerCase().includes("sac");
        const quantiteKgTotal = isSac
          ? (stock.poids_par_sac ? stock.quantite_kg + stock.quantite_sac * stock.poids_par_sac : stock.quantite_kg)
          : stock.quantite_sac;
        const hasStock = stock.quantite_sac > 0 || stock.quantite_kg > 0;
        const stockLabel = isSac
          ? (stock.quantite_sac > 0 && stock.quantite_kg > 0)
            ? `${stock.quantite_sac} sacs + ${stock.quantite_kg} kg`
            : (stock.quantite_sac > 0)
              ? `${stock.quantite_sac} sacs`
              : (stock.quantite_kg > 0)
                ? `${stock.quantite_kg} kg`
                : "0"
          : `${stock.quantite_sac} ${p.unite}`;
        return {
          ...p,
          quantite_sac: stock.quantite_sac,
          quantite_kg: stock.quantite_kg,
          quantite_kg_total: quantiteKgTotal,
          poids_par_sac: stock.poids_par_sac,
          has_stock: hasStock,
          stock_label: stockLabel,
        };
      });
      setProduits(liste);

      const ventesList = Array.isArray(ventesRes) ? ventesRes : ventesRes.results;
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

  // Pré-remplir le prix mouture/kg depuis le défaut configuré sur le lieu (identique à la console mouture)
  useEffect(() => {
    const defaut = user?.lieu?.prix_mouture_defaut;
    if (defaut && !prixMoutureKg) {
      setPrixMoutureKg(String(defaut));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.lieu?.prix_mouture_defaut]);

  // Charger clients quand la recherche change (crédit / partiel)
  useEffect(() => {
    if (typeVente === "cash") return;
    if (!clientSearch.trim()) { setClients([]); return; }
    const t = setTimeout(async () => {
      setClientsLoading(true);
      try {
        interface ClientPage { results: ClientFinance[] }
        const res = await apiFetch<ClientPage | ClientFinance[]>(`/boutique/clients/?search=${encodeURIComponent(clientSearch)}`);
        setClients(Array.isArray(res) ? res : res.results);
      } catch { setClients([]); }
      finally { setClientsLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [clientSearch, typeVente]);

  const ajouterAuPanier = useCallback(
    (p: ProduitWithStock, qte: number = 1, prix: number = 0) => {
      if (!p.has_stock) return;
      const existant = panier.find((l) => l.produit_id === p.id);
      const uniteVente = existant?.unite_vente ?? getDefaultUnite(p);
      const maxDispo = getMaxDispo(p, uniteVente);
      if (maxDispo < 1) return;
      if (existant) {
        setPanier((prev) =>
          prev.map((l) =>
            l.produit_id === p.id
              ? {
                  ...l,
                  quantite: Math.min(l.quantite + qte, maxDispo),
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
            unite_vente: uniteVente,
            quantite: Math.min(qte, maxDispo),
            prix_unitaire: prix,
            poids_par_sac: p.poids_par_sac,
          },
        ]);
      }
      setSearch("");
      searchInputRef.current?.focus();
    },
    [panier, getDefaultUnite, getMaxDispo]
  );

  const modifierLigne = useCallback(
    (produit_id: number, field: "quantite" | "prix_unitaire" | "unite_vente", value: number | string) => {
      setPanier((prev) =>
        prev.map((l) => {
          if (l.produit_id !== produit_id) return l;
          const produit = produits.find((p) => p.id === produit_id);
          if (!produit) return { ...l, [field]: value } as LignePanier;
          if (field === "unite_vente") {
            const unite = String(value);
            const max = getMaxDispo(produit, unite);
            const newQuantite = Math.min(l.quantite, max || l.quantite);
            return { ...l, unite_vente: unite, quantite: newQuantite };
          }
          if (field === "quantite") {
            const max = getMaxDispo(produit, l.unite_vente);
            const q = Number(value) || 0;
            return { ...l, quantite: max ? Math.min(q, max) : q };
          }
          return { ...l, prix_unitaire: Number(value) || 0 };
        })
      );
    },
    [produits, getMaxDispo]
  );

  const retirerLigne = useCallback((produit_id: number) => {
    setPanier((prev) => prev.filter((l) => l.produit_id !== produit_id));
  }, []);

  const totalPanier = panier.reduce(
    (acc, l) => acc + l.quantite * l.prix_unitaire,
    0
  );

  // Calcul mouture — si quantité totale saisie manuellement, elle prime sur le panier
  // Math.round() élimine les imprécisions float (FCFA = entier, pas de centimes)
  const coutMouture = (() => {
    if (quantiteTotaleMouture && parseFloat(quantiteTotaleMouture) > 0) {
      const q = parseFloat(quantiteTotaleMouture);
      const u = uniteMouture.toLowerCase();
      if (u === "kg" && prixMoutureKg) return Math.round(q * +prixMoutureKg);
      if (u === "tonne" && prixMoutureTonne) return Math.round(q * +prixMoutureTonne);
      return 0;
    }
    return Math.round(panier.reduce((acc, l) => {
      const unite = (l.unite_vente || l.produit_unite || "").toLowerCase();
      if (unite.includes("kg") && prixMoutureKg) return acc + l.quantite * +prixMoutureKg;
      if (unite.includes("tonne") && prixMoutureTonne) return acc + l.quantite * +prixMoutureTonne;
      if (unite.includes("sac") && prixMoutureKg) {
        const pds = l.poids_par_sac ?? (parseFloat(poidsSacManuel[l.produit_id] || "0") || 0);
        if (pds > 0) return acc + l.quantite * pds * +prixMoutureKg;
      }
      return acc;
    }, 0));
  })();

  const totalGeneral = totalPanier + (mouture ? coutMouture : 0);

  const creerClient = useCallback(async (nom: string, contact: string = "") => {
    if (!nom.trim()) return;
    try {
      const res = await apiFetch<ClientFinance>("/boutique/clients/", {
        method: "POST",
        body: JSON.stringify({ nom: nom.trim(), contact: contact.trim() }),
      });
      setClientId(res.id);
      setClientSearch(res.nom);
      setClientContact(res.contact || "");
      setShowContactField(false);
      setShowClientDropdown(false);
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "Erreur création client");
    }
  }, []);

  const handleStockConvert = useCallback(async () => {
    if (!stockConvertTarget) return;
    const n = parseInt(stockNombreSacs, 10);
    if (isNaN(n) || n <= 0) return;
    setStockConverting(true);
    try {
      await apiFetch(`/boutique/stock/${stockConvertTarget.id}/convertir/`, {
        method: "POST",
        headers: { "Idempotency-Key": buildIdempotencyKey("conversion") },
        body: JSON.stringify({ nombre_sacs: n }),
      });
      setStockConvertTarget(null);
      setStockNombreSacs("");
      chargerDonnees();
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "Erreur conversion");
    } finally {
      setStockConverting(false);
    }
  }, [stockConvertTarget, stockNombreSacs, chargerDonnees]);

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
    if ((typeVente === "credit" || typeVente === "partiel") && !clientId) {
      setErreur("Sélectionnez un client pour une vente à crédit ou partielle.");
      return;
    }
    if (typeVente === "partiel" && (!montantCash || Number(montantCash) < 0)) {
      setErreur("Saisissez l'acompte (montant encaissé) pour une vente partielle.");
      return;
    }
    setErreur("");
    isPayingRef.current = true;
    setPaiementEnCours(true);
    try {
      const body: Record<string, unknown> = {
        lignes: panier.map((l) => ({
          produit: l.produit_id,
          quantite: l.quantite,
          prix_unitaire: l.prix_unitaire,
          unite: l.unite_vente,
        })),
        type_vente: typeVente,
        mouture,
        prix_mouture_kg: mouture && prixMoutureKg ? prixMoutureKg : null,
        prix_mouture_tonne: mouture && prixMoutureTonne ? prixMoutureTonne : null,
      };
      if (mouture && quantiteTotaleMouture && parseFloat(quantiteTotaleMouture) > 0) {
        body.quantite_apportee_mouture = parseFloat(quantiteTotaleMouture);
        body.unite_quantite_apportee = uniteMouture;
      }
      if (clientId) {
        body.client_id = clientId;
      }
      if (typeVente === "partiel") {
        body.montant_cash = montantCash;
      }
      const ticket = await apiFetch<TicketReponse>("/boutique/ventes/", {
        method: "POST",
        headers: { "Idempotency-Key": buildIdempotencyKey("vente") },
        body: JSON.stringify(body),
      });
      setTicketImprimer(ticket);
      setPanier([]);
      // Reset type vente après chaque vente
      setTypeVente("cash");
      setClientId(null);
      setClientSearch("");
      setClientContact("");
      setShowContactField(false);
      setShowClientForCash(false);
      setMontantCash("");
      chargerDonnees();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erreur paiement";
      // Erreur STRICT_MODE : le backend rejette les requêtes sans Idempotency-Key
      const isIdempotencyError =
        msg.includes("Idempotency-Key") ||
        msg.includes("idempotency") ||
        msg.toLowerCase().includes("clé de sécurité");
      if (isIdempotencyError) {
        setErreur("Erreur technique : impossible d'enregistrer la vente (clé de sécurité manquante). Rechargez la page et réessayez.");
      } else {
        setErreur(msg);
      }
    } finally {
      isPayingRef.current = false;
      setPaiementEnCours(false);
    }
  }, [panier, mouture, prixMoutureKg, prixMoutureTonne, quantiteTotaleMouture, uniteMouture, typeVente, clientId, montantCash, chargerDonnees]);

  const fermerTicket = useCallback(() => setTicketImprimer(null), []);

  const nouvelleVente = useCallback(() => {
    setPanier([]);
    setTicketImprimer(null);
    setErreur("");
    setMouture(false);
    setPrixMoutureKg("");
    setPrixMoutureTonne("");
    setPoidsSacManuel({});
    setQuantiteTotaleMouture("");
    setUniteMouture("kg");
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
        if (p && p.has_stock) ajouterAuPanier(p);
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
    if (!ticketImprimer) return;
    openTicketPrintWindow({
      numero: ticketImprimer.numero,
      date: new Date(ticketImprimer.date).toLocaleString("fr-FR"),
      lieu_nom: ticketImprimer.lieu_nom,
      lignes: ticketImprimer.lignes,
      montant_total: Number(ticketImprimer.montant_total),
      mouture: ticketImprimer.mouture,
      cout_mouture: Number(ticketImprimer.cout_mouture ?? 0),
      prix_mouture_kg: ticketImprimer.prix_mouture_kg ?? null,
      prix_mouture_tonne: ticketImprimer.prix_mouture_tonne ?? null,
      produit_apporte: ticketImprimer.produit_apporte,
      client_nom: ticketImprimer.client_nom,
      client_contact: ticketImprimer.client_contact,
    });
  }, [ticketImprimer]);

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
            produitApporte={ticketImprimer.produit_apporte}
            clientNom={ticketImprimer.client_nom}
            clientContact={ticketImprimer.client_contact}
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
            <Button
              variant="outline"
              type="button"
              className="w-full"
              onClick={() =>
                openTicketPrintWindow(
                  {
                    numero: ticketImprimer.numero,
                    date: new Date(ticketImprimer.date).toLocaleString("fr-FR"),
                    lieu_nom: ticketImprimer.lieu_nom,
                    lignes: lignesTicket,
                    montant_total: Number(totalGen),
                    mouture: ticketImprimer.mouture,
                    cout_mouture: Number(ticketImprimer.cout_mouture ?? 0),
                    prix_mouture_kg: ticketImprimer.prix_mouture_kg ?? null,
                    prix_mouture_tonne: ticketImprimer.prix_mouture_tonne ?? null,
                    produit_apporte: ticketImprimer.produit_apporte,
                    client_nom: ticketImprimer.client_nom,
                    client_contact: ticketImprimer.client_contact,
                  },
                  { autoPrint: false }
                )
              }
            >
              Ouvrir aperçu d&apos;impression
            </Button>
            <Button
              className="w-full"
              onClick={() => {
                fermerTicket();
                nouvelleVente();
              }}
            >
              Nouvelle vente
            </Button>
            {(ticketImprimer.type_vente === "credit" || ticketImprimer.type_vente === "partiel") &&
              ticketImprimer.client_nom && (
                <Link
                  href={`/boutique/creances?client=${encodeURIComponent(ticketImprimer.client_nom)}`}
                  className="w-full inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow-sm hover:bg-accent hover:text-accent-foreground transition-colors"
                >
                  <CreditCard className="h-4 w-4 mr-2" />
                  Journal de {ticketImprimer.client_nom}
                </Link>
            )}
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
              <span className="text-lg font-semibold text-green-700 dark:text-green-300">{fmt(caDuJour)} FCFA</span>
            </div>
            {ventesDuJour.length > 0 && (
              <ul className="text-sm max-h-24 overflow-y-auto space-y-0.5">
                {ventesDuJour.slice(0, 8).map((t) => (
                  <li key={t.id} className="flex justify-between">
                    <span className="font-mono text-green-700 dark:text-green-300">{t.numero}</span>
                    <span className="font-medium">{fmt(t.total)}</span>
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
                    <th className="py-1"></th>
                  </tr>
                </thead>
                <tbody>
                  {produits
                    .filter((p) => p.has_stock)
                    .slice(0, 10)
                    .map((p) => (
                      <tr key={p.id} className="border-b">
                        <td className="py-0.5 truncate max-w-[120px]">{p.nom}</td>
                        <td className={`py-0.5 text-right font-mono font-medium ${p.quantite_sac < 5 ? "text-red-600 dark:text-red-400" : "text-green-700 dark:text-green-300"}`}>
                          {p.stock_label}
                        </td>
                        <td className="py-0.5 pl-1">
                          {(p.poids_par_sac ?? 0) > 0 && p.quantite_sac > 0 && (
                            <button
                              type="button"
                              onClick={() => { setStockConvertTarget(p); setStockNombreSacs(""); }}
                              className="text-[10px] text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap"
                              title="Convertir sacs → kg"
                            >
                              ⇄ kg
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
              {produits.filter((p) => p.has_stock).length > 10 && (
                <p className="text-xs text-muted-foreground mt-1">
                  + {produits.filter((p) => p.has_stock).length - 10} autres
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
                        !p.has_stock && "opacity-50"
                      )}
                      onClick={() => p.has_stock && ajouterAuPanier(p)}
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
                        Stock: {p.stock_label}
                      </span>
                      {p.has_stock && (
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
                {panier.map((l) => {
                  const produitRef = produits.find((p) => p.id === l.produit_id);
                  const isSac = (produitRef?.unite || l.produit_unite || "").toLowerCase().includes("sac");
                  const canKg = isSac && ((produitRef?.quantite_kg ?? 0) > 0 || (produitRef?.poids_par_sac ?? 0) > 0);
                  return (
                    <li
                      key={l.produit_id}
                      className="flex items-center gap-2 text-sm border-b pb-2"
                    >
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">
                        {l.produit_nom}{" "}
                        <span className="text-xs font-normal text-muted-foreground bg-muted px-1.5 py-0.5 rounded-full">
                          {l.unite_vente}
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
                        {canKg ? (
                          <select
                            className="w-16 rounded border border-input px-1 py-0.5 text-xs"
                            value={l.unite_vente}
                            onChange={(e) => modifierLigne(l.produit_id, "unite_vente", e.target.value)}
                          >
                            <option value="sac">sac</option>
                            <option value="kg">kg</option>
                          </select>
                        ) : (
                          <span className="text-xs text-muted-foreground">{l.unite_vente}</span>
                        )}
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
                          = {fmt(Number(l.quantite) * Number(l.prix_unitaire))}
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
                  );
                })}
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
                  {/* Poids par sac — si produit sac sans poids défini */}
                  {mouture && panier.some((l) => {
                    const u = (l.unite_vente || l.produit_unite || "").toLowerCase();
                    return u.includes("sac") && !l.poids_par_sac;
                  }) && (
                    <div className="border border-orange-300 dark:border-orange-700 rounded p-2 space-y-1.5 bg-orange-50/40 dark:bg-orange-950/20">
                      <p className="text-xs font-medium text-orange-700 dark:text-orange-300">
                        Poids par sac (pour calcul mouture)
                      </p>
                      {panier.filter((l) => {
                        const u = (l.unite_vente || l.produit_unite || "").toLowerCase();
                        return u.includes("sac") && !l.poids_par_sac;
                      }).map((l) => (
                        <div key={l.produit_id} className="flex items-center gap-1.5">
                          <span className="text-xs text-muted-foreground flex-1 truncate">{l.produit_nom}</span>
                          <Input
                            type="number"
                            min="0.001"
                            step="0.001"
                            placeholder="kg/sac"
                            value={poidsSacManuel[l.produit_id] ?? ""}
                            onChange={(e) => setPoidsSacManuel((prev) => ({ ...prev, [l.produit_id]: e.target.value }))}
                            className="h-7 text-xs w-24"
                          />
                          <span className="text-xs text-muted-foreground">kg/sac</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {/* Quantité totale à moudre — peut dépasser ce qui est acheté */}
                  <div className="border-t border-orange-200 dark:border-orange-800 pt-2 mt-1 space-y-1">
                    <p className="text-xs text-muted-foreground font-medium">
                      Quantité totale à moudre <span className="font-normal">(si différente du panier)</span>
                    </p>
                    <div className="flex gap-1">
                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="Quantité"
                        value={quantiteTotaleMouture}
                        onChange={(e) => setQuantiteTotaleMouture(e.target.value)}
                        className="h-8 text-xs flex-1"
                      />
                      <select
                        value={uniteMouture}
                        onChange={(e) => setUniteMouture(e.target.value)}
                        className="h-8 rounded border border-input px-1.5 text-xs"
                      >
                        <option value="kg">kg</option>
                        <option value="tonne">tonne</option>
                      </select>
                    </div>
                    {quantiteTotaleMouture && parseFloat(quantiteTotaleMouture) > 0 && (
                      <p className="text-xs text-orange-600">
                        ↳ calcul basé sur {quantiteTotaleMouture} {uniteMouture}(s)
                      </p>
                    )}
                  </div>
                  {coutMouture > 0 && (
                    <>
                      <p className="text-xs text-orange-700 dark:text-orange-300 font-semibold">
                        Coût mouture calculé : {fmt(coutMouture)} FCFA
                      </p>
                      {panier.length > 0 && (
                        <div className="border-t border-orange-200 dark:border-orange-800 pt-1.5 mt-1 space-y-0.5">
                          <p className="text-xs font-semibold text-orange-600 dark:text-orange-400 mb-1">
                            Détail par produit :
                          </p>
                          {panier.map((l) => {
                            const u = (l.unite_vente || l.produit_unite || "").toLowerCase();
                            let prix = 0;
                            let label = "";
                            let kgParUnite = 1;
                            if (u.includes("kg") && prixMoutureKg) { prix = +prixMoutureKg; label = "kg"; }
                            else if (u.includes("tonne") && prixMoutureTonne) { prix = +prixMoutureTonne; label = "tonne"; }
                            else if (u.includes("sac") && prixMoutureKg) {
                              const pds = l.poids_par_sac ?? (parseFloat(poidsSacManuel[l.produit_id] || "0") || 0);
                              if (pds > 0) { prix = +prixMoutureKg; kgParUnite = pds; label = "sac"; }
                            }
                            if (!prix) return null;
                            const totalLigne = label === "sac"
                              ? l.quantite * kgParUnite * prix
                              : l.quantite * prix;
                            return (
                              <div key={l.produit_id} className="flex justify-between text-xs text-orange-700 dark:text-orange-300">
                                <span className="truncate flex-1 mr-2">
                                  {l.produit_nom}
                                  {label === "sac"
                                    ? ` (${l.quantite} sacs × ${kgParUnite} kg × ${prix}/kg)`
                                    : ` (${l.quantite} ${l.produit_unite} × ${prix}/${label})`}
                                </span>
                                <span className="shrink-0 font-medium">
                                  {fmt(totalLigne)} F
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
                        <span>{fmt(totalPanier)} FCFA</span>
                      </div>
                      <div className="flex justify-between text-sm text-orange-600 dark:text-orange-400">
                        <span>Mouture</span>
                        <span>+{fmt(coutMouture)} FCFA</span>
                      </div>
                    </>
                  )}
                  <div className="flex items-center justify-between font-semibold bg-green-50/50 dark:bg-green-950/20 -mx-3 px-3 py-2 rounded-b">
                    <span>TOTAL</span>
                    <span className="text-lg text-green-700 dark:text-green-300">{fmt(totalGeneral)} FCFA</span>
                  </div>
                </div>
                {/* Type de vente */}
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Mode de paiement</p>
                  <div className="grid grid-cols-3 gap-1.5">
                    {(["cash", "credit", "partiel"] as TypeVente[]).map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => { setTypeVente(t); setClientId(null); setClientSearch(""); setMontantCash(""); }}
                        className={cn(
                          "rounded border py-1.5 text-xs font-semibold transition-colors",
                          typeVente === t
                            ? t === "cash"
                              ? "bg-green-600 text-white border-green-600"
                              : t === "credit"
                              ? "bg-red-500 text-white border-red-500"
                              : "bg-amber-500 text-white border-amber-500"
                            : "bg-background hover:bg-muted border-input"
                        )}
                      >
                        {t === "cash" ? "Cash" : t === "credit" ? "Crédit" : "Partiel"}
                      </button>
                    ))}
                  </div>

                  {/* Fiche client (crédit/partiel = obligatoire, cash = optionnel) */}
                  {typeVente === "cash" && !showClientForCash && !clientId && (
                    <button
                      type="button"
                      className="text-xs text-blue-600 hover:underline"
                      onClick={() => setShowClientForCash(true)}
                    >
                      + Associer un client à cette vente (optionnel)
                    </button>
                  )}
                  {(typeVente === "credit" || typeVente === "partiel" || showClientForCash || clientId) && (
                    <div className="space-y-1.5">
                      {clientId ? (
                        /* ── Client sélectionné ── */
                        <div className="rounded border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-950/20 p-2 space-y-1">
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <p className="text-xs font-semibold text-green-800 dark:text-green-300">✓ {clientSearch}</p>
                              {clientContact && <p className="text-xs text-muted-foreground">{clientContact}</p>}
                            </div>
                            <button
                              type="button"
                              className="text-xs text-muted-foreground hover:text-destructive shrink-0"
                              onClick={() => { setClientId(null); setClientSearch(""); setClientContact(""); setShowContactField(false); }}
                            >
                              Changer
                            </button>
                          </div>
                          <Link
                            href={`/boutique/creances?client=${encodeURIComponent(clientSearch)}`}
                            className="text-xs text-blue-600 hover:underline"
                          >
                            → Voir journal créances
                          </Link>
                        </div>
                      ) : showContactField ? (
                        /* ── Formulaire nouveau client ── */
                        <div className="rounded border border-blue-200 dark:border-blue-800 bg-blue-50/40 dark:bg-blue-950/20 p-2 space-y-1.5">
                          <p className="text-xs font-medium">Nouveau client : <span className="font-semibold">{clientSearch}</span></p>
                          <Input
                            type="text"
                            placeholder="Contact (téléphone, email…)"
                            value={clientContact}
                            onChange={(e) => setClientContact(e.target.value)}
                            className="h-8 text-xs"
                            autoFocus
                          />
                          <div className="flex gap-1">
                            <Button size="sm" className="flex-1 h-7 text-xs" onClick={() => creerClient(clientSearch, clientContact)}>
                              Créer et sélectionner
                            </Button>
                            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setShowContactField(false)}>
                              Annuler
                            </Button>
                          </div>
                        </div>
                      ) : (
                        /* ── Recherche ── */
                        <div className="relative">
                          <Input
                            placeholder="Nom du client…"
                            value={clientSearch}
                            onChange={(e) => { setClientSearch(e.target.value); setClientId(null); setShowClientDropdown(true); }}
                            onFocus={() => setShowClientDropdown(true)}
                            className="h-8 text-xs"
                          />
                          {showClientDropdown && clientSearch.trim() && (
                            <ul className="absolute z-50 top-full left-0 right-0 mt-0.5 border rounded-md bg-popover shadow-md max-h-44 overflow-y-auto">
                              {clientsLoading ? (
                                <li className="px-3 py-2 text-xs text-muted-foreground">Chargement…</li>
                              ) : (
                                <>
                                  {clients.map((c) => (
                                    <li key={c.id} className="px-3 py-2 text-xs hover:bg-muted cursor-pointer"
                                      onMouseDown={(e) => { e.preventDefault(); setClientId(c.id); setClientSearch(c.nom); setClientContact(c.contact || ""); setShowClientDropdown(false); }}
                                    >
                                      <span className="font-medium">{c.nom}</span>
                                      {c.contact && <span className="text-muted-foreground ml-2 text-xs">{c.contact}</span>}
                                    </li>
                                  ))}
                                  <li className="px-3 py-2 text-xs text-blue-700 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/30 cursor-pointer border-t font-medium"
                                    onMouseDown={(e) => { e.preventDefault(); setShowContactField(true); setShowClientDropdown(false); }}
                                  >
                                    + Créer « {clientSearch} » avec contact…
                                  </li>
                                </>
                              )}
                            </ul>
                          )}
                        </div>
                      )}
                      {/* Annuler association client (vente cash uniquement) */}
                      {typeVente === "cash" && showClientForCash && !clientId && (
                        <button
                          type="button"
                          className="text-xs text-muted-foreground hover:text-destructive"
                          onClick={() => { setShowClientForCash(false); setClientSearch(""); setClientContact(""); setShowContactField(false); }}
                        >
                          Annuler (vente sans client)
                        </button>
                      )}
                    </div>
                  )}

                  {/* Acompte (partiel uniquement) */}
                  {typeVente === "partiel" && (
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      placeholder={`Acompte encaissé (max ${fmt(totalGeneral)} FCFA)`}
                      value={montantCash}
                      onChange={(e) => setMontantCash(e.target.value)}
                      className="h-8 text-xs"
                    />
                  )}
                </div>

                <Button
                  className={cn(
                    "w-full h-11 text-white",
                    typeVente === "cash"
                      ? "bg-green-600 hover:bg-green-700"
                      : typeVente === "credit"
                      ? "bg-red-500 hover:bg-red-600"
                      : "bg-amber-500 hover:bg-amber-600"
                  )}
                  onClick={payer}
                  disabled={paiementEnCours}
                >
                  <CreditCard className="h-4 w-4 mr-2" />
                  {paiementEnCours
                    ? "Enregistrement…"
                    : typeVente === "cash"
                    ? "Payer Cash (F4)"
                    : typeVente === "credit"
                    ? "Vente à Crédit (F4)"
                    : "Vente Partielle (F4)"}
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Modal conversion sacs → kg (stock caisse) ──────────────────────── */}
      {stockConvertTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white dark:bg-card rounded-lg shadow-xl w-full max-w-sm mx-4 p-6 space-y-4">
            <h2 className="text-base font-semibold">Convertir sacs → kg</h2>
            <p className="text-sm text-muted-foreground">
              <span className="font-medium">{stockConvertTarget.nom}</span>{" "}
              — {stockConvertTarget.quantite_sac} sac(s) disponible(s)
              {stockConvertTarget.poids_par_sac && (
                <> · {stockConvertTarget.poids_par_sac} kg/sac</>
              )}
            </p>
            {stockNombreSacs && !isNaN(parseInt(stockNombreSacs, 10)) && parseInt(stockNombreSacs, 10) > 0 && stockConvertTarget.poids_par_sac && (
              <p className="text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded p-2">
                → {(parseInt(stockNombreSacs, 10) * stockConvertTarget.poids_par_sac).toFixed(3)} kg générés
              </p>
            )}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium">
                  Nombre de sacs à convertir
                  <span className="text-muted-foreground font-normal ml-1">(max {stockConvertTarget.quantite_sac})</span>
                </label>
                <button
                  type="button"
                  onClick={() => setStockNombreSacs(String(stockConvertTarget.quantite_sac))}
                  className="text-xs text-blue-600 hover:underline"
                >
                  Tout
                </button>
              </div>
              <Input
                type="number"
                min={1}
                max={stockConvertTarget.quantite_sac}
                value={stockNombreSacs}
                onChange={(e) => setStockNombreSacs(e.target.value)}
                placeholder={`1 – ${stockConvertTarget.quantite_sac}`}
                autoFocus
              />
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => setStockConvertTarget(null)} disabled={stockConverting}>
                Annuler
              </Button>
              <Button onClick={handleStockConvert} disabled={stockConverting || !stockNombreSacs}>
                {stockConverting ? "Conversion…" : "Confirmer"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
