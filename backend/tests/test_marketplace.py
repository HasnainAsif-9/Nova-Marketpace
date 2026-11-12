"""NovaMarket backend test suite.

Run:  cd backend && python -m pytest tests/ -v
Uses mongomock — no real MongoDB required.
"""
import pytest
from datetime import datetime, timezone
from bson import ObjectId

from app import create_app
from app.config import TestConfig
from app.extensions import get_db
from app.utils.decorators import reset_rate_limits
from werkzeug.security import generate_password_hash


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    app.config["TESTING"] = True
    with app.app_context():
        yield app


@pytest.fixture()
def client(app):
    reset_rate_limits()
    return app.test_client()


@pytest.fixture()
def db(app):
    return get_db()


def register(client, username, email, password="password123", role="buyer", **extra):
    body = {"username": username, "email": email, "password": password,
            "full_name": username.title(), "role": role}
    body.update(extra)
    return client.post("/api/auth/register", json=body)


def login(client, email, password="password123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def make_admin(db):
    now = datetime.now(timezone.utc)
    res = db.users.insert_one({
        "username": "admin1", "email": "admin@test.com",
        "password_hash": generate_password_hash("adminpass123"),
        "full_name": "Admin", "role": "admin", "status": "active",
        "created_at": now, "updated_at": now,
    })
    return res.inserted_id


def make_seller(db, approved=True):
    now = datetime.now(timezone.utc)
    uid = db.users.insert_one({
        "username": f"seller{str(ObjectId())}", "email": f"s{str(ObjectId())}@t.com",
        "password_hash": generate_password_hash("sellerpass123"),
        "full_name": "Seller", "role": "seller", "status": "active",
        "created_at": now, "updated_at": now,
    }).inserted_id
    db.sellers.insert_one({
        "user_id": uid, "store_name": "Test Store", "store_slug": f"store-{str(ObjectId())}",
        "status": "approved" if approved else "pending",
        "created_at": now, "updated_at": now,
    })
    return uid


def make_category(db):
    return db.categories.insert_one({
        "name": "Electronics", "slug": "electronics", "is_active": True,
    }).inserted_id


def make_product(db, seller_id, category_id, price=1000, stock=10, status="active"):
    return db.products.insert_one({
        "name": "Test Product", "slug": f"prod-{str(ObjectId())}",
        "price": price, "compare_price": 0, "stock": stock,
        "status": status, "seller_id": seller_id, "category_id": category_id,
        "images": [], "rating_avg": 0, "rating_count": 0, "sold_count": 0,
        "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
    }).inserted_id


# ================= AUTH =================

class TestAuth:
    def test_register_buyer(self, client):
        r = register(client, "buyer1", "buyer1@test.com")
        assert r.status_code == 201
        assert r.get_json()["success"] is True
        assert r.get_json()["data"]["user"]["role"] == "buyer"

    def test_register_seller_creates_pending_seller(self, client, db):
        r = register(client, "seller1", "seller1@test.com", role="seller", store_name="My Store")
        assert r.status_code == 201
        seller = db.sellers.find_one({"store_name": "My Store"})
        assert seller is not None
        assert seller["status"] == "pending"  # REQUIRE_SELLER_APPROVAL=True in TestConfig? default True

    def test_register_duplicate_email(self, client):
        register(client, "user_one", "dup@test.com")
        r = register(client, "user_two", "dup@test.com")
        assert r.status_code == 409

    def test_register_weak_password(self, client):
        r = register(client, "user_one", "u1@test.com", password="short")
        assert r.status_code == 400

    def test_register_invalid_username(self, client):
        r = register(client, "a!", "u1@test.com")
        assert r.status_code == 400

    def test_login_success(self, client):
        register(client, "user_one", "u1@test.com")
        r = login(client, "u1@test.com")
        assert r.status_code == 200
        assert r.get_json()["success"] is True

    def test_login_wrong_password(self, client):
        register(client, "user_one", "u1@test.com")
        r = login(client, "u1@test.com", "wrongpass")
        assert r.status_code == 401

    def test_login_unknown_user(self, client):
        r = login(client, "nobody@test.com")
        assert r.status_code == 401

    def test_logout(self, client):
        register(client, "user_one", "u1@test.com")
        login(client, "u1@test.com")
        r = client.post("/api/auth/logout")
        assert r.status_code == 200

    def test_me_requires_auth(self, client):
        r = client.get("/api/users/me")
        assert r.status_code == 401

    def test_me_returns_user(self, client):
        register(client, "user_one", "u1@test.com")
        login(client, "u1@test.com")
        r = client.get("/api/users/me")
        assert r.status_code == 200
        assert "password_hash" not in r.get_json()["data"]["user"]

    def test_password_never_exposed(self, client, db):
        register(client, "user_one", "u1@test.com")
        user = db.users.find_one({"email": "u1@test.com"})
        assert "password_hash" in user
        assert user["password_hash"] != "password123"
        assert "password123" not in user["password_hash"]

    def test_change_password(self, client):
        register(client, "user_one", "u1@test.com")
        login(client, "u1@test.com")
        r = client.post("/api/auth/change-password", json={
            "current_password": "password123", "new_password": "newpass456"})
        assert r.status_code == 200
        # old password fails
        client.post("/api/auth/logout")
        r = login(client, "u1@test.com", "password123")
        assert r.status_code == 401
        r = login(client, "u1@test.com", "newpass456")
        assert r.status_code == 200


# ================= AUTHORIZATION / IDOR =================

class TestAuthorization:
    def test_guest_cannot_cart(self, client):
        r = client.post("/api/cart/items", json={"product_id": str(ObjectId()), "quantity": 1})
        assert r.status_code == 401

    def test_guest_cannot_checkout(self, client):
        r = client.post("/api/orders/checkout", json={})
        assert r.status_code == 401

    def test_guest_cannot_wishlist(self, client):
        r = client.post("/api/wishlist/items", json={"product_id": str(ObjectId())})
        assert r.status_code == 401

    def test_buyer_cannot_access_admin(self, client):
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        r = client.get("/api/admin/stats")
        assert r.status_code == 403

    def test_seller_cannot_access_admin(self, client, db):
        uid = make_seller(db)
        # login as that seller
        client.post("/api/auth/login", json={"email": db.users.find_one({"_id": uid})["email"], "password": "sellerpass123"})
        r = client.get("/api/admin/stats")
        assert r.status_code == 403

    def test_admin_can_access_admin(self, client, db):
        make_admin(db)
        client.post("/api/auth/login", json={"email": "admin@test.com", "password": "adminpass123"})
        r = client.get("/api/admin/stats")
        assert r.status_code == 200

    def test_buyer_cannot_create_product(self, client, db):
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        cat = make_category(db)
        r = client.post("/api/products", json={"name": "X", "price": 100, "category_id": str(cat)})
        assert r.status_code == 403

    def test_seller_cannot_edit_other_sellers_product(self, client, db):
        seller_a = make_seller(db)
        seller_b = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller_a, cat)
        # login as seller B
        email_b = db.users.find_one({"_id": seller_b})["email"]
        client.post("/api/auth/login", json={"email": email_b, "password": "sellerpass123"})
        r = client.put(f"/api/products/{prod}", json={"price": 1})
        assert r.status_code == 403

    def test_buyer_cannot_view_other_users_order(self, client, db):
        # buyer A places order, buyer B tries to view
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=100)
        register(client, "buyer_a", "ba@test.com")
        login(client, "ba@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "A", "phone": "1234567", "address_line1": "St 1", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 1})
        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        assert r.status_code == 201
        order_id = r.get_json()["data"]["order"]["id"]

        # buyer B
        client.post("/api/auth/logout")
        register(client, "buyer_b", "bb@test.com")
        login(client, "bb@test.com")
        r = client.get(f"/api/orders/{order_id}")
        assert r.status_code == 403

    def test_price_manipulation_ignored(self, client, db):
        """Client-submitted price must be ignored — server recalculates."""
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=1000)
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "A", "phone": "1234567", "address_line1": "St 1", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 1})
        # Try to inject a fake price in checkout payload
        r = client.post("/api/orders/checkout", json={
            "delivery_option": "standard", "payment_method": "cod",
            "total": 1, "price": 1, "subtotal": 1})
        assert r.status_code == 201
        order = r.get_json()["data"]["order"]
        assert order["subtotal"] == 1000  # real price, not injected 1


