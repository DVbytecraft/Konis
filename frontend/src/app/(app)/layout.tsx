"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";
import { ErrorBoundary } from "@/components/error-boundary";
import { Button } from "@/components/ui/button";
import { LayoutDashboard, Store, Calculator, LogOut, Users, Package, Warehouse, Receipt, BarChart3, ClipboardList, Wheat, Tag, Truck, TrendingUp, TrendingDown, Banknote, FolderKanban, Landmark, CreditCard, Building2 } from "lucide-react";
import { cn } from "@/lib/utils";

const navByRole: Record<string, { href: string; label: string; icon: React.ComponentType<{ className?: string }> }[]> = {
  admin: [
    { href: "/admin", label: "Tableau de bord", icon: LayoutDashboard },
    { href: "/admin/users", label: "Utilisateurs", icon: Users },
    { href: "/admin/factories", label: "Usines", icon: Warehouse },
    { href: "/admin/magasins", label: "Lieux", icon: Store },
    { href: "/admin/produits", label: "Produits", icon: Package },
    { href: "/admin/rapport", label: "Rapport", icon: BarChart3 },
    { href: "/factures", label: "Factures", icon: Receipt },
    { href: "/comptable", label: "Vue comptable", icon: Calculator },
    { href: "/comptable/depenses", label: "Dépenses", icon: ClipboardList },
    { href: "/admin/categories-depense", label: "Catégories dépenses", icon: Tag },
  ],
  comptable: [
    { href: "/comptable", label: "Tableau de bord", icon: LayoutDashboard },
    { href: "/comptable/depenses", label: "Dépenses", icon: ClipboardList },
    { href: "/factures", label: "Factures", icon: Receipt },
  ],
  usine: [
    { href: "/factory", label: "Tableau de bord", icon: Warehouse },
    { href: "/factory/raw-materials", label: "Achats", icon: Package },
    { href: "/factory/production", label: "Production", icon: Warehouse },
    { href: "/factory/transfers", label: "Transferts", icon: Store },
    { href: "/factory/shop-stock", label: "Stocks boutiques", icon: Store },
    { href: "/factory/mouture", label: "Mouture", icon: Wheat },
    { href: "/factures", label: "Factures", icon: Receipt },
  ],
  factory: [
    { href: "/factory", label: "Tableau de bord", icon: Warehouse },
    { href: "/factory/raw-materials", label: "Achats", icon: Package },
    { href: "/factory/production", label: "Production", icon: Warehouse },
    { href: "/factory/transfers", label: "Transferts", icon: Store },
    { href: "/factory/shop-stock", label: "Stocks boutiques", icon: Store },
    { href: "/factory/mouture", label: "Mouture", icon: Wheat },
    { href: "/factures", label: "Factures", icon: Receipt },
  ],
  boutique: [
    { href: "/boutique/caisse", label: "Caisse", icon: Store },
    { href: "/boutique/mouture", label: "Mouture", icon: Wheat },
    { href: "/boutique/tickets", label: "Tickets", icon: ClipboardList },
    { href: "/factures", label: "Factures", icon: Receipt },
  ],
  mpsl: [
    { href: "/mpsl", label: "Tableau de bord", icon: Truck },
    { href: "/mpsl/achats", label: "Achats", icon: Package },
    { href: "/mpsl/transferts", label: "Transferts", icon: Warehouse },
  ],
  supreme_admin: [
    { href: "/admin", label: "Tableau de bord", icon: LayoutDashboard },
    { href: "/admin/users", label: "Utilisateurs", icon: Users },
    { href: "/admin/factories", label: "Usines", icon: Warehouse },
    { href: "/admin/magasins", label: "Lieux", icon: Store },
    { href: "/admin/produits", label: "Produits", icon: Package },
    { href: "/admin/rapport", label: "Rapport", icon: BarChart3 },
    { href: "/factures", label: "Factures", icon: Receipt },
    { href: "/comptable", label: "Vue comptable", icon: Calculator },
    { href: "/comptable/depenses", label: "Dépenses", icon: ClipboardList },
    { href: "/admin/categories-depense", label: "Catégories dépenses", icon: Tag },
    { href: "/finance", label: "Finance", icon: TrendingUp },
    { href: "/finance/creanciers", label: "Créanciers", icon: Landmark },
    { href: "/finance/journaux-payables", label: "À payer", icon: TrendingDown },
    { href: "/finance/clients", label: "Clients Finance", icon: Users },
    { href: "/finance/journaux-creances", label: "Créances", icon: TrendingUp },
    { href: "/finance/emprunts", label: "Emprunts", icon: CreditCard },
    { href: "/finance/tresorerie", label: "Trésorerie", icon: Banknote },
    { href: "/finance/projets", label: "Projets", icon: FolderKanban },
  ],
  daf: [
    { href: "/finance", label: "Tableau de bord", icon: LayoutDashboard },
    { href: "/finance/creanciers", label: "Créanciers", icon: Landmark },
    { href: "/finance/journaux-payables", label: "À payer", icon: TrendingDown },
    { href: "/finance/clients", label: "Clients Finance", icon: Building2 },
    { href: "/finance/journaux-creances", label: "Créances", icon: TrendingUp },
    { href: "/finance/emprunts", label: "Emprunts", icon: CreditCard },
    { href: "/finance/tresorerie", label: "Trésorerie", icon: Banknote },
    { href: "/finance/projets", label: "Projets", icon: FolderKanban },
  ],
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) { router.replace("/login"); return; }
    // Route protection: redirect if current path is not accessible for the user's role
    const allowedPaths = (navByRole[user.role] ?? []).map(n => n.href);
    const hasAccess = allowedPaths.some(
      p => pathname === p || pathname.startsWith(p + "/")
    );
    if (!hasAccess) {
      router.replace(allowedPaths[0] ?? "/login");
    }
  }, [user, loading, pathname]); // router exclu : stable par définition, l'inclure cause une boucle infinie

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-pulse rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  const moutureEnabled = user.lieu?.mouture_enabled !== false;
  const navItems = (navByRole[user.role] || []).filter(
    (item) => item.href.endsWith("/mouture") ? moutureEnabled : true
  );

  return (
    <div className="min-h-screen min-w-0 bg-muted/20 overflow-x-hidden">
      <header className="md:hidden border-b border-border bg-card">
        <div className="flex h-14 items-center justify-between px-4">
          <div className="flex flex-col min-w-0">
            <Link href="/" className="font-bold tracking-tight text-green-600 dark:text-green-400 leading-tight">
              KONIS
            </Link>
            {user.lieu && (
              <span className="text-xs text-muted-foreground truncate leading-tight">{user.lieu.nom}</span>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-2 gap-1 text-muted-foreground shrink-0"
            onClick={() => logout().then(() => router.push("/login"))}
          >
            <LogOut className="h-4 w-4" />
            Sortir
          </Button>
        </div>
        <nav className="scrollbar-hidden flex gap-2 overflow-x-auto px-2 pb-2">
          {navItems.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href}>
              <span
                className={cn(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium whitespace-nowrap transition-colors",
                  pathname === href || pathname.startsWith(href + "/")
                    ? "bg-green-600 text-white dark:bg-green-500"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </span>
            </Link>
          ))}
        </nav>
      </header>

      <div className="flex min-w-0">
        <aside className="hidden md:flex w-52 lg:w-56 shrink-0 flex-col border-r border-border bg-card">
          <div className="flex h-14 items-center border-b border-border px-4">
            <Link href="/" className="font-bold tracking-tight text-green-600 dark:text-green-400 text-lg">
              KONIS
            </Link>
          </div>
          <nav className="flex-1 space-y-0.5 p-2">
            {navItems.map(({ href, label, icon: Icon }) => {
              const isActive = pathname === href || pathname.startsWith(href + "/");
              return (
                <Link key={href} href={href}>
                  <span
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors border-l-2",
                      isActive
                        ? "bg-green-50 dark:bg-green-950/40 text-green-700 dark:text-green-300 border-green-600 dark:border-green-400"
                        : "border-transparent text-muted-foreground hover:bg-muted hover:text-foreground"
                    )}
                  >
                    <Icon className={cn("h-4 w-4 shrink-0", isActive && "text-green-600 dark:text-green-400")} />
                    {label}
                  </span>
                </Link>
              );
            })}
          </nav>
          <div className="border-t border-border p-2">
            <div className="rounded-lg px-3 py-2 text-xs text-muted-foreground">
              {user.username}
              {user.lieu && <span className="block font-medium text-foreground">{user.lieu.nom}</span>}
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="mt-1 w-full justify-start gap-2 text-muted-foreground"
              onClick={() => logout().then(() => router.push("/login"))}
            >
              <LogOut className="h-4 w-4" />
              Deconnexion
            </Button>
          </div>
        </aside>
        <main className="flex-1 min-w-0 overflow-auto">
          <div className="container max-w-7xl mx-auto py-4 sm:py-6 px-3 sm:px-6">
            <ErrorBoundary>{children}</ErrorBoundary>
          </div>
        </main>
      </div>
    </div>
  );
}
