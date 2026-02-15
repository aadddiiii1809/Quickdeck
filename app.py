from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.errors import InvalidId
from datetime import datetime, timedelta
import os
import base64
import io
import csv
import zipfile
import xml.etree.ElementTree as ET
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from functools import wraps
import json
import re

try:
    import razorpay  # type: ignore
except Exception:
    razorpay = None

try:
    import stripe  # type: ignore
except Exception:
    stripe = None

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SESSION_SECRET', 'quickdeck-retail-2026-key')
app.config['UPLOAD_FOLDER'] = 'static/images/products'
# Allow larger admin upload files (default 50 MB, configurable by env).
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_MB', '50')) * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database Setup
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGODB_URI)
db = client['quickdeck_db']

users_collection = db['users']
products_collection = db['products']
orders_collection = db['orders']
cart_collection = db['cart']
wishlist_collection = db['wishlist']
reviews_collection = db['reviews']
coupons_collection = db['coupons']
returns_collection = db['returns']

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
BULK_ALLOWED_EXTENSIONS = {'csv', 'xlsx'}
BULK_REQUIRED_ATTRIBUTES = [
    'SKU',
    'Product Name',
    'Description',
    'Ornamentation',
    'Occasion',
    'Generic Name',
    'Size',
    'Fastening & Back Detail',
    'Heel Height',
    'Heel Type',
    'Heel Height (in)',
    'Insole',
    'Material',
    'Sole Material',
    'Pattern',
    'Type',
    'Net Quantity',
    'MRP',
    'Selling Price',
    'Wrong/Defective Returns Price',
    'Length Size',
    'Width Size',
    'Net Weight',
    'HSN Code',
    'GST',
    'Color',
    'Ankle Height',
    'Toe Type',
    'COUNTRY OF ORIGIN',
    'Manufacturer Name',
    'Manufacturer Address'
]
BULK_REQUIRED_NORMALIZED = set()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def normalize_bulk_header(value):
    return ' '.join((value or '').replace('\n', ' ').replace('\r', ' ').strip().lower().split())


BULK_REQUIRED_NORMALIZED = {normalize_bulk_header(h) for h in BULK_REQUIRED_ATTRIBUTES}


def parse_number(value, default=0.0):
    if value is None:
        return default
    cleaned = str(value).strip().replace(',', '')
    if not cleaned:
        return default
    try:
        return float(cleaned)
    except ValueError:
        return default


def parse_int(value, default=0):
    return int(parse_number(value, default))


def split_multi_value(raw):
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    parts = re.split(r'[,/|;\n]+', text)
    cleaned = []
    for p in parts:
        v = p.strip()
        if v:
            cleaned.append(v)
    return cleaned


def normalize_image_reference(value):
    raw = str(value or '').strip().strip('"').strip("'")
    if not raw:
        return ''
    raw = raw.replace('\\', '/')
    lowered = raw.lower()

    if lowered.startswith(('http://', 'https://', 'data:image', 'blob:')):
        return raw
    if raw.startswith('/static/'):
        return raw
    if raw.startswith('static/'):
        return '/' + raw
    if raw.startswith('images/'):
        return '/static/' + raw
    if raw.startswith('/images/'):
        return '/static' + raw

    # If excel contains just a file name (e.g., shoe1.jpg), point to products folder.
    if re.search(r'\.(jpg|jpeg|png|gif|webp|avif)$', lowered):
        return '/static/images/products/' + raw.split('/')[-1]
    return raw


def collect_product_images(product):
    urls = []
    seen = set()

    for idx in range(1, 9):
        candidate = normalize_image_reference(product.get(f'image_{idx}', ''))
        if candidate and candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)

    image_list = product.get('images', [])
    if isinstance(image_list, list):
        for img in image_list:
            candidate = normalize_image_reference(img)
            if candidate and candidate not in seen:
                seen.add(candidate)
                urls.append(candidate)

    fallback_single = normalize_image_reference(product.get('image', ''))
    if fallback_single and fallback_single not in seen:
        seen.add(fallback_single)
        urls.append(fallback_single)

    if not urls:
        urls.append('/static/images/default-product.jpg')
    return urls


def collect_product_sizes(product):
    sizes = []
    seen = set()

    raw_sizes = product.get('sizes', [])
    if isinstance(raw_sizes, str):
        raw_sizes = split_multi_value(raw_sizes)
    if isinstance(raw_sizes, list):
        for s in raw_sizes:
            val = normalize_size_value(s)
            if val and val not in seen:
                seen.add(val)
                sizes.append(val)

    variants = product.get('variants', [])
    if isinstance(variants, list):
        for v in variants:
            if isinstance(v, dict):
                val = normalize_size_value(v.get('size', ''))
                if val and val not in seen:
                    seen.add(val)
                    sizes.append(val)

    return sizes


def enrich_product_for_display(product):
    if not product:
        return product
    images = collect_product_images(product)
    product['display_images'] = images
    product['display_image'] = images[0] if images else '/static/images/default-product.jpg'
    product['display_sizes'] = collect_product_sizes(product)
    return product


def normalize_size_value(value):
    val = str(value).strip()
    if not val:
        return ''
    # Normalize excel numeric-like sizes: 6.0 -> 6
    if re.fullmatch(r'\d+\.0+', val):
        return val.split('.')[0]
    return val


def get_non_empty_by_header_match(row, index_map, matcher):
    out = []
    for normalized, original in index_map.items():
        if matcher(normalized):
            value = str(row.get(original, '')).strip()
            if value:
                out.append((normalized, original, value))
    return out


def extract_variant_sizes(row, index_map):
    sizes = []
    seen = set()

    # Primary size column
    size_value = get_from_row(row, index_map, 'Size')
    for token in split_multi_value(size_value):
        s = normalize_size_value(token)
        if s and s not in seen:
            seen.add(s)
            sizes.append(s)

    # Any additional size/variant columns
    extra_size_cols = get_non_empty_by_header_match(
        row,
        index_map,
        lambda n: ('size' in n or 'variant' in n) and n not in {
            normalize_bulk_header('Length Size'),
            normalize_bulk_header('Width Size'),
            normalize_bulk_header('Heel Height'),
            normalize_bulk_header('Heel Height (in)')
        }
    )
    for _, _, value in extra_size_cols:
        # Pattern example: 6:10,7:8 or 6=10|7=8 -> extract size keys first
        pairs = re.findall(r'([0-9]+(?:\.[0-9]+)?)\s*[:=]\s*[0-9]+', value)
        candidate_tokens = pairs if pairs else split_multi_value(value)
        for token in candidate_tokens:
            s = normalize_size_value(token)
            if s and s not in seen:
                seen.add(s)
                sizes.append(s)

    # Fallback to length/width if still empty
    if not sizes:
        length_size = get_from_row(row, index_map, 'Length Size')
        width_size = get_from_row(row, index_map, 'Width Size')
        for token in [length_size, width_size]:
            s = normalize_size_value(token)
            if s and s not in seen:
                seen.add(s)
                sizes.append(s)

    return sizes


def extract_image_data(row, index_map):
    image_urls = []
    seen = set()

    # Pick all columns that look like image URL/path columns.
    image_cells = get_non_empty_by_header_match(
        row,
        index_map,
        lambda n: ('image' in n or 'img' in n or 'photo' in n or 'pic' in n)
        and 'tag' not in n and 'alt' not in n and 'label' not in n
    )
    for _, _, value in image_cells:
        for token in split_multi_value(value):
            token = normalize_image_reference(token.strip())
            if token and token not in seen:
                seen.add(token)
                image_urls.append(token)

    tags = []
    tag_cells = get_non_empty_by_header_match(
        row,
        index_map,
        lambda n: 'tag' in n or 'label' in n or 'keyword' in n
    )
    for _, _, value in tag_cells:
        for token in split_multi_value(value):
            t = token.strip()
            if t and t not in tags:
                tags.append(t)

    return image_urls, tags


def xlsx_rows_to_dicts(file_storage):
    ns = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    raw = file_storage.read()
    workbook = zipfile.ZipFile(io.BytesIO(raw))

    shared_strings = []
    if 'xl/sharedStrings.xml' in workbook.namelist():
        root = ET.fromstring(workbook.read('xl/sharedStrings.xml'))
        for si in root.findall('a:si', ns):
            text = ''.join(t.text or '' for t in si.findall('.//a:t', ns))
            shared_strings.append(text)

    if 'xl/worksheets/sheet1.xml' not in workbook.namelist():
        return [], []

    sheet = ET.fromstring(workbook.read('xl/worksheets/sheet1.xml'))
    rows = sheet.findall('a:sheetData/a:row', ns)
    if not rows:
        return [], []

    def col_ref_to_index(ref):
        letters = ''.join(ch for ch in (ref or '') if ch.isalpha()).upper()
        if not letters:
            return -1
        idx = 0
        for ch in letters:
            idx = idx * 26 + (ord(ch) - ord('A') + 1)
        return idx - 1

    def cell_value(cell):
        cell_type = cell.get('t')
        v = cell.find('a:v', ns)
        if cell_type == 'inlineStr':
            t = cell.find('.//a:t', ns)
            return t.text if t is not None and t.text is not None else ''
        if v is None:
            return ''
        raw_value = v.text or ''
        if cell_type == 's':
            idx = int(raw_value) if raw_value.isdigit() else -1
            return shared_strings[idx] if 0 <= idx < len(shared_strings) else ''
        return raw_value

    header_cells = rows[0].findall('a:c', ns)
    header_map = {}
    for c in header_cells:
        col_idx = col_ref_to_index(c.get('r', ''))
        if col_idx >= 0:
            header_map[col_idx] = str(cell_value(c)).strip()
    max_header_idx = max(header_map.keys()) if header_map else -1
    headers = [header_map.get(i, '').strip() for i in range(max_header_idx + 1)]

    data = []
    for row in rows[1:]:
        row_cells = row.findall('a:c', ns)
        row_map = {}
        for c in row_cells:
            col_idx = col_ref_to_index(c.get('r', ''))
            if col_idx >= 0:
                row_map[col_idx] = str(cell_value(c)).strip()
        if not any(row_map.values()):
            continue
        data.append({headers[i]: row_map.get(i, '') for i in range(len(headers))})

    return headers, data


def csv_rows_to_dicts(file_storage):
    raw = file_storage.read().decode('utf-8-sig', errors='ignore')
    reader = csv.DictReader(io.StringIO(raw))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    rows = []
    for row in reader:
        normalized = {str(k).strip(): (str(v).strip() if v is not None else '') for k, v in row.items()}
        if any(normalized.values()):
            rows.append(normalized)
    return headers, rows


def get_from_row(row, index_map, key, default=''):
    idx = index_map.get(normalize_bulk_header(key))
    return str(row.get(idx, default) if idx in row else default).strip() if idx is not None else default


def build_product_from_bulk_row(row, index_map):
    sku = get_from_row(row, index_map, 'SKU')
    product_name = get_from_row(row, index_map, 'Product Name')
    description = get_from_row(row, index_map, 'Description')

    sizes = extract_variant_sizes(row, index_map)
    image_urls, tags = extract_image_data(row, index_map)

    now = datetime.now()
    price = parse_number(get_from_row(row, index_map, 'Selling Price'), 0)
    mrp = parse_number(get_from_row(row, index_map, 'MRP'), price)
    inventory = parse_int(get_from_row(row, index_map, 'Net Quantity'), 0)

    color = get_from_row(row, index_map, 'Color')
    variants = [{'size': s, 'color': color, 'price': price} for s in sizes] if sizes else []

    product = {
        'sku_id': sku,
        'product_name': product_name,
        'name': product_name,
        'description': description,
        'ornamentation': get_from_row(row, index_map, 'Ornamentation'),
        'occasion': get_from_row(row, index_map, 'Occasion'),
        'generic_name': get_from_row(row, index_map, 'Generic Name'),
        'sizes': sizes,
        'fastening': get_from_row(row, index_map, 'Fastening & Back Detail'),
        'heel_height': get_from_row(row, index_map, 'Heel Height'),
        'heel_type': get_from_row(row, index_map, 'Heel Type'),
        'heel_height_in': get_from_row(row, index_map, 'Heel Height (in)'),
        'insole': get_from_row(row, index_map, 'Insole'),
        'material': get_from_row(row, index_map, 'Material'),
        'sole_material': get_from_row(row, index_map, 'Sole Material'),
        'pattern': get_from_row(row, index_map, 'Pattern'),
        'type': get_from_row(row, index_map, 'Type'),
        'mrp': mrp,
        'price': price,
        'meesho_price': price,
        'return_price': parse_number(get_from_row(row, index_map, 'Wrong/Defective Returns Price'), 0),
        'length_size': get_from_row(row, index_map, 'Length Size'),
        'width_size': get_from_row(row, index_map, 'Width Size'),
        'weight': parse_int(get_from_row(row, index_map, 'Net Weight'), 0),
        'hsn_code': get_from_row(row, index_map, 'HSN Code'),
        'gst': get_from_row(row, index_map, 'GST'),
        'color': get_from_row(row, index_map, 'Color'),
        'ankle_height': get_from_row(row, index_map, 'Ankle Height'),
        'toe_type': get_from_row(row, index_map, 'Toe Type'),
        'origin': get_from_row(row, index_map, 'COUNTRY OF ORIGIN'),
        'mfg_name': get_from_row(row, index_map, 'Manufacturer Name'),
        'mfg_address': get_from_row(row, index_map, 'Manufacturer Address'),
        'category': get_from_row(row, index_map, 'Type') or 'General',
        'inventory': inventory,
        'image_1': image_urls[0] if image_urls else 'https://via.placeholder.com/400x400',
        'created_at': now,
        'updated_at': now
    }
    for idx, url in enumerate(image_urls[:8], start=1):
        product[f'image_{idx}'] = url
    if image_urls:
        product['images'] = image_urls
    if tags:
        product['tags'] = tags
    if variants:
        product['variants'] = variants
    return product


def process_bulk_upload_file(file_storage):
    if not file_storage or not file_storage.filename:
        return False, ['No file selected'], {'created': 0, 'skipped': 0}

    extension = file_storage.filename.rsplit('.', 1)[-1].lower() if '.' in file_storage.filename else ''
    if extension not in BULK_ALLOWED_EXTENSIONS:
        return False, ['Only CSV and XLSX files are supported'], {'created': 0, 'skipped': 0}

    headers, rows = csv_rows_to_dicts(file_storage) if extension == 'csv' else xlsx_rows_to_dicts(file_storage)
    normalized_headers = [normalize_bulk_header(h) for h in headers if h]
    header_index_map = {normalize_bulk_header(h): h for h in headers if h}

    missing = [h for h in BULK_REQUIRED_ATTRIBUTES if normalize_bulk_header(h) not in normalized_headers]
    if missing:
        return False, [f'Missing required column(s): {", ".join(missing)}'], {'created': 0, 'skipped': 0}

    created = 0
    skipped = 0
    errors = []

    for row_index, row in enumerate(rows, start=2):
        missing_values = []
        for col in BULK_REQUIRED_ATTRIBUTES:
            original_col = header_index_map.get(normalize_bulk_header(col), col)
            val = str(row.get(original_col, '')).strip()
            if not val and col == 'Size':
                # Accept if sizes exist in any variant/size column.
                val = ','.join(extract_variant_sizes(row, header_index_map))
            if not val:
                missing_values.append(col)

        if missing_values:
            skipped += 1
            errors.append(f'Row {row_index}: missing value(s) in {", ".join(missing_values)}')
            continue

        product_doc = build_product_from_bulk_row(row, header_index_map)
        sku = product_doc.get('sku_id', '')
        if products_collection.find_one({'sku_id': sku}):
            skipped += 1
            errors.append(f'Row {row_index}: SKU "{sku}" already exists')
            continue

        products_collection.insert_one(product_doc)
        created += 1

    return True, errors, {'created': created, 'skipped': skipped}


# ==================== ADMIN DECORATOR ====================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access admin panel', 'error')
            return redirect(url_for('login', next=request.url))

        if not session.get('is_admin', False):
            flash('Admin access required', 'error')
            return redirect(url_for('index'))

        return f(*args, **kwargs)

    return decorated_function


# ==================== HELPER FUNCTIONS ====================
def format_time_ago(timestamp):
    """Format timestamp to relative time string"""
    if not timestamp:
        return "Just now"

    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except:
            return "Some time ago"

    now = datetime.now()
    diff = now - timestamp

    if diff.days > 365:
        years = diff.days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"
    elif diff.days > 30:
        months = diff.days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Just now"


def calculate_total_revenue():
    """Calculate total revenue from all orders"""
    try:
        pipeline = [
            {'$match': {'status': {'$in': ['Delivered', 'Completed']}}},
            {'$group': {
                '_id': None,
                'total': {'$sum': '$total_amount'}
            }}
        ]
        result = list(orders_collection.aggregate(pipeline))
        return result[0]['total'] if result else 0
    except:
        return 0


def calculate_inventory_value():
    """Calculate total inventory value"""
    try:
        products = list(products_collection.find())
        total_value = 0
        for product in products:
            price = product.get('meesho_price') or product.get('price', 0)
            inventory = product.get('inventory') or product.get('stock', 0)
            total_value += price * inventory
        return total_value
    except:
        return 0


def get_top_selling_products(limit=5):
    """Get top selling products"""
    try:
        pipeline = [
            {'$unwind': '$products'},
            {'$group': {
                '_id': '$products.name',
                'product_id': {'$first': '$products.product_id'},
                'total_sold': {'$sum': '$products.quantity'},
                'total_revenue': {'$sum': {'$multiply': ['$products.price', '$products.quantity']}}
            }},
            {'$sort': {'total_sold': -1}},
            {'$limit': limit},
            {'$project': {
                'product_id': '$product_id',
                'name': '$_id',
                'total_sold': 1,
                'total_revenue': 1
            }}
        ]
        return list(orders_collection.aggregate(pipeline))
    except Exception as e:
        print(f"Error getting top products: {e}")
        return []


def get_order_status_stats():
    """Get order status distribution"""
    try:
        pipeline = [
            {'$group': {
                '_id': '$status',
                'count': {'$sum': 1}
            }}
        ]
        result = list(orders_collection.aggregate(pipeline))

        # Format result
        stats = {}
        for item in result:
            stats[item['_id']] = item['count']

        return stats
    except:
        return {}


def ensure_default_coupons():
    """Seed a few default coupons if they don't exist."""
    defaults = [
        {'code': 'WELCOME10', 'type': 'percent', 'value': 10, 'min_order': 999, 'max_discount': 500, 'active': True},
        {'code': 'SAVE200', 'type': 'flat', 'value': 200, 'min_order': 1999, 'max_discount': 200, 'active': True},
        {'code': 'FESTIVE15', 'type': 'percent', 'value': 15, 'min_order': 2499, 'max_discount': 800, 'active': True},
    ]
    for c in defaults:
        if not coupons_collection.find_one({'code': c['code']}):
            c['created_at'] = datetime.now()
            coupons_collection.insert_one(c)


def calculate_shipping_charge(pincode, subtotal, total_weight_grams=0):
    """
    Compute shipping charges by pincode + weight + order value.
    Rules:
    - Free shipping for subtotal >= 1499
    - Remote pincodes (starting with 7/8) extra 60
    - Base 49 + weight slabs (per additional 500g: +20)
    """
    if subtotal >= 1499:
        return 0
    base = 49
    pin = (pincode or '').strip()
    if pin[:1] in {'7', '8'}:
        base += 60
    if total_weight_grams > 500:
        extra_slabs = max(0, (total_weight_grams - 1) // 500)
        base += int(extra_slabs) * 20
    return base


def evaluate_coupon(code, subtotal):
    """Return coupon evaluation dictionary."""
    if not code:
        return {'valid': False, 'message': 'Coupon code required', 'discount': 0}

    coupon = coupons_collection.find_one({'code': code.upper().strip(), 'active': True})
    if not coupon:
        return {'valid': False, 'message': 'Invalid coupon', 'discount': 0}

    min_order = float(coupon.get('min_order', 0) or 0)
    if subtotal < min_order:
        return {'valid': False, 'message': f'Minimum order value is Rs {int(min_order)}', 'discount': 0}

    if coupon.get('type') == 'flat':
        discount = float(coupon.get('value', 0) or 0)
    else:
        discount = subtotal * (float(coupon.get('value', 0) or 0) / 100.0)

    max_discount = float(coupon.get('max_discount', discount) or discount)
    discount = max(0, min(discount, max_discount, subtotal))
    return {'valid': True, 'message': 'Coupon applied', 'discount': discount, 'coupon': coupon}


def send_order_email(recipient, subject, html_body):
    """Send order email through SMTP if configured."""
    smtp_host = os.getenv('SMTP_HOST')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_user = os.getenv('SMTP_USER')
    smtp_pass = os.getenv('SMTP_PASS')
    smtp_sender = os.getenv('SMTP_SENDER', smtp_user or 'no-reply@quickdeck.local')

    if not smtp_host or not smtp_user or not smtp_pass or not recipient:
        return False, 'SMTP not configured'

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_sender
        msg['To'] = recipient
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_sender, [recipient], msg.as_string())
        return True, 'Email sent'
    except Exception as e:
        return False, str(e)


def build_invoice_html(order, user=None):
    """Build a simple HTML invoice document."""
    items_html = ""
    for item in order.get('products', []):
        items_html += f"""
        <tr>
            <td>{item.get('name', 'Item')}</td>
            <td>{item.get('quantity', 1)}</td>
            <td>Rs {int(item.get('price', 0))}</td>
            <td>Rs {int(item.get('subtotal', 0))}</td>
        </tr>
        """

    return f"""
    <!doctype html>
    <html><head>
    <meta charset='utf-8'>
    <title>Invoice {order.get('_id')}</title>
    <style>
    body{{font-family:Arial,sans-serif;padding:24px;color:#111;}}
    table{{width:100%;border-collapse:collapse;margin-top:16px;}}
    th,td{{border:1px solid #ddd;padding:8px;text-align:left;}}
    th{{background:#f5f5f5;}}
    .totals{{margin-top:16px;max-width:380px;float:right;}}
    .totals div{{display:flex;justify-content:space-between;padding:4px 0;}}
    </style>
    </head><body>
    <h2>QUICKDECK Tax Invoice</h2>
    <p><strong>Order ID:</strong> {order.get('_id')}</p>
    <p><strong>Date:</strong> {order.get('order_date', datetime.now()).strftime('%d %b %Y')}</p>
    <p><strong>Customer:</strong> {order.get('user_name', user.get('name') if user else 'Customer')}</p>
    <p><strong>Address:</strong> {order.get('delivery_address', '')}</p>
    <table>
      <thead><tr><th>Item</th><th>Qty</th><th>Unit Price</th><th>Subtotal</th></tr></thead>
      <tbody>{items_html}</tbody>
    </table>
    <div class='totals'>
      <div><span>Subtotal</span><span>Rs {int(order.get('subtotal', order.get('total_amount', 0)))}</span></div>
      <div><span>Shipping</span><span>Rs {int(order.get('shipping_charge', 0))}</span></div>
      <div><span>Discount</span><span>- Rs {int(order.get('discount_amount', 0))}</span></div>
      <div><strong>Total</strong><strong>Rs {int(order.get('total_amount', 0))}</strong></div>
    </div>
    </body></html>
    """