# ================= BUSINESS LOGIC =================

class TestBusinessLogic:
    def test_commission_calculation_spec_example(self, client, db):
        """Product Rs.1,000 × qty 2 + Rs.50 delivery, 10% commission.
        Expected: Subtotal 2000, Buyer total 2050, Commission 200, Seller earning 1800."""
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=1000, stock=10)

        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "Buyer", "phone": "03001234567",
            "address_line1": "House 1", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 2})

        r = client.post("/api/orders/checkout", json={
            "delivery_option": "express", "payment_method": "cod"})
        assert r.status_code == 201
        order = r.get_json()["data"]["order"]

        assert order["subtotal"] == 2000
        assert order["delivery_fee"] == 50
        assert order["total"] == 2050
        assert order["commission_rate"] == 10

        sub = db.order_items.find_one({"parent_order_id": order["id"] if isinstance(order["id"], ObjectId) else ObjectId(order["id"])})
        # order["id"] is string; find by parent_order_id ObjectId
        from bson import ObjectId as OID
        sub = db.order_items.find_one({"parent_order_id": OID(order["id"])})
        assert sub["commission_amount"] == 200
        assert sub["seller_earning"] == 1800

        comm = db.commissions.find_one({"order_id": OID(order["id"])})
        assert comm["commission_amount"] == 200
        assert comm["seller_earning"] == 1800

        # Stock deducted
        p = db.products.find_one({"_id": prod})
        assert p["stock"] == 8
        assert p["sold_count"] == 2

        # Cart cleared
        cart = db.carts.find_one({"user_id": db.users.find_one({"email": "b1@test.com"})["_id"]})
        assert cart["items"] == []

    def test_multi_seller_order_creates_sub_orders(self, client, db):
        seller_a = make_seller(db)
        seller_b = make_seller(db)
        cat = make_category(db)
        pa = make_product(db, seller_a, cat, price=500)
        pb = make_product(db, seller_b, cat, price=700)

        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(pa), "quantity": 1})
        client.post("/api/cart/items", json={"product_id": str(pb), "quantity": 1})

        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        assert r.status_code == 201
        order_id = r.get_json()["data"]["order"]["id"]

        subs = list(db.order_items.find({"parent_order_id": ObjectId(order_id)}))
        assert len(subs) == 2  # one sub-order per seller
        assert len(list(db.commissions.find({"order_id": ObjectId(order_id)}))) == 2

    def test_insufficient_stock_rejected(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=100, stock=2)
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 2})
        # Try to checkout with qty 5 via cart manipulation — simulate by direct cart update
        db.carts.update_one({}, {"$set": {"items.0.quantity": 5}})
        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        assert r.status_code == 409
        assert r.get_json()["error_code"] == "INSUFFICIENT_STOCK"

    def test_out_of_stock_product_rejected(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=100, stock=0)
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        # Manually insert into cart (API blocks adding out-of-stock)
        uid = db.users.find_one({"email": "b1@test.com"})["_id"]
        db.carts.insert_one({"user_id": uid, "items": [{"product_id": str(prod), "quantity": 1}]})
        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        assert r.status_code == 409

    def test_empty_cart_checkout_fails(self, client):
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        assert r.status_code == 400
        assert r.get_json()["error_code"] == "EMPTY_CART"

    def test_order_status_flow(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=100)
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 1})
        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        order_id = r.get_json()["data"]["order"]["id"]

        # Buyer cannot skip to shipped
        r = client.post(f"/api/orders/{order_id}/status", json={"status": "shipped"})
        assert r.status_code == 403  # buyer role not allowed

        # Seller can confirm
        email_s = db.users.find_one({"_id": seller})["email"]
        client.post("/api/auth/logout")
        client.post("/api/auth/login", json={"email": email_s, "password": "sellerpass123"})
        r = client.post(f"/api/orders/{order_id}/status", json={"status": "confirmed"})
        assert r.status_code == 200
        # Seller cannot set delivered (admin-only status)
        r = client.post(f"/api/orders/{order_id}/status", json={"status": "delivered"})
        assert r.status_code == 403
        # Invalid transition also blocked
        r = client.post(f"/api/orders/{order_id}/status", json={"status": "shipped"})
        assert r.status_code == 400

    def test_cancel_restock(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=100, stock=5)
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 2})
        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        order_id = r.get_json()["data"]["order"]["id"]
        assert db.products.find_one({"_id": prod})["stock"] == 3

        r = client.post(f"/api/orders/{order_id}/cancel")
        assert r.status_code == 200
        assert db.products.find_one({"_id": prod})["stock"] == 5  # restocked


