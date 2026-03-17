"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { fmt } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Banknote, FolderKanban, TrendingDown, TrendingUp } from "lucide-react";

interface Resume {
  total_creances_restantes: string;
  total_payables_restants: string;
  total_emprunts_restants: string;
  solde_caisse: string;
  projets_en_cours: number;
  projets_en_depassement: number;
}

export default function FinanceDashboardPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resume, setResume] = useState<Resume | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await apiFetch<Resume>("/finance/resume/");
      setResume(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const kpis = resume
    ? [
        {
          label: "Créances restantes",
          value: `${fmt(resume.total_creances_restantes)} FCFA`,
          icon: TrendingUp,
          iconClass: "text-emerald-600",
          cardClass: "border-emerald-200",
        },
        {
          label: "Payables restants",
          value: `${fmt(resume.total_payables_restants)} FCFA`,
          icon: TrendingDown,
          iconClass: "text-red-500",
          cardClass: "border-red-200",
        },
        {
          label: "Emprunts restants",
          value: `${fmt(resume.total_emprunts_restants)} FCFA`,
          icon: TrendingDown,
          iconClass: "text-red-500",
          cardClass: "border-red-200",
        },
        {
          label: "Solde caisse",
          value: `${fmt(resume.solde_caisse)} FCFA`,
          icon: Banknote,
          iconClass: "text-emerald-600",
          cardClass: "border-emerald-200",
        },
        {
          label: "Projets en cours",
          value: String(resume.projets_en_cours),
          icon: FolderKanban,
          iconClass: "text-blue-600",
          cardClass: "border-blue-200",
        },
        {
          label: "Projets en dépassement",
          value: String(resume.projets_en_depassement),
          icon: FolderKanban,
          iconClass: "text-orange-500",
          cardClass: "border-orange-200",
        },
      ]
    : [];

  return (
    <div className="space-y-8 min-w-0">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Finance — Tableau de bord</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Vue d&apos;ensemble de la situation financière.
        </p>
      </div>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement...</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {kpis.map((kpi) => {
            const Icon = kpi.icon;
            return (
              <Card key={kpi.label} className={kpi.cardClass}>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    {kpi.label}
                  </CardTitle>
                  <Icon className={`h-5 w-5 ${kpi.iconClass}`} />
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold">{kpi.value}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
