# Catalog Management Portal Starter (Meesho-style)

This module adds a production-friendly starter blueprint using:
- Next.js + Tailwind CSS (single upload + admin QC UI)
- PostgreSQL + Prisma ORM (catalog schema)
- Python bulk upload service (CSV/XLSX parser + validation)

## What is included
- `database/schema.sql`: PostgreSQL DDL with dynamic attributes, variants, inventory, and QC workflow.
- `prisma/schema.prisma`: Prisma models aligned with SQL schema.
- `bulk_upload/bulk_upload.py`: Bulk uploader with validation (`selling_price <= mrp`) and DB upsert logic.
- `nextjs/components/catalog/CatalogMultiStepForm.tsx`: Multi-step single upload form with dynamic attributes and image previews.
- `nextjs/app/api/catalog/single/route.ts`: API endpoint for single catalog create.
- `nextjs/app/admin/qc/page.tsx`: Admin quality check dashboard.
- `nextjs/app/api/admin/qc/route.ts`: Approve/Reject endpoint with rejection reason validation.
- `nextjs/app/api/catalog/bulk/route.ts`: Trigger/ingest endpoint for bulk upload in Next.js layer.

## Integration notes
1. Create PostgreSQL DB and apply `database/schema.sql`.
2. Update `prisma/schema.prisma` `DATABASE_URL` and run Prisma migrations.
3. Add Python dependencies: `pip install pandas openpyxl psycopg2-binary`.
4. Wire your auth middleware so seller/admin IDs flow into API routes.
5. Connect file upload storage to S3/Cloudinary before production.

## Clean code defaults used
- Explicit DTO-style payload parsing and validation.
- Separation of parsing, validation, and persistence in bulk upload.
- Guard clauses for all failure paths.
- Consistent naming and typed interfaces in TS.

## Recent Changes Applied (Feb 14, 2026)

### New Files and Features
- Added `TECHNICAL_BLUEPRINT.md` with module architecture, data model, API contracts, and rollout plan.
- Added PostgreSQL schema at `database/schema.sql`.
- Added Prisma schema at `prisma/schema.prisma`.
- Added bulk upload service at `bulk_upload/bulk_upload.py`.
- Added Next.js UI and APIs:
  - `app/catalog/new/page.tsx`
  - `components/catalog/CatalogMultiStepForm.tsx`
  - `app/admin/qc/page.tsx`
  - `app/api/catalog/single/route.ts`
  - `app/api/catalog/bulk/route.ts`
  - `app/api/admin/qc/route.ts`

### Important Fixes Done
- Enforced price ordering in DB (`selling_price <= mrp`) and added ALTER statements for existing DBs.
- Updated bulk ingestion to support both `variantSku` and `variant_sku` payload keys.
- Updated bulk product upsert to refresh `category_id` on SKU conflicts.
- Added image preview URL cleanup in React (`URL.revokeObjectURL`).
- Added persistent QC data via `nextjs/data/qc_rows.json` and hardened API JSON parsing.
- Added Next.js root route (`app/page.tsx`) to remove `/` 404.
- Fixed config/JSON encoding issues (BOM-related parsing failures).
- Improved Step 4 variant UX with proper labels and clearer price validation message.

### Local Run Commands
```bash
# Flask app
python app.py

# Next.js catalog module
cd catalog_portal/nextjs
npm install
npm run dev
```

