from flask import Blueprint, request
from datetime import datetime, timezone

from ..extensions import get_db
from ..utils.responses import ok, fail, not_found, forbidden
from ..utils.helpers import serialize, serialize_list, to_object_id, clamp_int, clean_str
from ..utils.decorators import auth_required, role_required, get_current_user
from ..utils.audit import audit_log

bp = Blueprint("reviews", __name__, url_prefix="/api/reviews")


def _can_review(user_id, product_id):
    """Buyer can review only if they have a delivered order containing the product."""
    db = get_db()
    sub = db.order_items.find_one({
        "buyer_id": user_id,
        "status": "delivered",
        "items.product_id": product_id,
    })
    return sub is not None


@bp.get("/product/<product_id>")
def product_reviews(product_id):
    db = get_db()
    pid = to_object_id(product_id)
    if not pid:
        return not_found("Product not found")
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 10, 1, 50)

    query = {"product_id": pid, "status": "approved"}
    total = db.reviews.count_documents(query)
    reviews = list(db.reviews.find(query).sort("created_at", -1)
                   .skip((page - 1) * limit).limit(limit))

    # Attach reviewer names
    user_ids = [r["user_id"] for r in reviews]
    users = {u["_id"]: u for u in db.users.find({"_id": {"$in": user_ids}})}
    out = []
    for r in reviews:
        d = serialize(r)
        u = users.get(r["user_id"])
        d["reviewer_name"] = (u.get("full_name") or u.get("username")) if u else "Customer"
        out.append(d)

    return ok({
        "reviews": out,
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


@bp.post("")
@auth_required
def create_review():
    user = get_current_user()
    if user["role"] != "buyer":
        return forbidden("Only buyers can review products")

    data = request.get_json(silent=True) or {}
    product_id = to_object_id(data.get("product_id"))
    try:
        rating = int(data.get("rating", 0) or 0)
    except (TypeError, ValueError):
        rating = 0
    comment = clean_str(data.get("comment"), 2000)

    if not product_id:
        return fail("product_id is required", "VALIDATION", 400)
    if rating < 1 or rating > 5:
        return fail("Rating must be between 1 and 5", "VALIDATION", 400)

    db = get_db()
    product = db.products.find_one({"_id": product_id})
    if not product:
        return not_found("Product not found")

    if not _can_review(user["_id"], product_id):
        return fail("You can only review products from delivered orders",
                    "REVIEW_NOT_ELIGIBLE", 403)

    if db.reviews.find_one({"product_id": product_id, "user_id": user["_id"]}):
        return fail("You have already reviewed this product", "REVIEW_EXISTS", 409)

    now = datetime.now(timezone.utc)
    doc = {
        "product_id": product_id,
        "user_id": user["_id"],
        "seller_id": product.get("seller_id"),
        "rating": rating,
        "comment": comment,
        "status": "approved",
        "created_at": now,
        "updated_at": now,
    }
    result = db.reviews.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Recalculate product rating
    pipeline = [
        {"$match": {"product_id": product_id, "status": "approved"}},
        {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "count": {"$sum": 1}}},
    ]
    agg = list(db.reviews.aggregate(pipeline))
    if agg:
        db.products.update_one({"_id": product_id}, {"$set": {
            "rating_avg": round(agg[0]["avg"], 2), "rating_count": agg[0]["count"]}})

    return ok({"review": serialize(doc)}, "Review submitted", 201)


@bp.get("/mine")
@auth_required
def my_reviews():
    user = get_current_user()
    reviews = list(get_db().reviews.find({"user_id": user["_id"]})
                   .sort("created_at", -1).limit(100))
    # Attach product names
    pids = [r["product_id"] for r in reviews]
    products = {p["_id"]: p for p in get_db().products.find({"_id": {"$in": pids}})}
    out = []
    for r in reviews:
        d = serialize(r)
        p = products.get(r["product_id"])
        d["product_name"] = p.get("name") if p else "Unknown product"
        out.append(d)
    return ok({"reviews": out})


@bp.delete("/<review_id>")
@auth_required
def delete_review(review_id):
    user = get_current_user()
    db = get_db()
    rid = to_object_id(review_id)
    if not rid:
        return not_found("Review not found")
    review = db.reviews.find_one({"_id": rid})
    if not review:
        return not_found("Review not found")
    if review["user_id"] != user["_id"] and user["role"] != "admin":
        return forbidden()
    db.reviews.delete_one({"_id": rid})
    return ok(message="Review deleted")


# ---------- Admin moderation ----------

@bp.get("/admin/all")
@role_required("admin")
def admin_all_reviews():
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 20, 1, 100)
    status = clean_str(request.args.get("status"), 20)
    query = {}
    if status:
        query["status"] = status
    total = db.reviews.count_documents(query)
    reviews = list(db.reviews.find(query).sort("created_at", -1)
                   .skip((page - 1) * limit).limit(limit))
    return ok({
        "reviews": serialize_list(reviews),
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


@bp.put("/admin/<review_id>/status")
@role_required("admin")
def moderate_review(review_id):
    user = get_current_user()
    db = get_db()
    rid = to_object_id(review_id)
    if not rid:
        return not_found("Review not found")
    data = request.get_json(silent=True) or {}
    status = clean_str(data.get("status"), 20)
    if status not in ("approved", "rejected", "hidden"):
        return fail("Invalid status", "VALIDATION", 400)
    review = db.reviews.find_one({"_id": rid})
    if not review:
        return not_found("Review not found")
    db.reviews.update_one({"_id": rid},
                          {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}})
    audit_log("review.moderate", actor_id=user["_id"], actor_role="admin",
              target_type="review", target_id=str(rid),
              details={"status": status}, ip=request.remote_addr)
    return ok({"review": serialize(db.reviews.find_one({"_id": rid}))}, "Review updated")
