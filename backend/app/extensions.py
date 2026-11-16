from pymongo import MongoClient
from pymongo.database import Database

_client = None
_db = None


def init_db(app):
    global _client, _db
    uri = app.config["MONGODB_URI"]
    if uri.startswith("mongomock"):
        import mongomock
        _client = mongomock.MongoClient()
    else:
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    _db = _client[app.config["DATABASE_NAME"]]
    _create_indexes(_db)
    return _db


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db(app) first.")
    return _db


def _ensure_ttl_index(collection, field, seconds, index_name=None):
    """Create an index, upgrading an existing same-key index to add TTL.

    Older deploys created plain indexes on these fields; MongoDB rejects a
    same-name index with different options (IndexOptionsConflict), so drop
    and recreate when that happens."""
    name = index_name or f"{field}_1"
    try:
        collection.create_index(field, name=name, expireAfterSeconds=seconds)
    except Exception:
        try:
            collection.drop_index(name)
            collection.create_index(field, name=name, expireAfterSeconds=seconds)
        except Exception:
            pass


def _create_indexes(db):
    db.users.create_index("email", unique=True, sparse=True)
    db.users.create_index("username", unique=True)
    db.users.create_index("role")
    db.users.create_index("status")

    db.sellers.create_index("user_id", unique=True)
    db.sellers.create_index("store_slug", unique=True, sparse=True)
    db.sellers.create_index("status")

    db.categories.create_index("slug", unique=True)
    db.categories.create_index("parent_id")

    db.products.create_index("slug", unique=True, sparse=True)
    db.products.create_index("sku", unique=True, sparse=True)
    db.products.create_index("seller_id")
    db.products.create_index("category_id")
    db.products.create_index("status")
    db.products.create_index([("name", "text"), ("description", "text")])
    db.products.create_index("created_at")
    db.products.create_index([("status", 1), ("created_at", -1)])
    db.products.create_index([("status", 1), ("category_id", 1)])
    db.products.create_index([("status", 1), ("seller_id", 1)])

    db.orders.create_index("order_number", unique=True)
    db.orders.create_index("buyer_id")
    db.orders.create_index("status")
    db.orders.create_index("created_at")
    db.orders.create_index([("buyer_id", 1), ("created_at", -1)])

    db.order_items.create_index("order_id")
    db.order_items.create_index("seller_id")
    db.order_items.create_index("product_id")
    db.order_items.create_index("parent_order_id")
    db.order_items.create_index([("parent_order_id", 1), ("seller_id", 1)])
    db.order_items.create_index([("seller_id", 1), ("status", 1)])

    db.carts.create_index("user_id", unique=True)
    db.carts.create_index("items.product_id")

    db.wishlists.create_index("user_id", unique=True)
    db.wishlists.create_index("product_ids")

    db.reviews.create_index([("product_id", 1), ("user_id", 1)], unique=True)
    db.reviews.create_index("product_id")
    db.reviews.create_index([("product_id", 1), ("status", 1), ("created_at", -1)])
    db.reviews.create_index("seller_id")
    db.reviews.create_index("status")

    db.payments.create_index("order_id")
    db.payments.create_index("status")

    db.commissions.create_index("seller_id")
    db.commissions.create_index("order_id")
    db.commissions.create_index("sub_order_id")
    db.commissions.create_index("status")

    db.addresses.create_index("user_id")
    db.notifications.create_index([("user_id", 1), ("read", 1)])
    db.notifications.create_index("created_at")

    # Audit log retention: auto-delete entries older than 1 year.
    _ensure_ttl_index(db.audit_logs, "created_at", 365 * 24 * 3600)
    db.audit_logs.create_index("actor_id")
    db.audit_logs.create_index("action")

    db.password_resets.create_index("token_hash", unique=True)
    db.password_resets.create_index("user_id")
    _ensure_ttl_index(db.password_resets, "expires_at", 0)

    db.email_verifications.create_index("token_hash", unique=True)
    db.email_verifications.create_index("user_id")
    _ensure_ttl_index(db.email_verifications, "expires_at", 0)

    # Refresh tokens: hashed, rotated on use; auto-expire with the JWT lifetime
    db.refresh_tokens.create_index("token_hash", unique=True)
    db.refresh_tokens.create_index("user_id")
    _ensure_ttl_index(db.refresh_tokens, "expires_at", 0)
