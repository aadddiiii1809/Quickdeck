# QUICKDECK E-Commerce Project

## Overview
Complete e-commerce website for QUICKDECK - a premium ladies footwear retailer. Built with Flask (Python) backend and MongoDB database, featuring a beautiful blue/white gradient design with animations.

## Current State (November 17, 2024)
✅ **FULLY FUNCTIONAL**

The website is live and running with:
- Flask server on port 5000 (webview workflow)
- MongoDB database (separate workflow)
- 12 sample products across 6 categories
- Admin panel fully functional
- Customer shopping experience complete

## Architecture

### Backend
- **Framework**: Flask 3.1.2
- **Database**: MongoDB (local instance)
- **Authentication**: Session-based with Werkzeug password hashing
- **File Upload**: Product images to static/images/products/

### Frontend
- **Templates**: Jinja2 (12 HTML files)
- **Styling**: Custom CSS with QUICKDECK blue gradient (#0066cc to #003d7a)
- **JavaScript**: Vanilla JS for cart operations and animations
- **Framework**: Bootstrap 5.3.0
- **Icons**: Font Awesome 6.4.0

### Database Collections
1. **users** - Customer and admin accounts
2. **products** - Footwear inventory
3. **orders** - Customer orders with status
4. **cart** - User shopping carts

## Key Features

### Customer Features
- Browse products by category
- Product search
- User registration and login
- Add to cart with quantity selection
- Checkout with address collection
- Order confirmation
- Responsive mobile design

### Admin Features  
- Dashboard with statistics
- Add/edit/delete products
- Upload product images
- Manage stock levels
- View all orders
- Update order status (Pending/Processing/Shipped/Delivered/Cancelled)

### Design Features
- Animated hero section with floating icons
- Blue/white gradient theme
- Smooth hover effects
- Product card animations
- Amazon and Flipkart logo section
- Mobile responsive

## Workflows

### MongoDB Workflow
- **Command**: `mongod --dbpath /tmp/mongodb --bind_ip 127.0.0.1 --port 27017 --logpath /tmp/mongodb/mongod.log`
- **Status**: Running
- **Purpose**: Database server for application data

### QUICKDECK Server Workflow
- **Command**: `python app.py`
- **Status**: Running
- **Port**: 5000 (webview)
- **URL**: Accessible via Replit webview

## Project Structure
```
/
├── app.py                   # Main Flask application (437 lines)
├── init_data.py            # Database initialization script
├── requirements.txt        # Python dependencies
├── static/
│   ├── css/style.css      # Custom QUICKDECK styling
│   ├── js/main.js         # Frontend JavaScript
│   └── images/
│       └── products/      # Product images
├── templates/             # 12 HTML templates
│   ├── base.html         # Navigation and footer
│   ├── index.html        # Homepage
│   ├── products.html     # Product listing
│   ├── cart.html         # Shopping cart
│   ├── checkout.html     # Checkout
│   └── admin/            # Admin panel templates
└── README.md             # Documentation
```

## Default Accounts

### Admin
- **Email**: admin@quickdeck.com
- **Password**: admin123
- **Access**: Full admin panel

### Demo User
- **Email**: demo@example.com
- **Password**: demo123
- **Access**: Customer features

## Recent Changes
- **Nov 17, 2024**: Complete build and deployment
  - Set up MongoDB workflow for persistent database
  - Created all 12 templates with QUICKDECK branding
  - Implemented full admin panel
  - Added sample data with 12 products
  - Configured workflows for MongoDB and Flask server
  - Verified application running successfully

## Known Issues & Future Improvements

### Security Enhancements Needed
- Add CSRF protection for admin forms (Flask-WTF)
- Implement rate limiting for login attempts
- Add input validation on all forms

### Feature Enhancements
- Payment gateway integration (Razorpay/Stripe)
- Email notifications for orders
- Product image gallery (multiple images per product)
- Customer reviews and ratings
- Wishlist functionality
- Advanced filtering (price range, size, brand)

### Technical Improvements
- Migrate to MongoDB Atlas for production reliability
- Add proper error logging
- Implement caching for product listings
- Add unit tests
- Create database migrations system

## Development Notes

### MongoDB Setup
MongoDB runs as a separate workflow to ensure persistent connection. The database is initialized with sample data on first run.

### Static File Handling
Product images are uploaded to `static/images/products/` directory. Currently using placeholder.jpg for all products - admin can upload real images through the admin panel.

### Session Management
Uses Flask's built-in session management with a secret key. Sessions persist across requests for user authentication and cart operations.

## Company Information
- **Name**: QUICKDECK
- **Tagline**: Your Gateway to Global Retail
- **Type**: E-commerce Partner
- **Address**: Vasant Nagar, G-70/2, Thakkar Bappa Colony, Near Gopal Hotel, Chembur, Mumbai, Maharashtra, 400071
- **Contact**: 8097130846 / 9619328102
- **Platforms**: Also available on Amazon and Flipkart

## Success Criteria Met
✅ Animated homepage with QUICKDECK branding  
✅ Complete navigation system (all pages)  
✅ User authentication (login/signup)  
✅ Product catalog with categories  
✅ Shopping cart functionality  
✅ Checkout and order placement  
✅ Admin panel (products, orders, stock)  
✅ MongoDB integration  
✅ Amazon/Flipkart logos section  
✅ Mobile responsive design  
✅ Blue/white gradient theme  
✅ Smooth animations and transitions  

## Next Session TODO
- Consider migrating to MongoDB Atlas
- Add CSRF protection
- Implement payment gateway
- Add email notifications
- Upload real product images
