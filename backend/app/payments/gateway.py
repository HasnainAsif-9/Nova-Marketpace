"""Payment gateway abstraction.

Each gateway implements:
  - create_payment(order, payment) -> dict   called at checkout; returns extra
    fields merged into the payment document (e.g. gateway_ref, checkout_url).
    For redirect-based gateways this is where you create the provider session
    and return the URL the frontend should redirect the buyer to.
  - handle_webhook(headers, raw_body) -> None  called by
    POST /api/payments/webhook/<method>. Must verify the provider signature,
    find the payment by gateway_ref, update its status and the parent order's
    payment_status, and write an audit_log entry. Return None on success.

To add a provider:
  1. Subclass PaymentGateway below and set `method`.
  2. Register it in GATEWAYS.
  3. Enable it via PAYMENT_METHODS_ENABLED env (comma-separated).
  4. Implement create_payment() and handle_webhook() with the provider SDK.

TODO(payment): JazzCashGateway / EasyPaisaGateway for the PK market —
save-card / wallet flow with HMAC integrity hash (merchant credentials).
"""
import logging
from datetime import datetime, timezone

from flask import current_app

logger = logging.getLogger(__name__)


class PaymentGateway:
    """Base class for payment providers."""

    method = "base"

    def is_available(self):
        """False when required credentials are missing — method stays hidden."""
        return True

    def create_payment(self, order, payment):
        """Return extra fields to store on the payment document."""
        return {}

    def handle_webhook(self, headers, raw_body):
        """Verify and apply a provider webhook. Implement per provider."""
        raise NotImplementedError(f"Webhooks not implemented for '{self.method}'")


class CODGateway(PaymentGateway):
    """Cash on delivery — no online charge; paid on delivery confirmation."""

    method = "cod"

    def is_available(self):
        return True


class StripeGateway(PaymentGateway):
    """Stripe Checkout — redirect flow.

    create_payment() opens a Stripe Checkout Session and returns
    {gateway_ref: <session id>, checkout_url: <hosted page url>}; the
    frontend redirects the buyer there. Payment stays 'pending' until the
    webhook confirms it.

    Required env: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, and
    PAYMENT_METHODS_ENABLED including 'stripe'.
    Note: Stripe does not onboard businesses registered in Pakistan —
    a Stripe account requires a supported-country entity.
    """

    method = "stripe"

    def is_available(self):
        return bool(current_app.config.get("STRIPE_SECRET_KEY"))

    def _stripe(self):
        import stripe
        stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
        return stripe

    def create_payment(self, order, payment):
        from ..extensions import get_db
        stripe = self._stripe()
        base = current_app.config["FRONTEND_BASE_URL"].rstrip("/")
        buyer = get_db().users.find_one({"_id": order["buyer_id"]})
        order_id = str(order["_id"])
        session = stripe.checkout.Session.create(
            mode="payment",
            client_reference_id=order_id,
            customer_email=(buyer or {}).get("email"),
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency": current_app.config["CURRENCY"].lower(),
                    "unit_amount": int(round(payment["amount"] * 100)),
                    "product_data": {
                        "name": f"Order {order['order_number']}",
                    },
                },
            }],
            metadata={"order_id": order_id},
            payment_intent_data={"metadata": {"order_id": order_id}},
            success_url=f"{base}/buyer/index.html?payment=success",
            cancel_url=f"{base}/checkout.html?payment=cancelled",
        )
        return {"gateway_ref": session.id, "checkout_url": session.url}

    def handle_webhook(self, headers, raw_body):
        from ..extensions import get_db
        from ..utils.audit import audit_log
        stripe = self._stripe()
        secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
        if not secret:
            raise ValueError("STRIPE_WEBHOOK_SECRET is not configured")
        event = stripe.Webhook.construct_event(
            raw_body, headers.get("Stripe-Signature"), secret)

        db = get_db()
        etype = event["type"]
        obj = event["data"]["object"]
        session_id = obj.get("id")
        if not session_id:
            return

        payment = db.payments.find_one({"gateway_ref": session_id})
        if not payment:
            logger.warning("Stripe webhook for unknown session %s", session_id)
            return
        if payment.get("status") == "paid":
            return  # idempotent — already processed

        now = datetime.now(timezone.utc)
        order_id = payment["order_id"]

        if etype in ("checkout.session.completed",
                     "checkout.session.async_payment_succeeded"):
            db.payments.update_one(
                {"_id": payment["_id"]},
                {"$set": {"status": "paid", "paid_at": now, "updated_at": now,
                          "gateway_event": etype}})
            db.orders.update_one(
                {"_id": order_id},
                {"$set": {"payment_status": "paid", "updated_at": now}})
            audit_log("payment.stripe_paid", target_type="order",
                      target_id=str(order_id),
                      details={"session": session_id})
        elif etype in ("checkout.session.async_payment_failed",
                       "checkout.session.expired"):
            db.payments.update_one(
                {"_id": payment["_id"]},
                {"$set": {"status": "failed", "updated_at": now,
                          "gateway_event": etype}})
            db.orders.update_one(
                {"_id": order_id},
                {"$set": {"payment_status": "failed", "updated_at": now}})
            audit_log("payment.stripe_failed", target_type="order",
                      target_id=str(order_id),
                      details={"session": session_id, "event": etype})


