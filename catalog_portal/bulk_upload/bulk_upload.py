"""Bulk upload engine for catalog products.

Usage:
  python bulk_upload.py --file products.xlsx --db-url postgresql://user:pass@host:5432/dbname
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg2
from psycopg2.extras import Json

REQUIRED_COLUMNS = ["sku", "name", "category_slug", "mrp", "selling_price"]


@dataclass
class ValidationError:
    row_number: int
    message: str


class BulkUploader:
    def __init__(self, db_url: str) -> None:
        self.db_url = db_url

    def run(self, file_path: str, dry_run: bool = False) -> dict[str, Any]:
        frame = self._load_file(file_path)
        errors = self._validate_frame(frame)
        if errors:
            return {
                "ok": False,
                "created": 0,
                "updated": 0,
                "skipped": len(errors),
                "errors": [f"Row {e.row_number}: {e.message}" for e in errors],
            }

        if dry_run:
            return {"ok": True, "created": len(frame), "updated": 0, "skipped": 0, "errors": []}

        return self._persist(frame)

    def _load_file(self, file_path: str) -> pd.DataFrame:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = path.suffix.lower()
        if suffix == ".csv":
            frame = pd.read_csv(path)
        elif suffix in {".xlsx", ".xls"}:
            frame = pd.read_excel(path)
        else:
            raise ValueError("Only CSV/XLS/XLSX files are supported")

        frame.columns = [str(column).strip().lower() for column in frame.columns]
        return frame.fillna("")

    def _validate_frame(self, frame: pd.DataFrame) -> list[ValidationError]:
        errors: list[ValidationError] = []

        for column in REQUIRED_COLUMNS:
            if column not in frame.columns:
                errors.append(ValidationError(1, f"Missing required column '{column}'"))

        if errors:
            return errors

        for index, row in frame.iterrows():
            row_number = index + 2
            for column in REQUIRED_COLUMNS:
                if str(row[column]).strip() == "":
                    errors.append(ValidationError(row_number, f"'{column}' cannot be empty"))

            try:
                mrp = self._to_decimal(row["mrp"])
                selling_price = self._to_decimal(row["selling_price"])
            except ValueError as exc:
                errors.append(ValidationError(row_number, str(exc)))
                continue

            if selling_price > mrp:
                errors.append(ValidationError(row_number, "selling_price cannot be greater than mrp"))

        return errors

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            raise ValueError(f"Invalid numeric value '{value}'")

        if number < 0:
            raise ValueError("Numeric values cannot be negative")
        return number

    def _persist(self, frame: pd.DataFrame) -> dict[str, Any]:
        created = 0
        updated = 0

        with psycopg2.connect(self.db_url) as connection:
            with connection.cursor() as cursor:
                for _, row in frame.iterrows():
                    product_payload = self._map_row(row)
                    product_id, is_created = self._upsert_product(cursor, product_payload)
                    if is_created:
                        created += 1
                    else:
                        updated += 1

                    self._replace_product_images(cursor, product_id, product_payload["images"])
                    self._replace_variants(cursor, product_id, product_payload["variants"])
                    self._upsert_attribute_values(cursor, product_id, product_payload["attributes"])

        return {"ok": True, "created": created, "updated": updated, "skipped": 0, "errors": []}

    def _map_row(self, row: pd.Series) -> dict[str, Any]:
        images = [img.strip() for img in str(row.get("images", "")).split("|") if img.strip()]

        variants: list[dict[str, Any]] = []
        variant_cell = str(row.get("variants", "")).strip()
        if variant_cell:
            try:
                parsed_variants = json.loads(variant_cell)
                if isinstance(parsed_variants, list):
                    variants = parsed_variants
            except json.JSONDecodeError:
                variants = []

        attributes: dict[str, Any] = {}
        for key, value in row.items():
            if key.startswith("attr_") and str(value).strip() != "":
                attributes[key.replace("attr_", "")] = value

        return {
            "sku": str(row["sku"]).strip(),
            "name": str(row["name"]).strip(),
            "category_slug": str(row["category_slug"]).strip(),
            "description": str(row.get("description", "")).strip() or None,
            "brand": str(row.get("brand", "")).strip() or None,
            "hsn_code": str(row.get("hsn_code", "")).strip() or None,
            "mrp": self._to_decimal(row["mrp"]),
            "selling_price": self._to_decimal(row["selling_price"]),
            "currency": str(row.get("currency", "INR")).strip() or "INR",
            "images": images,
            "variants": variants,
            "attributes": attributes,
        }

    @staticmethod
    def _variant_value(variant: dict[str, Any], snake_key: str, camel_key: str, default: Any = None) -> Any:
        if snake_key in variant:
            return variant.get(snake_key)
        if camel_key in variant:
            return variant.get(camel_key)
        return default

    @staticmethod
    def _upsert_product(cursor: Any, payload: dict[str, Any]) -> tuple[str, bool]:
        cursor.execute(
            """
            INSERT INTO products (
                category_id, sku, name, description, brand, hsn_code, mrp, selling_price, currency, primary_image_url
            )
            SELECT c.id, %s, %s, %s, %s, %s, %s, %s, %s, %s
            FROM categories c
            WHERE c.slug = %s
            ON CONFLICT (sku)
            DO UPDATE SET
                category_id = EXCLUDED.category_id,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                brand = EXCLUDED.brand,
                hsn_code = EXCLUDED.hsn_code,
                mrp = EXCLUDED.mrp,
                selling_price = EXCLUDED.selling_price,
                currency = EXCLUDED.currency,
                primary_image_url = EXCLUDED.primary_image_url,
                updated_at = NOW()
            RETURNING id, (xmax = 0) AS inserted
            """,
            (
                payload["sku"],
                payload["name"],
                payload["description"],
                payload["brand"],
                payload["hsn_code"],
                payload["mrp"],
                payload["selling_price"],
                payload["currency"],
                payload["images"][0] if payload["images"] else None,
                payload["category_slug"],
            ),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Category slug '{payload['category_slug']}' does not exist")
        return row[0], bool(row[1])

    @staticmethod
    def _replace_product_images(cursor: Any, product_id: str, images: list[str]) -> None:
        cursor.execute("DELETE FROM product_images WHERE product_id = %s", (product_id,))
        for index, image_url in enumerate(images):
            cursor.execute(
                "INSERT INTO product_images (product_id, image_url, sort_order) VALUES (%s, %s, %s)",
                (product_id, image_url, index),
            )

    def _replace_variants(self, cursor: Any, product_id: str, variants: list[dict[str, Any]]) -> None:
        cursor.execute(
            "DELETE FROM inventory WHERE variant_id IN (SELECT id FROM product_variants WHERE product_id = %s)",
            (product_id,),
        )
        cursor.execute("DELETE FROM product_variants WHERE product_id = %s", (product_id,))

        for variant in variants:
            variant_sku = str(self._variant_value(variant, "variant_sku", "variantSku", "") or "").strip()
            if not variant_sku:
                continue

            cursor.execute(
                """
                INSERT INTO product_variants (product_id, variant_sku, color, size, mrp, selling_price, barcode)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    product_id,
                    variant_sku,
                    self._variant_value(variant, "color", "color"),
                    self._variant_value(variant, "size", "size"),
                    self._variant_value(variant, "mrp", "mrp"),
                    self._variant_value(variant, "selling_price", "sellingPrice"),
                    self._variant_value(variant, "barcode", "barcode"),
                ),
            )
            variant_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO inventory (variant_id, quantity, reserved_quantity, reorder_level)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    variant_id,
                    int(self._variant_value(variant, "quantity", "quantity", 0) or 0),
                    int(self._variant_value(variant, "reserved_quantity", "reservedQuantity", 0) or 0),
                    int(self._variant_value(variant, "reorder_level", "reorderLevel", 0) or 0),
                ),
            )

    @staticmethod
    def _upsert_attribute_values(cursor: Any, product_id: str, attributes: dict[str, Any]) -> None:
        for code, value in attributes.items():
            cursor.execute("SELECT id, value_type FROM attributes WHERE code = %s", (code,))
            attr_row = cursor.fetchone()
            if not attr_row:
                continue

            attribute_id, value_type = attr_row
            fields = {
                "value_text": None,
                "value_number": None,
                "value_boolean": None,
                "value_date": None,
                "value_json": None,
            }

            if value_type == "TEXT":
                fields["value_text"] = str(value)
            elif value_type == "NUMBER":
                fields["value_number"] = Decimal(str(value))
            elif value_type == "BOOLEAN":
                fields["value_boolean"] = str(value).strip().lower() in {"true", "1", "yes"}
            elif value_type == "DATE":
                fields["value_date"] = str(value)
            elif value_type == "JSON":
                fields["value_json"] = Json(value if isinstance(value, dict) else {"value": value})

            cursor.execute(
                """
                INSERT INTO product_attribute_values (
                    product_id, attribute_id, value_text, value_number, value_boolean, value_date, value_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (product_id, attribute_id)
                DO UPDATE SET
                    value_text = EXCLUDED.value_text,
                    value_number = EXCLUDED.value_number,
                    value_boolean = EXCLUDED.value_boolean,
                    value_date = EXCLUDED.value_date,
                    value_json = EXCLUDED.value_json,
                    updated_at = NOW()
                """,
                (
                    product_id,
                    attribute_id,
                    fields["value_text"],
                    fields["value_number"],
                    fields["value_boolean"],
                    fields["value_date"],
                    fields["value_json"],
                ),
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk upload catalog products")
    parser.add_argument("--file", required=True, help="Path to CSV/XLSX file")
    parser.add_argument("--db-url", required=True, help="PostgreSQL connection URL")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, skip database writes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uploader = BulkUploader(args.db_url)

    try:
        result = uploader.run(args.file, dry_run=args.dry_run)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, indent=2))
        raise SystemExit(1)

    print(json.dumps(result, indent=2, default=str))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