@app.errorhandler(413)
def request_entity_too_large(error):
    if request.path.startswith('/admin'):
        flash(
            f'Uploaded file is too large. Max allowed size is {int(app.config["MAX_CONTENT_LENGTH"] / (1024 * 1024))} MB.',
            'error'
        )
        if request.path.startswith('/admin/bulk'):
            return redirect(url_for('admin_bulk_upload'))
        return redirect(url_for('admin_products'))
    return 'File too large', 413


def log_login_activity(user_id, ip_address):
    """Log user login activity for security monitoring"""
    try:
        activity_log = {
            'user_id': user_id,
            'action': 'login',
            'ip_address': ip_address,
            'user_agent': request.headers.get('User-Agent', ''),
            'timestamp': datetime.utcnow()
        }
        # Create a collection for activity logs if it doesn't exist
        activity_collection = db.get_collection('user_activity')
        activity_collection.insert_one(activity_log)
    except Exception as e:
        print(f"Failed to log activity: {str(e)}")


# ==================== JINJA FILTERS ====================
@app.template_filter('format_number')
def format_number(value):
    """Format number with commas"""
    try:
        return "{:,}".format(int(value))
    except:
        return value


@app.context_processor
def inject_admin_nav_stats():
    """Provide dynamic admin counters to sidebar navigation."""
    try:
        return {
            'nav_total_products': products_collection.count_documents({}),
            'nav_pending_orders': orders_collection.count_documents({'status': 'Pending'})
        }
    except Exception:
        return {
            'nav_total_products': 0,
            'nav_pending_orders': 0
        }


@app.context_processor
def inject_storefront_meta():
    """Provide storefront nav/search metadata globally."""
    try:
        categories = products_collection.distinct('category')
        categories = sorted([c for c in categories if c])[:10]
    except Exception:
        categories = []

    cart_count = 0
    wishlist_count = 0
    try:
        if session.get('user_id'):
            cart_items = list(cart_collection.find({'user_id': session['user_id']}))
            cart_count = sum(int(item.get('quantity', 0) or 0) for item in cart_items)
            wishlist_count = wishlist_collection.count_documents({'user_id': session['user_id']})
    except Exception:
        cart_count = 0
        wishlist_count = 0

    return {
        'storefront_categories': categories,
        'storefront_cart_count': cart_count,
        'storefront_wishlist_count': wishlist_count
    }


# ==================== SESSION MANAGEMENT ====================
COUPONS_SEEDED = False


@app.before_request
def make_session_permanent():
    global COUPONS_SEEDED
    session.permanent = True
    app.permanent_session_lifetime = timedelta(hours=24)
    if not COUPONS_SEEDED:
        ensure_default_coupons()
        COUPONS_SEEDED = True


# ==================== ROUTES ====================

# --- HOME PAGE ---
@app.route('/')
def index():
    try:
        featured_products = list(products_collection.find().sort('created_at', -1).limit(8))
        new_arrivals = list(products_collection.find().sort('created_at', -1).limit(4))
        categories = products_collection.distinct('category')

        # Lightweight bestseller approximation by stock movement/availability
        best_sellers = list(products_collection.find({'inventory': {'$gt': 0}}).sort('inventory', 1).limit(4))

        # Homepage visual blocks (placeholders can be replaced from admin later)
        hero_banners = [
            {
                'title': 'Wedding Collection',
                'subtitle': 'Elegant styles for festive and bridal looks',
                'image': 'https://images.unsplash.com/photo-1543163521-1bf539c55dd2?auto=format&fit=crop&w=1600&q=80',
                'link': url_for('products', category='Bridal')
            },
            {
                'title': 'Daily Comfort Edit',
                'subtitle': 'Lightweight comfort for everyday wear',
                'image': 'https://images.unsplash.com/photo-1514989940723-e8e51635b782?auto=format&fit=crop&w=1600&q=80',
                'link': url_for('products')
            },
            {
                'title': 'Party Glam',
                'subtitle': 'Statement heels and festive picks',
                'image': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=1600&q=80',
                'link': url_for('products', category='Heels')
            }
        ]

        promo_banners = [
            {
                'title': 'Flat 20% Off on New Arrivals',
                'image': 'https://images.unsplash.com/photo-1460353581641-37baddab0fa2?auto=format&fit=crop&w=1200&q=80',
                'link': url_for('products')
            },
            {
                'title': 'Premium Bridal Edit',
                'image': 'https://images.unsplash.com/photo-1449505278894-297fdb3edbc1?auto=format&fit=crop&w=1200&q=80',
                'link': url_for('products', category='Bridal')
            },
            {
                'title': 'Bestsellers of the Week',
                'image': 'https://images.unsplash.com/photo-1463100099107-aa0980c362e6?auto=format&fit=crop&w=1200&q=80',
                'link': url_for('products')
            }
        ]

        default_round_categories = [
            {'name': 'Heels', 'image': 'https://images.unsplash.com/photo-1543163521-1bf539c55dd2?auto=format&fit=crop&w=400&q=80'},
            {'name': 'Flats', 'image': 'https://images.unsplash.com/photo-1465453869711-7e174808ace9?auto=format&fit=crop&w=400&q=80'},
            {'name': 'Sandals', 'image': 'https://images.unsplash.com/photo-1511556532299-8f662fc26c06?auto=format&fit=crop&w=400&q=80'},
            {'name': 'Slip-ons', 'image': 'https://images.unsplash.com/photo-1491553895911-0055eca6402d?auto=format&fit=crop&w=400&q=80'},
            {'name': 'Sneakers', 'image': 'https://images.unsplash.com/photo-1515955656352-a1fa3ffcd111?auto=format&fit=crop&w=400&q=80'},
            {'name': 'Bridal', 'image': 'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=400&q=80'},
            {'name': 'Festive', 'image': 'https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77?auto=format&fit=crop&w=400&q=80'},
            {'name': 'Boots', 'image': 'https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=400&q=80'}
        ]

        existing = {c.get('name') for c in default_round_categories}
        for c in sorted([c for c in categories if c]):
            if c not in existing:
                default_round_categories.append({
                    'name': c,
                    'image': 'https://images.unsplash.com/photo-1515955656352-a1fa3ffcd111?auto=format&fit=crop&w=400&q=80'
                })

        women_collage = {
            'large': {
                'name': 'Bridal',
                'image': 'https://images.unsplash.com/photo-1543163521-1bf539c55dd2?auto=format&fit=crop&w=1200&q=80',
                'link': url_for('products', category='Bridal')
            },
            'tiles': [
                {'name': 'Flats', 'image': 'https://images.unsplash.com/photo-1463100099107-aa0980c362e6?auto=format&fit=crop&w=800&q=80', 'link': url_for('products', category='Flats')},
                {'name': 'Heels', 'image': 'https://images.unsplash.com/photo-1511556532299-8f662fc26c06?auto=format&fit=crop&w=800&q=80', 'link': url_for('products', category='Heels')},
                {'name': 'Ethnic', 'image': 'https://images.unsplash.com/photo-1539185441755-769473a23570?auto=format&fit=crop&w=800&q=80', 'link': url_for('products', category='Festive')},
                {'name': 'Accessories', 'image': 'https://images.unsplash.com/photo-1523779105320-d1cd346ff52b?auto=format&fit=crop&w=800&q=80', 'link': url_for('products')}
            ]
        }

        women_collection_tiles = [
            {'name': 'Party', 'image': 'https://images.unsplash.com/photo-1511556532299-8f662fc26c06?auto=format&fit=crop&w=700&q=80', 'link': url_for('products', category='Heels')},
            {'name': 'Festive Edit', 'image': 'https://images.unsplash.com/photo-1539185441755-769473a23570?auto=format&fit=crop&w=700&q=80', 'link': url_for('products', category='Festive')},
            {'name': 'Winter', 'image': 'https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=700&q=80', 'link': url_for('products', category='Boots')},
            {'name': 'Work Wear', 'image': 'https://images.unsplash.com/photo-1460353581641-37baddab0fa2?auto=format&fit=crop&w=700&q=80', 'link': url_for('products', category='Flats')}
        ]

        men_collection_tiles = [
            {'name': 'Festive', 'image': 'https://images.unsplash.com/photo-1560769629-975ec94e6a86?auto=format&fit=crop&w=700&q=80', 'link': url_for('products', category='Festive')},
            {'name': 'XLite', 'image': 'https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77?auto=format&fit=crop&w=700&q=80', 'link': url_for('products')},
            {'name': 'Loafer', 'image': 'https://images.unsplash.com/photo-1491553895911-0055eca6402d?auto=format&fit=crop&w=700&q=80', 'link': url_for('products')},
            {'name': 'Summer', 'image': 'https://images.unsplash.com/photo-1514989940723-e8e51635b46a?auto=format&fit=crop&w=700&q=80', 'link': url_for('products')}
        ]

        return render_template('index.html',
                               featured_products=featured_products,
                               new_arrivals=new_arrivals,
                               best_sellers=best_sellers,
                               categories=categories,
                               hero_banners=hero_banners,
                               promo_banners=promo_banners,
                               round_categories=default_round_categories,
                               women_collage=women_collage,
                               women_collection_tiles=women_collection_tiles,
                               men_collection_tiles=men_collection_tiles)
    except Exception as e:
        print(f"Index Error: {e}")
        # Return a simple error page with debug info
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>QUICKDECK - Error</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body class="bg-light">
            <div class="container mt-5">
                <div class="alert alert-danger">
                    <h4>Error Loading Home Page</h4>
                    <p>{str(e)}</p>
                    <hr>
                    <p class="mb-0">
                        <a href="/admin/login" class="btn btn-dark">Go to Admin Login</a>
                        <a href="/test_structure" class="btn btn-outline-dark">Check Structure</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """


# --- TEST STRUCTURE ROUTE ---
@app.route('/test_structure')
def test_structure():
    """Test file and database structure"""
    import os

    result = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>QUICKDECK - System Check</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            .success { color: green; }
            .error { color: red; }
            .warning { color: orange; }
        </style>
    </head>
    <body class="bg-light">
        <div class="container mt-5">
            <h1 class="mb-4">QUICKDECK System Check</h1>
    """

    # Check current directory
    result += f"<h3>Current Directory: {os.getcwd()}</h3>"

    # Check templates folder
    templates_path = "templates"
    if os.path.exists(templates_path):
        result += f'<p class="success">âœ“ templates folder exists</p>'
        files = os.listdir(templates_path)
        result += f"<h4>Files in templates ({len(files)}):</h4><ul>"
        for file in files:
            file_path = os.path.join(templates_path, file)
            if os.path.isfile(file_path):
                result += f"<li>{file} (file)</li>"
            else:
                result += f"<li>{file}/ (folder)</li>"
        result += "</ul>"
    else:
        result += f'<p class="error">âœ— templates folder does not exist!</p>'

    # Check database connection
    try:
        db_status = client.server_info()
        result += f'<p class="success">âœ“ Database connected successfully</p>'

        # Check collections
        collections = db.list_collection_names()
        result += f"<h4>Database Collections ({len(collections)}):</h4><ul>"
        for col in collections:
            count = db[col].count_documents({})
            result += f"<li>{col} - {count} documents</li>"
        result += "</ul>"

        # Check if we have any products
        product_count = products_collection.count_documents({})
        result += f'<p>Total Products: {product_count}</p>'

        if product_count == 0:
            result += f'<p class="warning">âš  No products found in database</p>'
            result += f'<a href="/admin/login" class="btn btn-dark">Add Products via Admin</a>'

    except Exception as e:
        result += f'<p class="error">âœ— Database error: {str(e)}</p>'

    # Check routes
    result += "<h4>Available Routes:</h4><ul>"
    for rule in app.url_map.iter_rules():
        if 'static' not in rule.rule:
            result += f"<li>{rule.rule}</li>"
    result += "</ul>"

    result += """
            <div class="mt-4">
                <a href="/" class="btn btn-primary">Try Home Page Again</a>
                <a href="/admin/login" class="btn btn-dark">Admin Login</a>
            </div>
        </div>
    </body>
    </html>
    """

    return result


