"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { apiFetch, apiUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface ProductItem {
  id: number;
  nom?: string;
  name?: string;
  code?: string | null;
  unite?: string;
  unit?: string;
}

type ProductPayload =
  | ProductItem[]
  | {
      results?: ProductItem[];
      products?: ProductItem[];
      items?: ProductItem[];
      data?: ProductItem[];
    }
  | null
  | undefined;

interface LieuItem {
  id: number;
  nom: string;
  type_lieu: string;
}

type LieuPayload =
  | LieuItem[]
  | {
      results?: LieuItem[];
      items?: LieuItem[];
      data?: LieuItem[];
    }
  | null
  | undefined;

interface FactureLine {
  id: number;
  produit?: number | null;
  produit_nom?: string;
  description: string;
  quantite: string | number;
  prix_unitaire: string | number;
  total: string | number;
}

interface FactureItem {
  id: number;
  numero: string;
  date: string;
  source_role: string;
  lieu: number;
  lieu_nom: string;
  client_nom: string;
  client_contact: string;
  notes: string;
  total: string | number;
  lignes: FactureLine[];
}

type DraftLine = {
  produit: string;
  description: string;
  quantite: string;
  prix_unitaire: string;
};

export default function FacturesPage() {
  const { user } = useAuth();
  const [factures, setFactures] = useState<FactureItem[]>([]);
  const [products, setProducts] = useState<unknown>([]);
  const [lieux, setLieux] = useState<LieuItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<FactureItem | null>(null);

  const [form, setForm] = useState({
    lieu: "",
    client_nom: "",
    client_contact: "",
    notes: "",
  });
  const [lines, setLines] = useState<DraftLine[]>([
    { produit: "", description: "", quantite: "1", prix_unitaire: "0" },
  ]);

  const canChooseLieu = user?.role === "admin" || user?.role === "supreme_admin" || user?.role === "comptable" || user?.role === "daf";

  const toProductArray = useCallback((payload: ProductPayload): ProductItem[] => {
    if (Array.isArray(payload)) return payload;
    if (!payload || typeof payload !== "object") return [];
    if (Array.isArray(payload.results)) return payload.results;
    if (Array.isArray(payload.products)) return payload.products;
    if (Array.isArray(payload.items)) return payload.items;
    if (Array.isArray(payload.data)) return payload.data;
    return [];
  }, []);

  const toLieuArray = useCallback((payload: LieuPayload): LieuItem[] => {
    if (Array.isArray(payload)) return payload;
    if (!payload || typeof payload !== "object") return [];
    if (Array.isArray(payload.results)) return payload.results;
    if (Array.isArray(payload.items)) return payload.items;
    if (Array.isArray(payload.data)) return payload.data;
    return [];
  }, []);

  const normalizedProducts = useMemo(
    () =>
      toProductArray(products as ProductPayload).map((p) => ({
        id: p.id,
        name: p.nom || p.name || `Produit #${p.id}`,
        code: p.code || "",
      })),
    [products, toProductArray]
  );

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const reqs: Promise<unknown>[] = [apiFetch("/factures/")];
      if (canChooseLieu) reqs.push(apiFetch("/locations/by-type/"));
      if (user?.role === "boutique") {
        reqs.push(apiFetch("/boutique/produits/"));
      } else if (user?.role === "factory" || user?.role === "usine") {
        reqs.push(apiFetch("/factory/raw-materials/catalog/"));
        reqs.push(apiFetch("/factory/finished-products/catalog/"));
      } else if (user?.role === "admin" || user?.role === "supreme_admin") {
        reqs.push(apiFetch("/admin/produits/"));
      }

      const results = await Promise.all(reqs);
      const [facturesRes, ...rest] = results;
      setFactures((facturesRes as FactureItem[]) ?? []);

      let cursor = 0;
      if (canChooseLieu) {
        const lieuxRes = rest[cursor++] as LieuPayload;
        setLieux(toLieuArray(lieuxRes));
      }

      if (user?.role === "factory" || user?.role === "usine") {
        const rawRes = rest[cursor++];
        const finishedRes = rest[cursor++];
        const raw = toProductArray(rawRes as ProductPayload);
        const finished = toProductArray(finishedRes as ProductPayload);
        const merged = [...raw, ...finished];
        const seen = new Set<number>();
        setProducts(merged.filter((p) => (seen.has(p.id) ? false : (seen.add(p.id), true))));
      } else {
        const prodRes = rest[cursor];
        setProducts(prodRes as ProductPayload);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
      setFactures([]);
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }, [canChooseLieu, toProductArray, toLieuArray, user?.role]);

  useEffect(() => {
    load().catch(() => null);
  }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (lines.length === 0) {
      setError("Ajoute au moins une ligne.");
      return;
    }
    for (const line of lines) {
      if (!line.description.trim()) {
        setError("Chaque ligne doit avoir une description.");
        return;
      }
      if (!line.quantite || Number(line.quantite) <= 0) {
        setError("Quantite invalide.");
        return;
      }
      if (!line.prix_unitaire || Number(line.prix_unitaire) < 0) {
        setError("Prix unitaire invalide.");
        return;
      }
    }
    try {
      setSaving(true);
      const payload: Record<string, unknown> = {
        client_nom: form.client_nom,
        client_contact: form.client_contact,
        notes: form.notes,
        lignes: lines.map((l) => ({
          produit: l.produit ? Number(l.produit) : undefined,
          description: l.description,
          quantite: l.quantite,
          prix_unitaire: l.prix_unitaire,
        })),
      };
      if (canChooseLieu && form.lieu) payload.lieu = Number(form.lieu);

      const created = (await apiFetch("/factures/", {
        method: "POST",
        body: JSON.stringify(payload),
      })) as FactureItem;
      setSelected(created);
      setForm({ lieu: "", client_nom: "", client_contact: "", notes: "" });
      setLines([{ produit: "", description: "", quantite: "1", prix_unitaire: "0" }]);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur creation facture");
    } finally {
      setSaving(false);
    }
  };

  const fetchInvoicePdfBlob = useCallback(async (factureId: number, download = false) => {
    const suffix = download ? "?download=1" : "";
    const url = apiUrl(`/factures/${factureId}/pdf/${suffix}`);
    let res = await fetch(url, { credentials: "include" });
    if (res.status === 401) {
      try {
        await apiFetch("/auth/refresh", { method: "POST" }, false);
      } catch {
        // Ignore refresh errors; second attempt will surface failure.
      }
      res = await fetch(url, { credentials: "include" });
    }
    if (!res.ok) {
      throw new Error(`Erreur ${res.status} lors du chargement du PDF`);
    }
    return res.blob();
  }, []);

  const downloadInvoice = useCallback(async (factureId: number) => {
    const blob = await fetchInvoicePdfBlob(factureId, true);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `facture-${factureId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, [fetchInvoicePdfBlob]);

  const printInvoice = useCallback(async (factureId: number) => {
    try {
      const blob = await fetchInvoicePdfBlob(factureId, false);
      const pdfUrl = URL.createObjectURL(blob);
      const popup = window.open(pdfUrl, "_blank");
      if (!popup) {
        window.open(pdfUrl, "_blank");
        return;
      }
      const interval = window.setInterval(() => {
        try {
          if (popup.document && popup.document.readyState === "complete") {
            popup.focus();
            popup.print();
            window.clearInterval(interval);
          }
        } catch {
          // Ignore cross-origin access errors while the PDF loads.
        }
      }, 300);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de l'impression du PDF.");
    }
  }, [fetchInvoicePdfBlob]);

  return (
    <div className="space-y-6 min-w-0">
      <h1 className="text-2xl font-semibold tracking-tight">Factures A4</h1>

      <form onSubmit={submit} className="space-y-3 rounded-md border p-3">
        <p className="text-sm font-medium">Nouvelle facture</p>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {canChooseLieu && (
            <select
              className="h-10 rounded-md border border-input bg-background px-2 text-sm"
              value={form.lieu}
              onChange={(e) => setForm((f) => ({ ...f, lieu: e.target.value }))}
            >
              <option value="">Lieu</option>
              {lieux.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.nom} ({l.type_lieu})
                </option>
              ))}
            </select>
          )}
          <Input placeholder="Client" value={form.client_nom} onChange={(e) => setForm((f) => ({ ...f, client_nom: e.target.value }))} />
          <Input placeholder="Contact" value={form.client_contact} onChange={(e) => setForm((f) => ({ ...f, client_contact: e.target.value }))} />
          <Input placeholder="Notes" value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
        </div>

        <div className="space-y-2">
          {lines.map((line, idx) => (
            <div key={idx} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
              <select
                className="h-10 rounded-md border border-input bg-background px-2 text-sm"
                value={line.produit}
                onChange={(e) => {
                  const value = e.target.value;
                  const prod = normalizedProducts.find((p) => String(p.id) === value);
                  setLines((prev) =>
                    prev.map((l, i) =>
                      i === idx ? { ...l, produit: value, description: l.description || (prod?.name ?? "") } : l
                    )
                  );
                }}
              >
                <option value="">Produit (optionnel)</option>
                {normalizedProducts.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} {p.code ? `(${p.code})` : ""}
                  </option>
                ))}
              </select>
              <Input
                placeholder="Description"
                value={line.description}
                onChange={(e) => setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, description: e.target.value } : l)))}
              />
              <Input
                placeholder="Quantite"
                value={line.quantite}
                onChange={(e) => setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, quantite: e.target.value } : l)))}
              />
              <Input
                placeholder="Prix unitaire"
                value={line.prix_unitaire}
                onChange={(e) => setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, prix_unitaire: e.target.value } : l)))}
              />
              <Button
                type="button"
                variant="outline"
                className="w-full sm:w-auto"
                onClick={() => setLines((prev) => prev.filter((_, i) => i !== idx))}
                disabled={lines.length <= 1}
              >
                Retirer
              </Button>
            </div>
          ))}
          <div className="flex flex-col sm:flex-row gap-2">
            <Button type="button" variant="outline" className="w-full sm:w-auto" onClick={() => setLines((prev) => [...prev, { produit: "", description: "", quantite: "1", prix_unitaire: "0" }])}>
              Ajouter ligne
            </Button>
            <Button type="submit" className="w-full sm:w-auto" disabled={saving}>
              {saving ? "Enregistrement..." : "Enregistrer facture"}
            </Button>
          </div>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </form>

      <div className="overflow-x-auto rounded-md border p-2 -mx-1 sm:mx-0">
        <table className="w-full text-xs sm:text-sm min-w-[640px]">
          <thead>
            <tr className="border-b">
              <th className="text-left py-2">Numero</th>
              <th className="text-left py-2">Date</th>
              <th className="text-left py-2">Lieu</th>
              <th className="text-left py-2">Client</th>
              <th className="text-right py-2">Total</th>
              <th className="text-left py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="py-2" colSpan={6}>Chargement...</td>
              </tr>
            ) : factures.length === 0 ? (
              <tr>
                <td className="py-2" colSpan={6}>Aucune facture.</td>
              </tr>
            ) : (
              factures.map((f) => (
                <tr key={f.id} className="border-b">
                  <td className="py-1.5 font-mono">{f.numero}</td>
                  <td className="py-1.5">{new Date(f.date).toLocaleString("fr-FR")}</td>
                  <td className="py-1.5">{f.lieu_nom}</td>
                  <td className="py-1.5">{f.client_nom || "-"}</td>
                  <td className="py-1.5 text-right">{Number(f.total).toFixed(2)}</td>
                  <td className="py-1.5">
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" type="button" onClick={() => setSelected(f)}>
                        Voir
                      </Button>
                      <Button size="sm" type="button" onClick={() => printInvoice(f.id)}>
                        Imprimer facture
                      </Button>
                      <Button size="sm" type="button" variant="outline" onClick={() => downloadInvoice(f.id)}>PDF</Button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 print:bg-transparent">
          <div className="invoice-a4-print w-full max-w-3xl rounded-md bg-white text-black p-6 shadow-xl print:shadow-none">
            <div className="flex items-start justify-between border-b pb-3">
              <div>
                <p className="text-2xl font-semibold">FACTURE</p>
                <p className="text-sm">{selected.lieu_nom}</p>
              </div>
              <div className="text-right text-sm">
                <p className="font-mono">{selected.numero}</p>
                <p>{new Date(selected.date).toLocaleString("fr-FR")}</p>
              </div>
            </div>
            <div className="mt-3 text-sm space-y-1">
              <p><span className="font-medium">Client:</span> {selected.client_nom || "-"}</p>
              <p><span className="font-medium">Contact:</span> {selected.client_contact || "-"}</p>
              {selected.notes && <p><span className="font-medium">Notes:</span> {selected.notes}</p>}
            </div>
            <table className="w-full mt-4 text-sm border">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-2">Description</th>
                  <th className="text-right p-2">Qté</th>
                  <th className="text-right p-2">PU</th>
                  <th className="text-right p-2">Total</th>
                </tr>
              </thead>
              <tbody>
                {selected.lignes.map((l) => (
                  <tr className="border-b" key={l.id}>
                    <td className="p-2">{l.description}</td>
                    <td className="p-2 text-right">{Number(l.quantite).toFixed(2)}</td>
                    <td className="p-2 text-right">{Number(l.prix_unitaire).toFixed(2)}</td>
                    <td className="p-2 text-right">{Number(l.total).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-4 text-right text-lg font-semibold">Total: {Number(selected.total).toFixed(2)}</p>
          </div>

          <div className="print:hidden absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2">
            <Button type="button" onClick={() => printInvoice(selected.id)}>Imprimer A4</Button>
            <Button type="button" variant="outline" onClick={() => downloadInvoice(selected.id)}>Télécharger PDF</Button>
            <Button type="button" variant="outline" onClick={() => setSelected(null)}>Fermer</Button>
          </div>
        </div>
      )}
    </div>
  );
}
