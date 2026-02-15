import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-100 p-8">
      <div className="mx-auto max-w-3xl rounded-xl bg-white p-8 shadow-sm">
        <h1 className="text-3xl font-semibold text-slate-900">Catalog Management Portal</h1>
        <p className="mt-2 text-slate-600">Use the links below to start working with catalogs.</p>

        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href="/catalog/new"
            className="rounded-md bg-slate-900 px-4 py-2 text-white"
          >
            Single Catalog Upload
          </Link>
          <Link
            href="/admin/qc"
            className="rounded-md bg-emerald-600 px-4 py-2 text-white"
          >
            Admin QC Dashboard
          </Link>
        </div>
      </div>
    </main>
  );
}