# --- ADMIN LOGIN ROUTE ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = users_collection.find_one({'email': email})
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['user_name'] = user['name']
            session['is_admin'] = user.get('is_admin', False)
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard') if session['is_admin'] else url_for('index'))
        flash('Invalid credentials', 'error')

    # Simple login form
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Login - QUICKDECK</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    </head>
    <body class="bg-light" style="min-height: 100vh; display: flex; align-items: center;">
        <div class="container">
            <div class="row justify-content-center">
                <div class="col-md-4">
                    <div class="card shadow-lg border-0">
                        <div class="card-header bg-dark text-white text-center py-4">
                            <h1 class="h4 mb-0"><i class="fas fa-shoe-prints me-2"></i>QUICKDECK</h1>
                            <p class="mb-0 mt-2">Admin Portal</p>
                        </div>
                        <div class="card-body p-4">
                            <h2 class="h5 mb-4 text-center">Admin Login</h2>
                            <form method="POST">
                                <div class="mb-3">
                                    <label class="form-label">Email Address</label>
                                    <div class="input-group">
                                        <span class="input-group-text"><i class="fas fa-envelope"></i></span>
                                        <input type="email" name="email" class="form-control" placeholder="admin@quickdeck.com" required>
                                    </div>
                                </div>
                                <div class="mb-4">
                                    <label class="form-label">Password</label>
                                    <div class="input-group">
                                        <span class="input-group-text"><i class="fas fa-lock"></i></span>
                                        <input type="password" name="password" class="form-control" placeholder="Enter password" required>
                                    </div>
                                </div>
                                <button type="submit" class="btn btn-dark w-100 py-2 mb-3">
                                    <i class="fas fa-sign-in-alt me-2"></i>Login
                                </button>
                                <div class="text-center">
                                    <small class="text-muted">Default Admin: admin@quickdeck.com / password</small>
                                </div>
                            </form>
                        </div>
                        <div class="card-footer text-center py-3">
                            <small>
                                <a href="/" class="text-decoration-none text-dark">
                                    <i class="fas fa-home me-1"></i>Back to Home
                                </a>
                            </small>
                        </div>
                    </div>
                    <div class="text-center mt-3">
                        <small class="text-muted">Need help? <a href="/test_structure" class="text-decoration-none">Check System Status</a></small>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


# --- NEW ADMIN DASHBOARD ---
@app.route('/admin')
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin Dashboard - Main admin portal"""

    # Get current date
    now = datetime.now()

    # Get recent activities (combine recent orders, new products, etc.)
    recent_orders = list(orders_collection.find().sort('created_at', -1).limit(5))
    recent_products = list(products_collection.find().sort('created_at', -1).limit(5))
    recent_customers = list(users_collection.find({'is_admin': False}).sort('created_at', -1).limit(5))

    # Prepare activities list
    activities = []

    # Add recent orders to activities
    for order in recent_orders:
        activities.append({
            'type': 'order',
            'icon': 'fas fa-shopping-cart',
            'text': f'New order #{order.get("_id", "N/A")} placed',
            'time': format_time_ago(order.get('created_at', now)),
            'order_id': str(order.get('_id')),
            'timestamp': order.get('created_at', now)
        })

    # Add recent products to activities
    for product in recent_products:
        activities.append({
            'type': 'product',
            'icon': 'fas fa-box',
            'text': f'New product "{product.get("product_name", "N/A")}" added',
            'time': format_time_ago(product.get('created_at', now)),
            'product_id': str(product.get('_id')),
            'timestamp': product.get('created_at', now)
        })

    # Add recent customers to activities
    for customer in recent_customers:
        activities.append({
            'type': 'customer',
            'icon': 'fas fa-user-plus',
            'text': f'New customer registered: {customer.get("name", "N/A")}',
            'time': format_time_ago(customer.get('created_at', now)),
            'customer_id': str(customer.get('_id')),
            'timestamp': customer.get('created_at', now)
        })

    # Sort activities by timestamp (most recent first)
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    activities = activities[:10]  # Limit to 10 most recent

    # Calculate dashboard statistics
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_orders = list(orders_collection.find({'created_at': {'$gte': today_start}}))
    today_revenue = sum(float(order.get('total_amount', 0) or 0) for order in today_orders)
    total_orders_count = orders_collection.count_documents({})
    total_revenue = calculate_total_revenue()
    cancelled_orders_count = orders_collection.count_documents({'status': 'Cancelled'})

    stats = {
        'total_products': products_collection.count_documents({}),
        'total_orders': total_orders_count,
        'total_customers': users_collection.count_documents({'is_admin': False}),
        'pending_orders': orders_collection.count_documents({'status': 'Pending'}),
        'today_orders': orders_collection.count_documents({
            'created_at': {
                '$gte': datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            }
        }),
        'today_revenue': today_revenue,
        'total_revenue': total_revenue,
        'avg_order_value': (total_revenue / total_orders_count) if total_orders_count else 0,
        'cancellation_rate': (cancelled_orders_count / total_orders_count * 100) if total_orders_count else 0,
        'total_inventory_value': calculate_inventory_value(),
        'low_stock_products': products_collection.count_documents({'inventory': {'$lt': 10, '$gt': 0}}),
        'out_of_stock': products_collection.count_documents({'inventory': 0})
    }

    # Get recent orders for table
    recent_orders_detailed = list(orders_collection.find()
                                  .sort('created_at', -1)
                                  .limit(10))

    # Get low stock products
    low_stock_products = list(products_collection.find({'inventory': {'$lt': 10}})
                              .sort('inventory', 1)
                              .limit(10))

    # Get top selling products
    top_products = get_top_selling_products(limit=5)

    # Get order status distribution
    order_status_stats = get_order_status_stats()

    # Last 7 days sales and order trend for charts
    seven_days_ago = datetime.now() - timedelta(days=6)
    sales_pipeline = [
        {'$match': {'created_at': {'$gte': seven_days_ago}}},
        {'$group': {
            '_id': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$created_at'}},
            'revenue': {'$sum': '$total_amount'},
            'orders': {'$sum': 1}
        }},
        {'$sort': {'_id': 1}}
    ]
    sales_rows = list(orders_collection.aggregate(sales_pipeline))
    sales_map = {row['_id']: row for row in sales_rows}
    daily_labels = []
    daily_revenue = []
    daily_orders = []
    for i in range(7):
        day = (seven_days_ago + timedelta(days=i)).strftime('%Y-%m-%d')
        daily_labels.append((seven_days_ago + timedelta(days=i)).strftime('%d %b'))
        daily_revenue.append(float(sales_map.get(day, {}).get('revenue', 0) or 0))
        daily_orders.append(int(sales_map.get(day, {}).get('orders', 0) or 0))

    # Check if admin dashboard template exists, if not create it
    if not os.path.exists('templates/admin/dashboard.html'):
        os.makedirs('templates/admin', exist_ok=True)
        # Create a simple dashboard template
        dashboard_template = '''{% extends "admin/base.html" %}
{% block title %}Dashboard - QUICKDECK Admin{% endblock %}
{% block content %}
<div class="dashboard-page">
    <div class="page-header">
        <h2>Dashboard</h2>
        <p>Welcome back, {{ session.get('user_name', 'Admin') }}! Here's what's happening with your store.</p>
    </div>

    <div class="alert alert-info">
        <i class="fas fa-info-circle me-2"></i>
        New admin portal is being set up. For now, use the links below to access admin features.
    </div>

    <div class="row row-cols-1 row-cols-md-3 g-4">
        <div class="col">
            <div class="card h-100">
                <div class="card-body text-center">
                    <h1 class="display-1 text-primary">{{ stats.total_products }}</h1>
                    <h5 class="card-title">Total Products</h5>
                    <a href="{{ url_for('admin_products') }}" class="btn btn-outline-primary">Manage Products</a>
                </div>
            </div>
        </div>
        <div class="col">
            <div class="card h-100">
                <div class="card-body text-center">
                    <h1 class="display-1 text-success">{{ stats.total_orders }}</h1>
                    <h5 class="card-title">Total Orders</h5>
                    <a href="{{ url_for('admin_orders') }}" class="btn btn-outline-success">View Orders</a>
                </div>
            </div>
        </div>
        <div class="col">
            <div class="card h-100">
                <div class="card-body text-center">
                    <h1 class="display-1 text-warning">{{ stats.total_customers }}</h1>
                    <h5 class="card-title">Total Customers</h5>
                    <a href="{{ url_for('admin_customers') }}" class="btn btn-outline-warning">View Customers</a>
                </div>
            </div>
        </div>
    </div>

    <div class="mt-4">
        <h4>Quick Links</h4>
        <div class="d-flex flex-wrap gap-2">
            <a href="{{ url_for('admin_add_product') }}" class="btn btn-dark">
                <i class="fas fa-plus me-2"></i>Add New Product
            </a>
            <a href="{{ url_for('admin_orders') }}" class="btn btn-outline-dark">
                <i class="fas fa-shipping-fast me-2"></i>Order Logistics
            </a>
            <a href="/" class="btn btn-outline-secondary" target="_blank">
                <i class="fas fa-store me-2"></i>View Store
            </a>
        </div>
    </div>
</div>
{% endblock %}'''
        with open('templates/admin/dashboard.html', 'w') as f:
            f.write(dashboard_template)

    # Render the new admin dashboard template
    return render_template('admin/dashboard.html',
                           now=now,
                           stats=stats,
                           activities=activities,
                           recent_orders=recent_orders_detailed,
                           low_stock_products=low_stock_products,
                           top_products=top_products,
                           order_status_stats=order_status_stats,
                           daily_labels=daily_labels,
                           daily_revenue=daily_revenue,
                           daily_orders=daily_orders,
                           user_name=session.get('user_name', 'Admin'))


# --- ADMIN API ENDPOINTS ---
@app.route('/admin/api/stats')
@admin_required
def admin_api_stats():
    """API endpoint for dashboard statistics (AJAX)"""
    try:
        total_orders_count = orders_collection.count_documents({})
        total_revenue = calculate_total_revenue()
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_orders = list(orders_collection.find({'created_at': {'$gte': today_start}}))
        today_revenue = sum(float(order.get('total_amount', 0) or 0) for order in today_orders)
        cancelled_orders_count = orders_collection.count_documents({'status': 'Cancelled'})

        stats = {
            'total_products': products_collection.count_documents({}),
            'total_orders': total_orders_count,
            'total_customers': users_collection.count_documents({'is_admin': False}),
            'pending_orders': orders_collection.count_documents({'status': 'Pending'}),
            'today_orders': orders_collection.count_documents({
                'created_at': {
                    '$gte': datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                }
            }),
            'today_revenue': today_revenue,
            'total_revenue': total_revenue,
            'avg_order_value': (total_revenue / total_orders_count) if total_orders_count else 0,
            'cancellation_rate': (cancelled_orders_count / total_orders_count * 100) if total_orders_count else 0,
            'total_inventory_value': calculate_inventory_value(),
            'low_stock_products': products_collection.count_documents({'inventory': {'$lt': 10, '$gt': 0}}),
            'out_of_stock': products_collection.count_documents({'inventory': 0}),
            'success': True
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/admin/api/recent-activities')
@admin_required
def admin_api_activities():
    """API endpoint for recent activities"""
    try:
        activities = []
        now = datetime.now()

        # Get recent orders
        recent_orders = list(orders_collection.find().sort('created_at', -1).limit(3))
        for order in recent_orders:
            activities.append({
                'icon': 'fas fa-shopping-cart',
                'text': f'Order #{str(order.get("_id", "N/A"))[:8]} placed',
                'time': format_time_ago(order.get('created_at', now))
            })

        # Get recent products
        recent_products = list(products_collection.find().sort('created_at', -1).limit(3))
        for product in recent_products:
            activities.append({
                'icon': 'fas fa-box',
                'text': f'Product "{product.get("product_name", "N/A")}" added',
                'time': format_time_ago(product.get('created_at', now))
            })

        return jsonify({'success': True, 'activities': activities})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# --- CATALOG CONTROL ---
@app.route('/admin/products')
@admin_required
def admin_products():
    # Fetch all products from your database
    products = list(products_collection.find().sort('created_at', -1))

    # Calculate stats
    total_products = len(products)

    # Check for inventory field (try multiple field names)
    in_stock_count = 0
    low_stock_count = 0
    out_of_stock_count = 0

    for idx, product in enumerate(products):
        # Normalize media fields for admin UI rendering.
        product = enrich_product_for_display(product)
        products[idx] = product

        # Try different field names for stock/inventory
        stock = product.get('inventory') or product.get('stock') or product.get('quantity') or 0

        if stock > 10:
            in_stock_count += 1
        elif stock > 0:
            low_stock_count += 1
        else:
            out_of_stock_count += 1

    return render_template('admin/products.html',
                           products=products,
                           total_products=total_products,
                           in_stock_count=in_stock_count,
                           low_stock_count=low_stock_count,
                           out_of_stock_count=out_of_stock_count)
# --- ORDER LOGISTICS ---
@app.route('/admin/orders')
@admin_required
def admin_orders():
    status_filter = request.args.get('status', 'all')
    query_text = request.args.get('q', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    mongo_query = {}
    if status_filter and status_filter != 'all':
        mongo_query['status'] = status_filter

    date_query = {}
    try:
        if date_from:
            date_query['$gte'] = datetime.strptime(date_from, '%Y-%m-%d')
        if date_to:
            date_query['$lte'] = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
    except ValueError:
        date_query = {}

    if date_query:
        mongo_query['created_at'] = date_query

    all_orders = list(orders_collection.find(mongo_query).sort('created_at', -1))

    if query_text:
        lowered = query_text.lower()
        all_orders = [
            o for o in all_orders
            if lowered in str(o.get('_id', '')).lower()
            or lowered in str(o.get('user_name', '')).lower()
            or lowered in str(o.get('customer_name', '')).lower()
            or lowered in str(o.get('status', '')).lower()
        ]

    # Calculate stats
    total_orders = len(all_orders)
    pending_count = len([o for o in all_orders if o.get('status') == 'Pending'])
    processing_count = len([o for o in all_orders if o.get('status') == 'Processing'])
    shipped_count = len([o for o in all_orders if o.get('status') == 'Shipped'])
    delivered_count = len([o for o in all_orders if o.get('status') == 'Delivered'])

    # Create a simple orders template if it doesn't exist
    if not os.path.exists('templates/admin/orders.html'):
        os.makedirs('templates/admin', exist_ok=True)
        with open('templates/admin/orders.html', 'w') as f:
            f.write("""{% extends "base.html" %}
{% block admin_content %}
<div class="container-fluid px-0">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h4 class="fw-bold mb-1">Order Logistics</h4>
            <p class="text-muted mb-0">Manage and track customer orders</p>
        </div>
        <div class="text-end">
            <span class="badge bg-dark rounded-0 px-3 py-2">
                Total Orders: {{ total_orders }}
            </span>
        </div>
    </div>

    <div class="row g-3 mb-4">
        <div class="col-md-3">
            <div class="card bg-warning bg-opacity-10 border-warning">
                <div class="card-body p-3">
                    <h6 class="text-warning">Pending</h6>
                    <h3 class="mb-0">{{ pending_count }}</h3>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card bg-info bg-opacity-10 border-info">
                <div class="card-body p-3">
                    <h6 class="text-info">Processing</h6>
                    <h3 class="mb-0">{{ processing_count }}</h3>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card bg-primary bg-opacity-10 border-primary">
                <div class="card-body p-3">
                    <h6 class="text-primary">Shipped</h6>
                    <h3 class="mb-0">{{ shipped_count }}</h3>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card bg-success bg-opacity-10 border-success">
                <div class="card-body p-3">
                    <h6 class="text-success">Delivered</h6>
                    <h3 class="mb-0">{{ delivered_count }}</h3>
                </div>
            </div>
        </div>
    </div>

    <div class="card border rounded-0">
        <div class="table-responsive">
            <table class="table table-hover mb-0">
                <thead class="bg-light">
                    <tr>
                        <th>Order ID</th>
                        <th>Customer</th>
                        <th>Date</th>
                        <th>Amount</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for order in orders %}
                    <tr>
                        <td>#{{ order._id|string|truncate(8, True, '') }}</td>
                        <td>{{ order.get('user_name', 'Customer') }}</td>
                        <td>{{ order.created_at.strftime('%d %b %Y') if order.created_at else 'N/A' }}</td>
                        <td>â‚¹{{ order.total_amount }}</td>
                        <td>
                            <span class="badge {% if order.status == 'Pending' %}bg-warning{% elif order.status == 'Processing' %}bg-info{% elif order.status == 'Shipped' %}bg-primary{% else %}bg-success{% endif %}">
                                {{ order.status }}
                            </span>
                        </td>
                        <td>
                            <button class="btn btn-sm btn-outline-dark" onclick="updateStatus('{{ order._id }}')">
                                <i class="fas fa-edit"></i> Update
                            </button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>

