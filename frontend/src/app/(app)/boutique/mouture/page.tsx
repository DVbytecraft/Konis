"use client";

import { MoutureConsole } from "@/components/mouture/mouture-console";

export default function BoutiqueMouturePage() {
  return (
    <MoutureConsole
      submitPath="/boutique/mouture-seule/"
      historyPath="/boutique/mouture-seule/"
      statsPath="/boutique/mouture-stats/"
      exportPath="/boutique/mouture-export/"
      roleGuard="boutique"
      lieuLabel="Boutique"
    />
  );
}
