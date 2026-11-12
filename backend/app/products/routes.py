from flask import Blueprint, request

from ..extensions import get_db
from ..utils.responses import ok, not_found, fail
from ..utils.helpers import (
    serialize, serialize_list, to_object_id, slugify, unique_slug, clean_str,
    clamp_int, clamp_float,
)
from ..utils.decorators import role_required, get_current_user, auth_required
from ..utils.audit import audit_log

bp = Blueprint("products", __name__, url_prefix="/api/products")

PUBLIC_FIELDS = {
    "name", "slug", "sku", "description", "short_description", "price",
    "compare_price", "stock", "images", "category_id", "brand", "tags",
    "specifications", "status", "seller_id", "rating_avg", "rating_count",
    "sold_count", "created_at", "updated_at",
}


def _public_product(p):
    data = serialize(p)
    data.pop("password_hash", None)
    return data


def _enrich_products(products):
    """Attach seller store info and category names without N+1 where possible."""
    db = get_db()
    seller_ids = {p.get("seller_id") for p in products if p.get("seller_id")}
    cat_ids = {p.get("category_id") for p in products if p.get("category_id")}
    sellers = {s["user_id"]: s for s in db.sellers.find({"user_id": {"$in": list(seller_ids)}})} if seller_ids else {}
    cats = {c["_id"]: c for c in db.categories.find({"_id": {"$in": list(cat_ids)}})} if cat_ids else {}
    out = []
    for p in products:
        d = _public_product(p)
        seller = sellers.get(p.get("seller_id"))
        if seller:
            d["store"] = {"id": str(seller["_id"]), "name": seller.get("store_name"),
                         "slug": seller.get("store_slug")}
        cat = cats.get(p.get("category_id"))
        if cat:
            d["category_name"] = cat.get("name")
        out.append(d)
    return out