<script>
function updateStatus(orderId) {
    const newStatus = prompt('Enter new status (Pending, Processing, Shipped, Delivered):');
    if (newStatus) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/admin/order/update_status/' + orderId;

        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'status';
        input.value = newStatus;
        form.appendChild(input);

        document.body.appendChild(form);
        form.submit();
    }
}
</script>
{% endblock %}""")

    return render_template('admin/orders.html',
                           orders=all_orders,
                           total_orders=total_orders,
                           pending_count=pending_count,
                           processing_count=processing_count,
                           shipped_count=shipped_count,
                           delivered_count=delivered_count,
                           status_filter=status_filter,
                           query_text=query_text,
                           date_from=date_from,
                           date_to=date_to)


# --- LIST NEW ITEM ---
@app.route('/admin/add-product', methods=['GET', 'POST'])
@admin_required
def admin_add_product():
    if request.method == 'POST':
        product_data = {
            'product_name': request.form.get('name', 'New Product'),
            'category': request.form.get('category', 'General'),
            'description': request.form.get('description', ''),
            'sku_id': request.form.get('sku', f'SKU-{datetime.now().strftime("%Y%m%d%H%M%S")}'),
            'mrp': float(request.form.get('mrp', 0)),
            'price': float(request.form.get('price', 0)),
            'meesho_price': float(request.form.get('price', 0)),
            'material': request.form.get('material', ''),
            'heel_type': request.form.get('heel_type', ''),
            'inventory': int(request.form.get('stock', 0)),
            'sizes': [s.strip() for s in request.form.get('sizes', '').split(',') if s.strip()],
            'image_1': 'https://via.placeholder.com/400x400',
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }

        products_collection.insert_one(product_data)
        flash('Product added successfully!', 'success')
        return redirect(url_for('admin_products'))

    # Create a simple add product form if template doesn't exist
    if not os.path.exists('templates/admin/add_product.html'):
        os.makedirs('templates/admin', exist_ok=True)
        with open('templates/admin/add_product.html', 'w') as f:
            f.write("""{% extends "base.html" %}
{% block admin_content %}
<div class="container-fluid px-0">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h4 class="fw-bold mb-1">Add New Product</h4>
            <p class="text-muted mb-0">Expand your footwear collection</p>
        </div>
        <div class="text-end">
            <a href="{{ url_for('admin_products') }}" class="btn btn-outline-dark rounded-0">
                <i class="fas fa-arrow-left me-2"></i>Back to Products
            </a>
        </div>
    </div>

    <div class="card border rounded-0">
        <div class="card-body">
            <form method="POST">
                <div class="row g-3">
                    <div class="col-md-6">
                        <label class="form-label">Product Name *</label>
                        <input type="text" name="name" class="form-control rounded-0" required>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label">Category *</label>
                        <select name="category" class="form-select rounded-0" required>
                            <option value="Heels">Heels</option>
                            <option value="Sneakers">Sneakers</option>
                            <option value="Sandals">Sandals</option>
                            <option value="Flats">Flats</option>
                            <option value="Boots">Boots</option>
                            <option value="Slip-ons">Slip-ons</option>
                        </select>
                    </div>
                    <div class="col-12">
                        <label class="form-label">Description</label>
                        <textarea name="description" class="form-control rounded-0" rows="3"></textarea>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label">SKU (Optional)</label>
                        <input type="text" name="sku" class="form-control rounded-0">
                    </div>
                    <div class="col-md-6">
                        <label class="form-label">Material</label>
                        <input type="text" name="material" class="form-control rounded-0" placeholder="e.g., Leather, Synthetic">
                    </div>
                    <div class="col-md-4">
                        <label class="form-label">MRP (â‚¹) *</label>
                        <input type="number" name="mrp" class="form-control rounded-0" step="0.01" required>
                    </div>
                    <div class="col-md-4">
                        <label class="form-label">Selling Price (â‚¹) *</label>
                        <input type="number" name="price" class="form-control rounded-0" step="0.01" required>
                    </div>
                    <div class="col-md-4">
                        <label class="form-label">Stock Quantity *</label>
                        <input type="number" name="stock" class="form-control rounded-0" required>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label">Heel Type</label>
                        <input type="text" name="heel_type" class="form-control rounded-0" placeholder="e.g., Stiletto, Block">
                    </div>
                    <div class="col-md-6">
                        <label class="form-label">Available Sizes</label>
                        <input type="text" name="sizes" class="form-control rounded-0" placeholder="e.g., 5,6,7,8">
                        <small class="text-muted">Enter sizes separated by commas</small>
                    </div>
                    <div class="col-12">
                        <div class="alert alert-info">
                            <i class="fas fa-info-circle me-2"></i>
                            Note: Image upload will be added in the next update. For now, a placeholder image will be used.
                        </div>
                    </div>
                    <div class="col-12">
                        <button type="submit" class="btn btn-dark rounded-0 px-4">
                            <i class="fas fa-save me-2"></i>Save Product
                        </button>
                        <a href="{{ url_for('admin_products') }}" class="btn btn-outline-dark rounded-0 px-4">
                            Cancel
                        </a>
                    </div>
                </div>
            </form>
        </div>
    </div>
