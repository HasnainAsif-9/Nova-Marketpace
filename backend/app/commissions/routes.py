from flask import Blueprint, request

from ..extensions import get_db
from ..utils.responses import ok
from ..utils.helpers import serialize_list, clamp_int, clean_str
from ..utils.decorators import auth_required, role_required, get_current_user

bp = Blueprint("commissions", __name__, url_prefix="/api/commissions")


@bp.get("/mine")
@auth_required
def my_commissions():
    """Seller's own commission records."""
    user = get_current_user()
    if user["role"] != "seller":
        return ok({"commissions": [], "summary": {}})
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 20, 1, 100)

    query = {"seller_id": user["_id"]}
    total = db.commissions.count_documents(query)
    comms = list(db.commissions.find(query).sort("created_at", -1)
                 .skip((page - 1) * limit).limit(limit))

    pipeline = [
        {"$match": {"seller_id": user["_id"], "status": {"$ne": "cancelled"}}},
        {"$group": {"_id": None,
                    "total_sales": {"$sum": "$sale_amount"},
                    "total_commission": {"$sum": "$commission_amount"},
                    "total_earnings": {"$sum": "$seller_earning"},
                    "count": {"$sum": 1}}},
    ]
    agg = list(db.commissions.aggregate(pipeline))
    summary = agg[0] if agg else {}
    summary.pop("_id", None)

    return ok({
        "commissions": serialize_list(comms),
        "summary": {k: round(v, 2) if isinstance(v, float) else v
                    for k, v in summary.items()},
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })
