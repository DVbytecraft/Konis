"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Calculator, Printer, RotateCcw, Wheat } from "lucide-react";

import { Ticket58mm } from "@/components/caisse/ticket-58mm";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/contexts/auth-context";
import { useFetch } from "@/hooks/use-fetch";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { openTicketPrintWindow } from "@/lib/print";

type Unite = "kg" | "tonne" | "sac";
type Numeric = number | string;

// Seuil au-delà duquel une alerte visuelle est affichée (en unités saisies)
const SEUIL_ALERTE = 1000;

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
  quantite_apportee_client: Numeric;
  produit_apporte?: string;
}

interface MoutureStats {
  aujourd_hui: { nb_tickets: number; cout_total: string; kg_apportee: string };
  "7_jours": { nb_tickets: number; cout_total: string; kg_apportee: string };
  "30_jours": { nb_tickets: number; cout_total: string; kg_apportee: string };
  prix_defaut: string | null;
  prix_max: string | null;
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
  statsPath?: "/boutique/mouture-stats/";
  roleGuard: "boutique" | "usine";
  lieuLabel: "Boutique" | "Usine";
}

const UNITE_LABELS: Record<Unite, string> = {
  kg: "Kilogrammes (kg)",
  tonne: "Tonnes",
  sac: "Sacs",
};