# ================= PRODUCTS / CATALOG =================

class TestCatalog:
    def test_public_product_listing(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        make_product(db, seller, cat, price=500)
        r = client.get("/api/products")
        assert r.status_code == 200
        assert r.get_json()["data"]["pagination"]["total"] == 1

    def test_inactive_product_hidden(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        make_product(db, seller, cat, status="inactive")
        r = client.get("/api/products")
        assert r.get_json()["data"]["pagination"]["total"] == 0

    def test_product_search(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        make_product(db, seller, cat)
        db.products.update_one({}, {"$set": {"name": "Wireless Headphones Pro"}})
        r = client.get("/api/products?q=headphones")
        assert r.get_json()["data"]["pagination"]["total"] == 1
        r = client.get("/api/products?q=nonexistentitem")
        assert r.get_json()["data"]["pagination"]["total"] == 0

    def test_price_filter(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        make_product(db, seller, cat, price=100)
        make_product(db, seller, cat, price=5000)
        r = client.get("/api/products?min_price=1000")
        assert r.get_json()["data"]["pagination"]["total"] == 1

    def test_invalid_object_id_returns_404(self, client):
        r = client.get("/api/products/not-a-valid-id")
        assert r.status_code == 404


# ================= SELLER =================

class TestSeller:
    def test_unapproved_seller_cannot_create_product(self, client, db):
        # Create seller with pending status
        now = datetime.now(timezone.utc)
        uid = db.users.insert_one({
            "username": "pendingseller", "email": "p@t.com",
            "password_hash": generate_password_hash("pass12345"),
            "full_name": "P", "role": "seller", "status": "active",
            "created_at": now, "updated_at": now,
        }).inserted_id
        db.sellers.insert_one({
            "user_id": uid, "store_name": "Pending", "status": "pending",
            "created_at": now, "updated_at": now,
        })
        client.post("/api/auth/login", json={"email": "p@t.com", "password": "pass12345"})
        cat = make_category(db)
        r = client.post("/api/products", json={"name": "X", "price": 100, "category_id": str(cat)})
        assert r.status_code == 403
        assert r.get_json()["error_code"] == "SELLER_NOT_APPROVED"

    def test_admin_approves_seller(self, client, db):
        uid = make_seller(db, approved=False)
        seller = db.sellers.find_one({"user_id": uid})
        make_admin(db)
        client.post("/api/auth/login", json={"email": "admin@test.com", "password": "adminpass123"})
        r = client.put(f"/api/admin/sellers/{seller['_id']}/status", json={"status": "approved"})
        assert r.status_code == 200
        assert db.sellers.find_one({"_id": seller["_id"]})["status"] == "approved"

    def test_seller_earnings_endpoint(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=1000)
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 1})
        client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})

        email_s = db.users.find_one({"_id": seller})["email"]
        client.post("/api/auth/logout")
        client.post("/api/auth/login", json={"email": email_s, "password": "sellerpass123"})
        r = client.get("/api/sellers/me/earnings")
        assert r.status_code == 200
        e = r.get_json()["data"]["earnings"]
        assert e["total_sales"] == 1000
        assert e["total_commission"] == 100
        assert e["total_earnings"] == 900


