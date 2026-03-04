"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";

export default function FactoryLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) return;
    if (user.role !== "usine" && user.role !== "factory") {
      router.replace("/");
    }
  }, [loading, router, user]);

  if (loading) return null;
  if (!user) return null;
  if (user.role !== "usine" && user.role !== "factory") return null;

  return <>{children}</>;
}
