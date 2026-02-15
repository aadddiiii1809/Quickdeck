"use client";

import { useEffect, useState } from "react";

type CatalogQcRow = {
  id: string;
  sku: string;
  name: string;
  categoryName: string;
  sellerName: string;
  qcStatus: "PENDING" | "APPROVED" | "REJECTED";
  createdAt: string;
};

export default function AdminQcPage() {
  const [rows, setRows] = useState<CatalogQcRow[]>([]);
  const [reasonById, setReasonById] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadRows = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/admin/qc");
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error ?? "Unable to load QC rows");
      }
      setRows(data.rows ?? []);
    } catch (apiError) {
      const message = apiError instanceof Error ? apiError.message : "Unexpected error";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadRows();
  }, []);

  const updateQc = async (id: string, action: "APPROVED" | "REJECTED") => {
    setError("");
    try {
      const response = await fetch("/api/admin/qc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ productId: id, action, reason: reasonById[id] ?? "" }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error ?? "QC update failed");
      }

      await loadRows();
    } catch (actionError) {
      const message = actionError instanceof Error ? actionError.message : "Unexpected error";
      setError(message);
    }
  };

  return (
    <main className="min-h-screen bg-slate-100 p-6">
      <div className="mx-auto max-w-7xl rounded-xl bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold text-slate-900">Catalog QC Dashboard</h1>
        <p className="mt-1 text-sm text-slate-500">Approve or reject submitted catalogs with mandatory rejection reason.</p>

        {error ? <div className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}

        {loading ? (
          <div className="mt-6 text-sm text-slate-600">Loading...</div>
        ) : (
          <div className="mt-6 overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="px-3 py-2">SKU</th>
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Category</th>
                  <th className="px-3 py-2">Seller</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Reason for Rejection</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className="px-3 py-3">{row.sku}</td>
                    <td className="px-3 py-3">{row.name}</td>
                    <td className="px-3 py-3">{row.categoryName}</td>
                    <td className="px-3 py-3">{row.sellerName}</td>
                    <td className="px-3 py-3">{row.qcStatus}</td>
                    <td className="px-3 py-3">
                      <input
                        value={reasonById[row.id] ?? ""}
                        onChange={(event) => setReasonById((prev) => ({ ...prev, [row.id]: event.target.value }))}
                        placeholder="Required for reject"
                        className="w-64 rounded-md border border-slate-300 px-2 py-1"
                      />
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex gap-2">
                        <button className="rounded bg-emerald-600 px-3 py-1 text-white" onClick={() => updateQc(row.id, "APPROVED")}>Approve</button>
                        <button className="rounded bg-rose-600 px-3 py-1 text-white" onClick={() => updateQc(row.id, "REJECTED")}>Reject</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
