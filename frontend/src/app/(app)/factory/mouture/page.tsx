"use client";

import { MoutureConsole } from "@/components/mouture/mouture-console";

export default function FactoryMouturePage() {
  return (
    <MoutureConsole
      submitPath="/factory/mouture-seule/"
      historyPath="/factory/mouture-seule/"
      roleGuard="usine"
      lieuLabel="Usine"
    />
  );
}