# ================= REVIEWS =================

class TestReviews:
    def test_review_requires_delivered_order(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat)
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        r = client.post("/api/reviews", json={"product_id": str(prod), "rating": 5, "comment": "Great"})
        assert r.status_code == 403
        assert r.get_json()["error_code"] == "REVIEW_NOT_ELIGIBLE"

    def test_review_after_delivery(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat)
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 1})
        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        order_id = r.get_json()["data"]["order"]["id"]

        # Admin marks delivered
        make_admin(db)
        client.post("/api/auth/logout")
        client.post("/api/auth/login", json={"email": "admin@test.com", "password": "adminpass123"})
        client.post(f"/api/orders/{order_id}/status", json={"status": "confirmed"})
        client.post(f"/api/orders/{order_id}/status", json={"status": "processing"})
        client.post(f"/api/orders/{order_id}/status", json={"status": "shipped"})
        client.post(f"/api/orders/{order_id}/status", json={"status": "out_for_delivery"})
        client.post(f"/api/orders/{order_id}/status", json={"status": "delivered"})

        # Buyer reviews
        client.post("/api/auth/logout")
        client.post("/api/auth/login", json={"email": "b1@test.com", "password": "password123"})
        r = client.post("/api/reviews", json={"product_id": str(prod), "rating": 5, "comment": "Excellent!"})
        assert r.status_code == 201
        # Duplicate review blocked
        r = client.post("/api/reviews", json={"product_id": str(prod), "rating": 4})
        assert r.status_code == 409


