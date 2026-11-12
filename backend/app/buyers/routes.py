from flask import Blueprint, request

from ..extensions import get_db
from ..utils.responses import ok, fail, not_found
from ..utils.helpers import serialize, serialize_list, to_object_id, clean_str
from ..utils.decorators import auth_required, get_current_user
from ..utils.audit import audit_log

bp = Blueprint("buyers", __name__, url_prefix="/api/buyers")


@bp.get("/addresses")
@auth_required
def list_addresses():
    user = get_current_user()
    addrs = list(get_db().addresses.find({"user_id": user["_id"]}).sort("is_default", -1))
    return ok({"addresses": serialize_list(addrs)})


@bp.post("/addresses")
@auth_required
def create_address():
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    label = clean_str(data.get("label"), 50) or "Home"
    recipient = clean_str(data.get("recipient_name"), 120)
    phone = clean_str(data.get("phone"), 20)
    address_line1 = clean_str(data.get("address_line1"), 200)
    city = clean_str(data.get("city"), 100)

    if not all([recipient, phone, address_line1, city]):
        return fail("recipient_name, phone, address_line1 and city are required",
                    "VALIDATION", 400)

    db = get_db()
    is_default = bool(data.get("is_default", False))
    if is_default:
        db.addresses.update_many({"user_id": user["_id"]}, {"$set": {"is_default": False}})
    elif db.addresses.count_documents({"user_id": user["_id"]}) == 0:
        is_default = True

    from datetime import datetime, timezone
    doc = {
        "user_id": user["_id"],
        "label": label,
        "recipient_name": recipient,
        "phone": phone,
        "address_line1": address_line1,
        "address_line2": clean_str(data.get("address_line2"), 200),
        "city": city,
        "state": clean_str(data.get("state"), 100),
        "postal_code": clean_str(data.get("postal_code"), 20),
        "country": clean_str(data.get("country"), 100) or "Pakistan",
        "is_default": is_default,
        "created_at": datetime.now(timezone.utc),
    }
    result = db.addresses.insert_one(doc)
    doc["_id"] = result.inserted_id
    return ok({"address": serialize(doc)}, "Address added", 201)


@bp.put("/addresses/<address_id>")
@auth_required
def update_address(address_id):
    user = get_current_user()
    oid = to_object_id(address_id)
    if not oid:
        return not_found("Address not found")
    db = get_db()
    addr = db.addresses.find_one({"_id": oid, "user_id": user["_id"]})
    if not addr:
        return not_found("Address not found")

    data = request.get_json(silent=True) or {}
    allowed = ["label", "recipient_name", "phone", "address_line1", "address_line2",
               "city", "state", "postal_code", "country"]
    update = {k: clean_str(data[k], 200) for k in allowed if k in data}
    if "is_default" in data and data["is_default"]:
        db.addresses.update_many({"user_id": user["_id"], "_id": {"$ne": oid}},
                                 {"$set": {"is_default": False}})
        update["is_default"] = True
    if update:
        db.addresses.update_one({"_id": oid}, {"$set": update})
    return ok({"address": serialize(db.addresses.find_one({"_id": oid}))}, "Address updated")


@bp.delete("/addresses/<address_id>")
@auth_required
def delete_address(address_id):
    user = get_current_user()
    oid = to_object_id(address_id)
    if not oid:
        return not_found("Address not found")
    result = get_db().addresses.delete_one({"_id": oid, "user_id": user["_id"]})
    if result.deleted_count == 0:
        return not_found("Address not found")
    return ok(message="Address deleted")
