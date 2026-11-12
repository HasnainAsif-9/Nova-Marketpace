from flask import Blueprint, request

from ..extensions import get_db
from ..utils.responses import ok, fail, not_found
from ..utils.helpers import serialize, clean_str
from ..utils.decorators import auth_required, get_current_user, validate_phone
from ..utils.audit import audit_log

bp = Blueprint("users", __name__, url_prefix="/api/users")


@bp.get("/me")
@auth_required
def get_me():
    user = get_current_user()
    data = serialize(user)
    data.pop("password_hash", None)
    return ok({"user": data})


@bp.put("/me")
@auth_required
def update_me():
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    update = {}
    for field, max_len in (("full_name", 120), ("phone", 20)):
        if field in data:
            val = clean_str(data[field], max_len)
            if field == "phone" and val and not validate_phone(val):
                return fail("Invalid phone number", "VALIDATION", 400)
            update[field] = val
    if update:
        from datetime import datetime, timezone
        update["updated_at"] = datetime.now(timezone.utc)
        get_db().users.update_one({"_id": user["_id"]}, {"$set": update})
        audit_log("user.profile_update", actor_id=user["_id"], actor_role=user["role"],
                  target_type="user", target_id=str(user["_id"]),
                  details={"fields": list(update.keys())}, ip=request.remote_addr)
    fresh = get_db().users.find_one({"_id": user["_id"]})
    fresh = serialize(fresh)
    fresh.pop("password_hash", None)
    return ok({"user": fresh}, "Profile updated")