# ================= SECURITY =================

class TestSecurity:
    def test_no_sql_injection_in_search(self, client, db):
        r = client.get("/api/products?q='; DROP TABLE users; --")
        assert r.status_code == 200  # treated as text search, no injection

    def test_no_sql_injection_in_login(self, client):
        r = client.post("/api/auth/login", json={
            "email": {"$ne": None}, "password": {"$ne": None}})
        assert r.status_code in (400, 401)  # rejected, not crashed

    def test_invalid_json_handled(self, client):
        r = client.post("/api/auth/login", data="not json", content_type="application/json")
        assert r.status_code in (400, 401, 500)
        # Should not leak stack trace
        assert b"Traceback" not in r.data

    def test_error_response_has_no_stacktrace(self, client):
        r = client.get("/api/nonexistent-endpoint")
        assert r.status_code == 404
        assert b"Traceback" not in r.data

    def test_security_headers_present(self, client):
        r = client.get("/api/settings")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_seller_cannot_access_other_seller_orders(self, client, db):
        seller_a = make_seller(db)
        seller_b = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller_a, cat)
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 1})
        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        order_id = r.get_json()["data"]["order"]["id"]

        # Seller B tries to view order detail
        email_b = db.users.find_one({"_id": seller_b})["email"]
        client.post("/api/auth/logout")
        client.post("/api/auth/login", json={"email": email_b, "password": "sellerpass123"})
        r = client.get(f"/api/orders/{order_id}")
        assert r.status_code == 403

    def test_admin_seed_password_hashed(self, db):
        make_admin(db)
        admin = db.users.find_one({"username": "admin1"})
        assert admin["password_hash"] != "adminpass123"
        assert "adminpass123" not in admin["password_hash"]


# ================= SETTINGS / DELIVERY =================

