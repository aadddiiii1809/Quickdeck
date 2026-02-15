# QUICKDECK E-Commerce + Catalog Portal

QUICKDECK is a Flask-based e-commerce platform with customer and admin flows, extended with a new Catalog Management Portal module (`catalog_portal/`) for Meesho-style catalog operations.

## Overview

This repository currently contains two working parts:

1. Flask app (primary system)
- Customer storefront
- Cart and checkout
- Orders and returns
- Admin dashboard and operations
- Bulk upload flow for products

2. Catalog Portal module (new)
- PostgreSQL + Prisma schema for flexible cataloging
- Next.js UI for single upload and admin QC
- Python bulk upload engine for CSV/XLSX ingestion

## Core Tech Stack

### Primary App
- Python 3.11+
- Flask
- MongoDB (PyMongo)
- Jinja2 templates
- Bootstrap + custom CSS/JS

### Catalog Portal Module
- Next.js (App Router)
- React + Tailwind CSS
- PostgreSQL schema + Prisma models
- Python ingestion service (`pandas`, `openpyxl`, `psycopg2-binary`)

## Features

### Customer Features (Flask)
- Product browsing and search
- Category listing
- User signup/login/logout
- Cart management
- Checkout and order placement
- My Orders, Wishlist

### Admin Features (Flask)
- Dashboard with live stats and charts
- Product add/edit/delete
- Order status management
- Customer view
- Returns handling
- Settings and analytics views
- Bulk upload page

### Catalog Portal Features (New)
- Dynamic attribute-ready data model
- Variant-level catalog creation (size/color/quantity)
- Single upload multi-step form
- Admin QC dashboard (Approve/Reject + reason)
- Bulk ingest script with validations and DB mapping

## Project Structure

```text
QuickdeckEcom/
|-- app.py
|-- init_data.py
|-- update_db.py
|-- requirements.txt
|-- pyproject.toml
|-- README.md
|-- replit.md
|-- static/
|   |-- js/
|   |   |-- admin.js
|   |   |-- catalog.js
|   |   |-- customers.js
|   |   |-- main.js
|   |   `-- orders.js
|   `-- admin/css/
|       |-- admin.css
|       |-- catalog.css
|       `-- style.css
|-- templates/
|   |-- base.html
|   |-- index.html
|   |-- products.html
|   |-- product_detail.html
|   |-- cart.html
|   |-- checkout.html
|   |-- my_orders.html
|   |-- order_success.html
|   |-- login.html
|   |-- signup.html
|   |-- wishlist.html
|   |-- categories.html
|   |-- about.html
|   |-- contact.html
|   `-- admin/
|       |-- base.html
|       |-- dashboard.html
|       |-- products.html
|       |-- add_product.html
|       |-- edit_product.html
|       |-- orders.html
|       |-- customers.html
|       |-- bulk_upload.html
|       |-- analytics.html
|       |-- activities.html
|       |-- returns.html
|       `-- settings.html
`-- catalog_portal/
    |-- TECHNICAL_BLUEPRINT.md
    |-- README.md
    |-- database/
    |   `-- schema.sql
    |-- prisma/
    |   `-- schema.prisma
    |-- bulk_upload/
    |   `-- bulk_upload.py
    `-- nextjs/
        |-- package.json
        |-- tsconfig.json
        |-- next.config.mjs
        |-- tailwind.config.ts
        |-- postcss.config.js
        |-- app/
        |   |-- layout.tsx
        |   |-- page.tsx
        |   |-- globals.css
        |   |-- catalog/new/page.tsx
        |   |-- admin/qc/page.tsx
        |   `-- api/
        |       |-- catalog/single/route.ts
        |       |-- catalog/bulk/route.ts
        |       `-- admin/qc/route.ts
        |-- components/catalog/CatalogMultiStepForm.tsx
        `-- data/qc_rows.json
```

## Setup and Run

### A) Flask App

1. Install Python deps
```bash
pip install -r requirements.txt
```

2. Ensure MongoDB is running (local or configured URI)
- Default expected: `mongodb://localhost:27017/`

3. (Optional) Seed data
```bash
python init_data.py
```

4. Start app
```bash
python app.py
```

5. Open
- `http://localhost:5000`

### B) Catalog Portal Next.js Module

```bash
cd catalog_portal/nextjs
npm install
npm run dev
```

Open:
- `http://localhost:3000/`
- `http://localhost:3000/catalog/new`
- `http://localhost:3000/admin/qc`

### C) Catalog Portal Bulk Script

From project root (`QuickdeckEcom/`):
```bash
python catalog_portal/bulk_upload/bulk_upload.py --file products.xlsx --db-url postgresql://USER:PASS@HOST:5432/DBNAME
```

If you are inside `catalog_portal/nextjs`:
```bash
python ../bulk_upload/bulk_upload.py --file ../../products.xlsx --db-url postgresql://USER:PASS@HOST:5432/DBNAME
```

Dry run:
```bash
python catalog_portal/bulk_upload/bulk_upload.py --file products.xlsx --db-url postgresql://USER:PASS@HOST:5432/DBNAME --dry-run
```

Dry run (from `catalog_portal/nextjs`):
```bash
python ../bulk_upload/bulk_upload.py --file ../../products.xlsx --db-url postgresql://USER:PASS@HOST:5432/DBNAME --dry-run
```

## Environment Notes

### Flask
- `MONGODB_URI` (optional)
- `SESSION_SECRET` (optional)
- `MAX_UPLOAD_MB` (optional)

### Catalog Portal
- Prisma uses `DATABASE_URL` in `catalog_portal/prisma/schema.prisma`.
- Apply SQL from `catalog_portal/database/schema.sql` before using PostgreSQL workflows.

## Important Recent Changes

- Added full `catalog_portal/` module with SQL, Prisma, Next.js UI/API, and Python ingestion.
- Added DB-level constraints for price ordering (`selling_price <= mrp`).
- Bulk uploader now supports both `variantSku` and `variant_sku` inputs.
- Added Next.js root page to remove `/` 404.
- Fixed BOM/encoding issues in JSON/config files that caused runtime parse failures.
- Hardened QC API loading and persistence with `nextjs/data/qc_rows.json`.
- Updated Step 4 catalog form UX with proper variant labels and clearer price validation.
- Fixed admin dashboard template robustness for mixed image field types.
- Refactored dashboard chart-data injection to reduce VS Code false syntax errors in template JS.

## Default Accounts (if seeded)

Admin:
- Email: `admin@quickdeck.com`
- Password: `admin123`

Demo User:
- Email: `demo@example.com`
- Password: `demo123`

## Known Scope

- Primary production app is still Flask + MongoDB.
- `catalog_portal/nextjs` is a modular starter and currently runs separately from Flask.
- End-to-end auth unification between Flask and Next.js is not yet wired.

## Company

- Name: QUICKDECK
- Tagline: Your Gateway to Global Retail
- Contact: 8097130846 / 9619328102
- Address: Vasant Nagar, G-70/2, Thakkar Bappa Colony, Near Gopal Hotel, Chembur, Mumbai, Maharashtra, 400071

## License

Proprietary project for QUICKDECK.
