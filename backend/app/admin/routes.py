from flask import Blueprint, request, current_app
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from ..extensions import get_db
from ..utils.responses import ok, fail, not_found, forbidden
from ..utils.helpers import serialize, serialize_list, to_object_id, clamp_int, clean_str
from ..utils.decorators import role_required, get_current_user
from ..utils.audit import audit_log

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _notify(user_id, ntype, title, message, data=None):
    get_db().notifications.insert_one({
        "user_id": user_id, "type": ntype, "title": title, "message": message,
        "data": data or {}, "read": False,
        "created_at": datetime.now(timezone.utc),
    })


# ---------- Dashboard stats ----------

@bp.get("/stats")
@role_required("admin")
def stats():
    db = get_db()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)

    total_buyers = db.users.count_documents({"role": "buyer"})
    total_sellers = db.users.count_documents({"role": "seller"})
    pending_sellers = db.sellers.count_documents({"status": "pending"})
    total_products = db.products.count_documents({})
    active_products = db.products.count_documents({"status": "active"})
    pending_products = db.products.count_documents({"status": "pending"})

    total_orders = db.orders.count_documents({})
    orders_today = db.orders.count_documents({"created_at": {"$gte": today_start}})
    pending_orders = db.orders.count_documents({"status": {"pending"}})
    delivered_orders = db.orders.count_documents({"status": "delivered"})
    cancelled_orders = db.orders.count_documents({"status": "cancelled"})

    # Revenue: sum of delivered/confirmed order totals (all non-cancelled)
    pipeline = [
        {"$match": {"status": {"$in": ["confirmed", "processing", "shipped",
                                       "out_for_delivery", "delivered"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}},
    ]
    rev = list(db.orders.aggregate(pipeline))
    total_revenue = rev[0]["total"] if rev else 0

    comm_pipeline = [
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$group": {"_id": None,
                    "commission": {"$sum": "$commission_amount"},
                    "earnings": {"$sum": "$seller_earning"}}},
    ]
    comm = list(db.commissions.aggregate(comm_pipeline))
    total_commission = comm[0]["commission"] if comm else 0
    total_seller_earnings = comm[0]["earnings"] if comm else 0

    # Recent orders
    recent = list(db.orders.find().sort("created_at", -1).limit(10))

    return ok({"stats": {
        "total_buyers": total_buyers,
        "total_sellers": total_sellers,
        "pending_sellers": pending_sellers,
        "total_products": total_products,
        "active_products": active_products,
        "pending_products": pending_products,
        "total_orders": total_orders,
        "orders_today": orders_today,
        "pending_orders": pending_orders,
        "delivered_orders": delivered_orders,
        "cancelled_orders": cancelled_orders,
        "total_revenue": round(total_revenue, 2),
        "total_commission": round(total_commission, 2),
        "total_seller_earnings": round(total_seller_earnings, 2),
        "recent_orders": serialize_list(recent),
    }})


# ---------- Users ----------

@bp.get("/users")
@role_required("admin")
def list_users():
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 20, 1, 100)
    role = clean_str(request.args.get("role"), 20)
    status = clean_str(request.args.get("status"), 20)
    q = clean_str(request.args.get("q"), 100)

    query = {}
    if role in ("buyer", "seller", "admin"):
        query["role"] = role
    if status in ("active", "suspended", "pending"):
        query["status"] = status
    if q:
        import re as _re
        safe = _re.escape(q)
        query["$or"] = [
            {"username": {"$regex": safe, "$options": "i"}},
            {"email": {"$regex": safe, "$options": "i"}},
            {"full_name": {"$regex": safe, "$options": "i"}},
        ]

    total = db.users.count_documents(query)
    users = list(db.users.find(query).sort("created_at", -1)
                 .skip((page - 1) * limit).limit(limit))
    out = []
    for u in users:
        d = serialize(u)
        d.pop("password_hash", None)
        out.append(d)
    return ok({
        "users": out,
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


@bp.put("/users/<user_id>/status")
@role_required("admin")
def set_user_status(user_id):
    admin = get_current_user()
    db = get_db()
    uid = to_object_id(user_id)
    if not uid:
        return not_found("User not found")
    target = db.users.find_one({"_id": uid})
    if not target:
        return not_found("User not found")
    if target["role"] == "admin":
        return fail("Cannot modify admin accounts", "FORBIDDEN", 403)

    data = request.get_json(silent=True) or {}
    status = clean_str(data.get("status"), 20)
    if status not in ("active", "suspended"):
        return fail("Invalid status", "VALIDATION", 400)

    db.users.update_one({"_id": uid},
                        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}})
    audit_log("admin.user_status", actor_id=admin["_id"], actor_role="admin",
              target_type="user", target_id=str(uid),
              details={"status": status, "username": target.get("username")},
              ip=request.remote_addr)
    _notify(uid, "account_status", "Account status updated",
            f"Your account has been {status}.", {})
    return ok(message=f"User {status}")


