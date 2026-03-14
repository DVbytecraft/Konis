"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { Calculator, Printer, RotateCcw, Wheat } from "lucide-react";

import { Ticket58mm } from "@/components/caisse/ticket-58mm";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/contexts/auth-context";
import { useFetch } from "@/hooks/use-fetch";
import { apiFetch } from "@/lib/api";
import { openTicketPrintWindow } from "@/lib/print";

type Unite = "kg" | "tonne" | "sac";
type Numeric = number | string;

interface TicketMouture {
  id: number;
  numero: string;
  date: string;
  lieu_nom: string;
  lignes_count?: number;
  mouture_source?: "mouture_seule" | "vente_avec_mouture" | null;
  cout_mouture: Numeric;
  montant_total: Numeric;
  prix_mouture_kg: Numeric | null;
  prix_mouture_tonne: Numeric | null;
  prix_mouture_sac: Numeric | null;
  produit_apporte?: string;
}

interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

interface MoutureConsoleProps {
  submitPath: "/boutique/mouture-seule/" | "/factory/mouture-seule/";
  historyPath: "/boutique/mouture-seule/" | "/factory/mouture-seule/";
  roleGuard: "boutique" | "usine";
  lieuLabel: "Boutique" | "Usine";
}

const UNITE_LABELS: Record<Unite, string> = {
  kg: "Kilogrammes (kg)",
  tonne: "Tonnes",
  sac: "Sacs",
};

function toNumber(value: Numeric | null | undefined): number {
  if (value == null) return 0;
  return typeof value === "number" ? value : Number.parseFloat(value);
}

