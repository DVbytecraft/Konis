"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Banknote, History, Package, RefreshCw, Trash2, X } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Lieu {
  id: number;
  nom: string;
  code: string;
}

interface Produit {
  id: number;
  nom: string;
  code: string;
  unite: string;
}

interface CorrectionHistorique {
  id: number;
  montant: string;
  motif: string;
  created_by: string;
  created_at: string;
}

interface Ticket {
  id: number;
  numero: string;
  montant_total: string;
  montant_cash: string;
  montant_credit: string;
  date: string;
  type_vente: string;
}

type Tab = "caisse" | "stock" | "ticket";

// ── Composant principal ───────────────────────────────────────────────────────

export default function AdminCorrectionsPage() {
  const [tab, setTab] = useState<Tab>("caisse");
  const [boutiques, setBoutiques] = useState<Lieu[]>([]);
  const [produits, setProduits] = useState<Produit[]>([]);

  // Chargement des listes au montage
  useEffect(() => {
    apiFetch<{ results?: Lieu[]; count?: number } | Lieu[]>("/admin/lieux/?type_lieu=magasin")
      .then((d) => setBoutiques(Array.isArray(d) ? d : (d as { results: Lieu[] }).results ?? []))
      .catch(() => {});

    apiFetch<{ results?: Produit[] } | Produit[]>("/admin/produits/")
      .then((d) => setProduits(Array.isArray(d) ? d : (d as { results: Produit[] }).results ?? []))
      .catch(() => {});
  }, []);

  return (
    <div className="space-y-6 min-w-0">
      {/* En-tête */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-amber-500" />
          Corrections d&apos;urgence
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Actions irréversibles réservées aux administrateurs. Chaque opération est auditée.
        </p>
      </div>

      {/* Onglets */}
      <div className="flex gap-1 border-b">
        {([
          { key: "caisse", label: "Caisse", icon: Banknote },
          { key: "stock",  label: "Stock",  icon: Package },
          { key: "ticket", label: "Annuler ticket", icon: Trash2 },
        ] as { key: Tab; label: string; icon: React.ComponentType<{ className?: string }> }[]).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === key
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Contenu par onglet */}
      {tab === "caisse" && <CorrectionCaisse boutiques={boutiques} />}
      {tab === "stock"  && <CorrectionStock  boutiques={boutiques} produits={produits} />}
      {tab === "ticket" && <AnnulerTicket    boutiques={boutiques} />}
    </div>
  );
}

// ── Section 1 : Correction Caisse ─────────────────────────────────────────────

function CorrectionCaisse({ boutiques }: { boutiques: Lieu[] }) {
  const [lieuId, setLieuId]         = useState("");
  const [montant, setMontant]       = useState("");
  const [operation, setOperation]   = useState<"ajouter" | "retrancher">("ajouter");
  const [motif, setMotif]           = useState("");
  const [loading, setLoading]       = useState(false);
  const [result, setResult]         = useState<Record<string, string> | null>(null);
  const [error, setError]           = useState<string | null>(null);
  const [caisse, setCaisse]         = useState<string | null>(null);
  const [historique, setHistorique] = useState<CorrectionHistorique[]>([]);
  const [loadingInfo, setLoadingInfo] = useState(false);

  const loadHistorique = useCallback(async (lid: string) => {
    if (!lid) { setCaisse(null); setHistorique([]); return; }
    setLoadingInfo(true);
    try {
      const d = await apiFetch<{ caisse_physique: string; corrections: CorrectionHistorique[] }>(
        `/admin/corrections/historique/?lieu_id=${lid}`
      );
      setCaisse(d.caisse_physique);
      setHistorique(d.corrections);
    } catch {
      setCaisse(null); setHistorique([]);
    } finally {
      setLoadingInfo(false);
    }
  }, []);

  const handleLieu = (lid: string) => {
    setLieuId(lid);
    setResult(null);
    setError(null);
    loadHistorique(lid);
  };

  const reset = () => {
    setMontant(""); setOperation("ajouter"); setMotif("");
    setResult(null); setError(null);
    if (lieuId) loadHistorique(lieuId);
  };

  const submit = async () => {
    if (!lieuId || !montant || !motif.trim()) {
      setError("Tous les champs sont requis."); return;
    }
    setLoading(true); setError(null); setResult(null);
    try {
      const data = await apiFetch<Record<string, string>>("/admin/corrections/caisse/", {
        method: "POST",
        body: JSON.stringify({ lieu_id: Number(lieuId), montant, operation, motif }),
      });
      setResult(data);
      // Rafraîchir le solde et l'historique
      loadHistorique(lieuId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la correction.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3 pt-4 px-4">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Banknote className="h-4 w-4 text-blue-500" />
            Corriger le solde caisse d&apos;une boutique
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-5 space-y-4">
          {/* Sélection boutique + solde courant */}
          <div className="max-w-md space-y-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Boutique</label>
              <select
                value={lieuId}
                onChange={(e) => handleLieu(e.target.value)}
                className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Sélectionner…</option>
                {boutiques.map((l) => (
                  <option key={l.id} value={l.id}>{l.nom} ({l.code})</option>
                ))}
              </select>
            </div>

            {/* Solde courant */}
            {lieuId && (
              <div className={cn(
                "rounded-md border px-4 py-3 flex items-center justify-between",
                caisse !== null
                  ? parseFloat(caisse) >= 0
                    ? "bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800"
                    : "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800"
                  : "bg-muted/40 border-border"
              )}>
                <span className="text-sm text-muted-foreground">Caisse physique actuelle</span>
                {loadingInfo ? (
                  <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" />
                ) : caisse !== null ? (
                  <span className={cn(
                    "text-lg font-bold",
                    parseFloat(caisse) >= 0 ? "text-blue-700 dark:text-blue-300" : "text-red-700 dark:text-red-300"
                  )}>
                    {parseFloat(caisse).toLocaleString("fr-FR")} FCFA
                  </span>
                ) : (
                  <span className="text-sm text-muted-foreground">—</span>
                )}
              </div>
            )}
          </div>

          {result ? (
            <div className="space-y-3 max-w-md">
              <div className="rounded bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 p-4 text-sm space-y-1">
                <p className="font-semibold text-green-800 dark:text-green-300">Correction appliquée</p>
                <p><span className="text-muted-foreground">Opération :</span> {result.operation}</p>
                <p><span className="text-muted-foreground">Montant :</span> {parseFloat(result.montant).toLocaleString("fr-FR")} FCFA</p>
                <p><span className="text-muted-foreground">Caisse avant :</span> {parseFloat(result.caisse_avant).toLocaleString("fr-FR")} FCFA</p>
                <p><span className="text-muted-foreground">Caisse après :</span> <strong>{parseFloat(result.caisse_apres).toLocaleString("fr-FR")} FCFA</strong></p>
                <p><span className="text-muted-foreground">Motif :</span> {result.motif}</p>
              </div>
              <Button variant="outline" size="sm" onClick={reset}>Nouvelle correction</Button>
            </div>
          ) : (
            <div className="space-y-3 max-w-md">
              <div>
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Opération</label>
                <div className="flex gap-2 mt-1">
                  {(["ajouter", "retrancher"] as const).map((op) => (
                    <button
                      key={op}
                      onClick={() => setOperation(op)}
                      className={cn(
                        "flex-1 h-9 rounded-md text-sm font-medium border transition-colors",
                        operation === op
                          ? op === "ajouter"
                            ? "bg-green-600 text-white border-green-600"
                            : "bg-red-600 text-white border-red-600"
                          : "bg-background border-input hover:bg-accent"
                      )}
                    >
                      {op === "ajouter" ? "+ Ajouter" : "− Retrancher"}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Montant (FCFA)</label>
                <input
                  type="number" min="0" step="1"
                  value={montant}
                  onChange={(e) => setMontant(e.target.value)}
                  placeholder="ex: 5000"
                  className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Motif (obligatoire)</label>
                <input
                  type="text"
                  value={motif}
                  onChange={(e) => setMotif(e.target.value)}
                  placeholder="Raison de la correction…"
                  className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              {error && (
                <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{error}</p>
              )}

              <Button onClick={submit} disabled={loading || !lieuId} className="w-full sm:w-auto">
                {loading ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Banknote className="h-4 w-4 mr-2" />}
                Appliquer la correction caisse
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Historique des corrections */}
      {lieuId && (
        <Card>
          <CardHeader className="pb-3 pt-4 px-4">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <History className="h-4 w-4 text-muted-foreground" />
              Historique des corrections caisse
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            {loadingInfo ? (
              <p className="text-sm text-muted-foreground">Chargement…</p>
            ) : historique.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucune correction enregistrée.</p>
            ) : (
              <div className="border rounded-md overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr className="text-xs text-muted-foreground uppercase tracking-wide">
                      <th className="text-left px-3 py-2 font-medium">Date</th>
                      <th className="text-right px-3 py-2 font-medium">Montant</th>
                      <th className="text-left px-3 py-2 font-medium">Motif</th>
                      <th className="text-left px-3 py-2 font-medium">Par</th>
                    </tr>
                  </thead>
                  <tbody>
                    {historique.map((c) => {
                      const val = parseFloat(c.montant);
                      return (
                        <tr key={c.id} className="border-t">
                          <td className="px-3 py-2 text-muted-foreground text-xs whitespace-nowrap">{c.created_at}</td>
                          <td className={cn(
                            "px-3 py-2 text-right font-semibold whitespace-nowrap",
                            val >= 0 ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"
                          )}>
                            {val >= 0 ? "+" : ""}{val.toLocaleString("fr-FR")} FCFA
                          </td>
                          <td className="px-3 py-2 text-xs">{c.motif}</td>
                          <td className="px-3 py-2 text-xs text-muted-foreground">{c.created_by}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Section 2 : Correction Stock ──────────────────────────────────────────────

function CorrectionStock({ boutiques, produits }: { boutiques: Lieu[]; produits: Produit[] }) {
  const [lieuId, setLieuId]       = useState("");
  const [produitId, setProduitId] = useState("");
  const [quantite, setQuantite]   = useState("");
  const [operation, setOperation] = useState<"ajouter" | "retrancher" | "supprimer">("ajouter");
  const [motif, setMotif]         = useState("");
  const [loading, setLoading]     = useState(false);
  const [result, setResult]       = useState<Record<string, string> | null>(null);
  const [error, setError]         = useState<string | null>(null);

  const reset = () => {
    setLieuId(""); setProduitId(""); setQuantite(""); setOperation("ajouter"); setMotif("");
    setResult(null); setError(null);
  };

  const submit = async () => {
    if (!lieuId || !produitId || !motif.trim()) {
      setError("Boutique, produit et motif sont requis."); return;
    }
    if (operation !== "supprimer" && !quantite) {
      setError("La quantité est requise pour cette opération."); return;
    }
    setLoading(true); setError(null); setResult(null);
    try {
      const body: Record<string, unknown> = {
        lieu_id: Number(lieuId),
        produit_id: Number(produitId),
        operation,
        motif,
      };
      if (operation !== "supprimer") body.quantite = quantite;

      const data = await apiFetch<Record<string, string>>("/admin/corrections/stock/", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la correction.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3 pt-4 px-4">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <Package className="h-4 w-4 text-amber-500" />
          Corriger le stock d&apos;un produit dans une boutique
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-5 space-y-4">
        {result ? (
          <div className="space-y-3">
            <div className="rounded bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 p-4 text-sm space-y-1">
              <p className="font-semibold text-green-800 dark:text-green-300">Correction appliquée</p>
              <p><span className="text-muted-foreground">Boutique :</span> {result.lieu_nom}</p>
              <p><span className="text-muted-foreground">Produit :</span> {result.produit_nom}</p>
              <p><span className="text-muted-foreground">Opération :</span> {result.operation}</p>
              <p><span className="text-muted-foreground">Quantité avant :</span> {result.quantite_avant}</p>
              <p><span className="text-muted-foreground">Quantité après :</span> <strong>{result.quantite_apres}</strong></p>
              <p><span className="text-muted-foreground">Motif :</span> {result.motif}</p>
            </div>
            <Button variant="outline" size="sm" onClick={reset}>Nouvelle correction</Button>
          </div>
        ) : (
          <div className="space-y-3 max-w-md">
            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Boutique</label>
              <select
                value={lieuId}
                onChange={(e) => setLieuId(e.target.value)}
                className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Sélectionner…</option>
                {boutiques.map((l) => (
                  <option key={l.id} value={l.id}>{l.nom} ({l.code})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Produit</label>
              <select
                value={produitId}
                onChange={(e) => setProduitId(e.target.value)}
                className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Sélectionner…</option>
                {produits.map((p) => (
                  <option key={p.id} value={p.id}>{p.nom} ({p.code})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Opération</label>
              <div className="flex gap-2 mt-1">
                {(["ajouter", "retrancher", "supprimer"] as const).map((op) => (
                  <button
                    key={op}
                    onClick={() => setOperation(op)}
                    className={cn(
                      "flex-1 h-9 rounded-md text-sm font-medium border transition-colors",
                      operation === op
                        ? op === "ajouter"
                          ? "bg-green-600 text-white border-green-600"
                          : op === "retrancher"
                          ? "bg-amber-500 text-white border-amber-500"
                          : "bg-red-600 text-white border-red-600"
                        : "bg-background border-input hover:bg-accent"
                    )}
                  >
                    {op === "ajouter" ? "+ Ajouter" : op === "retrancher" ? "− Retrancher" : "✕ Vider"}
                  </button>
                ))}
              </div>
            </div>

            {operation !== "supprimer" && (
              <div>
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Quantité</label>
                <input
                  type="number" min="0" step="0.01"
                  value={quantite}
                  onChange={(e) => setQuantite(e.target.value)}
                  placeholder="ex: 10"
                  className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            )}

            {operation === "supprimer" && (
              <p className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 px-3 py-2 rounded">
                Cette opération remettra le stock à zéro pour ce produit dans cette boutique.
              </p>
            )}

            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Motif (obligatoire)</label>
              <input
                type="text"
                value={motif}
                onChange={(e) => setMotif(e.target.value)}
                placeholder="Raison de la correction…"
                className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{error}</p>
            )}

            <Button onClick={submit} disabled={loading} className="w-full sm:w-auto">
              {loading ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Package className="h-4 w-4 mr-2" />}
              Appliquer la correction stock
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Section 3 : Annuler un ticket ─────────────────────────────────────────────

function AnnulerTicket({ boutiques }: { boutiques: Lieu[] }) {
  const [lieuId, setLieuId]           = useState("");
  const [tickets, setTickets]         = useState<Ticket[]>([]);
  const [loadingTickets, setLoadingTickets] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [motif, setMotif]             = useState("");
  const [loading, setLoading]         = useState(false);
  const [result, setResult]           = useState<Record<string, string> | null>(null);
  const [error, setError]             = useState<string | null>(null);

  const loadTickets = useCallback(async (lid: string) => {
    if (!lid) { setTickets([]); return; }
    setLoadingTickets(true);
    try {
      const d = await apiFetch<{ results?: Ticket[] } | Ticket[]>(`/admin/tickets/?lieu=${lid}`);
      setTickets(Array.isArray(d) ? d : (d as { results: Ticket[] }).results ?? []);
    } catch {
      setTickets([]);
    } finally {
      setLoadingTickets(false);
    }
  }, []);

  const handleLieu = (lid: string) => {
    setLieuId(lid);
    setSelectedTicket(null);
    setTickets([]);
    loadTickets(lid);
  };

  const reset = () => {
    setLieuId(""); setTickets([]); setSelectedTicket(null);
    setMotif(""); setResult(null); setError(null);
  };

  const submit = async () => {
    if (!selectedTicket || !motif.trim()) {
      setError("Sélectionnez un ticket et saisissez un motif."); return;
    }
    setLoading(true); setError(null); setResult(null);
    try {
      const data = await apiFetch<Record<string, string>>(
        `/admin/corrections/ticket/${selectedTicket.id}/`,
        { method: "POST", body: JSON.stringify({ motif }) }
      );
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de l'annulation.");
    } finally {
      setLoading(false);
    }
  };

  if (result) {
    return (
      <Card>
        <CardContent className="px-4 py-5 space-y-3">
          <div className="rounded bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 p-4 text-sm space-y-1">
            <p className="font-semibold text-green-800 dark:text-green-300">Ticket supprimé</p>
            <p><span className="text-muted-foreground">Numéro :</span> {result.ticket_numero}</p>
            <p><span className="text-muted-foreground">Boutique :</span> {result.lieu_nom}</p>
            <p><span className="text-muted-foreground">Montant supprimé :</span> {parseFloat(result.montant_total).toLocaleString("fr-FR")} FCFA</p>
            <p><span className="text-muted-foreground">Cash retiré de la caisse :</span> {parseFloat(result.montant_cash).toLocaleString("fr-FR")} FCFA</p>
            <p><span className="text-muted-foreground">Motif :</span> {result.motif}</p>
          </div>
          <Button variant="outline" size="sm" onClick={reset}>Nouvelle annulation</Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3 pt-4 px-4">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <Trash2 className="h-4 w-4 text-red-500" />
          Annuler un ticket de vente
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-5 space-y-4">
        <div className="max-w-md space-y-3">
          {/* Sélection boutique */}
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Boutique</label>
            <select
              value={lieuId}
              onChange={(e) => handleLieu(e.target.value)}
              className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">Sélectionner une boutique…</option>
              {boutiques.map((l) => (
                <option key={l.id} value={l.id}>{l.nom} ({l.code})</option>
              ))}
            </select>
          </div>
        </div>

        {/* Liste tickets */}
        {lieuId && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {loadingTickets ? "Chargement…" : `${tickets.length} ticket(s) récents — cliquez pour sélectionner`}
            </p>

            {!loadingTickets && tickets.length === 0 && (
              <p className="text-sm text-muted-foreground">Aucun ticket trouvé pour cette boutique.</p>
            )}

            {!loadingTickets && tickets.length > 0 && (
              <div className="border rounded-md overflow-hidden max-h-64 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr className="text-xs text-muted-foreground uppercase tracking-wide">
                      <th className="text-left px-3 py-2 font-medium">Numéro</th>
                      <th className="text-right px-3 py-2 font-medium">Montant</th>
                      <th className="text-right px-3 py-2 font-medium">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tickets.map((t) => (
                      <tr
                        key={t.id}
                        onClick={() => setSelectedTicket(selectedTicket?.id === t.id ? null : t)}
                        className={cn(
                          "border-t cursor-pointer transition-colors",
                          selectedTicket?.id === t.id
                            ? "bg-red-50 dark:bg-red-950/30"
                            : "hover:bg-muted/40"
                        )}
                      >
                        <td className="px-3 py-2 font-mono text-xs">{t.numero}</td>
                        <td className="px-3 py-2 text-right font-semibold">{parseFloat(t.montant_total).toLocaleString()} FCFA</td>
                        <td className="px-3 py-2 text-right text-muted-foreground text-xs">
                          {new Date(t.date).toLocaleDateString("fr-FR")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Confirmation après sélection */}
        {selectedTicket && (
          <div className="max-w-md space-y-3 border rounded-md p-4 bg-red-50/50 dark:bg-red-950/20 border-red-200 dark:border-red-800">
            <div className="flex items-start justify-between gap-2">
              <div className="text-sm space-y-0.5">
                <p className="font-semibold text-red-800 dark:text-red-300">Ticket sélectionné</p>
                <p className="font-mono text-xs">{selectedTicket.numero}</p>
                <p className="text-muted-foreground">
                  Montant total : <strong>{parseFloat(selectedTicket.montant_total).toLocaleString()} FCFA</strong>
                  {parseFloat(selectedTicket.montant_cash) > 0 && (
                    <> · Cash : {parseFloat(selectedTicket.montant_cash).toLocaleString()} FCFA</>
                  )}
                </p>
              </div>
              <button onClick={() => setSelectedTicket(null)} className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Motif d&apos;annulation (obligatoire)</label>
              <input
                type="text"
                value={motif}
                onChange={(e) => setMotif(e.target.value)}
                placeholder="Raison de l'annulation…"
                className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">{error}</p>
            )}

            <Button
              onClick={submit}
              disabled={loading || !motif.trim()}
              variant="destructive"
              className="w-full"
            >
              {loading
                ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                : <Trash2 className="h-4 w-4 mr-2" />
              }
              Confirmer l&apos;annulation du ticket
            </Button>
          </div>
        )}

        {error && !selectedTicket && (
          <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded max-w-md">{error}</p>
        )}
      </CardContent>
    </Card>
  );
}
