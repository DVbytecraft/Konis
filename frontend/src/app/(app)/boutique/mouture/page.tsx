"use client";

import { MoutureConsole } from "@/components/mouture/mouture-console";

export default function BoutiqueMouturePage() {
  return (
    <MoutureConsole
      submitPath="/boutique/mouture-seule/"
      historyPath="/boutique/mouture-seule/"
      roleGuard="boutique"
      lieuLabel="Boutique"
    />
  );
}