function toNum(value: Numeric | null | undefined): number {
  if (value == null) return 0;
  return typeof value === "number" ? value : Number.parseFloat(String(value));
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
  statsPath,
  roleGuard,
  lieuLabel,
}: MoutureConsoleProps) {
  const { user } = useAuth();

  const [produitApporte, setProduitApporte] = useState("");
  const [qteApportee, setQteApportee] = useState("");
  const [qteAchetee, setQteAchetee] = useState("");
  const [unite, setUnite] = useState<Unite>("kg");
  const [prixParKg, setPrixParKg] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [createdTicket, setCreatedTicket] = useState<TicketMouture | null>(null);
  const [selectedTicket, setSelectedTicket] = useState<TicketMouture | null>(null);

  const lastApporteeRef = useRef<number>(0);
  const lastAcheteeRef = useRef<number>(0);
  const apporteeRef = useRef<HTMLInputElement>(null);
  const submitLockRef = useRef(false);

  const historyUrl = user?.role ? `${historyPath}?page=1&page_size=20` : null;
  const { data, loading, error: historyError, refetch, cancel } =
    useFetch<PaginatedResponse<TicketMouture>>(historyUrl);
  const historyTickets = data?.results ?? [];

  // Stats dashboard (boutique uniquement)
  const { data: statsData, refetch: refetchStats } =
    useFetch<MoutureStats>(statsPath ?? null);

  // Pré-remplir le prix depuis le défaut configuré sur le lieu
  useEffect(() => {
    const defaut = user?.lieu?.prix_mouture_defaut;
    if (defaut && !prixParKg) {
      setPrixParKg(String(defaut));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.lieu?.prix_mouture_defaut]);

  const prixMax = user?.lieu?.prix_mouture_max
    ? Number(user.lieu.prix_mouture_max)
    : null;

  // Preview calcul
  const { totalQte, coutMouture } = useMemo(() => {
    const a = Number.parseFloat(qteApportee) || 0;
    const b = Number.parseFloat(qteAchetee) || 0;
    const p = Number.parseFloat(prixParKg) || 0;
    const total = a + b;
    if (total <= 0 || p < 0 || !Number.isFinite(total) || !Number.isFinite(p)) {
      return { totalQte: null, coutMouture: null };
    }
    return { totalQte: total, coutMouture: total * p };
  }, [qteApportee, qteAchetee, prixParKg]);

  const depasseSeuil = totalQte !== null && totalQte > SEUIL_ALERTE;
  const depassePrixMax =
    prixMax !== null &&
    Number.parseFloat(prixParKg) > prixMax &&
    prixParKg !== "";

  const imprimerTicket = useCallback(
    (ticket: TicketMouture, apporteeKg: number, acheteeKg: number) => {
      const prixKg = toNum(ticket.prix_mouture_kg);
      const totalKg = prixKg > 0 ? toNum(ticket.cout_mouture) / prixKg : apporteeKg + acheteeKg;
      openTicketPrintWindow({
        numero: ticket.numero,
        date: new Date(ticket.date).toLocaleString("fr-FR"),
        lieu_nom: ticket.lieu_nom,
        lignes: [],
        montant_total: toNum(ticket.montant_total),
        mouture: true,
        cout_mouture: toNum(ticket.cout_mouture),
        prix_par_kg: prixKg,
        quantite_apportee_kg: apporteeKg,
        quantite_achetee_kg: acheteeKg,
        total_mouture_kg: totalKg,
        produit_apporte: ticket.produit_apporte,
      });
    },
    [],
  );

  const resetForm = useCallback(() => {
    setProduitApporte("");
    setQteApportee("");
    setQteAchetee("");
    setUnite("kg");
    // Conserver le prix configuré lors du reset
    const defaut = user?.lieu?.prix_mouture_defaut;
    setPrixParKg(defaut ? String(defaut) : "");
    setError("");
    setCreatedTicket(null);
    setTimeout(() => apporteeRef.current?.focus(), 50);
  }, [user?.lieu?.prix_mouture_defaut]);

  const submit = useCallback(async () => {
    if (submitLockRef.current) return;
    setError("");

    const a = Number.parseFloat(qteApportee) || 0;
    const b = Number.parseFloat(qteAchetee) || 0;
    const p = Number.parseFloat(prixParKg);

    // Validations strictes
    if (a < 0 || b < 0 || (a === 0 && b === 0)) {
      setError("Saisir au moins une quantité (apportée ou achetée) supérieure à 0.");
      return;
    }
    if (!prixParKg || !Number.isFinite(p) || p < 0) {
      setError("Saisir un prix par kg valide (≥ 0).");
      return;
    }
    if (depassePrixMax) {
      setError(
        `Prix ${p} FCFA/kg dépasse le plafond autorisé (${prixMax} FCFA/kg). Contactez l'administrateur.`,
      );
      return;
    }

    // Confirmation si quantité élevée
    if (a + b > SEUIL_ALERTE) {
      const ok = window.confirm(
        `Attention : quantité élevée (${fmt(a + b, 3)} ${unite}).\n` +
          `Coût estimé : ${fmt((a + b) * p)} FCFA\n\n` +
          `Confirmer l'opération ?`,
      );
      if (!ok) return;
    } else {
      // Confirmation standard
      const ok = window.confirm(
        `Confirmer la mouture ?\n` +
          `Grain : ${produitApporte || "—"}\n` +
          `Total : ${fmt(a + b, 3)} ${unite} × ${p} FCFA/kg\n` +
          `= ${fmt((a + b) * p)} FCFA`,
      );
      if (!ok) return;
    }

    lastApporteeRef.current = a;
    lastAcheteeRef.current = b;

    submitLockRef.current = true;
    setSaving(true);
    try {
      const response = await apiFetch<TicketMouture>(submitPath, {
        method: "POST",
        headers: { "Idempotency-Key": buildIdempotencyKey(roleGuard) },
        body: JSON.stringify({
          quantite_apportee: String(a),
          quantite_achetee: String(b),
          unite,
          prix_par_kg: prixParKg,
          produit_nom: produitApporte,
        }),
      });
      setCreatedTicket(response);
      refetch();
      refetchStats?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur lors de l'enregistrement.");
    } finally {
      setSaving(false);
      submitLockRef.current = false;
    }
  }, [depassePrixMax, prixMax, prixParKg, produitApporte, qteApportee, qteAchetee, refetch, refetchStats, roleGuard, submitPath, unite]);

  // ── Access guards ──────────────────────────────────────────────────────────
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

  // ── Main UI ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-4 max-w-5xl mx-auto">
      <div className="flex items-center gap-2">
        <Wheat className="h-6 w-6 text-green-600" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Service Mouture</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Formule unifiée : (apportée + achetée) × prix/kg
          </p>
        </div>
      </div>

      {/* ── Dashboard Stats ── */}
      {statsData && (
        <div className="grid grid-cols-3 gap-3">
          {(
            [
              { label: "Aujourd'hui", key: "aujourd_hui" },
              { label: "7 jours", key: "7_jours" },
              { label: "30 jours", key: "30_jours" },
            ] as const
          ).map(({ label, key }) => {
            const s = statsData[key];
            return (
              <Card key={key} className="bg-muted/20">
                <CardContent className="py-3 px-4 space-y-0.5">
                  <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
                    {label}
                  </p>
                  <p className="text-lg font-bold tabular-nums">
                    {fmt(Number(s.cout_total))} FCFA
                  </p>
                  <p className="text-xs text-muted-foreground tabular-nums">
                    {s.nb_tickets} ticket{s.nb_tickets !== 1 ? "s" : ""} ·{" "}
                    {fmt(Number(s.kg_apportee), 1)} kg apportés
                  </p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* ── Saisie ── */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Calculator className="h-4 w-4" />
              Saisie de la mouture
              {prixMax !== null && (
                <span className="ml-auto text-xs font-normal text-muted-foreground">
                  Plafond : {fmt(prixMax)} FCFA/kg
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && (
              <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded">
                {error}
              </p>
            )}

            {/* Produit apporté */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Produit / grain</label>
              <Input
                type="text"
                placeholder="Ex: Maïs, Manioc, Sorgho..."
                value={produitApporte}
                onChange={(e) => setProduitApporte(e.target.value)}
                className="h-10"
              />
            </div>

            {/* Unité */}
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

            {/* Quantités */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">
                  Apportée ({unite})
                  <span className="ml-1 text-xs text-muted-foreground font-normal">client</span>
                </label>
                <Input
                  ref={apporteeRef}
                  type="number"
                  min="0"
                  step="0.001"
                  placeholder={`0 ${unite}`}
                  value={qteApportee}
                  onChange={(e) => setQteApportee(e.target.value)}
                  autoFocus
                  className="h-10"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">
                  Achetée ({unite})
                  <span className="ml-1 text-xs text-muted-foreground font-normal">boutique</span>
                </label>
                <Input
                  type="number"
                  min="0"
                  step="0.001"
                  placeholder={`0 ${unite}`}
                  value={qteAchetee}
                  onChange={(e) => setQteAchetee(e.target.value)}
                  className="h-10"
                />
              </div>
            </div>

            {/* Alerte quantité élevée */}
            {depasseSeuil && (
              <div className="flex items-start gap-2 text-sm text-amber-700 bg-amber-50 dark:bg-amber-950/30 dark:text-amber-400 border border-amber-200 dark:border-amber-800 rounded-md px-3 py-2">
                <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>
                  Quantité élevée ({fmt(totalQte!, 3)} {unite}). Vérifiez avant de valider.
                </span>
              </div>
            )}

            {/* Total à moudre */}
            {totalQte !== null && totalQte > 0 && (
              <div className="flex items-center justify-between rounded-md border border-dashed px-3 py-2 text-sm bg-muted/30">
                <span className="text-muted-foreground">Total à moudre</span>
                <span className="font-semibold tabular-nums">
                  {fmt(totalQte, 3)} {unite}
                </span>
              </div>
            )}

            {/* Prix/kg */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Prix / kg (FCFA)</label>
              <Input
                type="number"
                min="0"
                step="0.01"
                placeholder="Ex: 200 FCFA/kg"
                value={prixParKg}
                onChange={(e) => setPrixParKg(e.target.value)}
                className={`h-10 ${depassePrixMax ? "border-destructive ring-1 ring-destructive" : ""}`}
              />
              {depassePrixMax ? (
                <p className="text-xs text-destructive">
                  Dépasse le plafond autorisé ({fmt(prixMax!)} FCFA/kg)
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Toutes unités normalisées en kg avant calcul.
                </p>
              )}
            </div>

            {/* Preview coût */}
            {coutMouture !== null && totalQte !== null && totalQte > 0 && (
              <div className="border rounded-md p-3 bg-green-50/50 dark:bg-green-950/20 space-y-1">
                <div className="flex justify-between text-sm text-muted-foreground">
                  <span>
                    {fmt(totalQte, 3)} {unite} × {prixParKg} FCFA/kg
                  </span>
                </div>
                <div className="flex justify-between font-bold text-lg">
                  <span>COÛT MOUTURE</span>
                  <span className="text-green-700 dark:text-green-300">
                    {fmt(coutMouture)} FCFA
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Aperçu en unité brute — le montant exact est calculé en kg normalisé.
                </p>
              </div>
            )}

            <Button
              className="w-full h-12 bg-green-600 hover:bg-green-700 text-white text-base gap-2"
              onClick={submit}
              disabled={
                saving ||
                depassePrixMax ||
                ((!qteApportee || Number.parseFloat(qteApportee) <= 0) &&
                  (!qteAchetee || Number.parseFloat(qteAchetee) <= 0)) ||
                !prixParKg
              }
            >
              <Wheat className="h-5 w-5" />
              {saving ? "Enregistrement..." : "Encaisser la mouture"}
            </Button>
          </CardContent>
        </Card>

        {/* ── Historique ── */}
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
              <p className="text-sm text-muted-foreground">Chargement...</p>
            ) : historyTickets.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucune opération de mouture.</p>
            ) : (
              <div className="space-y-2 max-h-96 overflow-auto pr-1">
                {historyTickets.map((t) => {
                  const apporteeKg = toNum(t.quantite_apportee_client);
                  const prixKg = toNum(t.prix_mouture_kg);
                  const totalKg = prixKg > 0 ? toNum(t.cout_mouture) / prixKg : 0;
                  const acheteeKg = Math.max(0, totalKg - apporteeKg);
                  return (
                    <button
                      key={t.id}
                      type="button"
                      className="w-full text-left border rounded-md p-3 hover:bg-muted/40"
                      onClick={() => setSelectedTicket(t)}
                    >
                      <div className="flex justify-between text-sm">
                        <span className="font-mono text-xs">{t.numero}</span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(t.date).toLocaleString("fr-FR")}
                        </span>
                      </div>
                      <div className="flex justify-between mt-1 text-sm">
                        <span className="text-muted-foreground">
                          {t.mouture_source === "vente_avec_mouture"
                            ? `Vente + mouture (${t.lignes_count ?? 0} ligne(s))`
                            : (t.produit_apporte || "Mouture seule")}
                        </span>
                        <span className="font-semibold tabular-nums">
                          {fmt(t.montant_total)} FCFA
                        </span>
                      </div>
                      {t.mouture_source !== "vente_avec_mouture" && totalKg > 0 && (
                        <div className="mt-1 text-xs text-muted-foreground tabular-nums">
                          {apporteeKg > 0 && `Apporté ${fmt(apporteeKg, 3)} kg`}
                          {apporteeKg > 0 && acheteeKg > 0 && " · "}
                          {acheteeKg > 0 && `Acheté ${fmt(acheteeKg, 3)} kg`}
                          {` · Total ${fmt(totalKg, 3)} kg`}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Ticket créé ── */}
      {createdTicket && (
        <Card className="border-green-200 bg-green-50/50 dark:bg-green-950/20 dark:border-green-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-green-700 dark:text-green-300">
              Mouture enregistrée
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="text-sm space-y-0.5">
              <p>
                Ticket{" "}
                <span className="font-mono font-semibold">{createdTicket.numero}</span>
              </p>
              <p>
                Coût mouture :{" "}
                <span className="font-semibold">{fmt(createdTicket.cout_mouture)} FCFA</span>
              </p>
              {(() => {
                const apporteeKg = lastApporteeRef.current;
                const acheteeKg = lastAcheteeRef.current;
                return (apporteeKg + acheteeKg) > 0 ? (
                  <p className="text-muted-foreground text-xs">
                    Apporté {fmt(apporteeKg, 3)} {unite} · Acheté {fmt(acheteeKg, 3)} {unite} · Total {fmt(apporteeKg + acheteeKg, 3)} {unite}
                  </p>
                ) : null;
              })()}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                className="gap-2"
                onClick={() =>
                  imprimerTicket(
                    createdTicket,
                    lastApporteeRef.current,
                    lastAcheteeRef.current,
                  )
                }
              >
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
                totalGeneral={toNum(createdTicket.montant_total)}
                mouture
                coutMouture={toNum(createdTicket.cout_mouture)}
                prixParKg={toNum(createdTicket.prix_mouture_kg)}
                quantiteApporteeKg={lastApporteeRef.current}
                quantiteAcheteeKg={lastAcheteeRef.current}
                produitApporte={createdTicket.produit_apporte}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Détail ticket sélectionné ── */}
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
          <CardContent className="space-y-1 text-sm">
            <p>
              <span className="text-muted-foreground">Ticket :</span>{" "}
              <span className="font-mono">{selectedTicket.numero}</span>
            </p>
            <p>
              <span className="text-muted-foreground">{lieuLabel} :</span>{" "}
              {selectedTicket.lieu_nom}
            </p>
            <p>
              <span className="text-muted-foreground">Date :</span>{" "}
              {new Date(selectedTicket.date).toLocaleString("fr-FR")}
            </p>
            <p>
              <span className="text-muted-foreground">Type :</span>{" "}
              {selectedTicket.mouture_source === "vente_avec_mouture"
                ? "Vente avec mouture"
                : "Mouture seule"}
            </p>
            {selectedTicket.mouture_source !== "vente_avec_mouture" && (() => {
              const apporteeKg = toNum(selectedTicket.quantite_apportee_client);
              const prixKg = toNum(selectedTicket.prix_mouture_kg);
              const totalKg = prixKg > 0 ? toNum(selectedTicket.cout_mouture) / prixKg : 0;
              const acheteeKg = Math.max(0, totalKg - apporteeKg);
              return (
                <>
                  <p>
                    <span className="text-muted-foreground">Grain :</span>{" "}
                    {selectedTicket.produit_apporte || "—"}
                  </p>
                  {totalKg > 0 && (
                    <div className="mt-2 border rounded-md p-2 space-y-0.5 bg-muted/20 text-xs tabular-nums">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Apporté</span>
                        <span>{fmt(apporteeKg, 3)} kg</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Acheté</span>
                        <span>{fmt(acheteeKg, 3)} kg</span>
                      </div>
                      <div className="flex justify-between font-semibold border-t pt-0.5 mt-0.5">
                        <span>Total moudre</span>
                        <span>{fmt(totalKg, 3)} kg</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Prix/kg</span>
                        <span>{fmt(prixKg)} FCFA</span>
                      </div>
                    </div>
                  )}
                </>
              );
            })()}
            <p className="font-semibold pt-2">
              Total : {fmt(selectedTicket.montant_total)} FCFA
            </p>
          </CardContent>
        </Card>
      )}

      {roleGuard === "usine" && (
        <Card className="bg-muted/20">
          <CardContent className="py-4 text-sm text-muted-foreground">
            Mouture seule : aucun débit de stock produit fini. Traçabilité par ticket et journal
            d&apos;audit.
          </CardContent>
        </Card>
      )}
    </div>
  );
}
