from flask import Blueprint, request

from ..extensions import get_db
from ..utils.responses import ok, fail, not_found
from ..utils.helpers import serialize, serialize_list, to_object_id
from ..utils.decorators import auth_required, get_current_user

bp = Blueprint("wishlist", __name__, url_prefix="/api/wishlist")


def _get_or_create(user_id):
    db = get_db()
    wl = db.wishlists.find_one({"user_id": user_id})
    if not wl:
        from datetime import datetime, timezone
        wl = {"user_id": user_id, "product_ids": [], "created_at": datetime.now(timezone.utc)}
        db.wishlists.insert_one(wl)
        wl = db.wishlists.find_one({"user_id": user_id})
    return wl


@bp.get("")
@auth_required
def get_wishlist():
    user = get_current_user()
    wl = _get_or_create(user["_id"])
    ids = [to_object_id(p) for p in wl.get("product_ids", [])]
    ids = [i for i in ids if i]
    products = list(get_db().products.find({"_id": {"$in": ids}}))
    # Preserve wishlist order
    order = {str(i): n for n, i in enumerate(ids)}
    products.sort(key=lambda p: order.get(str(p["_id"]), 9999))
    from ..products.routes import _enrich_products
    return ok({"products": _enrich_products(products)})


@bp.post("/items")
@auth_required
def add_item():
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    pid = to_object_id(data.get("product_id"))
    if not pid:
        return fail("product_id is required", "VALIDATION", 400)
    db = get_db()
    if not db.products.find_one({"_id": pid}):
        return not_found("Product not found")
    wl = _get_or_create(user["_id"])
    ids = wl.get("product_ids", [])
    sid = str(pid)
    if sid in ids:
        return ok(message="Already in wishlist")
    ids.append(sid)
    db.wishlists.update_one({"user_id": user["_id"]}, {"$set": {"product_ids": ids}})
    return ok(message="Added to wishlist")


@bp.delete("/items/<product_id>")
@auth_required
def remove_item(product_id):
    user = get_current_user()
    pid = to_object_id(product_id)
    if not pid:
        return not_found("Item not found")
    get_db().wishlists.update_one({"user_id": user["_id"]},
                                  {"$pull": {"product_ids": str(pid)}})
    return ok(message="Removed from wishlist")
