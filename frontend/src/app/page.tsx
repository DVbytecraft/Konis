"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    const targets: Record<string, string> = {
      supreme_admin: "/admin",
      admin: "/admin",
      daf: "/finance",
      comptable: "/comptable",
      factory: "/factory",
      usine: "/factory",
      boutique: "/boutique/caisse",
      mpsl: "/mpsl",
    };
    const target = targets[user.role] ?? "/login";
    router.replace(target);
  }, [user, loading]); // router exclu intentionnellement (stable, l'inclure cause une boucle)

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="h-8 w-8 animate-pulse rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
}