class TestSettings:
    def test_delivery_options_public(self, client):
        r = client.get("/api/orders/delivery-options")
        assert r.status_code == 200
        opts = r.get_json()["data"]["options"]
        fees = {o["id"]: o["fee"] for o in opts}
        assert fees["standard"] == 20
        assert fees["express"] == 50

    def test_admin_updates_commission(self, client, db):
        make_admin(db)
        client.post("/api/auth/login", json={"email": "admin@test.com", "password": "adminpass123"})
        r = client.put("/api/settings", json={"commission_rate": 15})
        assert r.status_code == 200
        # New order uses new rate
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=1000)
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 1})
        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        order = r.get_json()["data"]["order"]
        assert order["commission_rate"] == 15

    def test_free_delivery_threshold(self, client, db):
        make_admin(db)
        client.post("/api/auth/login", json={"email": "admin@test.com", "password": "adminpass123"})
        client.put("/api/settings", json={"free_delivery_threshold": 5000})
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=6000)
        register(client, "buyer_one", "b1@test.com")
        login(client, "b1@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 1})
        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        order = r.get_json()["data"]["order"]
        assert order["delivery_fee"] == 0  # free above threshold
        assert order["total"] == 6000


# ================= SECURITY AUDIT REGRESSION TESTS =================

class TestSecurityAudit:
    def test_refresh_token_rejected_as_access(self, client):
        """A refresh token must not work as an access token."""
        register(client, "rt_user", "rt@test.com")
        resp = client.post("/api/auth/login", json={"email": "rt@test.com", "password": "password123"})
        refresh_token = None
        for h in resp.headers.getlist("Set-Cookie"):
            if h.startswith("refresh_token="):
                refresh_token = h.split("refresh_token=", 1)[1].split(";", 1)[0]
        assert refresh_token, "refresh_token cookie not set"
        r = client.get("/api/users/me",
                       headers={"Authorization": f"Bearer {refresh_token}"})
        assert r.status_code == 401

    def test_password_change_revokes_old_tokens(self, client):
        register(client, "pv_user", "pv@test.com")
        login(client, "pv@test.com")
        r = client.get("/api/users/me")
        assert r.status_code == 200
        # Change password
        r = client.post("/api/auth/change-password", json={
            "current_password": "password123", "new_password": "newpass456"})
        assert r.status_code == 200
        # Old access token must now be rejected (token_version bumped)
        # Re-login state was overwritten by change-password? No � cookies still hold old token.
        # The old Bearer token is no longer valid:
        # (client cookie jar still has old access_token cookie)
        r = client.get("/api/users/me")
        # Cookie-based auth also uses the old token -> should be rejected
        assert r.status_code == 401

    def test_email_case_normalization(self, client):
        r = register(client, "caseuser", "Mixed@Case.com")
        assert r.status_code == 201
        stored = client.application.config  # noqa
        # Login with different case must work
        r = login(client, "mixed@case.com")
        assert r.status_code == 200
        # Duplicate with different case must be rejected
        client.post("/api/auth/logout")
        r = register(client, "caseuser2", "MIXED@CASE.COM")
        assert r.status_code == 409

    def test_seller_cannot_view_other_order_payment(self, client, db):
        seller_a = make_seller(db)
        seller_b = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller_a, cat, price=100)
        register(client, "pay_buyer", "pay@test.com")
        login(client, "pay_buyer")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 1})
        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        order_id = r.get_json()["data"]["order"]["id"]

        email_b = db.users.find_one({"_id": seller_b})["email"]
        client.post("/api/auth/logout")
        client.post("/api/auth/login", json={"email": email_b, "password": "sellerpass123"})
        r = client.get(f"/api/payments/order/{order_id}")
        assert r.status_code == 403

    def test_public_store_endpoint_works(self, client, db):
        seller = make_seller(db)
        s = db.sellers.find_one({"user_id": seller})
        r = client.get(f"/api/sellers/{s['store_slug']}")
        assert r.status_code == 200
        assert r.get_json()["data"]["seller"]["store_name"] == "Test Store"

    def test_wishlist_endpoint_works(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat)
        register(client, "wl_user", "wl@test.com")
        login(client, "wl@test.com")
        r = client.post("/api/wishlist/items", json={"product_id": str(prod)})
        assert r.status_code == 200
        r = client.get("/api/wishlist")
        assert r.status_code == 200
        assert len(r.get_json()["data"]["products"]) == 1

    def test_status_cancel_restock(self, client, db):
        """Cancelling via status endpoint must restock inventory."""
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=100, stock=5)
        register(client, "rc_buyer", "rc@test.com")
        login(client, "rc_buyer")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 2})
        r = client.post("/api/orders/checkout", json={"delivery_option": "standard", "payment_method": "cod"})
        order_id = r.get_json()["data"]["order"]["id"]
        assert db.products.find_one({"_id": prod})["stock"] == 3

        # Seller cancels via status endpoint
        email_s = db.users.find_one({"_id": seller})["email"]
        client.post("/api/auth/logout")
        client.post("/api/auth/login", json={"email": email_s, "password": "sellerpass123"})
        r = client.post(f"/api/orders/{order_id}/status", json={"status": "cancelled"})
        assert r.status_code == 200
        assert db.products.find_one({"_id": prod})["stock"] == 5  # restocked