</div>
{% endblock %}""")

    return render_template('admin/add_product.html')


# --- CUSTOMERS ---
@app.route('/admin/customers')
@admin_required
def admin_customers():
    customers = list(users_collection.find({'is_admin': False}).sort('created_at', -1))

    # Create a simple customers template if it doesn't exist
    if not os.path.exists('templates/admin/customers.html'):
        os.makedirs('templates/admin', exist_ok=True)
        with open('templates/admin/customers.html', 'w') as f:
            f.write("""{% extends "base.html" %}
{% block admin_content %}
<div class="container-fluid px-0">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h4 class="fw-bold mb-1">Customers</h4>
            <p class="text-muted mb-0">Manage customer accounts</p>
        </div>
        <div class="text-end">
            <span class="badge bg-dark rounded-0 px-3 py-2">
                Total Customers: {{ customers|length }}
            </span>
        </div>
    </div>

    <div class="card border rounded-0">
        <div class="table-responsive">
            <table class="table table-hover mb-0">
                <thead class="bg-light">
                    <tr>
                        <th>Customer</th>
                        <th>Email</th>
                        <th>Phone</th>
                        <th>Address</th>
                        <th>Joined</th>
                    </tr>
                </thead>
                <tbody>
                    {% for customer in customers %}
                    <tr>
                        <td>
                            <div class="d-flex align-items-center gap-2">
                                <div class="bg-dark text-white rounded-circle d-flex align-items-center justify-content-center" 
                                     style="width: 36px; height: 36px;">
                                    {{ customer.name[0]|upper if customer.name else 'U' }}
                                </div>
                                <div>
                                    <strong>{{ customer.name }}</strong>
                                </div>
                            </div>
                        </td>
                        <td>{{ customer.email }}</td>
                        <td>{{ customer.phone or 'N/A' }}</td>
                        <td>{{ customer.address or 'N/A' }}</td>
                        <td>{{ customer.created_at.strftime('%d %b %Y') if customer.created_at else 'N/A' }}</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="5" class="text-center py-4">
                            <p class="text-muted mb-0">No customers found</p>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}""")

    return render_template('admin/customers.html', customers=customers)


# --- EDIT PRODUCT ---
@app.route('/admin/edit-product/<product_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(product_id):
    product = products_collection.find_one({'_id': ObjectId(product_id)})
    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('admin_products'))

    if request.method == 'POST':
        update_data = {
            'product_name': request.form.get('name', product.get('product_name', '')),
            'category': request.form.get('category'),
            'description': request.form.get('description'),
            'sku_id': request.form.get('sku'),
            'mrp': float(request.form.get('mrp', 0)),
            'price': float(request.form.get('price', 0)),
            'meesho_price': float(request.form.get('price', 0)),
            'material': request.form.get('material'),
            'heel_type': request.form.get('heel_type'),
            'inventory': int(request.form.get('stock', 0)),
            'sizes': [s.strip() for s in request.form.get('sizes', '').split(',') if s.strip()],
            'updated_at': datetime.now()
        }

        products_collection.update_one(
            {'_id': ObjectId(product_id)},
            {'$set': update_data}
        )
        flash('Product updated successfully!', 'success')
        return redirect(url_for('admin_products'))

    return render_template('admin/edit_product.html', product=product)


# --- DELETE PRODUCT ---
@app.route('/admin/delete-product/<product_id>', methods=['POST'])
@admin_required
def admin_delete_product(product_id):
    products_collection.delete_one({'_id': ObjectId(product_id)})
    flash('Product removed successfully', 'success')
    return redirect(url_for('admin_products'))


# --- UPDATE ORDER STATUS ---
@app.route('/admin/order/update_status/<order_id>', methods=['POST'])
@admin_required
def admin_update_order_status(order_id):
    if not ObjectId.is_valid(order_id):
        return jsonify({'success': False, 'message': 'Invalid order id'}), 400
    new_status = request.form.get('status')
    orders_collection.update_one(
        {'_id': ObjectId(order_id)},
        {'$set': {'status': new_status, 'updated_at': datetime.now()}}
    )
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({'success': True, 'message': 'Order status updated'})
    flash('Order status updated!', 'success')
    return redirect(url_for('admin_orders'))


# --- QUICK CATALOG UPDATE (AJAX) ---
@app.route('/admin/product/quick-update', methods=['POST'])
@admin_required
def admin_quick_update():
    """Handles the Quick Edit modal submission via AJAX"""
    try:
        data = request.get_json()
        product_id = data.get('id')
        new_price = float(data.get('price', 0))
        new_stock = int(data.get('stock', 0))

        # Update the product in MongoDB using the keys from your schema
        result = products_collection.update_one(
            {'_id': ObjectId(product_id)},
            {'$set': {
                'price': new_price,
                'meesho_price': new_price,
                'inventory': new_stock,
                'updated_at': datetime.now()
            }}
        )

        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'Catalog updated successfully'})
        return jsonify({'success': False, 'message': 'No changes detected'})

    except Exception as e:
        print(f"Quick Update Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# --- SIMPLE PRODUCTS PAGE FOR TESTING ---
@app.route('/products')
def products():
    selected_category = request.args.get('category', '').strip()
    selected_material = request.args.get('material', '').strip()
    search_query = request.args.get('q', '').strip()
    sort_by = request.args.get('sort', 'latest').strip()

    mongo_query = {}
    if selected_category:
        mongo_query['category'] = selected_category
    if selected_material:
        mongo_query['material'] = selected_material
    if search_query:
        mongo_query['$or'] = [
            {'product_name': {'$regex': search_query, '$options': 'i'}},
            {'description': {'$regex': search_query, '$options': 'i'}},
            {'category': {'$regex': search_query, '$options': 'i'}}
        ]

    projection = {
        'product_name': 1, 'name': 1, 'category': 1, 'material': 1,
        'price': 1, 'meesho_price': 1, 'mrp': 1, 'inventory': 1,
        'image': 1, 'image_1': 1, 'images': 1, 'created_at': 1
    }
    cursor = products_collection.find(mongo_query, projection)
    if sort_by == 'price_low':
        cursor = cursor.sort('meesho_price', 1)
    elif sort_by == 'price_high':
        cursor = cursor.sort('meesho_price', -1)
    elif sort_by == 'name_asc':
        cursor = cursor.sort('product_name', 1)
    else:
        cursor = cursor.sort('created_at', -1)

    products_list = [enrich_product_for_display(p) for p in list(cursor)]
    categories = sorted([c for c in products_collection.distinct('category') if c])
    materials = sorted([m for m in products_collection.distinct('material') if m])

    if not os.path.exists('templates/products.html'):
        with open('templates/products.html', 'w') as f:
            f.write("""{% extends "base.html" %}
{% block content %}
<div class="container py-5">
    <h1 class="mb-4">Our Collection</h1>
    <div class="row g-4">
        {% for product in products %}
        <div class="col-md-3">
            <div class="card border-0 h-100">
                <div class="card-img-top bg-light" style="height: 250px; overflow: hidden;">
                    <img src="{{ product.image_1 or 'https://via.placeholder.com/400x400' }}" 
                         alt="{{ product.product_name }}" 
                         class="img-fluid h-100 w-100 object-fit-cover">
                </div>
                <div class="card-body">
                    <h5 class="card-title">{{ product.product_name }}</h5>
                    <p class="card-text text-muted small">{{ product.category }}</p>
                    <div class="d-flex justify-content-between align-items-center">
                        <span class="h5 mb-0">â‚¹{{ product.meesho_price or product.price }}</span>
                        {% if product.mrp and product.mrp > (product.meesho_price or product.price) %}
                        <small class="text-muted text-decoration-line-through">â‚¹{{ product.mrp }}</small>
                        {% endif %}
                    </div>
                </div>
                <div class="card-footer bg-white border-0">
                    <a href="{{ url_for('product_detail', product_id=product._id|string) }}" 
                       class="btn btn-dark rounded-0 w-100">View Details</a>
                </div>
            </div>
        </div>
        {% else %}
        <div class="col-12 text-center py-5">
            <h3 class="text-muted">No products available yet.</h3>
            <p class="text-muted">Check back soon for our latest collection!</p>
        </div>
        {% endfor %}
    </div>
