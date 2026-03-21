"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";

interface AchatItem {
  id: number;
  produit_nom: string;
  fournisseur_nom?: string;
  quantite: string;
  unite: string;
  prix_unitaire: string;
  prix_total: string;
  type_paiement: string;
  date: string;
}

interface DetteItem {
  id: number;
  fournisseur_nom: string;
  montant_initial: string;
  montant_paye: string;
  montant_restant: string;
  date_echeance: string | null;
}

interface DetailMPSL {
  lieu_id: number;
  lieu_nom: string;
  total_achats: string;
  total_dettes: string;
  nb_dettes_en_cours: number;
  achats: AchatItem[];
  dettes_en_cours: DetteItem[];
}

function fmt(v: string | number) {
  return Number(v).toLocaleString("fr-FR");
}

const TYPE_PAIEMENT_LABELS: Record<string, string> = {
  cash: "Cash",
  credit: "Crédit",
  partiel: "Partiel",
};

export default function DetailMPSLPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [data, setData] = useState<DetailMPSL | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const qs = searchParams.toString() ? `?${searchParams.toString()}` : "";
    apiFetch(`/comptable/rapport-mpsl/${id}/${qs}`)
      .then((d) => setData(d as DetailMPSL))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [id, searchParams]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-pulse rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <button onClick={() => router.back()} className="text-sm text-muted-foreground hover:text-foreground">← Retour</button>
        <p className="text-muted-foreground">Dépôt MPSL introuvable.</p>
      </div>
    );
  }

  return (
    <div className="space-y-5 min-w-0">
      <div className="flex items-center gap-3">
        <button onClick={() => router.back()} className="text-sm text-muted-foreground hover:text-foreground">← Retour</button>
        <h1 className="text-xl font-semibold tracking-tight">{data.lieu_nom}</h1>
      </div>

      {/* Résumé */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <div className="rounded-lg border border-l-4 border-l-orange-500 bg-orange-50 dark:bg-orange-950/20 p-3">
          <p className="text-xs text-muted-foreground">Total achats</p>
          <p className="text-xl font-bold text-orange-700 dark:text-orange-400">{fmt(data.total_achats)}</p>
          <p className="text-xs text-muted-foreground">FCFA · {data.achats.length} achat(s)</p>
        </div>
        <div className="rounded-lg border border-l-4 border-l-red-500 bg-red-50 dark:bg-red-950/20 p-3">
          <p className="text-xs text-muted-foreground">Dettes fournisseurs</p>
          <p className="text-xl font-bold text-red-700 dark:text-red-400">{fmt(data.total_dettes)}</p>
          <p className="text-xs text-muted-foreground">FCFA · {data.nb_dettes_en_cours} en cours</p>
        </div>
        <div className="rounded-lg border border-l-4 border-l-green-500 bg-green-50 dark:bg-green-950/20 p-3 col-span-2 lg:col-span-1">
          <p className="text-xs text-muted-foreground">Achats payés cash</p>
          <p className="text-xl font-bold text-green-700 dark:text-green-400">
            {fmt(data.achats.filter(a => a.type_paiement === "cash").reduce((s, a) => s + Number(a.prix_total), 0))}
          </p>
          <p className="text-xs text-muted-foreground">FCFA</p>
        </div>
      </div>

      {/* Dettes en cours */}
      {data.dettes_en_cours.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold">Dettes fournisseurs en cours</h2>
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-xs sm:text-sm min-w-[540px]">
              <thead>
                <tr className="border-b bg-muted/40">
                  <th className="text-left py-2 px-3">Fournisseur</th>
                  <th className="text-right py-2 px-3">Montant initial (FCFA)</th>
                  <th className="text-right py-2 px-3">Payé (FCFA)</th>
                  <th className="text-right py-2 px-3">Restant (FCFA)</th>
                  <th className="text-left py-2 px-3">Échéance</th>
                </tr>
              </thead>
              <tbody>
                {data.dettes_en_cours.map((d) => (
                  <tr key={d.id} className="border-b hover:bg-muted/20">
                    <td className="py-2 px-3 font-medium">{d.fournisseur_nom}</td>
                    <td className="py-2 px-3 text-right">{fmt(d.montant_initial)}</td>
                    <td className="py-2 px-3 text-right text-green-700 dark:text-green-400">{fmt(d.montant_paye)}</td>
                    <td className="py-2 px-3 text-right font-bold text-red-600 dark:text-red-400">{fmt(d.montant_restant)}</td>
                    <td className="py-2 px-3 text-muted-foreground">
                      {d.date_echeance ? new Date(d.date_echeance).toLocaleDateString("fr-FR") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Liste des achats */}
      <div className="space-y-2">
        <h2 className="text-sm font-semibold">Achats ({data.achats.length})</h2>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-xs sm:text-sm min-w-[620px]">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="text-left py-2 px-3">Date</th>
                <th className="text-left py-2 px-3">Produit</th>
                <th className="text-left py-2 px-3">Fournisseur</th>
                <th className="text-right py-2 px-3">Qté</th>
                <th className="text-left py-2 px-3">Unité</th>
                <th className="text-right py-2 px-3">P.U.</th>
                <th className="text-right py-2 px-3">Total (FCFA)</th>
                <th className="text-left py-2 px-3">Paiement</th>
              </tr>
            </thead>
            <tbody>
              {data.achats.length === 0 && (
                <tr><td colSpan={8} className="py-6 text-center text-muted-foreground">Aucun achat.</td></tr>
              )}
              {data.achats.map((a) => (
                <tr key={a.id} className="border-b hover:bg-muted/20">
                  <td className="py-1.5 px-3 text-muted-foreground">{new Date(a.date).toLocaleDateString("fr-FR")}</td>
                  <td className="py-1.5 px-3 font-medium">{a.produit_nom}</td>
                  <td className="py-1.5 px-3 text-muted-foreground">{a.fournisseur_nom ?? "—"}</td>
                  <td className="py-1.5 px-3 text-right">{Number(a.quantite).toLocaleString("fr-FR")}</td>
                  <td className="py-1.5 px-3">{a.unite}</td>
                  <td className="py-1.5 px-3 text-right">{fmt(a.prix_unitaire)}</td>
                  <td className="py-1.5 px-3 text-right font-medium text-orange-700 dark:text-orange-400">{fmt(a.prix_total)}</td>
                  <td className="py-1.5 px-3">
                    <span className={
                      a.type_paiement === "cash"
                        ? "text-green-700 dark:text-green-400"
                        : a.type_paiement === "credit"
                        ? "text-red-600 dark:text-red-400"
                        : "text-amber-700 dark:text-amber-400"
                    }>
                      {TYPE_PAIEMENT_LABELS[a.type_paiement] ?? a.type_paiement}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