@bp.get("")
def list_products():
    db = get_db()
    args = request.args
    page = clamp_int(args.get("page"), 1, 1, 10000)
    limit = clamp_int(args.get("limit"), 20, 1, 60)
    skip = (page - 1) * limit

    query = {"status": "active"}

    q = clean_str(args.get("q"), 100)
    if q:
        import re as _re
        safe = _re.escape(q)
        query["$or"] = [
            {"name": {"$regex": safe, "$options": "i"}},
            {"brand": {"$regex": safe, "$options": "i"}},
            {"description": {"$regex": safe, "$options": "i"}},
        ]

    category_id = to_object_id(args.get("category_id"))
    if category_id:
        query["category_id"] = category_id

    seller_id = to_object_id(args.get("seller_id"))
    if seller_id:
        query["seller_id"] = seller_id

    brand = clean_str(args.get("brand"), 100)
    if brand:
        query["brand"] = brand

    min_price = clamp_float(args.get("min_price"), None, 0, 10_000_000)
    max_price = clamp_float(args.get("max_price"), None, 0, 10_000_000)
    if min_price is not None or max_price is not None:
        price_q = {}
        if min_price is not None:
            price_q["$gte"] = min_price
        if max_price is not None:
            price_q["$lte"] = max_price
        query["price"] = price_q

    min_rating = clamp_float(args.get("min_rating"), 0, 0, 5)
    if min_rating > 0:
        query["rating_avg"] = {"$gte": min_rating}

    in_stock = args.get("in_stock")
    if in_stock in ("1", "true"):
        query["stock"] = {"$gt": 0}

    on_sale = args.get("on_sale")
    if on_sale in ("1", "true"):
        query["compare_price"] = {"$gt": 0}
        query["$expr"] = {"$lt": ["$price", "$compare_price"]}

    sort = args.get("sort", "newest")
    sort_map = {
        "newest": [("created_at", -1)],
        "price_asc": [("price", 1)],
        "price_desc": [("price", -1)],
        "rating": [("rating_avg", -1), ("rating_count", -1)],
        "popular": [("sold_count", -1)],
    }
    sort_spec = sort_map.get(sort, sort_map["newest"])

    total = db.products.count_documents(query)
    cursor = db.products.find(query).sort(sort_spec).skip(skip).limit(limit)
    products = list(cursor)

    return ok({
        "products": _enrich_products(products),
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


@bp.get("/featured")
def featured():
    db = get_db()
    products = list(db.products.find({"status": "active"})
                    .sort("sold_count", -1).limit(12))
    return ok({"products": _enrich_products(products)})


@bp.get("/new-arrivals")
def new_arrivals():
    db = get_db()
    products = list(db.products.find({"status": "active"})
                    .sort("created_at", -1).limit(12))
    return ok({"products": _enrich_products(products)})


@bp.get("/<product_id>")
def get_product(product_id):
    db = get_db()
    oid = to_object_id(product_id)
    product = None
    if oid:
        product = db.products.find_one({"_id": oid, "status": "active"})
    if not product:
        product = db.products.find_one({"slug": product_id, "status": "active"})
    if not product:
        return not_found("Product not found")

    data = _enrich_products([product])[0]

    reviews = list(db.reviews.find({"product_id": product["_id"], "status": "approved"})
                   .sort("created_at", -1).limit(10))
    data["recent_reviews"] = serialize_list(reviews)

    related = list(db.products.find({
        "category_id": product.get("category_id"),
        "status": "active",
        "_id": {"$ne": product["_id"]},
    }).limit(8))
    data["related_products"] = _enrich_products(related)

    return ok({"product": data})


# ---------- Seller product management ----------

def _get_seller_for_user(user):
    return get_db().sellers.find_one({"user_id": user["_id"]})


def _can_manage_product(user, product):
    if user["role"] == "admin":
        return True
    if user["role"] == "seller":
        seller = _get_seller_for_user(user)
        return seller and product.get("seller_id") == seller["user_id"]
    return False


@bp.post("")
@role_required("seller", "admin")
def create_product():
    user = get_current_user()
    db = get_db()

    seller = _get_seller_for_user(user)
    if user["role"] == "seller":
        if not seller:
            return fail("Seller profile not found", "NOT_FOUND", 404)
        if seller.get("status") != "approved":
            return fail("Your seller account is not approved yet", "SELLER_NOT_APPROVED", 403)
        seller_user_id = seller["user_id"]
    else:
        # Admin must specify seller
        seller_user_id = to_object_id(request.get_json(silent=True).get("seller_id"))
        if not seller_user_id:
            return fail("seller_id is required", "VALIDATION", 400)

    data = request.get_json(silent=True) or {}
    name = clean_str(data.get("name"), 200)
    price = clamp_float(data.get("price"), None, 0, 10_000_000)
    stock = clamp_int(data.get("stock"), 0, 0, 1_000_000)
    category_id = to_object_id(data.get("category_id"))

    if not name:
        return fail("Product name is required", "VALIDATION", 400)
    if price is None or price <= 0:
        return fail("A valid price greater than 0 is required", "VALIDATION", 400)
    if not category_id or not db.categories.find_one({"_id": category_id}):
        return fail("A valid category is required", "VALIDATION", 400)

    compare_price = clamp_float(data.get("compare_price"), 0, 0, 10_000_000)
    if compare_price and compare_price <= price:
        compare_price = 0

    images = data.get("images") or []
    if not isinstance(images, list):
        images = []
    images = [clean_str(i, 500) for i in images[:10] if clean_str(i, 500)]
    if not images:
        images = ["/assets/images/placeholder.svg"]

    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [clean_str(t, 50) for t in tags[:20] if clean_str(t, 50)]

    specs = data.get("specifications") or {}
    if not isinstance(specs, dict):
        specs = {}
    specs = {clean_str(k, 60): clean_str(v, 300) for k, v in list(specs.items())[:30]}

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    slug = unique_slug(db.products, slugify(data.get("slug") or name))
    sku = clean_str(data.get("sku"), 60)
    if sku and db.products.find_one({"sku": sku}):
        return fail("SKU already exists", "SKU_TAKEN", 409)
    if not sku:
        sku = f"SKU-{slug[:40].upper().replace('-', '')}-{int(now.timestamp()) % 100000}"

    status = "active"
    if current_app_require_approval():
        status = "pending"

    doc = {
        "name": name,
        "slug": slug,
        "sku": sku,
        "description": clean_str(data.get("description"), 10000),
        "short_description": clean_str(data.get("short_description"), 500),
        "price": price,
        "compare_price": compare_price,
        "stock": stock,
        "images": images,
        "category_id": category_id,
        "brand": clean_str(data.get("brand"), 100),
        "tags": tags,
        "specifications": specs,
        "status": status,
        "seller_id": seller_user_id,
        "rating_avg": 0,
        "rating_count": 0,
        "sold_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    result = db.products.insert_one(doc)
    doc["_id"] = result.inserted_id

    audit_log("product.create", actor_id=user["_id"], actor_role=user["role"],
              target_type="product", target_id=str(result.inserted_id),
              details={"name": name, "price": price}, ip=request.remote_addr)
    return ok({"product": _public_product(doc)}, "Product created", 201)


def current_app_require_approval():
    from flask import current_app
    return current_app.config.get("REQUIRE_PRODUCT_APPROVAL", False)


@bp.get("/seller/mine")
@role_required("seller", "admin")
def my_products():
    user = get_current_user()
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 20, 1, 100)
    status = clean_str(request.args.get("status"), 20)

    query = {}
    if user["role"] == "seller":
        seller = _get_seller_for_user(user)
        if not seller:
            return ok({"products": [], "pagination": {"page": 1, "limit": limit, "total": 0, "pages": 0}})
        query["seller_id"] = seller["user_id"]
    if status:
        query["status"] = status

    total = db.products.count_documents(query)
    products = list(db.products.find(query).sort("created_at", -1)
                    .skip((page - 1) * limit).limit(limit))
    return ok({
        "products": _enrich_products(products),
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


@bp.put("/<product_id>")
@role_required("seller", "admin")
def update_product(product_id):
    user = get_current_user()
    db = get_db()
    oid = to_object_id(product_id)
    product = db.products.find_one({"_id": oid}) if oid else db.products.find_one({"slug": product_id})
    if not product:
        return not_found("Product not found")
    if not _can_manage_product(user, product):
        from ..utils.responses import forbidden
        return forbidden()

    data = request.get_json(silent=True) or {}
    update = {}
    for field, max_len in (("name", 200), ("description", 10000),
                           ("short_description", 500), ("brand", 100)):
        if field in data:
            val = clean_str(data[field], max_len)
            if field == "name" and not val:
                return fail("Name cannot be empty", "VALIDATION", 400)
            update[field] = val

    if "price" in data:
        price = clamp_float(data["price"], None, 0, 10_000_000)
        if price is None or price <= 0:
            return fail("Price must be greater than 0", "VALIDATION", 400)
        update["price"] = price
    if "compare_price" in data:
        cp = clamp_float(data["compare_price"], 0, 0, 10_000_000)
        update["compare_price"] = cp if cp and cp > update.get("price", product["price"]) else 0
    if "stock" in data:
        update["stock"] = clamp_int(data["stock"], 0, 0, 1_000_000)
    if "category_id" in data:
        cid = to_object_id(data["category_id"])
        if not cid or not db.categories.find_one({"_id": cid}):
            return fail("Invalid category", "VALIDATION", 400)
        update["category_id"] = cid
    if "images" in data and isinstance(data["images"], list):
        update["images"] = [clean_str(i, 500) for i in data["images"][:10] if clean_str(i, 500)]
    if "tags" in data and isinstance(data["tags"], list):
        update["tags"] = [clean_str(t, 50) for t in data["tags"][:20] if clean_str(t, 50)]
    if "specifications" in data and isinstance(data["specifications"], dict):
        update["specifications"] = {clean_str(k, 60): clean_str(v, 300)
                                    for k, v in list(data["specifications"].items())[:30]}
    if "sku" in data:
        sku = clean_str(data["sku"], 60)
        if sku:
            dup = db.products.find_one({"sku": sku, "_id": {"$ne": product["_id"]}})
            if dup:
                return fail("SKU already exists", "SKU_TAKEN", 409)
        update["sku"] = sku

    if update:
        from datetime import datetime, timezone
        update["updated_at"] = datetime.now(timezone.utc)
        db.products.update_one({"_id": product["_id"]}, {"$set": update})

    audit_log("product.update", actor_id=user["_id"], actor_role=user["role"],
              target_type="product", target_id=str(product["_id"]),
              details={"fields": list(update.keys())}, ip=request.remote_addr)
    fresh = db.products.find_one({"_id": product["_id"]})
    return ok({"product": _public_product(fresh)}, "Product updated")


@bp.delete("/<product_id>")
@role_required("seller", "admin")
def delete_product(product_id):
    user = get_current_user()
    db = get_db()
    oid = to_object_id(product_id)
    product = db.products.find_one({"_id": oid}) if oid else db.products.find_one({"slug": product_id})
    if not product:
        return not_found("Product not found")
    if not _can_manage_product(user, product):
        from ..utils.responses import forbidden
        return forbidden()
    # Soft delete to preserve order history
    from datetime import datetime, timezone
    db.products.update_one({"_id": product["_id"]},
                           {"$set": {"status": "inactive", "updated_at": datetime.now(timezone.utc)}})
    audit_log("product.deactivate", actor_id=user["_id"], actor_role=user["role"],
              target_type="product", target_id=str(product["_id"]), ip=request.remote_addr)
    return ok(message="Product deactivated")


@bp.post("/<product_id>/stock")
@role_required("seller", "admin")
def adjust_stock(product_id):
    user = get_current_user()
    db = get_db()
    oid = to_object_id(product_id)
    product = db.products.find_one({"_id": oid}) if oid else None
    if not product:
        return not_found("Product not found")
    if not _can_manage_product(user, product):
        from ..utils.responses import forbidden
        return forbidden()

    data = request.get_json(silent=True) or {}
    try:
        delta = int(data.get("delta", 0) or 0)
    except (TypeError, ValueError):
        return fail("delta must be an integer", "VALIDATION", 400)
    if delta == 0:
        return fail("delta must be non-zero", "VALIDATION", 400)
    new_stock = max(0, product.get("stock", 0) + delta)
    from datetime import datetime, timezone
    db.products.update_one({"_id": product["_id"]},
                           {"$set": {"stock": new_stock, "updated_at": datetime.now(timezone.utc)}})
    return ok({"stock": new_stock}, "Stock updated")