function buildIdempotencyKey(scope: "boutique" | "usine"): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${scope}-${crypto.randomUUID()}`;
  }
  return `${scope}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function MoutureConsole({
  submitPath,
  historyPath,
  roleGuard,
  lieuLabel,
}: MoutureConsoleProps) {
  const { user } = useAuth();

  const [produitApporte, setProduitApporte] = useState("");
  const [quantite, setQuantite] = useState("");
  const [unite, setUnite] = useState<Unite>("kg");
  const [prixUnitaire, setPrixUnitaire] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [createdTicket, setCreatedTicket] = useState<TicketMouture | null>(null);
  const [selectedTicket, setSelectedTicket] = useState<TicketMouture | null>(null);
  const quantiteRef = useRef<HTMLInputElement>(null);
  const submitLockRef = useRef(false);
  const imprimerTicket = useCallback((ticket: TicketMouture) => {
    openTicketPrintWindow({
      numero: ticket.numero,
      date: new Date(ticket.date).toLocaleString("fr-FR"),
      lieu_nom: ticket.lieu_nom,
      lignes: [],
      montant_total: toNumber(ticket.montant_total),
      mouture: true,
      cout_mouture: toNumber(ticket.cout_mouture),
      prix_mouture_kg: ticket.prix_mouture_kg != null ? toNumber(ticket.prix_mouture_kg) : null,
      prix_mouture_tonne: ticket.prix_mouture_tonne != null ? toNumber(ticket.prix_mouture_tonne) : null,
      prix_mouture_sac: ticket.prix_mouture_sac != null ? toNumber(ticket.prix_mouture_sac) : null,
      produit_apporte: ticket.produit_apporte,
    });
  }, []);

  const historyUrl = user?.role ? `${historyPath}?page=1&page_size=20` : null;
  const { data, loading, error: historyError, refetch, cancel } =
    useFetch<PaginatedResponse<TicketMouture>>(historyUrl);

  const historyTickets = data?.results ?? [];

  const total = useMemo(() => {
    if (!quantite || !prixUnitaire) return null;
    const q = Number.parseFloat(quantite);
    const p = Number.parseFloat(prixUnitaire);
    if (!Number.isFinite(q) || !Number.isFinite(p)) return null;
    return (q * p).toFixed(2);
  }, [prixUnitaire, quantite]);

  const resetForm = useCallback(() => {
    setProduitApporte("");
    setQuantite("");
    setUnite("kg");
    setPrixUnitaire("");
    setError("");
    setCreatedTicket(null);
    setTimeout(() => quantiteRef.current?.focus(), 50);
  }, []);

  const submit = useCallback(async () => {
    if (submitLockRef.current) return;
    setError("");
    const q = Number.parseFloat(quantite);
    const p = Number.parseFloat(prixUnitaire);
    if (!quantite || !Number.isFinite(q) || q <= 0) {
      setError("Saisir une quantité valide (> 0).");
      return;
    }
    if (!prixUnitaire || !Number.isFinite(p) || p < 0) {
      setError("Saisir un prix par unité valide.");
      return;
    }

    submitLockRef.current = true;
    setSaving(true);
    try {
      const response = await apiFetch<TicketMouture>(submitPath, {
        method: "POST",
        headers: {
          "Idempotency-Key": buildIdempotencyKey(roleGuard),
        },
        body: JSON.stringify({
          quantite,
          unite,
          prix_unitaire: prixUnitaire,
          produit_nom: produitApporte,
        }),
      });
      setCreatedTicket(response);
      refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur lors de l'enregistrement.");
    } finally {
      setSaving(false);
      submitLockRef.current = false;
    }
  }, [prixUnitaire, produitApporte, quantite, refetch, roleGuard, submitPath, unite]);

  if (roleGuard === "boutique" && user?.role !== "boutique") {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">Service Mouture</h1>
        <p className="text-sm text-muted-foreground">Accès réservé aux boutiques.</p>
      </div>
    );
  }

  if (roleGuard === "usine" && user?.role !== "usine" && user?.role !== "factory") {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">Service Mouture</h1>
        <p className="text-sm text-muted-foreground">Accès réservé aux usines.</p>
      </div>
    );
  }

  if (user?.lieu?.mouture_enabled === false) {
    return (
      <div className="space-y-4 max-w-xl mx-auto">
        <div className="flex items-center gap-2">
          <Wheat className="h-6 w-6 text-muted-foreground" />
          <h1 className="text-2xl font-semibold tracking-tight">Service Mouture</h1>
        </div>
        <div className="border rounded-lg p-6 text-center space-y-2 bg-muted/30">
          <Wheat className="h-10 w-10 mx-auto text-muted-foreground opacity-50" />
          <p className="font-medium text-muted-foreground">
            Le service de mouture n&apos;est pas activé pour ce lieu.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 max-w-5xl mx-auto">
      <div className="flex items-center gap-2">
        <Wheat className="h-6 w-6 text-green-600" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Service Mouture</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Historique exhaustif: mouture seule + mouture effectuée pendant une vente.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Calculator className="h-4 w-4" />
              Saisie de la mouture
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && (
              <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">
                {error}
              </p>
            )}

            <div className="space-y-2">
              <label className="text-sm font-medium">Produit apporté par le client</label>
              <Input
                type="text"
                placeholder="Ex: Maïs, Manioc, Sorgho..."
                value={produitApporte}
                onChange={(e) => setProduitApporte(e.target.value)}
                className="h-11 text-base"
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Unité de mesure</label>
              <div className="grid grid-cols-3 gap-2">
                {(["kg", "tonne", "sac"] as Unite[]).map((u) => (
                  <button
                    key={u}
                    type="button"
                    onClick={() => setUnite(u)}
                    className={`rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                      unite === u
                        ? "bg-green-600 text-white border-green-600"
                        : "border-input bg-background hover:bg-muted"
                    }`}
                  >
                    {u.toUpperCase()}
                  </button>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">{UNITE_LABELS[unite]}</p>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Quantité ({unite})</label>
              <Input
                ref={quantiteRef}
                type="number"
                min="0.001"
                step="0.001"
                placeholder={`Ex: 50 ${unite}`}
                value={quantite}
                onChange={(e) => setQuantite(e.target.value)}
                autoFocus
                className="h-11 text-base"
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Prix par {unite} (FCFA)</label>
              <Input
                type="number"
                min="0"
                step="0.01"
                placeholder={`Ex: 200 FCFA/${unite}`}
                value={prixUnitaire}
                onChange={(e) => setPrixUnitaire(e.target.value)}
                className="h-11 text-base"
              />
            </div>

            {total !== null && (
              <div className="border rounded-md p-3 bg-green-50/50 dark:bg-green-950/20 space-y-1">
                <div className="flex justify-between text-sm text-muted-foreground">
                  <span>
                    {quantite} {unite} × {prixUnitaire} FCFA/{unite}
                  </span>
                </div>
                <div className="flex justify-between font-bold text-lg">
                  <span>TOTAL MOUTURE</span>
                  <span className="text-green-700 dark:text-green-300">{total} FCFA</span>
                </div>
              </div>
            )}

            <Button
              className="w-full h-12 bg-green-600 hover:bg-green-700 text-white text-base gap-2"
              onClick={submit}
              disabled={saving || !quantite || !prixUnitaire}
            >
              <Wheat className="h-5 w-5" />
              {saving ? "Enregistrement..." : "Encaisser la mouture"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center justify-between">
              <span>Historique Mouture</span>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={refetch}>
                  Rafraîchir
                </Button>
                {loading && (
                  <Button variant="ghost" size="sm" onClick={cancel}>
                    Annuler
                  </Button>
                )}
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {historyError && (
              <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">
                {historyError}
              </p>
            )}
            {loading ? (
              <p className="text-sm text-muted-foreground">Chargement de l&apos;historique...</p>
            ) : historyTickets.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucune opération de mouture.</p>
            ) : (
              <div className="space-y-2 max-h-96 overflow-auto pr-1">
                {historyTickets.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className="w-full text-left border rounded-md p-3 hover:bg-muted/40"
                    onClick={() => setSelectedTicket(t)}
                  >
                    <div className="flex justify-between text-sm">
                      <span className="font-mono">{t.numero}</span>
                      <span>{new Date(t.date).toLocaleString("fr-FR")}</span>
                    </div>
                    <div className="flex justify-between mt-1 text-sm">
                      <span className="text-muted-foreground">
                        {t.mouture_source === "vente_avec_mouture"
                          ? `Mouture en vente (${t.lignes_count ?? 0} ligne(s))`
                          : (t.produit_apporte || "Mouture seule")}
                      </span>
                      <span className="font-semibold">{toNumber(t.montant_total).toFixed(2)} FCFA</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {createdTicket && (
        <Card className="border-green-200 bg-green-50/50 dark:bg-green-950/20 dark:border-green-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-green-700 dark:text-green-300">Mouture enregistrée</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <p className="text-sm">
              Ticket <span className="font-mono font-semibold">{createdTicket.numero}</span> - Total{" "}
              <span className="font-semibold">{toNumber(createdTicket.montant_total).toFixed(2)} FCFA</span>
            </p>
            <div className="flex gap-2">
              <Button className="gap-2" onClick={() => imprimerTicket(createdTicket)}>
                <Printer className="h-4 w-4" />
                Imprimer
              </Button>
              <Button variant="outline" className="gap-2" onClick={resetForm}>
                <RotateCcw className="h-4 w-4" />
                Nouvelle opération
              </Button>
              <Button variant="ghost" onClick={() => setSelectedTicket(createdTicket)}>
                Voir détail
              </Button>
            </div>
            <div className="hidden print:block">
              <Ticket58mm
                lieuNom={createdTicket.lieu_nom}
                numero={createdTicket.numero}
                date={new Date(createdTicket.date).toLocaleString("fr-FR")}
                lignes={[]}
                totalGeneral={toNumber(createdTicket.montant_total)}
                mouture
                coutMouture={toNumber(createdTicket.cout_mouture)}
                prixMoutureKg={toNumber(createdTicket.prix_mouture_kg)}
                prixMoutureTonne={toNumber(createdTicket.prix_mouture_tonne)}
                prixMoutureSac={toNumber(createdTicket.prix_mouture_sac)}
                produitApporte={createdTicket.produit_apporte}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {selectedTicket && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between">
              <span>Détail Mouture</span>
              <Button variant="ghost" size="sm" onClick={() => setSelectedTicket(null)}>
                Fermer
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <p>
              <span className="text-muted-foreground">Ticket:</span> <span className="font-mono">{selectedTicket.numero}</span>
            </p>
            <p>
              <span className="text-muted-foreground">{lieuLabel}:</span> {selectedTicket.lieu_nom}
            </p>
            <p>
              <span className="text-muted-foreground">Date:</span>{" "}
              {new Date(selectedTicket.date).toLocaleString("fr-FR")}
            </p>
            <p>
              <span className="text-muted-foreground">Type:</span>{" "}
              {selectedTicket.mouture_source === "vente_avec_mouture" ? "Vente avec mouture" : "Mouture seule"}
            </p>
            <p>
              <span className="text-muted-foreground">Produit apporté:</span>{" "}
              {selectedTicket.mouture_source === "vente_avec_mouture"
                ? "N/A (vente de produits)"
                : (selectedTicket.produit_apporte || "Non renseigné")}
            </p>
            <p className="font-semibold pt-2">
              Total: {toNumber(selectedTicket.montant_total).toFixed(2)} FCFA
            </p>
          </CardContent>
        </Card>
      )}

      {roleGuard === "usine" && (
        <Card className="bg-muted/20">
          <CardContent className="py-4 text-sm text-muted-foreground">
            Impact stock usine: une mouture-seule n&apos;effectue aucun débit de stock produit fini. La traçabilité passe par ticket
            et journal d&apos;audit.
          </CardContent>
        </Card>
      )}
    </div>
  );
}
