from flask import Blueprint, request, current_app

from ..extensions import get_db
from ..utils.responses import ok, fail
from ..utils.helpers import serialize
from ..utils.decorators import role_required, get_current_user, auth_required
from ..utils.audit import audit_log

bp = Blueprint("settings", __name__, url_prefix="/api/settings")

PUBLIC_KEYS = ["marketplace_name", "currency", "currency_symbol",
               "commission_rate", "delivery_standard", "delivery_express",
               "free_delivery_threshold", "logo", "contact_email", "contact_phone",
               "maintenance_mode"]


@bp.get("")
def get_public_settings():
    db = get_db()
    doc = db.settings.find_one({"key": "marketplace"}) or {}
    data = {k: doc.get(k) for k in PUBLIC_KEYS}
    # Fallbacks from config (doc.get returns None for missing keys)
    data["marketplace_name"] = data.get("marketplace_name") or current_app.config["MARKETPLACE_NAME"]
    data["currency"] = data.get("currency") or current_app.config["CURRENCY"]
    data["currency_symbol"] = data.get("currency_symbol") or current_app.config["CURRENCY_SYMBOL"]
    data["commission_rate"] = data.get("commission_rate") if data.get("commission_rate") is not None else current_app.config["DEFAULT_COMMISSION_RATE"]
    data["delivery_standard"] = data.get("delivery_standard") if data.get("delivery_standard") is not None else current_app.config["DELIVERY_FEE_STANDARD"]
    data["delivery_express"] = data.get("delivery_express") if data.get("delivery_express") is not None else current_app.config["DELIVERY_FEE_EXPRESS"]
    data["free_delivery_threshold"] = data.get("free_delivery_threshold") if data.get("free_delivery_threshold") is not None else current_app.config["FREE_DELIVERY_THRESHOLD"]
    data["maintenance_mode"] = bool(data.get("maintenance_mode"))
    return ok({"settings": data})


@bp.put("")
@role_required("admin")
def update_settings():
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    db = get_db()

    allowed = {
        "marketplace_name": str, "currency": str, "currency_symbol": str,
        "commission_rate": float, "delivery_standard": float,
        "delivery_express": float, "free_delivery_threshold": float,
        "logo": str, "contact_email": str, "contact_phone": str,
        "maintenance_mode": bool,
    }
    update = {}
    for key, caster in allowed.items():
        if key in data:
            # maintenance_mode must be a real JSON boolean — bool("false")
            # would silently evaluate to True for string input.
            if key == "maintenance_mode" and not isinstance(data[key], bool):
                return fail("maintenance_mode must be true or false",
                            "VALIDATION", 400)
            try:
                val = caster(data[key])
            except (TypeError, ValueError):
                return fail(f"Invalid value for {key}", "VALIDATION", 400)
            if key in ("commission_rate",) and not (0 <= val <= 100):
                return fail("Commission rate must be between 0 and 100", "VALIDATION", 400)
            if key.startswith("delivery") or key == "free_delivery_threshold":
                if val < 0:
                    return fail(f"{key} cannot be negative", "VALIDATION", 400)
            update[key] = val

    if update:
        db.settings.update_one({"key": "marketplace"},
                               {"$set": update}, upsert=True)
        audit_log("settings.update", actor_id=user["_id"], actor_role="admin",
                  target_type="settings", target_id="marketplace",
                  details={"fields": list(update.keys())}, ip=request.remote_addr)
    doc = db.settings.find_one({"key": "marketplace"}) or {}
    return ok({"settings": serialize(doc)}, "Settings updated")
