import { NextResponse } from "next/server";

function badRequest(message: string) {
  return NextResponse.json({ error: message }, { status: 400 });
}

export async function POST(request: Request) {
  try {
    const payload = await request.json();

    if (!payload.categoryId || !payload.sku || !payload.name) {
      return badRequest("categoryId, sku, and name are required.");
    }

    const mrp = Number(payload.mrp);
    const sellingPrice = Number(payload.sellingPrice);

    if (Number.isNaN(mrp) || Number.isNaN(sellingPrice)) {
      return badRequest("mrp and sellingPrice must be valid numbers.");
    }

    if (sellingPrice > mrp) {
      return badRequest("sellingPrice cannot be greater than mrp.");
    }

    const record = {
      id: crypto.randomUUID(),
      qcStatus: "PENDING",
      createdAt: new Date().toISOString(),
      ...payload,
    };

    return NextResponse.json({ ok: true, catalog: record }, { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Internal server error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
