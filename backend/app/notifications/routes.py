from flask import Blueprint, request
from datetime import datetime, timezone

from ..extensions import get_db
from ..utils.responses import ok, not_found
from ..utils.helpers import serialize_list, to_object_id, clamp_int
from ..utils.decorators import auth_required, get_current_user

bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@bp.get("")
@auth_required
def list_notifications():
    user = get_current_user()
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 20, 1, 50)
    unread_only = request.args.get("unread") in ("1", "true")

    query = {"user_id": user["_id"]}
    if unread_only:
        query["read"] = False

    total = db.notifications.count_documents(query)
    unread_count = db.notifications.count_documents({"user_id": user["_id"], "read": False})
    notes = list(db.notifications.find(query).sort("created_at", -1)
                 .skip((page - 1) * limit).limit(limit))

    return ok({
        "notifications": serialize_list(notes),
        "unread_count": unread_count,
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


@bp.post("/<notification_id>/read")
@auth_required
def mark_read(notification_id):
    user = get_current_user()
    nid = to_object_id(notification_id)
    if not nid:
        return not_found("Notification not found")
    get_db().notifications.update_one(
        {"_id": nid, "user_id": user["_id"]},
        {"$set": {"read": True}})
    return ok(message="Marked as read")


@bp.post("/read-all")
@auth_required
def mark_all_read():
    user = get_current_user()
    get_db().notifications.update_many(
        {"user_id": user["_id"], "read": False},
        {"$set": {"read": True}})
    return ok(message="All notifications marked as read")
