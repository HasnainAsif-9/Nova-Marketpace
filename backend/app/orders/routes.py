from flask import Blueprint, request, current_app
from datetime import datetime, timezone
from bson import ObjectId

from ..extensions import get_db
from ..utils.responses import ok, fail, not_found, forbidden
from ..utils.helpers import serialize, serialize_list, to_object_id, clamp_int, clean_str
from ..utils.decorators import auth_required, role_required, get_current_user, rate_limit
from ..utils.audit import audit_log
from ..payments.gateway import get_gateway

bp = Blueprint("orders", __name__, url_prefix="/api/orders")

ORDER_STATUSES = [
    "pending", "confirmed", "processing", "shipped", "out_for_delivery",
    "delivered", "cancelled", "returned", "refunded",
]
ALLOWED_TRANSITIONS = {
    "pending": ["confirmed", "cancelled"],
    "confirmed": ["processing", "cancelled"],
    "processing": ["shipped", "cancelled"],
    "shipped": ["out_for_delivery", "cancelled"],
    "out_for_delivery": ["delivered", "returned"],
    "delivered": ["returned"],
    "cancelled": ["refunded"],
    "returned": ["refunded"],
    "refunded": [],
}


def _order_number():
    import secrets
    return f"NM-{datetime.now(timezone.utc).strftime('%y%m%d')}-{secrets.token_hex(4).upper()}"


def _settings_doc():
    return get_db().settings.find_one({"key": "marketplace"}) or {}


def _delivery_options():
    cfg = current_app.config
    s = _settings_doc()
    return [
        {"id": "standard", "name": "Standard Delivery",
         "fee": float(s.get("delivery_standard", cfg["DELIVERY_FEE_STANDARD"])), "days": "3-5"},
        {"id": "express", "name": "Express Delivery",
         "fee": float(s.get("delivery_express", cfg["DELIVERY_FEE_EXPRESS"])), "days": "1-2"},
    ]


def _calculate_delivery(subtotal, option_id):
    cfg = current_app.config
    s = _settings_doc()
    options = {o["id"]: o["fee"] for o in _delivery_options()}
    fee = options.get(option_id, options["standard"])
    threshold = float(s.get("free_delivery_threshold",
                            cfg.get("FREE_DELIVERY_THRESHOLD", 0)))
    if threshold and subtotal >= threshold:
        fee = 0
    return round(fee, 2)


def _commission_rate():
    s = get_db().settings.find_one({"key": "marketplace"}) or {}
    return float(s.get("commission_rate", current_app.config["DEFAULT_COMMISSION_RATE"]))


def _notify(user_id, ntype, title, message, data=None):
    get_db().notifications.insert_one({
        "user_id": user_id, "type": ntype, "title": title, "message": message,
        "data": data or {}, "read": False,
        "created_at": datetime.now(timezone.utc),
    })


# ---------- Public ----------

@bp.get("/delivery-options")
def delivery_options():
    return ok({"options": _delivery_options()})


# ---------- Buyer checkout ----------

