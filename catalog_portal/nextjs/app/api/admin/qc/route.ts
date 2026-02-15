import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";

export const runtime = "nodejs";

type QcAction = "APPROVED" | "REJECTED";

type QcRow = {
  id: string;
  sku: string;
  name: string;
  categoryName: string;
  sellerName: string;
  qcStatus: "PENDING" | "APPROVED" | "REJECTED";
  qcReason: string | null;
  createdAt: string;
};

const defaultRows: QcRow[] = [
  {
    id: "p-101",
    sku: "WK-HEEL-001",
    name: "Women Block Heels",
    categoryName: "Women Footwear",
    sellerName: "Quickdeck Supplier 1",
    qcStatus: "PENDING",
    qcReason: null,
    createdAt: "2026-02-14T00:00:00.000Z",
  },
  {
    id: "p-102",
    sku: "WK-KURTI-010",
    name: "Printed Kurti",
    categoryName: "Women Kurtis",
    sellerName: "Quickdeck Supplier 2",
    qcStatus: "PENDING",
    qcReason: null,
    createdAt: "2026-02-14T00:00:00.000Z",
  },
];

const candidatePaths = [
  path.resolve(process.cwd(), "data", "qc_rows.json"),
  path.resolve(process.cwd(), "catalog_portal", "nextjs", "data", "qc_rows.json"),
];

async function getDataFilePath(): Promise<string> {
  for (const filePath of candidatePaths) {
    try {
      await fs.access(filePath);
      return filePath;
    } catch {
      continue;
    }
  }

  const fallback = candidatePaths[candidatePaths.length - 1];
  await fs.mkdir(path.dirname(fallback), { recursive: true });
  await fs.writeFile(fallback, JSON.stringify(defaultRows, null, 2), "utf8");
  return fallback;
}

function stripBom(text: string): string {
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

async function readRows(): Promise<QcRow[]> {
  const filePath = await getDataFilePath();
  const raw = stripBom(await fs.readFile(filePath, "utf8")).trim();
  if (!raw) return [];
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed) ? parsed : [];
}

async function writeRows(rows: QcRow[]): Promise<void> {
  const filePath = await getDataFilePath();
  await fs.writeFile(filePath, JSON.stringify(rows, null, 2), "utf8");
}

export async function GET() {
  try {
    const rows = await readRows();
    return NextResponse.json({ rows }, { status: 200 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load QC rows";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const productId = String(body.productId ?? "").trim();
    const action = String(body.action ?? "").trim() as QcAction;
    const reason = String(body.reason ?? "").trim();

    if (!productId) return NextResponse.json({ error: "productId is required" }, { status: 400 });
    if (action !== "APPROVED" && action !== "REJECTED") {
      return NextResponse.json({ error: "action must be APPROVED or REJECTED" }, { status: 400 });
    }
    if (action === "REJECTED" && !reason) {
      return NextResponse.json({ error: "Reason for rejection is required" }, { status: 400 });
    }

    const rows = await readRows();
    const idx = rows.findIndex((row) => row.id === productId);
    if (idx < 0) return NextResponse.json({ error: "Catalog not found" }, { status: 404 });

    const updated: QcRow = {
      ...rows[idx],
      qcStatus: action,
      qcReason: action === "REJECTED" ? reason : null,
    };
    rows[idx] = updated;

    await writeRows(rows);
    return NextResponse.json({ ok: true, row: updated }, { status: 200 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Internal server error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
