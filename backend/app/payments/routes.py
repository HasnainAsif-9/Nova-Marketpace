from flask import Blueprint, request
from datetime import datetime, timezone

from ..extensions import get_db
from ..utils.responses import ok, fail, not_found
from ..utils.helpers import serialize, to_object_id, clean_str
from ..utils.decorators import auth_required, get_current_user, rate_limit
from ..utils.audit import audit_log
from .gateway import enabled_methods, get_gateway_any

bp = Blueprint("payments", __name__, url_prefix="/api/payments")


@bp.get("/methods")
def payment_methods():
    """Public list of payment methods available at checkout."""
    return ok({"methods": enabled_methods()})


@bp.post("/webhook/<method>")
@rate_limit(120, 60)
def payment_webhook(method):
    """Provider webhook endpoint — e.g. /api/payments/webhook/stripe.

    The gateway verifies the provider signature on the raw body, updates the
    payment + order docs, and writes an audit entry. Register this URL in the
    provider dashboard when a gateway goes live.
    """
    gateway = get_gateway_any(method)
    if not gateway:
        return not_found("Unknown payment method")
    try:
        gateway.handle_webhook(request.headers, request.get_data())
    except NotImplementedError:
        return fail("Webhooks are not implemented for this provider yet",
                    "NOT_IMPLEMENTED", 501)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Payment webhook failed for %s", method)
        return fail("Webhook processing failed", "WEBHOOK_ERROR", 400)
    return ok(message="Webhook processed")


@bp.get("/order/<order_id>")
@auth_required
def get_payment(order_id):
    user = get_current_user()
    db = get_db()
    oid = to_object_id(order_id)
    if not oid:
        return not_found("Order not found")
    order = db.orders.find_one({"_id": oid})
    if not order:
        return not_found("Order not found")
    # Authorization
    if user["role"] == "buyer" and order["buyer_id"] != user["_id"]:
        return fail("Access denied", "FORBIDDEN", 403)
    if user["role"] == "seller":
        if not db.order_items.find_one({"parent_order_id": oid, "seller_id": user["_id"]}):
            return fail("Access denied", "FORBIDDEN", 403)
    payment = db.payments.find_one({"order_id": oid})
    if not payment:
        return not_found("Payment not found")
    return ok({"payment": serialize(payment)})


@bp.post("/cod/confirm")
@auth_required
@rate_limit(10, 60)
def confirm_cod():
    """Buyer confirms COD payment on delivery — marks payment as paid.
    In a real deployment this would be triggered by delivery confirmation."""
    user = get_current_user()
    if user["role"] != "buyer":
        return fail("Only buyers can confirm payments", "FORBIDDEN", 403)
    data = request.get_json(silent=True) or {}
    order_id = to_object_id(data.get("order_id"))
    if not order_id:
        return fail("order_id is required", "VALIDATION", 400)
    db = get_db()
    order = db.orders.find_one({"_id": order_id, "buyer_id": user["_id"]})
    if not order:
        return not_found("Order not found")
    if order.get("payment_method") != "cod":
        return fail("This order is not COD", "VALIDATION", 400)
    if order.get("status") != "delivered":
        return fail("Payment can only be confirmed after delivery", "INVALID_STATUS", 400)

    now = datetime.now(timezone.utc)
    db.payments.update_one({"order_id": order_id},
                           {"$set": {"status": "paid", "paid_at": now, "updated_at": now}})
    db.orders.update_one({"_id": order_id},
                         {"$set": {"payment_status": "paid", "updated_at": now}})
    audit_log("payment.cod_confirmed", actor_id=user["_id"], actor_role="buyer",
              target_type="order", target_id=str(order_id), ip=request.remote_addr)
    return ok(message="Payment confirmed")