@bp.post("/checkout")
@auth_required
@rate_limit(20, 60)
def checkout():
    user = get_current_user()
    if user["role"] != "buyer":
        return forbidden("Only buyers can place orders")

    data = request.get_json(silent=True) or {}
    address_id = to_object_id(data.get("address_id"))
    delivery_option = clean_str(data.get("delivery_option"), 20) or "standard"
    payment_method = clean_str(data.get("payment_method"), 20) or "cod"
    notes = clean_str(data.get("notes"), 500)

    gateway = get_gateway(payment_method)
    if not gateway:
        return fail("Unsupported payment method", "PAYMENT_METHOD", 400)
    if delivery_option not in ("standard", "express"):
        return fail("Invalid delivery option", "VALIDATION", 400)

    db = get_db()

    cart = db.carts.find_one({"user_id": user["_id"]})
    if not cart or not cart.get("items"):
        return fail("Your cart is empty", "EMPTY_CART", 400)

    address = None
    if address_id:
        address = db.addresses.find_one({"_id": address_id, "user_id": user["_id"]})
    if not address:
        address = db.addresses.find_one({"user_id": user["_id"], "is_default": True})
    if not address:
        return fail("A shipping address is required", "ADDRESS_REQUIRED", 400)

    # --- Recalculate everything server-side ---
    cart_items = []
    product_ids = []
    for item in cart["items"]:
        pid = to_object_id(item.get("product_id"))
        qty = clamp_int(item.get("quantity"), 0, 1, 100)
        if pid and qty > 0:
            product_ids.append(pid)
            cart_items.append({"product_id": pid, "quantity": qty})

    if not cart_items:
        return fail("Your cart is empty", "EMPTY_CART", 400)

    products = {p["_id"]: p for p in db.products.find({"_id": {"$in": product_ids}})}

    seller_groups = {}
    subtotal = 0.0
    for ci in cart_items:
        product = products.get(ci["product_id"])
        if not product or product.get("status") != "active":
            name = product.get("name", "unknown") if product else str(ci["product_id"])
            return fail(f"Product '{name}' is unavailable", "PRODUCT_UNAVAILABLE", 409)
        seller = db.sellers.find_one({"user_id": product["seller_id"]})
        if not seller or seller.get("status") != "approved":
            return fail(f"Seller for '{product['name']}' is not active", "SELLER_INACTIVE", 409)
        if product.get("stock", 0) < ci["quantity"]:
            return fail(f"Insufficient stock for '{product['name']}' (available: {product.get('stock', 0)})",
                        "INSUFFICIENT_STOCK", 409)

        line_total = round(product["price"] * ci["quantity"], 2)
        subtotal += line_total
        seller_id = str(product["seller_id"])
        seller_groups.setdefault(seller_id, {"items": [], "subtotal": 0.0})
        seller_groups[seller_id]["items"].append({
            "product_id": product["_id"],
            "product_name": product["name"],
            "product_slug": product.get("slug"),
            "product_image": (product.get("images") or [None])[0],
            "sku": product.get("sku"),
            "unit_price": product["price"],
            "quantity": ci["quantity"],
            "line_total": line_total,
        })
        seller_groups[seller_id]["subtotal"] += line_total

    subtotal = round(subtotal, 2)
    delivery_fee = _calculate_delivery(subtotal, delivery_option)
    total = round(subtotal + delivery_fee, 2)
    commission_rate = _commission_rate()

    now = datetime.now(timezone.utc)
    order_number = _order_number()

    # --- Atomic stock deduction ---
    for ci in cart_items:
        result = db.products.find_one_and_update(
            {"_id": ci["product_id"], "stock": {"$gte": ci["quantity"]}},
            {"$inc": {"stock": -ci["quantity"], "sold_count": ci["quantity"]},
             "$set": {"updated_at": now}}
        )
        if result is None:
            return fail("Stock changed during checkout. Please review your cart.",
                        "STOCK_CHANGED", 409)

    try:
        parent = {
            "order_number": order_number,
            "buyer_id": user["_id"],
            "status": "pending",
            "payment_method": payment_method,
            "payment_status": "pending",
            "delivery_option": delivery_option,
            "delivery_fee": delivery_fee,
            "subtotal": subtotal,
            "total": total,
            "currency": current_app.config["CURRENCY"],
            "currency_symbol": current_app.config["CURRENCY_SYMBOL"],
            "commission_rate": commission_rate,
            "address_snapshot": {
                "recipient_name": address.get("recipient_name"),
                "phone": address.get("phone"),
                "address_line1": address.get("address_line1"),
                "address_line2": address.get("address_line2"),
                "city": address.get("city"),
                "state": address.get("state"),
                "postal_code": address.get("postal_code"),
                "country": address.get("country"),
            },
            "notes": notes,
            "seller_count": len(seller_groups),
            "created_at": now,
            "updated_at": now,
        }
        parent_result = db.orders.insert_one(parent)
        parent_id = parent_result.inserted_id

        for seller_id_str, group in seller_groups.items():
            seller_oid = ObjectId(seller_id_str)
            seller_subtotal = round(group["subtotal"], 2)
            commission_amount = round(seller_subtotal * commission_rate / 100, 2)
            seller_earning = round(seller_subtotal - commission_amount, 2)

            sub_order = {
                "parent_order_id": parent_id,
                "order_number": order_number,
                "seller_id": seller_oid,
                "buyer_id": user["_id"],
                "status": "pending",
                "items": group["items"],
                "subtotal": seller_subtotal,
                "commission_rate": commission_rate,
                "commission_amount": commission_amount,
                "seller_earning": seller_earning,
                "created_at": now,
                "updated_at": now,
            }
            sub_result = db.order_items.insert_one(sub_order)

            db.commissions.insert_one({
                "order_id": parent_id,
                "sub_order_id": sub_result.inserted_id,
                "seller_id": seller_oid,
                "buyer_id": user["_id"],
                "sale_amount": seller_subtotal,
                "commission_rate": commission_rate,
                "commission_amount": commission_amount,
                "seller_earning": seller_earning,
                "status": "pending",
                "created_at": now,
            })

        parent["_id"] = parent_id

        payment_doc = {
            "order_id": parent_id,
            "method": payment_method,
            "amount": total,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }
        # Gateway may add provider refs (gateway_ref, checkout_url, ...).
        # Redirect-based gateways: return {"checkout_url": ...} here and the
        # frontend should send the buyer to that URL after checkout.
        payment_doc.update(gateway.create_payment(parent, payment_doc))
        db.payments.insert_one(payment_doc)

        db.carts.update_one({"user_id": user["_id"]}, {"$set": {"items": []}})

        _notify(user["_id"], "order_created",
                "Order placed", f"Your order {order_number} has been placed.",
                {"order_id": str(parent_id)})

        audit_log("order.create", actor_id=user["_id"], actor_role="buyer",
                  target_type="order", target_id=str(parent_id),
                  details={"order_number": order_number, "total": total,
                           "sellers": len(seller_groups)}, ip=request.remote_addr)

        # Order confirmation email — never let mail failure break checkout.
        try:
            from ..utils.mailer import send_email
            from ..utils.email_templates import order_confirmation_email
            order_url = (f"{current_app.config['FRONTEND_BASE_URL']}"
                         "/buyer/index.html#orders")
            subject, text, html = order_confirmation_email(
                user.get("full_name") or user.get("username"),
                order_number, total,
                current_app.config["CURRENCY_SYMBOL"], order_url)
            send_email(user["email"], subject, text, html=html)
        except Exception:
            current_app.logger.exception("Failed to send order confirmation email")

        order = db.orders.find_one({"_id": parent_id})
        resp = {"order": serialize(order)}
        if payment_doc.get("checkout_url"):
            resp["payment"] = serialize(payment_doc)
        return ok(resp, "Order placed successfully", 201)

    except Exception:
        for ci in cart_items:
            db.products.update_one({"_id": ci["product_id"]},
                                   {"$inc": {"stock": ci["quantity"],
                                             "sold_count": -ci["quantity"]}})
        raise


