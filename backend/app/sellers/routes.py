from flask import Blueprint, request

from ..extensions import get_db
from ..utils.responses import ok, fail, not_found
from ..utils.helpers import serialize, serialize_list, to_object_id, slugify, clean_str, clamp_int
from ..utils.decorators import auth_required, role_required, get_current_user
from ..utils.audit import audit_log

bp = Blueprint("sellers", __name__, url_prefix="/api/sellers")


def _seller_public(seller, include_products=False):
    data = serialize(seller)
    data.pop("status_reason", None) if seller.get("status") != "rejected" else None
    if include_products:
        user_id = seller["user_id"]
        products = list(get_db().products.find(
            {"seller_id": user_id, "status": "active"})
            .sort("created_at", -1).limit(24))
        from ..products.routes import _enrich_products
        data["products"] = _enrich_products(products)
        data["product_count"] = get_db().products.count_documents(
            {"seller_id": user_id, "status": "active"})
    return data


@bp.get("")
def list_sellers():
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 20, 1, 60)
    query = {"status": "approved"}
    q = clean_str(request.args.get("q"), 100)
    if q:
        import re as _re
        safe = _re.escape(q)
        query["$or"] = [
            {"store_name": {"$regex": safe, "$options": "i"}},
            {"description": {"$regex": safe, "$options": "i"}},
        ]
    total = db.sellers.count_documents(query)
    sellers = list(db.sellers.find(query).sort("created_at", -1)
                   .skip((page - 1) * limit).limit(limit))
    return ok({
        "sellers": [_seller_public(s) for s in sellers],
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


@bp.get("/me")
@auth_required
def my_store():
    user = get_current_user()
    if user["role"] != "seller":
        return fail("Only sellers have a store profile", "FORBIDDEN", 403)
    seller = get_db().sellers.find_one({"user_id": user["_id"]})
    if not seller:
        return not_found("Seller profile not found")
    return ok({"seller": _seller_public(seller)})


@bp.put("/me")
@auth_required
def update_store():
    user = get_current_user()
    if user["role"] != "seller":
        return fail("Only sellers can update a store", "FORBIDDEN", 403)
    db = get_db()
    seller = db.sellers.find_one({"user_id": user["_id"]})
    if not seller:
        return not_found("Seller profile not found")

    data = request.get_json(silent=True) or {}
    update = {}
    for field, max_len in (("store_name", 120), ("description", 2000),
                           ("logo", 500), ("banner", 500),
                           ("contact_email", 254), ("contact_phone", 20),
                           ("address", 300), ("city", 100)):
        if field in data:
            update[field] = clean_str(data[field], max_len)

    if "store_slug" in data:
        slug = slugify(data["store_slug"] or "")
        if slug:
            dup = db.sellers.find_one({"store_slug": slug, "_id": {"$ne": seller["_id"]}})
            if dup:
                return fail("Store slug is already taken", "SLUG_TAKEN", 409)
            update["store_slug"] = slug

    if update:
        from datetime import datetime, timezone
        update["updated_at"] = datetime.now(timezone.utc)
        db.sellers.update_one({"_id": seller["_id"]}, {"$set": update})
        audit_log("seller.store_update", actor_id=user["_id"], actor_role=user["role"],
                  target_type="seller", target_id=str(seller["_id"]),
                  details={"fields": list(update.keys())}, ip=request.remote_addr)
    fresh = db.sellers.find_one({"_id": seller["_id"]})
    return ok({"seller": _seller_public(fresh)}, "Store updated")


@bp.get("/<store_ref>")
def get_store(store_ref):
    db = get_db()
    seller = None
    oid = to_object_id(store_ref)
    if oid:
        seller = db.sellers.find_one({"_id": oid})
    if not seller:
        seller = db.sellers.find_one({"store_slug": store_ref})
    if not seller:
        return not_found("Store not found")
    if seller.get("status") != "approved":
        return not_found("Store not found")
    return ok({"seller": _seller_public(seller, include_products=True)})


@bp.get("/<store_ref>/products")
def store_products(store_ref):
    db = get_db()
    seller = db.sellers.find_one({"store_slug": store_ref}) or \
        (db.sellers.find_one({"_id": to_object_id(store_ref)}) if to_object_id(store_ref) else None)
    if not seller or seller.get("status") != "approved":
        return not_found("Store not found")

    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 20, 1, 60)
    query = {"seller_id": seller["user_id"], "status": "active"}
    total = db.products.count_documents(query)
    products = list(db.products.find(query).sort("created_at", -1)
                    .skip((page - 1) * limit).limit(limit))
    from ..products.routes import _enrich_products
    return ok({
        "products": _enrich_products(products),
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


# ---------- Seller earnings ----------

@bp.get("/me/earnings")
@auth_required
def my_earnings():
    user = get_current_user()
    if user["role"] != "seller":
        return fail("Only sellers can view earnings", "FORBIDDEN", 403)
    db = get_db()
    seller = db.sellers.find_one({"user_id": user["_id"]})
    if not seller:
        return not_found("Seller profile not found")

    commissions = list(db.commissions.find({"seller_id": user["_id"]}))
    total_sales = sum(c.get("sale_amount", 0) for c in commissions)
    total_commission = sum(c.get("commission_amount", 0) for c in commissions)
    total_earnings = sum(c.get("seller_earning", 0) for c in commissions)
    pending = sum(c.get("seller_earning", 0) for c in commissions if c.get("status") == "pending")

    return ok({
        "earnings": {
            "total_sales": round(total_sales, 2),
            "total_commission": round(total_commission, 2),
            "total_earnings": round(total_earnings, 2),
            "pending_earnings": round(pending, 2),
            "commission_count": len(commissions),
        }
    })