# ================= PASSWORD RESET & EMAIL VERIFICATION =================

class TestPasswordReset:
    def test_forgot_password_no_enumeration(self, client):
        register(client, "fp_user", "fp@test.com")
        # Existing email -> success
        r = client.post("/api/auth/forgot-password", json={"email": "fp@test.com"})
        assert r.status_code == 200
        # Non-existing email -> same success response (no enumeration)
        r2 = client.post("/api/auth/forgot-password", json={"email": "nobody@test.com"})
        assert r2.status_code == 200
        assert r.get_json()["message"] == r2.get_json()["message"]

    def test_reset_password_flow(self, client, db):
        register(client, "rp_user", "rp@test.com")
        client.post("/api/auth/forgot-password", json={"email": "rp@test.com"})
        rec = db.password_resets.find_one({})
        assert rec is not None
        # Recover the raw token is impossible (hashed) — simulate by creating
        # a known token directly, as the email would deliver it.
        import hashlib, secrets
        from datetime import datetime, timedelta, timezone
        token = secrets.token_urlsafe(32)
        db.password_resets.insert_one({
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "user_id": rec["user_id"],
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "used": False, "created_at": datetime.now(timezone.utc)})
        r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "brandnew123"})
        assert r.status_code == 200
        # Old password no longer works, new one does
        client.post("/api/auth/logout")
        r = client.post("/api/auth/login", json={"email": "rp@test.com", "password": "password123"})
        assert r.status_code == 401
        r = client.post("/api/auth/login", json={"email": "rp@test.com", "password": "brandnew123"})
        assert r.status_code == 200
        # Token is single-use
        r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "another123"})
        assert r.status_code == 400

    def test_reset_password_invalid_token(self, client):
        r = client.post("/api/auth/reset-password", json={"token": "bogus", "new_password": "whatever123"})
        assert r.status_code == 400


class TestEmailVerification:
    def test_register_marks_unverified_and_sends_token(self, client, db):
        r = register(client, "ev_user", "ev@test.com")
        assert r.status_code == 201
        user = db.users.find_one({"email": "ev@test.com"})
        assert user["email_verified"] is False
        assert db.email_verifications.find_one({"user_id": user["_id"]}) is not None

    def test_verify_email_flow(self, client, db):
        register(client, "ev2_user", "ev2@test.com")
        import hashlib, secrets
        from datetime import datetime, timedelta, timezone
        user = db.users.find_one({"email": "ev2@test.com"})
        token = secrets.token_urlsafe(32)
        db.email_verifications.insert_one({
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "user_id": user["_id"],
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
            "used": False, "created_at": datetime.now(timezone.utc)})
        r = client.post("/api/auth/verify-email", json={"token": token})
        assert r.status_code == 200
        assert db.users.find_one({"_id": user["_id"]})["email_verified"] is True
        # Single use
        r = client.post("/api/auth/verify-email", json={"token": token})
        assert r.status_code == 400

    def test_resend_verification_requires_auth(self, client):
        r = client.post("/api/auth/resend-verification")
        assert r.status_code == 401


