from flask import Blueprint, request

from ..extensions import get_db
from ..utils.responses import ok, fail, not_found
from ..utils.helpers import serialize, to_object_id, clamp_int
from ..utils.decorators import auth_required, get_current_user

bp = Blueprint("cart", __name__, url_prefix="/api/cart")


def _get_or_create_cart(user_id):
    db = get_db()
    cart = db.carts.find_one({"user_id": user_id})
    if not cart:
        from datetime import datetime, timezone
        cart = {"user_id": user_id, "items": [], "created_at": datetime.now(timezone.utc)}
        db.carts.insert_one(cart)
        cart = db.carts.find_one({"user_id": user_id})
    return cart


def _enrich_cart_items(items):
    """Attach current product info. Prices shown are informational only —
    checkout always recalculates server-side."""
    db = get_db()
    product_ids = [to_object_id(i.get("product_id")) for i in items]
    product_ids = [p for p in product_ids if p]
    products = {p["_id"]: p for p in db.products.find({"_id": {"$in": product_ids}})}
    out = []
    for item in items:
        pid = to_object_id(item.get("product_id"))
        product = products.get(pid)
        entry = dict(item)
        entry["product_id"] = str(pid) if pid else item.get("product_id")
        if product:
            entry["product"] = {
                "id": str(product["_id"]),
                "name": product.get("name"),
                "slug": product.get("slug"),
                "price": product.get("price"),
                "compare_price": product.get("compare_price"),
                "stock": product.get("stock"),
                "images": product.get("images", []),
                "status": product.get("status"),
                "seller_id": str(product.get("seller_id")) if product.get("seller_id") else None,
            }
            entry["available"] = product.get("status") == "active" and product.get("stock", 0) > 0
            entry["line_total"] = round(product.get("price", 0) * item.get("quantity", 0), 2)
        else:
            entry["product"] = None
            entry["available"] = False
            entry["line_total"] = 0
        out.append(entry)
    return out


def cart_summary(cart):
    items = _enrich_cart_items(cart.get("items", []))
    subtotal = sum(i["line_total"] for i in items if i["available"])
    return {"items": items, "subtotal": round(subtotal, 2), "item_count": len(items)}


@bp.get("")
@auth_required
def get_cart():
    user = get_current_user()
    cart = _get_or_create_cart(user["_id"])
    return ok(cart_summary(cart))


@bp.post("/items")
@auth_required
def add_item():
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    product_id = to_object_id(data.get("product_id"))
    quantity = clamp_int(data.get("quantity"), 1, 1, 100)
    if not product_id:
        return fail("product_id is required", "VALIDATION", 400)

    db = get_db()
    product = db.products.find_one({"_id": product_id, "status": "active"})
    if not product:
        return not_found("Product not found or unavailable")
    if product.get("stock", 0) <= 0:
        return fail("Product is out of stock", "OUT_OF_STOCK", 409)

    cart = _get_or_create_cart(user["_id"])
    items = cart.get("items", [])
    existing = next((i for i in items if i.get("product_id") == str(product_id)), None)
    if existing:
        new_qty = min(existing.get("quantity", 0) + quantity, product.get("stock", 0), 100)
        if new_qty <= existing.get("quantity", 0):
            return fail("Maximum available quantity reached", "STOCK_LIMIT", 409)
        db.carts.update_one(
            {"user_id": user["_id"], "items.product_id": str(product_id)},
            {"$set": {"items.$.quantity": new_qty}}
        )
    else:
        items.append({"product_id": str(product_id), "quantity": quantity})
        db.carts.update_one({"user_id": user["_id"]}, {"$set": {"items": items}})

    fresh = db.carts.find_one({"user_id": user["_id"]})
    return ok(cart_summary(fresh), "Added to cart")


@bp.put("/items/<product_id>")
@auth_required
def update_item(product_id):
    user = get_current_user()
    pid = to_object_id(product_id)
    if not pid:
        return not_found("Item not found")
    data = request.get_json(silent=True) or {}
    quantity = clamp_int(data.get("quantity"), 0, 0, 100)

    db = get_db()
    product = db.products.find_one({"_id": pid})
    if quantity == 0:
        db.carts.update_one({"user_id": user["_id"]},
                            {"$pull": {"items": {"product_id": str(pid)}}})
    else:
        if product:
            quantity = min(quantity, product.get("stock", 0), 100)
        db.carts.update_one(
            {"user_id": user["_id"], "items.product_id": str(pid)},
            {"$set": {"items.$.quantity": quantity}}
        )
    fresh = db.carts.find_one({"user_id": user["_id"]})
    return ok(cart_summary(fresh) if fresh else {"items": [], "subtotal": 0, "item_count": 0},
              "Cart updated")


@bp.delete("/items/<product_id>")
@auth_required
def remove_item(product_id):
    user = get_current_user()
    pid = to_object_id(product_id)
    if not pid:
        return not_found("Item not found")
    db = get_db()
    db.carts.update_one({"user_id": user["_id"]},
                        {"$pull": {"items": {"product_id": str(pid)}}})
    fresh = db.carts.find_one({"user_id": user["_id"]})
    return ok(cart_summary(fresh) if fresh else {"items": [], "subtotal": 0, "item_count": 0},
              "Item removed")


@bp.delete("")
@auth_required
def clear_cart():
    user = get_current_user()
    get_db().carts.update_one({"user_id": user["_id"]}, {"$set": {"items": []}})
    return ok({"items": [], "subtotal": 0, "item_count": 0}, "Cart cleared")
