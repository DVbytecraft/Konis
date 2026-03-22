"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { apiFetch } from "@/lib/api";
import { buildIdempotencyKey, fmt } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { AlertCircle, CheckCircle2, RefreshCw, Search, Users, CreditCard } from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Paiement {
  id: number;
  montant: string;
  date: string;
  mode_paiement: string;
  mode_paiement_display: string;
  notes: string;
  created_at: string;
  created_by_username: string | null;
}

interface Creance {
  id: number;
  client: number;
  client_nom: string;
  lieu_nom: string | null;
  ticket_numero: string | null;
  reference: string;
  description: string;
  montant_initial: string;
  montant_paye: string;
  montant_restant: string;
  statut: "en_cours" | "solde";
  statut_display: string;
  date_echeance: string | null;
  notes: string;
  created_at: string;
  paiements: Paiement[];
}

interface Paginated<T> {
  results: T[];
  count: number;
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function CreancesBoutiquePage() {
  const { user } = useAuth();
  const lieuNom = user?.lieu?.nom ?? "Boutique";

  const [creances, setCreances] = useState<Creance[]>([]);
  const [loading, setLoading] = useState(true);
  const [erreur, setErreur] = useState("");
  const [filtre, setFiltre] = useState<"en_cours" | "solde" | "tous">("en_cours");
  const [searchClient, setSearchClient] = useState("");

  // Pré-remplir la recherche depuis ?client= (ex: lien depuis la caisse)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const client = params.get("client");
    if (client) { setSearchClient(client); setFiltre("tous"); }
  }, []);

  // ── Modal paiement ─────────────────────────────────────────────────────────
  const [selected, setSelected] = useState<Creance | null>(null);
  const [montantPaiement, setMontantPaiement] = useState("");
  const [datePaiement, setDatePaiement] = useState(() =>
    new Date().toISOString().slice(0, 10)
  );
  const [modePaiement, setModePaiement] = useState("especes");
  const [notesPaiement, setNotesPaiement] = useState("");
  const [payEnCours, setPayEnCours] = useState(false);
  const [payErreur, setPayErreur] = useState("");

  const charger = useCallback(async () => {
    try {
      setLoading(true);
      setErreur("");
      const params = filtre !== "tous" ? `?statut=${filtre}` : "";
      const res = await apiFetch<Paginated<Creance> | Creance[]>(
        `/boutique/creances/${params}`
      );
      setCreances(Array.isArray(res) ? res : res.results);
    } catch {
      setErreur("Impossible de charger les créances.");
    } finally {
      setLoading(false);
    }
  }, [filtre]);

  useEffect(() => {
    charger();
  }, [charger]);

  const ouvrirModal = (c: Creance) => {
    setSelected(c);
    setMontantPaiement(c.montant_restant);
    setDatePaiement(new Date().toISOString().slice(0, 10));
    setModePaiement("especes");
    setNotesPaiement("");
    setPayErreur("");
  };

  const fermerModal = () => {
    setSelected(null);
    setPayErreur("");
  };

  const enregistrerPaiement = async () => {
    if (!selected) return;
    const montant = parseFloat(montantPaiement);
    if (!montant || montant <= 0) {
      setPayErreur("Saisissez un montant valide.");
      return;
    }
    if (montant > parseFloat(selected.montant_restant)) {
      setPayErreur(
        `Le montant dépasse le restant dû (${fmt(parseFloat(selected.montant_restant))} FCFA).`
      );
      return;
    }
    setPayEnCours(true);
    setPayErreur("");
    try {
      await apiFetch(`/boutique/creances/${selected.id}/paiement/`, {
        method: "POST",
        headers: { "Idempotency-Key": buildIdempotencyKey("paiement-creance") },
        body: JSON.stringify({
          montant: montantPaiement,
          date: datePaiement,
          mode_paiement: modePaiement,
          notes: notesPaiement,
        }),
      });
      fermerModal();
      charger();
    } catch (e) {
      setPayErreur(e instanceof Error ? e.message : "Erreur lors du paiement.");
    } finally {
      setPayEnCours(false);
    }
  };

  const creancesFiltrees = searchClient.trim()
    ? creances.filter((c) =>
        c.client_nom.toLowerCase().includes(searchClient.toLowerCase())
      )
    : creances;

  const totalRestant = creancesFiltrees
    .filter((c) => c.statut === "en_cours")
    .reduce((a, c) => a + parseFloat(c.montant_restant), 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Users className="h-6 w-6 text-amber-500" />
            Créances clients — {lieuNom}
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Ventes à crédit et paiements en attente
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={charger}>
          <RefreshCw className="h-4 w-4 mr-2" /> Actualiser
        </Button>
      </div>

      {/* Filtre statut */}
      <div className="flex gap-2">
        {(["en_cours", "solde", "tous"] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFiltre(f)}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-semibold border transition-colors",
              filtre === f
                ? f === "en_cours"
                  ? "bg-amber-500 text-white border-amber-500"
                  : f === "solde"
                  ? "bg-green-600 text-white border-green-600"
                  : "bg-primary text-primary-foreground border-primary"
                : "bg-background hover:bg-muted border-input"
            )}
          >
            {f === "en_cours" ? "En cours" : f === "solde" ? "Soldées" : "Toutes"}
          </button>
        ))}
      </div>

      {/* Recherche client */}
      <div className="relative max-w-xs">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          placeholder="Filtrer par client…"
          value={searchClient}
          onChange={(e) => setSearchClient(e.target.value)}
          className="pl-8 h-8 text-sm"
        />
      </div>

      {/* Total restant */}
      {filtre !== "solde" && totalRestant > 0 && (
        <div className="flex items-center gap-2 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-md px-4 py-2">
          <AlertCircle className="h-4 w-4 text-amber-500 shrink-0" />
          <p className="text-sm font-medium text-amber-700 dark:text-amber-300">
            Total à encaisser : <strong>{fmt(totalRestant)} FCFA</strong>
          </p>
        </div>
      )}

      {/* Erreur */}
      {erreur && (
        <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{erreur}</p>
      )}

      {/* Liste */}
      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement…</p>
      ) : creancesFiltrees.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <CheckCircle2 className="h-8 w-8 mx-auto mb-2 text-green-400" />
          <p className="text-sm">
            {searchClient.trim()
              ? `Aucune créance pour "${searchClient}".`
              : `Aucune créance ${filtre === "en_cours" ? "en cours" : filtre === "solde" ? "soldée" : ""}.`}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {creancesFiltrees.map((c) => {
            const restant = parseFloat(c.montant_restant);
            const initial = parseFloat(c.montant_initial);
            const pct = initial > 0 ? Math.min(100, ((initial - restant) / initial) * 100) : 100;
            return (
              <Card
                key={c.id}
                className={cn(
                  "border-l-4",
                  c.statut === "en_cours" ? "border-l-amber-400" : "border-l-green-500"
                )}
              >
                <CardHeader className="pb-2 pt-4 px-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold truncate">{c.client_nom}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        {c.description || c.reference}
                        {c.ticket_numero && (
                          <span className="ml-1 font-mono text-blue-600">
                            #{c.ticket_numero}
                          </span>
                        )}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full",
                        c.statut === "en_cours"
                          ? "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                          : "bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-300"
                      )}
                    >
                      {c.statut_display}
                    </span>
                  </div>
                </CardHeader>
                <CardContent className="px-4 pb-4 space-y-2">
                  {/* Montants */}
                  <div className="grid grid-cols-3 gap-2 text-sm">
                    <div>
                      <p className="text-xs text-muted-foreground">Total</p>
                      <p className="font-semibold">{fmt(initial)} F</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Payé</p>
                      <p className="font-semibold text-green-600">
                        {fmt(parseFloat(c.montant_paye))} F
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Restant</p>
                      <p className={cn("font-bold", restant > 0 ? "text-amber-600 dark:text-amber-400" : "text-green-600")}>
                        {fmt(restant)} F
                      </p>
                    </div>
                  </div>

                  {/* Barre progression */}
                  <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        pct >= 100 ? "bg-green-500" : "bg-amber-400"
                      )}
                      style={{ width: `${pct}%` }}
                    />
                  </div>

                  {/* Paiements existants */}
                  {c.paiements.length > 0 && (
                    <details className="text-xs">
                      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                        {c.paiements.length} paiement{c.paiements.length > 1 ? "s" : ""} enregistré{c.paiements.length > 1 ? "s" : ""}
                      </summary>
                      <ul className="mt-1 space-y-0.5 pl-2 border-l-2 border-muted ml-1">
                        {c.paiements.map((p) => (
                          <li key={p.id} className="py-0.5">
                            <div className="flex justify-between gap-2 text-muted-foreground">
                              <span>{new Date(p.date).toLocaleDateString("fr-FR")}</span>
                              <span>{p.mode_paiement_display}</span>
                              <span className="font-medium text-green-600">+{fmt(parseFloat(p.montant))} F</span>
                            </div>
                            <div className="flex gap-3 text-[10px] text-muted-foreground/70 mt-0.5">
                              {p.created_by_username && (
                                <span>Opérateur : {p.created_by_username}</span>
                              )}
                              <span>{new Date(p.created_at).toLocaleString("fr-FR")}</span>
                            </div>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}

                  {/* Bouton paiement */}
                  {c.statut === "en_cours" && (
                    <Button
                      size="sm"
                      className="w-full mt-1 bg-amber-500 hover:bg-amber-600 text-white"
                      onClick={() => ouvrirModal(c)}
                    >
                      <CreditCard className="h-3.5 w-3.5 mr-1.5" />
                      Enregistrer un paiement
                    </Button>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Modal paiement */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <Card className="w-full max-w-sm">
            <CardHeader>
              <CardTitle className="text-base">
                Paiement — {selected.client_nom}
              </CardTitle>
              <p className="text-sm text-muted-foreground">
                Restant dû :{" "}
                <strong className="text-amber-600">
                  {fmt(parseFloat(selected.montant_restant))} FCFA
                </strong>
              </p>
            </CardHeader>
            <CardContent className="space-y-3">
              {payErreur && (
                <p className="text-sm text-destructive bg-destructive/10 px-2 py-1 rounded">
                  {payErreur}
                </p>
              )}

              <div className="space-y-1">
                <label className="text-xs font-medium">Montant reçu (FCFA)</label>
                <Input
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={montantPaiement}
                  onChange={(e) => setMontantPaiement(e.target.value)}
                  className="h-9"
                  autoFocus
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium">Date</label>
                <Input
                  type="date"
                  value={datePaiement}
                  onChange={(e) => setDatePaiement(e.target.value)}
                  className="h-9"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium">Mode de paiement</label>
                <select
                  value={modePaiement}
                  onChange={(e) => setModePaiement(e.target.value)}
                  className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="especes">Espèces</option>
                  <option value="mobile">Mobile Money</option>
                  <option value="cheque">Chèque</option>
                  <option value="virement">Virement</option>
                  <option value="autre">Autre</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium">Notes (optionnel)</label>
                <Input
                  placeholder="Notes…"
                  value={notesPaiement}
                  onChange={(e) => setNotesPaiement(e.target.value)}
                  className="h-9"
                />
              </div>

              <div className="flex gap-2 pt-1">
                <Button
                  className="flex-1 bg-amber-500 hover:bg-amber-600 text-white"
                  onClick={enregistrerPaiement}
                  disabled={payEnCours}
                >
                  {payEnCours ? "Enregistrement…" : "Confirmer"}
                </Button>
                <Button variant="outline" onClick={fermerModal}>
                  Annuler
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