</div>
{% endblock %}""")

    return render_template('products.html',
                           products=products_list,
                           categories=categories,
                           materials=materials,
                           selected_category=selected_category,
                           selected_material=selected_material,
                           query_text=search_query,
                           sort_by=sort_by)


# --- PRODUCT DETAIL PAGE ---
@app.route('/product/<product_id>')
def product_detail(product_id):
    try:
        if not ObjectId.is_valid(product_id):
            return redirect(url_for('products'))

        product = products_collection.find_one({'_id': ObjectId(product_id)})
        if not product:
            return redirect(url_for('products'))
        product = enrich_product_for_display(product)

        # Get related products (same category, exclude current product)
        related_projection = {
            'product_name': 1, 'name': 1, 'category': 1,
            'price': 1, 'meesho_price': 1, 'mrp': 1,
            'image': 1, 'image_1': 1, 'images': 1
        }
        related_products = [
            enrich_product_for_display(p) for p in list(products_collection.find({
                'category': product.get('category'),
                '_id': {'$ne': ObjectId(product_id)}
            }, related_projection).limit(4))
        ]

        product_reviews = list(reviews_collection.find({'product_id': product_id}).sort('created_at', -1).limit(20))
        rating_count = len(product_reviews)
        avg_rating = round(sum(r.get('rating', 0) for r in product_reviews) / rating_count, 1) if rating_count else 0
        in_wishlist = False
        if session.get('user_id'):
            in_wishlist = wishlist_collection.find_one({'user_id': session['user_id'], 'product_id': product_id}) is not None

        return render_template('product_detail.html',
                               product=product,
                               related_products=related_products,
                               product_reviews=product_reviews,
                               avg_rating=avg_rating,
                               rating_count=rating_count,
                               in_wishlist=in_wishlist)

    except Exception as e:
        print(f"Product detail error: {e}")
        return redirect(url_for('products'))


# --- USER AUTHENTICATION ROUTES ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        hashed_password = generate_password_hash(request.form.get('password'))
        user_data = {
            'name': request.form.get('name'),
            'email': request.form.get('email'),
            'phone': request.form.get('phone'),
            'address': request.form.get('address'),
            'password': hashed_password,
            'is_admin': False,
            'created_at': datetime.now()
        }
        users_collection.insert_one(user_data)
        flash('Account created! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')

            # Validate inputs
            if not email or not password:
                flash('Please enter both email and password', 'error')
                return render_template('login.html')

            # Find user in database
            user = users_collection.find_one({'email': email})

            if not user:
                flash('Invalid email or password', 'error')
                return render_template('login.html')

            # Check if account is active (if you have such a field)
            if user.get('is_active', True) == False:
                flash('Your account has been deactivated. Please contact support.', 'error')
                return render_template('login.html')

            # Verify password
            if not check_password_hash(user['password'], password):
                flash('Invalid email or password', 'error')
                return render_template('login.html')

            # Set session variables
            session['user_id'] = str(user['_id'])
            session['user_name'] = user.get('name', 'User')
            session['user_email'] = user['email']
            session['is_admin'] = user.get('is_admin', False)

            # Log login activity (optional)
            log_login_activity(user['_id'], request.remote_addr)

            # Set flash message
            flash(f'Welcome back, {session["user_name"]}!', 'success')

            # Redirect based on user role and intended destination
            next_url = request.args.get('next')
            if next_url:
                return redirect(next_url)

            # Redirect admin to admin dashboard, regular users to home
            if session['is_admin']:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('index'))

        except Exception as e:
            # Log the error for debugging
            print(f"Login error: {str(e)}")
            flash('An error occurred during login. Please try again.', 'error')
            return render_template('login.html')

    # If GET request, check if user is already logged in
    if 'user_id' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    # Log logout activity if needed
    if 'user_id' in session:
        try:
            activity_log = {
                'user_id': session['user_id'],
                'action': 'logout',
                'ip_address': request.remote_addr,
                'timestamp': datetime.utcnow()
            }
            activity_collection = db.get_collection('user_activity')
            activity_collection.insert_one(activity_log)
        except Exception as e:
            print(f"Failed to log logout activity: {str(e)}")

    # Clear the session
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/admin/settings')
@admin_required
def admin_settings():
    settings_data = {
        'store_name': os.getenv('STORE_NAME', 'QUICKDECK'),
        'support_email': os.getenv('SUPPORT_EMAIL', 'support@quickdeck.com'),
        'currency': os.getenv('STORE_CURRENCY', 'INR'),
        'tax_rate': os.getenv('STORE_TAX_RATE', '18'),
        'order_auto_confirm': True,
        'low_stock_threshold': 10
    }
    return render_template('admin/settings.html', settings=settings_data)

@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    total_orders = orders_collection.count_documents({})
    delivered_orders = orders_collection.count_documents({'status': 'Delivered'})
    cancelled_orders = orders_collection.count_documents({'status': 'Cancelled'})
    total_revenue = calculate_total_revenue()
    avg_order_value = (total_revenue / total_orders) if total_orders else 0

    # Monthly trend (last 6 months)
    six_months_ago = datetime.now() - timedelta(days=180)
    monthly_pipeline = [
        {'$match': {'created_at': {'$gte': six_months_ago}}},
        {'$group': {
            '_id': {'$dateToString': {'format': '%Y-%m', 'date': '$created_at'}},
            'orders': {'$sum': 1},
            'revenue': {'$sum': '$total_amount'}
        }},
        {'$sort': {'_id': 1}}
    ]
    monthly_rows = list(orders_collection.aggregate(monthly_pipeline))

    return render_template('admin/analytics.html',
                           total_orders=total_orders,
                           delivered_orders=delivered_orders,
                           cancelled_orders=cancelled_orders,
                           total_revenue=total_revenue,
                           avg_order_value=avg_order_value,
                           monthly_rows=monthly_rows)

@app.route('/admin/activities')
@admin_required
def admin_activities():
    now = datetime.now()
    recent_orders = list(orders_collection.find().sort('created_at', -1).limit(20))
    recent_products = list(products_collection.find().sort('created_at', -1).limit(20))
    recent_customers = list(users_collection.find({'is_admin': False}).sort('created_at', -1).limit(20))

    activities = []

    for order in recent_orders:
        activities.append({
            'type': 'order',
            'icon': 'fas fa-shopping-cart',
            'text': f'New order #{str(order.get("_id", "N/A"))[:8]} placed',
            'time': format_time_ago(order.get('created_at', now)),
            'timestamp': order.get('created_at', now)
        })

    for product in recent_products:
        activities.append({
            'type': 'product',
            'icon': 'fas fa-box',
            'text': f'Product "{product.get("product_name", "N/A")}" added',
            'time': format_time_ago(product.get('created_at', now)),
            'timestamp': product.get('created_at', now)
        })

    for customer in recent_customers:
        activities.append({
            'type': 'customer',
            'icon': 'fas fa-user-plus',
            'text': f'New customer registered: {customer.get("name", "N/A")}',
            'time': format_time_ago(customer.get('created_at', now)),
            'timestamp': customer.get('created_at', now)
        })

    activities.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template('admin/activities.html',
                           activities=activities[:50],
                           total_activities=len(activities))


@app.route('/admin/returns')
@admin_required
def admin_returns():
    requests = list(returns_collection.find().sort('created_at', -1))
    return render_template('admin/returns.html', requests=requests)


@app.route('/admin/returns/<return_id>/status', methods=['POST'])
@admin_required
def admin_update_return_status(return_id):
    if not ObjectId.is_valid(return_id):
        return jsonify({'success': False, 'message': 'Invalid return id'}), 400
    status = request.form.get('status', 'Requested')
    returns_collection.update_one(
        {'_id': ObjectId(return_id)},
        {'$set': {'status': status, 'updated_at': datetime.now()}}
    )
    return jsonify({'success': True, 'message': 'Return status updated'})

@app.route('/admin/bulk-upload', methods=['GET', 'POST'])
@admin_required
def admin_bulk_upload():
    if request.method == 'GET':
        return render_template('admin/bulk_upload.html', required_attributes=BULK_REQUIRED_ATTRIBUTES)

    ok, errors, stats = process_bulk_upload_file(request.files.get('file'))
    if ok:
        flash(f'Bulk upload complete. Added {stats["created"]} products, skipped {stats["skipped"]}.', 'success')
        if errors:
            flash('Some rows were skipped. First issue: ' + errors[0], 'warning')
        return redirect(url_for('admin_products'))

    flash(errors[0] if errors else 'Bulk upload failed.', 'error')
    return redirect(url_for('admin_bulk_upload'))


@app.route('/admin/bulk/upload', methods=['POST'])
@admin_required
def bulk_upload():
    ok, errors, stats = process_bulk_upload_file(request.files.get('file'))
    if ok:
        return jsonify({
            'success': True,
            'created': stats['created'],
            'skipped': stats['skipped'],
            'errors': errors
        })
    return jsonify({'success': False, 'errors': errors}), 400

# --- CART ROUTES ---
def build_cart_items(user_id):
    """Build normalized cart items with safe product fallbacks."""
    raw_items = list(cart_collection.find({'user_id': user_id}))
    items = []
    total = 0

    for item in raw_items:
        quantity = int(item.get('quantity', 1) or 1)
        product_id = str(item.get('product_id', ''))
        product = None

        if ObjectId.is_valid(product_id):
            product = products_collection.find_one({'_id': ObjectId(product_id)})

        if product:
            price = float(product.get('meesho_price') or product.get('price') or 0)
            stock = int(product.get('inventory') or product.get('stock') or 0)
            image = product.get('image_1') or product.get('image') or ''
            product_name = product.get('product_name') or product.get('name') or 'Product'
            category = product.get('category') or 'Footwear'
            available = True
        else:
            price = 0
            stock = 0
            image = ''
            product_name = 'Product unavailable'
            category = 'Removed from catalog'
            available = False

        subtotal = price * quantity
        total += subtotal

        item['product'] = {
            'name': product_name,
            'category': category,
            'price': price,
            'stock': stock,
            'image': image
        }
        item['is_available'] = available
        item['subtotal'] = subtotal
        items.append(item)

    return items, total


@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    items, total = build_cart_items(session['user_id'])
    return render_template('cart.html', cart_items=items, total=total)


@app.route('/update_cart/<cart_id>', methods=['POST'])
def update_cart(cart_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Login required'}), 401
    if not ObjectId.is_valid(cart_id):
        return jsonify({'success': False, 'message': 'Invalid cart item'}), 400

    try:
        quantity = int(request.form.get('quantity', 1))
    except ValueError:
        quantity = 1
    quantity = max(1, quantity)

    cart_item = cart_collection.find_one({'_id': ObjectId(cart_id), 'user_id': session['user_id']})
    if not cart_item:
        return jsonify({'success': False, 'message': 'Cart item not found'}), 404

    stock = quantity
    product_id = str(cart_item.get('product_id', ''))
    if ObjectId.is_valid(product_id):
        product = products_collection.find_one({'_id': ObjectId(product_id)})
        if product:
            stock = int(product.get('inventory') or product.get('stock') or quantity)

    quantity = max(1, min(quantity, max(stock, 1)))

    cart_collection.update_one(
        {'_id': ObjectId(cart_id), 'user_id': session['user_id']},
        {'$set': {'quantity': quantity, 'updated_at': datetime.now()}}
    )
    return jsonify({'success': True})


@app.route('/remove_from_cart/<cart_id>', methods=['POST'])
def remove_from_cart(cart_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Login required'}), 401
    if not ObjectId.is_valid(cart_id):
        return jsonify({'success': False, 'message': 'Invalid cart item'}), 400

    cart_collection.delete_one({'_id': ObjectId(cart_id), 'user_id': session['user_id']})
    return jsonify({'success': True})


@app.route('/checkout')
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = {}
    if ObjectId.is_valid(session['user_id']):
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])}) or {}
    cart_items, total = build_cart_items(session['user_id'])

    available_items = [i for i in cart_items if i.get('is_available')]
    if not available_items:
        flash('Your cart is empty', 'warning')
        return redirect(url_for('cart'))

    subtotal = sum(float(i.get('subtotal', 0) or 0) for i in available_items)
    default_pincode = user.get('pincode', '')
    total_weight = 0
    for i in available_items:
        pid = str(i.get('product_id', ''))
        if ObjectId.is_valid(pid):
            p = products_collection.find_one({'_id': ObjectId(pid)})
            total_weight += int((p or {}).get('weight', 300) or 300)
    shipping_charge = calculate_shipping_charge(default_pincode, subtotal, total_weight)

    return render_template(
        'checkout.html',
        user=user or {},
        cart_items=available_items,
        subtotal=subtotal,
        shipping_charge=shipping_charge,
        total=subtotal + shipping_charge
    )


@app.route('/apply_coupon', methods=['POST'])
def apply_coupon():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Login required'}), 401

    code = request.form.get('code', '').strip()
    subtotal = float(request.form.get('subtotal', 0) or 0)
    shipping = float(request.form.get('shipping', 0) or 0)
    result = evaluate_coupon(code, subtotal)
    if not result.get('valid'):
        return jsonify({'success': False, 'message': result.get('message', 'Invalid coupon')})

    discount = float(result.get('discount', 0) or 0)
    total = max(0, subtotal + shipping - discount)
    return jsonify({
        'success': True,
        'message': result.get('message', 'Coupon applied'),
        'discount': discount,
        'total': total,
        'coupon_code': code.upper()
    })


@app.route('/payment/create', methods=['POST'])
def payment_create():
    """Create payment intent/order for UPI/Razorpay/Stripe (sandbox-compatible)."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Login required'}), 401

    provider = request.form.get('provider', 'upi').strip().lower()
    amount = float(request.form.get('amount', 0) or 0)
    amount = max(0, amount)

    if provider == 'razorpay':
        key_id = os.getenv('RAZORPAY_KEY_ID')
        key_secret = os.getenv('RAZORPAY_KEY_SECRET')
        if razorpay and key_id and key_secret and amount > 0:
            try:
                client_rzp = razorpay.Client(auth=(key_id, key_secret))
                order = client_rzp.order.create({
                    'amount': int(amount * 100),
                    'currency': 'INR',
                    'payment_capture': 1
                })
                return jsonify({'success': True, 'provider': 'razorpay', 'order_id': order.get('id'), 'key_id': key_id})
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)})
        return jsonify({'success': True, 'provider': 'razorpay', 'sandbox': True, 'order_id': f'rzp_sandbox_{int(datetime.now().timestamp())}'})

    if provider == 'stripe':
        stripe_key = os.getenv('STRIPE_SECRET_KEY')
        if stripe and stripe_key and amount > 0:
            try:
                stripe.api_key = stripe_key
                intent = stripe.PaymentIntent.create(
                    amount=int(amount * 100),
                    currency='inr',
                    payment_method_types=['card']
                )
                return jsonify({'success': True, 'provider': 'stripe', 'client_secret': intent.client_secret})
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)})
        return jsonify({'success': True, 'provider': 'stripe', 'sandbox': True, 'client_secret': f'stripe_sandbox_{int(datetime.now().timestamp())}'})

    # UPI sandbox payload
    return jsonify({
        'success': True,
        'provider': 'upi',
        'sandbox': True,
        'upi_link': f'upi://pay?pa={os.getenv("UPI_ID", "quickdeck@upi")}&pn=QUICKDECK&am={amount:.2f}&cu=INR'
    })


