import pandas as pd
from pymongo import MongoClient
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def run_quickdeck_upsert():
    excel_filename = "products.xlsx"
    excel_path = "products.xlsx"

    try:
        MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        client = MongoClient(MONGODB_URI)
        db = client['quickdeck_db']
        products_collection = db['products']
    except Exception as e:
        print(f"Database Connection Error: {e}")
        return

    if not os.path.exists(excel_path):
        print(f"Error: File '{excel_filename}' not found.")
        return

    df = pd.read_excel(excel_path)
    df.columns = [str(c).strip().lower() for c in df.columns]

    # We group by SKU to avoid creating 5 separate products for different sizes
    # We will store sizes as a list inside the product document
    sku_col = 'sku'
    processed_skus = 0

    # Grouping sizes by SKU
    grouped = df.groupby(sku_col)

    for sku_val, group in grouped:
        if not sku_val or str(sku_val) == 'nan': continue

        # Take the first row for general product info
        first_row = group.iloc[0]

        # Get all sizes available for this SKU from the Excel
        available_sizes = group['size'].dropna().astype(str).tolist()

        product_data = {
            'product_name': str(first_row.get('product name', '')),
            'description': str(first_row.get('description', '')),
            'mrp': float(first_row.get('mrp', 0)),
            'price': float(first_row.get('selling price', 0)),
            'meesho_price': float(first_row.get('selling price', 0)),
            'sku_id': str(sku_val),
            'category': str(first_row.get('generic name', 'Ladies Footwear')),
            'color': str(first_row.get('color', '')),
            'material': str(first_row.get('material', '')),
            'heel_type': str(first_row.get('heel type', '')),
            'heel_height_in': str(first_row.get('heel height (in)', '')),
            'hsn_code': str(first_row.get('hsn code', '')),
            'gst': str(first_row.get('gst', '')),
            'sizes': available_sizes,  # Storing all sizes (4, 5, 6, 7, 8) in one record
            'image': 'placeholder.jpg',
            'image_1': '/static/images/products/placeholder.jpg',
            'updated_at': datetime.now()
        }

        # UPSERT: Update if SKU exists, Insert if it doesn't
        products_collection.update_one(
            {'sku_id': str(sku_val)},
            {'$set': product_data},
            upsert=True
        )
        print(f"Synced SKU: {sku_val} (Sizes: {', '.join(available_sizes)})")
        processed_skus += 1

    print(f"\n--- SYNC COMPLETE ---")
    print(f"Successfully synced {processed_skus} unique products to your database.")


if __name__ == "__main__":
    run_quickdeck_upsert()