@bp.get("")
@auth_required
def my_orders():
    user = get_current_user()
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 10, 1, 50)
    status = clean_str(request.args.get("status"), 20)

    query = {"buyer_id": user["_id"]}
    if status and status in ORDER_STATUSES:
        query["status"] = status

    total = db.orders.count_documents(query)
    orders = list(db.orders.find(query).sort("created_at", -1)
                  .skip((page - 1) * limit).limit(limit))

    order_ids = [o["_id"] for o in orders]
    counts = {}
    for doc in db.order_items.aggregate([
        {"$match": {"parent_order_id": {"$in": order_ids}}},
        {"$group": {"_id": "$parent_order_id",
                    "count": {"$sum": {"$size": "$items"}},
                    "sellers": {"$addToSet": "$seller_id"}}},
    ]):
        counts[doc["_id"]] = {"item_count": doc["count"], "seller_count": len(doc["sellers"])}

    out = []
    for o in orders:
        d = serialize(o)
        d.update(counts.get(o["_id"], {"item_count": 0, "seller_count": 0}))
        out.append(d)

    return ok({
        "orders": out,
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


@bp.get("/<order_id>")
@auth_required
def get_order(order_id):
    user = get_current_user()
    db = get_db()
    oid = to_object_id(order_id)
    if not oid:
        return not_found("Order not found")
    order = db.orders.find_one({"_id": oid})
    if not order:
        return not_found("Order not found")

    if user["role"] == "buyer" and order["buyer_id"] != user["_id"]:
        return forbidden()
    if user["role"] == "seller":
        if not db.order_items.find_one({"parent_order_id": oid, "seller_id": user["_id"]}):
            return forbidden()

    sub_orders = list(db.order_items.find({"parent_order_id": oid}))
    payment = db.payments.find_one({"order_id": oid})

    data = serialize(order)
    data["sub_orders"] = serialize_list(sub_orders)
    data["payment"] = serialize(payment)
    return ok({"order": data})


@bp.post("/<order_id>/cancel")
@auth_required
def cancel_order(order_id):
    user = get_current_user()
    db = get_db()
    oid = to_object_id(order_id)
    if not oid:
        return not_found("Order not found")
    order = db.orders.find_one({"_id": oid})
    if not order:
        return not_found("Order not found")
    if order["buyer_id"] != user["_id"]:
        return forbidden()
    if order["status"] != "pending":
        return fail("Only pending orders can be cancelled", "INVALID_STATUS", 400)

    now = datetime.now(timezone.utc)
    db.orders.update_one({"_id": oid},
                         {"$set": {"status": "cancelled", "updated_at": now}})
    db.order_items.update_many({"parent_order_id": oid},
                               {"$set": {"status": "cancelled", "updated_at": now}})
    db.commissions.update_many({"order_id": oid},
                               {"$set": {"status": "cancelled", "updated_at": now}})
    db.payments.update_one({"order_id": oid},
                           {"$set": {"status": "cancelled", "updated_at": now}})

    for sub in db.order_items.find({"parent_order_id": oid}):
        for item in sub.get("items", []):
            db.products.update_one({"_id": item["product_id"]},
                                   {"$inc": {"stock": item["quantity"],
                                             "sold_count": -item["quantity"]}})

    _notify(user["_id"], "order_cancelled", "Order cancelled",
            f"Your order {order['order_number']} has been cancelled.",
            {"order_id": str(oid)})
    audit_log("order.cancel", actor_id=user["_id"], actor_role="buyer",
              target_type="order", target_id=str(oid), ip=request.remote_addr)
    return ok({"order": serialize(db.orders.find_one({"_id": oid}))}, "Order cancelled")


# ---------- Seller order views ----------

@bp.get("/seller/mine")
@role_required("seller")
def seller_orders():
    user = get_current_user()
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 10, 1, 50)
    status = clean_str(request.args.get("status"), 20)

    query = {"seller_id": user["_id"]}
    if status and status in ORDER_STATUSES:
        query["status"] = status

    total = db.order_items.count_documents(query)
    subs = list(db.order_items.find(query).sort("created_at", -1)
                .skip((page - 1) * limit).limit(limit))

    parent_ids = [s["parent_order_id"] for s in subs]
    parents = {p["_id"]: p for p in db.orders.find({"_id": {"$in": parent_ids}})}
    buyer_ids = {s["buyer_id"] for s in subs}
    buyers = {b["_id"]: b for b in db.users.find({"_id": {"$in": list(buyer_ids)}})}

    out = []
    for s in subs:
        d = serialize(s)
        parent = parents.get(s["parent_order_id"])
        if parent:
            d["parent_status"] = parent.get("status")
            d["order_number"] = parent.get("order_number")
            d["delivery_option"] = parent.get("delivery_option")
        buyer = buyers.get(s["buyer_id"])
        if buyer:
            d["buyer_name"] = buyer.get("full_name") or buyer.get("username")
        out.append(d)

    return ok({
        "orders": out,
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })


@bp.post("/<order_id>/status")
@role_required("seller", "admin")
def update_order_status(order_id):
    user = get_current_user()
    db = get_db()
    oid = to_object_id(order_id)
    if not oid:
        return not_found("Order not found")

    data = request.get_json(silent=True) or {}
    new_status = clean_str(data.get("status"), 20)
    if new_status not in ORDER_STATUSES:
        return fail("Invalid status", "VALIDATION", 400)

    order = db.orders.find_one({"_id": oid})
    if not order:
        return not_found("Order not found")

    if user["role"] == "seller":
        if not db.order_items.find_one({"parent_order_id": oid, "seller_id": user["_id"]}):
            return forbidden()
        if new_status in ("delivered", "refunded", "returned"):
            return fail("Only admin can set this status", "FORBIDDEN", 403)

    current = order["status"]
    if new_status == current:
        return ok({"order": serialize(order)}, "Status unchanged")
    if new_status not in ALLOWED_TRANSITIONS.get(current, []):
        return fail(f"Cannot transition from '{current}' to '{new_status}'",
                    "INVALID_TRANSITION", 400)

    now = datetime.now(timezone.utc)
    db.orders.update_one({"_id": oid},
                         {"$set": {"status": new_status, "updated_at": now}})

    sub_query = {"parent_order_id": oid}
    if user["role"] == "seller":
        sub_query["seller_id"] = user["_id"]
    affected_subs = list(db.order_items.find(sub_query))
    db.order_items.update_many(sub_query, {"$set": {"status": new_status, "updated_at": now}})

    # Cancellation via status change must restock and void commissions,
    # matching the dedicated cancel endpoint's behavior.
    if new_status == "cancelled":
        for sub in affected_subs:
            for item in sub.get("items", []):
                db.products.update_one({"_id": item["product_id"]},
                                       {"$inc": {"stock": item["quantity"],
                                                 "sold_count": -item["quantity"]}})
            db.commissions.update_many({"sub_order_id": sub["_id"]},
                                       {"$set": {"status": "cancelled",
                                                 "updated_at": now}})
        if user["role"] == "admin":
            db.payments.update_one({"order_id": oid},
                                   {"$set": {"status": "cancelled", "updated_at": now}})

    status_messages = {
        "confirmed": "Your order has been confirmed.",
        "processing": "Your order is being prepared.",
        "shipped": "Your order has been shipped.",
        "out_for_delivery": "Your order is out for delivery.",
        "delivered": "Your order has been delivered.",
        "cancelled": "Your order has been cancelled.",
        "returned": "Your order has been marked as returned.",
        "refunded": "Your order has been refunded.",
    }
    _notify(order["buyer_id"], f"order_{new_status}",
            f"Order {new_status.replace('_', ' ').title()}",
            f"{status_messages.get(new_status, 'Order status updated.')} "
            f"Order {order['order_number']}.",
            {"order_id": str(oid)})

    audit_log("order.status_change", actor_id=user["_id"], actor_role=user["role"],
              target_type="order", target_id=str(oid),
              details={"from": current, "to": new_status}, ip=request.remote_addr)

    fresh = db.orders.find_one({"_id": oid})
    return ok({"order": serialize(fresh)}, f"Order marked as {new_status}")


# ---------- Admin ----------

@bp.get("/admin/all")
@role_required("admin")
def admin_all_orders():
    db = get_db()
    page = clamp_int(request.args.get("page"), 1, 1, 10000)
    limit = clamp_int(request.args.get("limit"), 20, 1, 100)
    status = clean_str(request.args.get("status"), 20)
    q = clean_str(request.args.get("q"), 50)

    query = {}
    if status and status in ORDER_STATUSES:
        query["status"] = status
    if q:
        import re as _re
        query["order_number"] = {"$regex": _re.escape(q), "$options": "i"}

    total = db.orders.count_documents(query)
    orders = list(db.orders.find(query).sort("created_at", -1)
                  .skip((page - 1) * limit).limit(limit))
    return ok({
        "orders": serialize_list(orders),
        "pagination": {"page": page, "limit": limit, "total": total,
                       "pages": (total + limit - 1) // limit},
    })
