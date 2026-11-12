"""Seed the initial admin account.

Usage:
    cd backend
    python ../scripts/seed_admin.py

Reads ADMIN_USERNAME / ADMIN_PASSWORD / ADMIN_EMAIL from environment/.env.
The password is hashed with Werkzeug before storage — never stored plaintext.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import get_db


def main(app=None):
    app = app or create_app()
    with app.app_context():
        db = get_db()
        username = os.getenv("ADMIN_USERNAME", "husnain")
        password = os.getenv("ADMIN_PASSWORD")
        email = os.getenv("ADMIN_EMAIL", "admin@marketplace.local")

        if not password:
            print("ERROR: ADMIN_PASSWORD env var is required.")
            if app is None:
                sys.exit(1)
            return

        existing = db.users.find_one({"$or": [{"username": username}, {"email": email}]})
        if existing:
            print(f"Admin '{username}' already exists. Skipping.")
            return

        now = datetime.now(timezone.utc)
        db.users.insert_one({
            "username": username,
            "email": email,
            "password_hash": generate_password_hash(password),
            "full_name": "Administrator",
            "phone": None,
            "role": "admin",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        })
        print(f"Admin '{username}' created successfully.")


if __name__ == "__main__":
    main()
