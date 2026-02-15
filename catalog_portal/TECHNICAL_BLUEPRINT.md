# Technical Blueprint: Catalog Management Portal

## 1. Objective
Build a supplier-facing catalog management system similar to the Meesho supplier panel with:
- Flexible category-driven product attributes.
- Variant-level inventory.
- Single and bulk catalog upload.
- Admin quality check (approve/reject) workflow.

## 2. Target Stack
- Frontend: Next.js 14+ (App Router), React, Tailwind CSS.
- Backend APIs: Next.js Route Handlers.
- DB: PostgreSQL.
- ORM: Prisma.
- Bulk ingestion worker: Python (`pandas`, `psycopg2`).

## 3. Core Domain Model
- `Category`: Tree hierarchy (`parent_id`) for nested dropdowns.
- `Attribute`: Global attribute definitions (`value_type`).
- `CategoryAttribute`: Attribute assignment to category with required/optional metadata.
- `Product`: Core listing and QC state.
- `ProductAttributeValue`: Actual attribute values per product.
- `ProductVariant`: Variant rows for size/color combinations.
- `Inventory`: Variant-wise stock and reserve counters.
- `QcLog`: Auditable approve/reject transitions.

## 4. Upload Flows
### 4.1 Single Upload (UI/API)
- Multi-step form:
1. Category selection (group + leaf).
2. Core product fields.
3. Image upload + dynamic category attributes.
4. Variant definition.
- Backend validation:
- Required fields present.
- `sellingPrice <= mrp`.
- Reject action requires reason.

### 4.2 Bulk Upload (CSV/XLSX)
- Parse file into normalized dataframe.
- Column-level required checks.
- Row-level validation with detailed error list.
- Transactional persistence:
- Upsert product by `sku`.
- Replace images and variants atomically.
- Upsert dynamic attributes by `attr_<code>` convention.

## 5. QC Workflow
- Initial state: `PENDING`.
- Admin actions:
- `APPROVED`: catalog moves live/ready.
- `REJECTED`: mandatory rejection reason saved.
- State changes logged in `qc_logs`.

## 6. API Contracts (starter)
- `POST /api/catalog/single`
- Input: product payload from form.
- Output: created catalog + `PENDING` QC status.
- `POST /api/catalog/bulk`
- Input: multipart file.
- Output: accepted file metadata (or validation errors).
- `GET /api/admin/qc`
- Output: pending/recent QC rows.
- `POST /api/admin/qc`
- Input: `{ productId, action, reason }`.
- Output: updated QC state.

## 7. Data Validation Rules
- Price rules:
- `mrp >= 0`, `selling_price >= 0`.
- `selling_price <= mrp`.
- Variant stock values are non-negative ints.
- Category and attribute IDs must exist.
- Rejection reason required when status is `REJECTED`.

## 8. Security and Access
- Seller scope:
- Create/update own products only.
- Admin scope:
- QC dashboard and approve/reject endpoints.
- Add auth middleware and role-based guards in API handlers.

## 9. Performance Considerations
- Indexes on `products(category_id)`, `products(qc_status)`, `product_variants(product_id)`.
- Bulk upload does batched transactional writes.
- Use background queue for very large files (future: Celery/BullMQ).

## 10. Rollout Plan
1. Apply SQL schema and Prisma migrations.
2. Integrate Next.js routes/components into main app.
3. Connect `/api/catalog/bulk` to Python worker/job queue.
4. Add object storage for image binaries.
5. Add automated tests for pricing and QC rules.
