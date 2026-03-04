"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface MovementRow {
  id: string;
  date: string;
  movement_type: string;
  product_name: string;
  product_category: string;
  quantity: string | number;
  unit_price: string | number;
  amount: string | number;
  reference: string;
}

interface JournalData {
  entries: MovementRow[];
  exits: MovementRow[];
  totals: {
    entries_value: string | number;
    exits_value: string | number;
    net_value: string | number;
  };
}

interface ProductOption {
  id: number;
  name: string;
  code: string;
  unit: string;
}

const MOVEMENT_TYPE_LABELS: Record<string, string> = {
  raw_material_receipt: "Entree MP",
  production_output: "Sortie production",
  production_consumption: "Consommation production",
  transfer_to_shop: "Transfert boutique",
};

export default function FactoryJournalPage() {
  const [data, setData] = useState<JournalData>({
    entries: [],
    exits: [],
    totals: { entries_value: 0, exits_value: 0, net_value: 0 },
  });
  const [products, setProducts] = useState<ProductOption[]>([]);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const [filters, setFilters] = useState({
    startDate: "",
    endDate: "",
    productId: "",
    movementType: "all",
  });

  const buildQuery = useCallback((f: typeof filters) => {
    const params = new URLSearchParams();
    if (f.startDate) params.set("start_date", f.startDate);
    if (f.endDate) params.set("end_date", f.endDate);
    if (f.productId) params.set("product_id", f.productId);
    const qs = params.toString();
    return qs ? `?${qs}` : "";
  }, []);

  const loadProducts = useCallback(async () => {
    const [raw, finished] = await Promise.all([
      apiFetch("/factory/raw-materials/catalog/"),
      apiFetch("/factory/finished-products/catalog/"),
    ]);
    const all = [...(raw as ProductOption[]), ...(finished as ProductOption[])];
    const seen = new Set<number>();
    const dedup = all.filter((p) => {
      if (seen.has(p.id)) return false;
      seen.add(p.id);
      return true;
    });
    dedup.sort((a, b) => a.name.localeCompare(b.name, "fr"));
    setProducts(dedup);
  }, []);

  const loadJournal = useCallback(async (f: typeof filters) => {
    setLoading(true);
    setErr("");
    try {
      const res = await apiFetch(`/factory/movements-journal/${buildQuery(f)}`);
      setData(res as JournalData);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, [buildQuery]);

  useEffect(() => {
    const initialFilters = { startDate: "", endDate: "", productId: "", movementType: "all" };
    loadProducts().catch(() => setProducts([]));
    loadJournal(initialFilters).catch(() => null);
  }, [loadProducts, loadJournal]);

  const filteredEntries = useMemo(() => {
    if (filters.movementType === "all") return data.entries;
    return data.entries.filter((row) => row.movement_type === filters.movementType);
  }, [data.entries, filters.movementType]);

  const filteredExits = useMemo(() => {
    if (filters.movementType === "all") return data.exits;
    return data.exits.filter((row) => row.movement_type === filters.movementType);
  }, [data.exits, filters.movementType]);

  const displayTotals = useMemo(() => {
    const entriesValue = filteredEntries.reduce((acc, row) => acc + Number(row.amount), 0);
    const exitsValue = filteredExits.reduce((acc, row) => acc + Number(row.amount), 0);
    return {
      entriesValue,
      exitsValue,
      netValue: entriesValue - exitsValue,
    };
  }, [filteredEntries, filteredExits]);

  const onApply = async () => {
    await loadJournal(filters);
  };

  const onReset = async () => {
    const cleared = { startDate: "", endDate: "", productId: "", movementType: "all" };
    setFilters(cleared);
    await loadJournal(cleared);
  };

  return (
    <div className="space-y-4 min-w-0">
      <h1 className="text-2xl font-semibold tracking-tight">Journal des mouvements usine</h1>
      {err && <p className="text-sm text-destructive">{err}</p>}

      <div className="rounded-md border p-3 space-y-3">
        <p className="text-sm font-medium">Filtres</p>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          <Input
            type="date"
            value={filters.startDate}
            onChange={(e) => setFilters((prev) => ({ ...prev, startDate: e.target.value }))}
          />
          <Input
            type="date"
            value={filters.endDate}
            onChange={(e) => setFilters((prev) => ({ ...prev, endDate: e.target.value }))}
          />
          <select
            className="h-10 rounded-md border border-input bg-background px-2 text-sm"
            value={filters.productId}
            onChange={(e) => setFilters((prev) => ({ ...prev, productId: e.target.value }))}
          >
            <option value="">Tous les produits</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} {p.code ? `(${p.code})` : ""}
              </option>
            ))}
          </select>
          <select
            className="h-10 rounded-md border border-input bg-background px-2 text-sm"
            value={filters.movementType}
            onChange={(e) => setFilters((prev) => ({ ...prev, movementType: e.target.value }))}
          >
            <option value="all">Tous les mouvements</option>
            <option value="raw_material_receipt">Entree MP</option>
            <option value="production_output">Sortie production</option>
            <option value="production_consumption">Consommation production</option>
            <option value="transfer_to_shop">Transfert boutique</option>
          </select>
          <div className="flex flex-col sm:flex-row gap-2">
            <Button type="button" className="w-full sm:w-auto" onClick={onApply} disabled={loading}>
              {loading ? "Chargement..." : "Appliquer"}
            </Button>
            <Button type="button" className="w-full sm:w-auto" variant="outline" onClick={onReset} disabled={loading}>
              Reinitialiser
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-md border p-3">
          <p className="text-sm text-muted-foreground">Valorisation entrees</p>
          <p className="text-xl font-semibold">{displayTotals.entriesValue.toFixed(2)}</p>
        </div>
        <div className="rounded-md border p-3">
          <p className="text-sm text-muted-foreground">Valorisation sorties</p>
          <p className="text-xl font-semibold">{displayTotals.exitsValue.toFixed(2)}</p>
        </div>
        <div className="rounded-md border p-3">
          <p className="text-sm text-muted-foreground">Solde valeur</p>
          <p className="text-xl font-semibold">{displayTotals.netValue.toFixed(2)}</p>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="overflow-x-auto rounded-md border p-2 -mx-1 sm:mx-0">
          <p className="text-sm font-medium mb-2">Entrees internes usine</p>
          <table className="w-full text-xs sm:text-sm min-w-[720px]">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2">Date</th>
                <th className="text-left py-2">Type</th>
                <th className="text-left py-2">Produit</th>
                <th className="text-right py-2">Qte</th>
                <th className="text-right py-2">PU</th>
                <th className="text-right py-2">Montant</th>
                <th className="text-left py-2">Reference</th>
              </tr>
            </thead>
            <tbody>
              {filteredEntries.map((r) => (
                <tr key={r.id} className="border-b">
                  <td className="py-1.5">{new Date(r.date).toLocaleString("fr-FR")}</td>
                  <td className="py-1.5">{MOVEMENT_TYPE_LABELS[r.movement_type] || r.movement_type}</td>
                  <td className="py-1.5">{r.product_name}</td>
                  <td className="py-1.5 text-right">{Number(r.quantity).toFixed(2)}</td>
                  <td className="py-1.5 text-right">{Number(r.unit_price).toFixed(2)}</td>
                  <td className="py-1.5 text-right">{Number(r.amount).toFixed(2)}</td>
                  <td className="py-1.5">{r.reference}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="overflow-x-auto rounded-md border p-2 -mx-1 sm:mx-0">
          <p className="text-sm font-medium mb-2">Sorties internes usine</p>
          <table className="w-full text-xs sm:text-sm min-w-[720px]">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2">Date</th>
                <th className="text-left py-2">Type</th>
                <th className="text-left py-2">Produit</th>
                <th className="text-right py-2">Qte</th>
                <th className="text-right py-2">PU</th>
                <th className="text-right py-2">Montant</th>
                <th className="text-left py-2">Reference</th>
              </tr>
            </thead>
            <tbody>
              {filteredExits.map((r) => (
                <tr key={r.id} className="border-b">
                  <td className="py-1.5">{new Date(r.date).toLocaleString("fr-FR")}</td>
                  <td className="py-1.5">{MOVEMENT_TYPE_LABELS[r.movement_type] || r.movement_type}</td>
                  <td className="py-1.5">{r.product_name}</td>
                  <td className="py-1.5 text-right">{Number(r.quantity).toFixed(2)}</td>
                  <td className="py-1.5 text-right">{Number(r.unit_price).toFixed(2)}</td>
                  <td className="py-1.5 text-right">{Number(r.amount).toFixed(2)}</td>
                  <td className="py-1.5">{r.reference}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
