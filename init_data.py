from pymongo import MongoClient
from werkzeug.security import generate_password_hash
from datetime import datetime
import os

MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGODB_URI)
db = client['quickdeck_db']

users_collection = db['users']
products_collection = db['products']
orders_collection = db['orders']
cart_collection = db['cart']

def init_data():
    print("Initializing QUICKDECK database...")
    
    users_collection.delete_many({})
    products_collection.delete_many({})
    orders_collection.delete_many({})
    cart_collection.delete_many({})
    
    admin_user = {
        'name': 'Admin',
        'email': 'admin@quickdeck.com',
        'phone': '8097130846',
        'address': 'Vasant Nagar, G-70/2, Thakkar Bappa Colony, Chembur, Mumbai',
        'password': generate_password_hash('admin123'),
        'is_admin': True,
        'created_at': datetime.now()
    }
    users_collection.insert_one(admin_user)
    print("✓ Admin user created (admin@quickdeck.com / admin123)")
    
    sample_user = {
        'name': 'Demo User',
        'email': 'demo@example.com',
        'phone': '9619328102',
        'address': 'Mumbai, Maharashtra',
        'password': generate_password_hash('demo123'),
        'is_admin': False,
        'created_at': datetime.now()
    }
    users_collection.insert_one(sample_user)
    print("✓ Demo user created (demo@example.com / demo123)")
    
    sample_products = [
        {
            'name': 'Elegant High Heels',
            'category': 'Heels',
            'price': 2499.00,
            'description': 'Stylish and comfortable high heels perfect for parties and formal events. Premium quality material with cushioned insoles.',
            'sizes': ['5', '6', '7', '8', '9'],
            'stock': 25,
            'image': 'placeholder.jpg',
            'created_at': datetime.now()
        },
        {
            'name': 'Classic Stiletto Heels',
            'category': 'Heels',
            'price': 2999.00,
            'description': 'Sophisticated stiletto heels with pointed toes. Perfect for adding elegance to any outfit.',
            'sizes': ['5', '6', '7', '8'],
            'stock': 18,
            'image': 'placeholder.jpg',
            'created_at': datetime.now()
        },
        {
            'name': 'Casual Sneakers',
            'category': 'Sneakers',
            'price': 1899.00,
            'description': 'Comfortable and trendy sneakers for daily wear. Breathable fabric with excellent grip.',
            'sizes': ['5', '6', '7', '8', '9', '10'],
            'stock': 35,
            'image': 'placeholder.jpg',
            'created_at': datetime.now()
        },
        {
            'name': 'Sports Sneakers',
            'category': 'Sneakers',
            'price': 2199.00,
            'description': 'Athletic sneakers with superior comfort and style. Ideal for workouts and casual outings.',
            'sizes': ['5', '6', '7', '8', '9'],
            'stock': 30,
            'image': 'placeholder.jpg',
            'created_at': datetime.now()
        },
        {
            'name': 'Summer Sandals',
            'category': 'Sandals',
            'price': 1299.00,
            'description': 'Light and airy sandals perfect for summer. Comfortable straps with soft sole.',
            'sizes': ['5', '6', '7', '8', '9'],
            'stock': 40,
            'image': 'placeholder.jpg',
            'created_at': datetime.now()
        },
        {
            'name': 'Designer Sandals',
            'category': 'Sandals',
            'price': 1799.00,
            'description': 'Beautifully designed sandals with intricate detailing. Perfect for both casual and semi-formal occasions.',
            'sizes': ['5', '6', '7', '8'],
            'stock': 22,
            'image': 'placeholder.jpg',
            'created_at': datetime.now()
        },
        {
            'name': 'Ballet Flats',
            'category': 'Flats',
            'price': 1599.00,
            'description': 'Comfortable and stylish ballet flats for everyday wear. Soft fabric with flexible sole.',
            'sizes': ['5', '6', '7', '8', '9'],
            'stock': 28,
            'image': 'placeholder.jpg',
            'created_at': datetime.now()
        },
        {
            'name': 'Pointed Toe Flats',
            'category': 'Flats',
            'price': 1699.00,
            'description': 'Elegant pointed toe flats that add sophistication to any outfit. Great for office wear.',
            'sizes': ['5', '6', '7', '8'],
            'stock': 20,
            'image': 'placeholder.jpg',
            'created_at': datetime.now()
        },
        {
            'name': 'Comfortable Slip-ons',
            'category': 'Slip-ons',
            'price': 1399.00,
            'description': 'Easy-to-wear slip-ons with cushioned footbed. Perfect for quick errands and casual outings.',
            'sizes': ['5', '6', '7', '8', '9', '10'],
            'stock': 32,
            'image': 'placeholder.jpg',
            'created_at': datetime.now()
        },
        {
            'name': 'Designer Slip-ons',
            'category': 'Slip-ons',
            'price': 1899.00,
            'description': 'Stylish slip-ons with modern design. Combines comfort with contemporary fashion.',
            'sizes': ['5', '6', '7', '8', '9'],
            'stock': 26,
            'image': 'placeholder.jpg',
            'created_at': datetime.now()
        },
        {
            'name': 'Ankle Boots',
            'category': 'Boots',
            'price': 3299.00,
            'description': 'Fashionable ankle boots perfect for winter. Premium leather with warm lining.',
            'sizes': ['5', '6', '7', '8'],
            'stock': 15,
            'image': 'placeholder.jpg',
            'created_at': datetime.now()
        },
        {
            'name': 'Long Boots',
            'category': 'Boots',
            'price': 3999.00,
            'description': 'Elegant long boots that make a statement. High-quality material with comfortable fit.',
            'sizes': ['5', '6', '7', '8', '9'],
            'stock': 12,
            'image': 'placeholder.jpg',
            'created_at': datetime.now()
        }
    ]
    
    products_collection.insert_many(sample_products)
    print(f"✓ Created {len(sample_products)} sample products")
    
    print("\n" + "="*60)
    print("QUICKDECK Database Initialization Complete!")
    print("="*60)
    print("\nAdmin Login:")
    print("  Email: admin@quickdeck.com")
    print("  Password: admin123")
    print("\nDemo User Login:")
    print("  Email: demo@example.com")
    print("  Password: demo123")
    print("\nCategories available:")
    categories = products_collection.distinct('category')
    for cat in categories:
        count = products_collection.count_documents({'category': cat})
        print(f"  - {cat}: {count} products")
    print("="*60)

if __name__ == '__main__':
    init_data()