@app.route('/place_order', methods=['POST'])
def place_order():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Login required'}), 401

    address = request.form.get('address', '').strip()
    phone = request.form.get('phone', '').strip()
    pincode = request.form.get('pincode', '').strip()
    payment_method = request.form.get('payment_method', 'cod').strip().lower()
    coupon_code = request.form.get('coupon_code', '').strip().upper()

    if not address or not phone or not pincode:
        return jsonify({'success': False, 'message': 'Address and phone are required'}), 400

    cart_items, _ = build_cart_items(session['user_id'])
    order_items = []
    order_total = 0.0
    for item in cart_items:
        if not item.get('is_available'):
            continue

        product_id = str(item.get('product_id', ''))
        if not ObjectId.is_valid(product_id):
            continue
        product = products_collection.find_one({'_id': ObjectId(product_id)})
        if not product:
            continue

        requested_qty = int(item.get('quantity', 1))
        current_stock = int(product.get('inventory') or product.get('stock') or 0)
        final_qty = max(0, min(requested_qty, current_stock))
        if final_qty <= 0:
            continue

        unit_price = float(item['product']['price'])
        subtotal = unit_price * final_qty

        order_items.append({
            'name': item['product']['name'],
            'product_id': product_id,
            'quantity': final_qty,
            'price': unit_price,
            'subtotal': subtotal
        })
        order_total += subtotal

        products_collection.update_one(
            {'_id': ObjectId(product_id)},
            {'$set': {'inventory': max(current_stock - final_qty, 0), 'updated_at': datetime.now()}}
        )

    if not order_items:
        return jsonify({'success': False, 'message': 'No valid items in cart'}), 400

    shipping_charge = calculate_shipping_charge(pincode, order_total, 0)
    discount_amount = 0
    applied_coupon = None
    if coupon_code:
        coupon_eval = evaluate_coupon(coupon_code, order_total)
        if coupon_eval.get('valid'):
            discount_amount = float(coupon_eval.get('discount', 0) or 0)
            applied_coupon = coupon_code

    user = {}
    if ObjectId.is_valid(session['user_id']):
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])}) or {}
    grand_total = max(0, order_total + shipping_charge - discount_amount)
    order_doc = {
        'user_id': session['user_id'],
        'user_name': user.get('name', session.get('user_name', 'Customer')),
        'phone': phone,
        'delivery_address': address,
        'pincode': pincode,
        'products': order_items,
        'subtotal': order_total,
        'shipping_charge': shipping_charge,
        'discount_amount': discount_amount,
        'coupon_code': applied_coupon,
        'payment_method': payment_method,
        'payment_status': 'Paid' if payment_method in {'upi', 'razorpay', 'stripe'} else 'Pending',
        'total_amount': grand_total,
        'status': 'Pending',
        'created_at': datetime.now(),
        'order_date': datetime.now(),
        'updated_at': datetime.now()
    }
    result = orders_collection.insert_one(order_doc)
    cart_collection.delete_many({'user_id': session['user_id']})

    # Email invoice/confirmation (best-effort)
    invoice_html = build_invoice_html({**order_doc, '_id': str(result.inserted_id)}, user=user)
    send_order_email(
        recipient=user.get('email', ''),
        subject=f'Order Confirmation #{str(result.inserted_id)[:8]}',
        html_body=invoice_html
    )

    return jsonify({'success': True, 'order_id': str(result.inserted_id)})


@app.route('/order_success/<order_id>')
def order_success(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not ObjectId.is_valid(order_id):
        return redirect(url_for('index'))

    order = orders_collection.find_one({'_id': ObjectId(order_id), 'user_id': session['user_id']})
    if not order:
        return redirect(url_for('index'))
    return render_template('order_success.html', order=order)


@app.route('/my-orders')
def my_orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    orders = list(orders_collection.find({'user_id': session['user_id']}).sort('created_at', -1))
    return render_template('my_orders.html', orders=orders)


@app.route('/return/request/<order_id>', methods=['POST'])
def request_return(order_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Login required'}), 401
    if not ObjectId.is_valid(order_id):
        return jsonify({'success': False, 'message': 'Invalid order id'}), 400

    reason = request.form.get('reason', '').strip() or 'No reason provided'
    order = orders_collection.find_one({'_id': ObjectId(order_id), 'user_id': session['user_id']})
    if not order:
        return jsonify({'success': False, 'message': 'Order not found'}), 404

    returns_collection.insert_one({
        'order_id': order_id,
        'user_id': session['user_id'],
        'reason': reason,
        'status': 'Requested',
        'created_at': datetime.now(),
        'updated_at': datetime.now()
    })
    orders_collection.update_one({'_id': ObjectId(order_id)}, {'$set': {'status': 'Return Requested', 'updated_at': datetime.now()}})
    return jsonify({'success': True, 'message': 'Return request submitted'})


@app.route('/invoice/<order_id>')
def download_invoice(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not ObjectId.is_valid(order_id):
        return redirect(url_for('index'))
    order = orders_collection.find_one({'_id': ObjectId(order_id), 'user_id': session['user_id']})
    if not order:
        return redirect(url_for('index'))

    user = {}
    if ObjectId.is_valid(session['user_id']):
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])}) or {}
    html = build_invoice_html(order, user=user)
    filename = f"invoice-{str(order.get('_id'))[:8]}.html"
    return Response(
        html,
        mimetype='text/html',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/wishlist')
def wishlist():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    rows = list(wishlist_collection.find({'user_id': session['user_id']}).sort('created_at', -1))
    product_ids = [ObjectId(r['product_id']) for r in rows if ObjectId.is_valid(str(r.get('product_id', '')))]
    products = list(products_collection.find({'_id': {'$in': product_ids}})) if product_ids else []
    product_map = {str(p['_id']): p for p in products}
    wishlist_items = []
    for r in rows:
        p = product_map.get(str(r.get('product_id')))
        if p:
            wishlist_items.append(p)
    return render_template('wishlist.html', wishlist_items=wishlist_items)


@app.route('/wishlist/add/<product_id>', methods=['POST'])
def wishlist_add(product_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Login required'}), 401
    if not ObjectId.is_valid(product_id):
        return jsonify({'success': False, 'message': 'Invalid product'}), 400

    wishlist_collection.update_one(
        {'user_id': session['user_id'], 'product_id': product_id},
        {'$setOnInsert': {'created_at': datetime.now()}},
        upsert=True
    )
    return jsonify({'success': True})


@app.route('/wishlist/remove/<product_id>', methods=['POST'])
def wishlist_remove(product_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Login required'}), 401
    wishlist_collection.delete_one({'user_id': session['user_id'], 'product_id': product_id})
    return jsonify({'success': True})


@app.route('/product/<product_id>/review', methods=['POST'])
def add_review(product_id):
    if 'user_id' not in session:
        flash('Please login to review this product', 'warning')
        return redirect(url_for('login', next=url_for('product_detail', product_id=product_id)))
    if not ObjectId.is_valid(product_id):
        return redirect(url_for('products'))

    try:
        rating = int(request.form.get('rating', 5))
    except ValueError:
        rating = 5
    rating = max(1, min(5, rating))
    comment = request.form.get('comment', '').strip()

    reviews_collection.insert_one({
        'product_id': product_id,
        'user_id': session['user_id'],
        'user_name': session.get('user_name', 'User'),
        'rating': rating,
        'comment': comment,
        'created_at': datetime.now()
    })
    flash('Review submitted', 'success')
    return redirect(url_for('product_detail', product_id=product_id))


@app.route('/add_to_cart/<product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'user_id' not in session:
        flash('Please login first to add items to cart', 'warning')
        return redirect(url_for('login', next=url_for('product_detail', product_id=product_id)))

    if not ObjectId.is_valid(product_id):
        flash('Invalid product', 'error')
        return redirect(url_for('products'))

    product = products_collection.find_one({'_id': ObjectId(product_id)})
    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('products'))

    selected_size = request.form.get('selected_size', '')
    try:
        quantity = int(request.form.get('quantity', 1))
    except ValueError:
        quantity = 1
    quantity = max(1, quantity)
    stock = int(product.get('inventory') or product.get('stock') or 0)
    if stock <= 0:
        flash('This product is currently out of stock', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    quantity = min(quantity, stock)

    existing = cart_collection.find_one({
        'user_id': session['user_id'],
        'product_id': product_id,
        'selected_size': selected_size
    })

    if existing:
        new_qty = min(int(existing.get('quantity', 1)) + quantity, stock)
        cart_collection.update_one(
            {'_id': existing['_id']},
            {'$set': {'quantity': new_qty, 'updated_at': datetime.now()}}
        )
    else:
        cart_collection.insert_one({
            'user_id': session['user_id'],
            'product_id': product_id,
            'quantity': quantity,
            'selected_size': selected_size,
            'added_at': datetime.now(),
            'updated_at': datetime.now()
        })
    flash('Added to cart!', 'success')
    return redirect(url_for('product_detail', product_id=product_id))


# Add this temporary function to your app.py (you can remove it after debugging)
@app.route('/admin/check-db')
@admin_required
def check_db():
    """Check database structure"""
    import json

    # Get first product to see structure
    product = products_collection.find_one()

    if not product:
        return "No products in database. Add products first."

    # Convert ObjectId to string for JSON serialization
    product['_id'] = str(product['_id'])

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Database Structure</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-5">
            <h1>Database Structure Check</h1>
            <p>Total Products: {products_collection.count_documents({})}</p>
            <h3>Sample Product Structure:</h3>
            <pre>{json.dumps(product, indent=2)}</pre>
            <h3>All Field Names:</h3>
            <ul>
    """

    if product:
        for key in product.keys():
            return f"""
                <li>{key}</li>
            """

    return """
            </ul>
            <a href="/admin/products" class="btn btn-primary mt-3">Back to Products</a>
        </div>
    </body>
    </html>
    """

# --- ADDITIONAL PAGE ROUTES ---
@app.route('/about')
def about():
    """Route for 'Our Story' page"""
    return render_template('about.html')


@app.route('/contact')
def contact():
    """Route for 'Contact Us' page"""
    return render_template('contact.html')


# --- NOTIFY ME ROUTE ---
@app.route('/notify-me', methods=['POST'])
def notify_me():
    email = request.form.get('email')
    product_id = request.form.get('product_id')
    # Logic to save notification request to DB
    flash('We will notify you when this item is back in stock!', 'info')
    return redirect(request.referrer or url_for('index'))


# --- SERVER START BLOCK ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
