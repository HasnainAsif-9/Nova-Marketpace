from flask import Blueprint, request
from datetime import datetime, timezone, timedelta

from ..extensions import get_db
from ..utils.responses import ok
from ..utils.helpers import clamp_int
from ..utils.decorators import role_required

bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@bp.get("/sales")
@role_required("admin")
def sales_report():
    db = get_db()
    days = clamp_int(request.args.get("days"), 30, 1, 365)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m", "date": "$created_at"}},
                    "orders": {"$sum": 1}, "revenue": {"$sum": "$total"}}},
        {"$sort": {"_id": 1}},
    ]
    monthly = list(db.orders.aggregate(pipeline))

    status_pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    by_status = list(db.orders.aggregate(status_pipeline))

    return ok({"monthly": monthly, "by_status": by_status, "days": days})


@bp.get("/inventory")
@role_required("admin", "seller")
def inventory_report():
    from ..utils.decorators import get_current_user
    user = get_current_user()
    db = get_db()
    query = {}
    if user["role"] == "seller":
        query["seller_id"] = user["_id"]

    pipeline = [
        {"$match": query},
        {"$group": {"_id": None,
                    "total_products": {"$sum": 1},
                    "total_stock": {"$sum": "$stock"},
                    "low_stock": {"$sum": {"$cond": [{"$lte": ["$stock", 5]}, 1, 0]}},
                    "out_of_stock": {"$sum": {"$cond": [{"$eq": ["$stock", 0]}, 1, 0]}}}},
    ]
    agg = list(db.products.aggregate(pipeline))
    summary = agg[0] if agg else {}
    summary.pop("_id", None)

    low = list(db.products.find({**query, "stock": {"$lte": 5}})
               .sort("stock", 1).limit(20))
    from ..utils.helpers import serialize_list
    return ok({"summary": summary, "low_stock_products": serialize_list(low)})
