"""Development server with in-process seeding.

Use this when running with MONGODB_URI=mongomock://... (no MongoDB installed).
mongomock keeps data in memory per process, so seeding must happen in the
same process as the server.

Usage:
    cd backend
    python ../scripts/dev_server.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from app import create_app
import seed_admin
import seed_demo_data


def main():
    app = create_app()

    # Seed in-process so mongomock data is visible to the server
    seed_admin.main(app)
    seed_demo_data.seed(app)

    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    print(f"\n  NovaMarket dev server → http://localhost:{port}\n")
    print("  Admin:   husnain / (ADMIN_PASSWORD from .env)")
    print("  Seller:  demo_seller / DemoSeller123!\n")
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