class TestEmailVerificationEnforcement:
    def test_login_blocked_when_enforcement_on(self, client, app):
        register(client, "enf_user", "enf@test.com")
        app.config["REQUIRE_EMAIL_VERIFICATION"] = True
        try:
            client.post("/api/auth/logout")
            r = client.post("/api/auth/login", json={"email": "enf@test.com", "password": "password123"})
            assert r.status_code == 403
            assert r.get_json()["error_code"] == "EMAIL_NOT_VERIFIED"
        finally:
            app.config["REQUIRE_EMAIL_VERIFICATION"] = False

    def test_login_allowed_after_verify_when_enforcement_on(self, client, app, db):
        register(client, "enf2_user", "enf2@test.com")
        import hashlib, secrets
        from datetime import datetime, timedelta, timezone
        user = db.users.find_one({"email": "enf2@test.com"})
        token = secrets.token_urlsafe(32)
        db.email_verifications.insert_one({
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "user_id": user["_id"],
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
            "used": False, "created_at": datetime.now(timezone.utc)})
        client.post("/api/auth/verify-email", json={"token": token})
        app.config["REQUIRE_EMAIL_VERIFICATION"] = True
        try:
            client.post("/api/auth/logout")
            r = client.post("/api/auth/login", json={"email": "enf2@test.com", "password": "password123"})
            assert r.status_code == 200
        finally:
            app.config["REQUIRE_EMAIL_VERIFICATION"] = False


# ================= PAYMENTS =================

class TestPayments:
    def test_payment_methods_lists_cod(self, client):
        r = client.get("/api/payments/methods")
        assert r.status_code == 200
        methods = r.get_json()["data"]["methods"]
        assert {m["id"] for m in methods} == {"cod"}

    def test_checkout_rejects_disabled_payment_method(self, client, db):
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=100)
        register(client, "pay_buyer", "pay@test.com")
        login(client, "pay@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 1})
        r = client.post("/api/orders/checkout", json={
            "delivery_option": "standard", "payment_method": "stripe"})
        assert r.status_code == 400
        assert r.get_json()["error_code"] == "PAYMENT_METHOD"

    def test_checkout_accepts_enabled_method_via_config(self, client, app, db):
        """A gateway that reports is_available()=False stays disabled;
        enabling it in config without credentials must not expose it."""
        seller = make_seller(db)
        cat = make_category(db)
        prod = make_product(db, seller, cat, price=100)
        register(client, "pay2_buyer", "pay2@test.com")
        login(client, "pay2@test.com")
        client.post("/api/buyers/addresses", json={
            "recipient_name": "B", "phone": "1234567", "address_line1": "St", "city": "Lahore"})
        client.post("/api/cart/items", json={"product_id": str(prod), "quantity": 1})
        app.config["PAYMENT_METHODS_ENABLED"] = ["cod", "stripe"]
        try:
            r = client.post("/api/orders/checkout", json={
                "delivery_option": "standard", "payment_method": "stripe"})
            assert r.status_code == 400  # no STRIPE_SECRET_KEY -> unavailable
        finally:
            app.config["PAYMENT_METHODS_ENABLED"] = ["cod"]

    def test_webhook_unknown_method_404(self, client):
        r = client.post("/api/payments/webhook/bogus", data=b"{}",
                        content_type="application/json")
        assert r.status_code == 404

    def test_webhook_unimplemented_gateway_501(self, client):
        r = client.post("/api/payments/webhook/cod", data=b"{}",
                        content_type="application/json")
        assert r.status_code == 501
