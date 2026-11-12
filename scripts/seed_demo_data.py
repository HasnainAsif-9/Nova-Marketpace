"""Seed demo data: categories, demo seller, demo products.

Usage:
    cd backend
    python ../scripts/seed_demo_data.py
"""
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import get_db
from app.utils.helpers import slugify, unique_slug


def seed(app=None):
    app = app or create_app()
    with app.app_context():
        db = get_db()
        now = datetime.now(timezone.utc)

        # Categories
        cats = [
            ("Electronics", "electronics", "Phones, laptops, audio and gadgets"),
            ("Fashion", "fashion", "Clothing, shoes and accessories"),
            ("Home & Living", "home-living", "Furniture, decor and kitchen"),
            ("Beauty", "beauty", "Skincare, cosmetics and personal care"),
            ("Sports", "sports", "Fitness, outdoor and sports gear"),
            ("Books", "books", "Books, stationery and media"),
        ]
        cat_ids = {}
        for name, slug, desc in cats:
            existing = db.categories.find_one({"slug": slug})
            if existing:
                cat_ids[slug] = existing["_id"]
                continue
            doc = {"name": name, "slug": slug, "description": desc,
                   "parent_id": None, "image": None, "is_active": True,
                   "sort_order": 0}
            res = db.categories.insert_one(doc)
            cat_ids[slug] = res.inserted_id
        print(f"Categories: {len(cat_ids)}")

        # Demo seller user
        seller_user = db.users.find_one({"username": "demo_seller"})
        if not seller_user:
            res = db.users.insert_one({
                "username": "demo_seller",
                "email": "seller@demo.local",
                "password_hash": generate_password_hash("DemoSeller123!"),
                "full_name": "Demo Seller",
                "phone": "+920001234567",
                "role": "seller",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            })
            seller_user_id = res.inserted_id
        else:
            seller_user_id = seller_user["_id"]

        seller = db.sellers.find_one({"user_id": seller_user_id})
        if not seller:
            res = db.sellers.insert_one({
                "user_id": seller_user_id,
                "store_name": "Demo Store",
                "store_slug": "demo-store",
                "description": "A demo store with sample products.",
                "status": "approved",
                "status_reason": None,
                "created_at": now,
                "updated_at": now,
            })
            print("Demo seller created (login: demo_seller / DemoSeller123!)")
        else:
            print("Demo seller already exists")

        # Demo products
        products = [
            ("Wireless Bluetooth Headphones", "electronics", 2499, 3499, 45, "Audio"),
            ("Smart Watch Series 5", "electronics", 8999, 12999, 20, "Wearables"),
            ("USB-C Fast Charger 65W", "electronics", 1499, 0, 120, "Accessories"),
            ("Cotton Casual T-Shirt", "fashion", 899, 1299, 200, "Apparel"),
            ("Running Shoes Pro", "sports", 4499, 5999, 60, "Footwear"),
            ("Ceramic Coffee Mug Set", "home-living", 1299, 0, 80, "Kitchen"),
            ("Vitamin C Serum 30ml", "beauty", 1799, 2499, 150, "Skincare"),
            ("Python Crash Course Book", "books", 1599, 0, 35, "Programming"),
        ]
        count = 0
        for name, cat_slug, price, compare, stock, brand in products:
            slug = slugify(name)
            if db.products.find_one({"slug": slug}):
                continue
            db.products.insert_one({
                "name": name,
                "slug": slug,
                "sku": f"DEMO-{slug[:20].upper().replace('-', '')}",
                "description": f"High quality {name.lower()} with premium build and great value.",
                "short_description": f"Premium {name.lower()}",
                "price": price,
                "compare_price": compare,
                "stock": stock,
                "images": ["/assets/images/placeholder.svg"],
                "category_id": cat_ids.get(cat_slug),
                "brand": brand,
                "tags": [brand.lower()],
                "specifications": {},
                "status": "active",
                "seller_id": seller_user_id,
                "rating_avg": 0,
                "rating_count": 0,
                "sold_count": 0,
                "created_at": now - timedelta(days=count),
                "updated_at": now,
            })
            count += 1
        print(f"Demo products added: {count}")

        # Default settings
        db.settings.update_one({"key": "marketplace"}, {"$setOnInsert": {
            "key": "marketplace",
            "marketplace_name": "NovaMarket",
            "currency": "PKR",
            "currency_symbol": "Rs.",
            "commission_rate": 10,
            "delivery_standard": 20,
            "delivery_express": 50,
            "free_delivery_threshold": 0,
            "maintenance_mode": False,
        }}, upsert=True)
        print("Settings initialized")


if __name__ == "__main__":
    seed()