# ---------- Sellers ----------

@bp.get("/sellers")
@role_required("admin")
def list_sellers_admin():
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 20, 1, 100)
    status = clean_str(request.args.get("status"), 20)
    query = {}
    if status in ("pending", "approved", "rejected", "suspended"):
        query["status"] = status
    total = db.sellers.count_documents(query)
    sellers = list(db.sellers.find(query).sort("created_at", -1)
                   .skip((page - 1) * limit).limit(limit))
    # Attach owner info
    user_ids = [s["user_id"] for s in sellers]
    users = {u["_id"]: u for u in db.users.find({"_id": {"$in": user_ids}})}
    out = []
    for s in sellers:
        d = serialize(s)
        u = users.get(s["user_id"])
        if u:
            d["owner"] = {"username": u.get("username"), "email": u.get("email"),
                          "full_name": u.get("full_name")}
        # product count
        d["product_count"] = db.products.count_documents({"seller_id": s["user_id"]})
        out.append(d)
    return ok({
        "sellers": out,
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


@bp.put("/sellers/<seller_id>/status")
@role_required("admin")
def set_seller_status(seller_id):
    admin = get_current_user()
    db = get_db()
    sid = to_object_id(seller_id)
    if not sid:
        return not_found("Seller not found")
    seller = db.sellers.find_one({"_id": sid})
    if not seller:
        return not_found("Seller not found")

    data = request.get_json(silent=True) or {}
    status = clean_str(data.get("status"), 20)
    reason = clean_str(data.get("reason"), 500)
    if status not in ("approved", "rejected", "suspended", "pending"):
        return fail("Invalid status", "VALIDATION", 400)

    db.sellers.update_one({"_id": sid},
                          {"$set": {"status": status, "status_reason": reason,
                                    "updated_at": datetime.now(timezone.utc)}})

    # If suspended/rejected, deactivate their products
    if status in ("suspended", "rejected"):
        db.products.update_many({"seller_id": seller["user_id"]},
                                {"$set": {"status": "inactive"}})
    elif status == "approved":
        # Reactivate products that were pending/active before
        db.products.update_many(
            {"seller_id": seller["user_id"], "status": "inactive"},
            {"$set": {"status": "active"}})

    audit_log(f"admin.seller_{status}", actor_id=admin["_id"], actor_role="admin",
              target_type="seller", target_id=str(sid),
              details={"reason": reason}, ip=request.remote_addr)

    titles = {"approved": "Seller account approved",
              "rejected": "Seller application rejected",
              "suspended": "Seller account suspended",
              "pending": "Seller account pending review"}
    _notify(seller["user_id"], f"seller_{status}", titles.get(status, "Seller status updated"),
            f"Your seller account '{seller.get('store_name')}' is now {status}."
            + (f" Reason: {reason}" if reason else ""), {})
    return ok(message=f"Seller {status}")


# ---------- Products moderation ----------

@bp.get("/products")
@role_required("admin")
def admin_products():
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 20, 1, 100)
    status = clean_str(request.args.get("status"), 20)
    q = clean_str(request.args.get("q"), 100)
    query = {}
    if status:
        query["status"] = status
    if q:
        import re as _re
        safe = _re.escape(q)
        query["$or"] = [
            {"name": {"$regex": safe, "$options": "i"}},
            {"sku": {"$regex": safe, "$options": "i"}},
        ]
    total = db.products.count_documents(query)
    products = list(db.products.find(query).sort("created_at", -1)
                    .skip((page - 1) * limit).limit(limit))
    # seller names
    seller_ids = [p["seller_id"] for p in products]
    sellers = {s["user_id"]: s for s in db.sellers.find({"user_id": {"$in": seller_ids}})}
    out = []
    for p in products:
        d = serialize(p)
        s = sellers.get(p.get("seller_id"))
        d["store_name"] = s.get("store_name") if s else None
        out.append(d)
    return ok({
        "products": out,
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


@bp.put("/products/<product_id>/status")
@role_required("admin")
def set_product_status(product_id):
    admin = get_current_user()
    db = get_db()
    pid = to_object_id(product_id)
    if not pid:
        return not_found("Product not found")
    product = db.products.find_one({"_id": pid})
    if not product:
        return not_found("Product not found")
    data = request.get_json(silent=True) or {}
    status = clean_str(data.get("status"), 20)
    valid = ("draft", "pending", "approved", "rejected", "active", "inactive", "out_of_stock")
    if status not in valid:
        return fail("Invalid status", "VALIDATION", 400)
    db.products.update_one({"_id": pid},
                           {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}})
    audit_log("admin.product_status", actor_id=admin["_id"], actor_role="admin",
              target_type="product", target_id=str(pid),
              details={"status": status, "name": product.get("name")}, ip=request.remote_addr)
    return ok(message=f"Product {status}")


# ---------- Commissions ----------

@bp.get("/commissions")
@role_required("admin")
def list_commissions():
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 20, 1, 100)
    status = clean_str(request.args.get("status"), 20)
    query = {}
    if status:
        query["status"] = status
    total = db.commissions.count_documents(query)
    comms = list(db.commissions.find(query).sort("created_at", -1)
                 .skip((page - 1) * limit).limit(limit))
    # seller names
    seller_ids = [c["seller_id"] for c in comms]
    sellers = {s["user_id"]: s for s in db.sellers.find({"user_id": {"$in": seller_ids}})}
    out = []
    for c in comms:
        d = serialize(c)
        s = sellers.get(c["seller_id"])
        d["store_name"] = s.get("store_name") if s else None
        out.append(d)
    return ok({
        "commissions": out,
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


# ---------- Audit logs ----------

@bp.get("/audit-logs")
@role_required("admin")
def audit_logs():
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 50, 1, 200)
    action = clean_str(request.args.get("action"), 100)
    query = {}
    if action:
        import re as _re
        query["action"] = {"$regex": _re.escape(action), "$options": "i"}
    total = db.audit_logs.count_documents(query)
    logs = list(db.audit_logs.find(query).sort("created_at", -1)
                .skip((page - 1) * limit).limit(limit))
    return ok({
        "logs": serialize_list(logs),
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


# ---------- Analytics ----------

@bp.get("/analytics/sales")
@role_required("admin")
def sales_analytics():
    db = get_db()
    days = clamp_int(request.args.get("days"), 30, 7, 365)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    pipeline = [
        {"$match": {"created_at": {"$gte": since},
                    "status": {"$in": ["confirmed", "processing", "shipped",
                                       "out_for_delivery", "delivered"]}}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                    "revenue": {"$sum": "$total"}, "orders": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    daily = list(db.orders.aggregate(pipeline))

    # Top products
    top_pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.product_id",
                    "name": {"$first": "$items.product_name"},
                    "quantity": {"$sum": "$items.quantity"},
                    "revenue": {"$sum": "$items.line_total"}}},
        {"$sort": {"revenue": -1}},
        {"$limit": 10},
    ]
    top_products = list(db.order_items.aggregate(top_pipeline))
    for tp in top_products:
        tp["_id"] = str(tp["_id"])

    # Seller performance
    seller_pipeline = [
        {"$match": {"created_at": {"$gte": since}, "status": {"$ne": "cancelled"}}},
        {"$group": {"_id": "$seller_id",
                    "sales": {"$sum": "$sale_amount"},
                    "commission": {"$sum": "$commission_amount"},
                    "orders": {"$sum": 1}}},
        {"$sort": {"sales": -1}},
        {"$limit": 10},
    ]
    seller_perf = list(db.commissions.aggregate(seller_pipeline))
    seller_ids = [sp["_id"] for sp in seller_perf]
    sellers = {s["user_id"]: s for s in db.sellers.find({"user_id": {"$in": seller_ids}})}
    for sp in seller_perf:
        sp["_id"] = str(sp["_id"])
        s = sellers.get(sp["_id"])
        sp["store_name"] = s.get("store_name") if s else "Unknown"

    return ok({
        "daily_sales": daily,
        "top_products": top_products,
        "seller_performance": seller_perf,
    })