class JazzCashGateway(PaymentGateway):
    """TODO(payment): implement once JazzCash merchant credentials are issued.

    Uses the JazzCash Payment Page API: build the token request with the
    integrity salt hash, redirect the buyer, then confirm via the wallet
    callback/webhook and reconcile the transaction status.
    """

    method = "jazzcash"

    def is_available(self):
        cfg = current_app.config
        return bool(cfg.get("JAZZCASH_MERCHANT_ID")
                    and cfg.get("JAZZCASH_PASSWORD")
                    and cfg.get("JAZZCASH_INTEGRITY_SALT"))

    def create_payment(self, order, payment):
        raise NotImplementedError("JazzCash gateway not implemented yet")


class EasyPaisaGateway(PaymentGateway):
    """TODO(payment): implement once EasyPaisa merchant credentials are issued.

    Uses the EasyPaisa HPP/API: SHA-256 hash-key request, redirect to the
    hosted payment page, reconcile via webhook/return URL.
    """

    method = "easypaisa"

    def is_available(self):
        cfg = current_app.config
        return bool(cfg.get("EASYPAISA_STORE_ID") and cfg.get("EASYPAISA_HASH_KEY"))

    def create_payment(self, order, payment):
        raise NotImplementedError("EasyPaisa gateway not implemented yet")


GATEWAYS = {
    "cod": CODGateway,
    "stripe": StripeGateway,
    "jazzcash": JazzCashGateway,
    "easypaisa": EasyPaisaGateway,
}


def enabled_methods():
    """Payment method ids the buyer may choose at checkout."""
    enabled = set(current_app.config.get("PAYMENT_METHODS_ENABLED", ["cod"]))
    out = []
    for method, cls in GATEWAYS.items():
        if method not in enabled:
            continue
        gw = cls()
        if gw.is_available():
            out.append({"id": method, "name": _METHOD_NAMES.get(method, method)})
    return out


_METHOD_NAMES = {
    "cod": "Cash on Delivery",
    "stripe": "Card (Stripe)",
    "jazzcash": "JazzCash",
    "easypaisa": "EasyPaisa",
}


def get_gateway(method):
    """Return a gateway instance for an enabled+available method, else None."""
    cls = GATEWAYS.get(method)
    if not cls:
        return None
    enabled = set(current_app.config.get("PAYMENT_METHODS_ENABLED", ["cod"]))
    if method not in enabled:
        return None
    gw = cls()
    return gw if gw.is_available() else None


def get_gateway_any(method):
    """Return a gateway instance regardless of enabled flag (for webhooks)."""
    cls = GATEWAYS.get(method)
    return cls() if cls else None
