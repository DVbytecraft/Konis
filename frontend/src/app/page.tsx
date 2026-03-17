"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    switch (user.role) {
      case "admin":
        router.replace("/admin");
        break;
      case "comptable":
        router.replace("/comptable");
        break;
      case "factory":
      case "usine":
        router.replace("/factory");
        break;
      case "boutique":
        router.replace("/boutique/caisse");
        break;
      case "mpsl":
        router.replace("/mpsl");
        break;
      default:
        router.replace("/login");
    }
  }, [user, loading, router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="h-8 w-8 animate-pulse rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
}
