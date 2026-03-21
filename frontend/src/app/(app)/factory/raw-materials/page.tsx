"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

/**
 * Les usines ne font plus d'achats directs.
 * Les achats de matières premières se font exclusivement au niveau du MPSL,
 * qui transfère ensuite les produits vers les usines.
 *
 * Cette page est conservée pour éviter les liens cassés dans les anciens favoris.
 */
export default function FactoryRawMaterialsPage() {
  const router = useRouter();

  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] gap-6 text-center">
      <div className="rounded-full bg-orange-100 dark:bg-orange-950/30 p-4">
        <svg className="h-10 w-10 text-orange-600 dark:text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10" />
        </svg>
      </div>
      <div className="space-y-2 max-w-md">
        <h1 className="text-xl font-semibold">Achats centralisés au MPSL</h1>
        <p className="text-sm text-muted-foreground">
          Les usines ne réalisent plus d&apos;achats directs. Toutes les acquisitions de matières premières
          sont gérées au niveau du <strong>dépôt MPSL</strong>, qui transfère ensuite les produits vers les usines.
        </p>
        <p className="text-xs text-muted-foreground">
          Les usines reçoivent les produits du MPSL et les transfèrent ensuite vers les boutiques.
        </p>
      </div>
      <div className="flex flex-wrap gap-3 justify-center">
        <Button onClick={() => router.push("/factory/transfers")} className="bg-blue-600 hover:bg-blue-700 text-white">
          Créer un transfert vers boutique
        </Button>
        <Button variant="outline" onClick={() => router.push("/factory")}>
          Tableau de bord usine
        </Button>
      </div>
    </div>
  );
}
