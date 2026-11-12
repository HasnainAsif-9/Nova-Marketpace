from flask import Blueprint, request

from ..extensions import get_db
from ..utils.responses import ok, not_found, fail
from ..utils.helpers import (
    serialize, serialize_list, to_object_id, slugify, unique_slug, clean_str,
)
from ..utils.decorators import role_required, get_current_user
from ..utils.audit import audit_log

bp = Blueprint("categories", __name__, url_prefix="/api/categories")


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@bp.get("")
def list_categories():
    cats = list(get_db().categories.find({"is_active": {"$ne": False}})
                .sort("sort_order", 1).sort("name", 1))
    return ok({"categories": serialize_list(cats)})


@bp.get("/<category_id>")
def get_category(category_id):
    oid = to_object_id(category_id)
    if not oid:
        return not_found("Category not found")
    cat = get_db().categories.find_one({"_id": oid})
    if not cat:
        return not_found("Category not found")
    data = serialize(cat)
    data["product_count"] = get_db().products.count_documents({
        "category_id": oid, "status": "active"
    })
    return ok({"category": data})


@bp.post("")
@role_required("admin")
def create_category():
    data = request.get_json(silent=True) or {}
    name = clean_str(data.get("name"), 100)
    if not name:
        return fail("Name is required", "VALIDATION", 400)

    slug = unique_slug(get_db().categories, slugify(data.get("slug") or name))
    parent_id = to_object_id(data["parent_id"]) if data.get("parent_id") else None

    doc = {
        "name": name,
        "slug": slug,
        "description": clean_str(data.get("description"), 1000),
        "parent_id": parent_id,
        "image": clean_str(data.get("image"), 500),
        "is_active": bool(data.get("is_active", True)),
        "sort_order": _safe_int(data.get("sort_order"), 0),
    }
    result = get_db().categories.insert_one(doc)
    doc["_id"] = result.inserted_id

    user = get_current_user()
    audit_log("category.create", actor_id=user["_id"], actor_role=user["role"],
              target_type="category", target_id=str(result.inserted_id),
              details={"name": name}, ip=request.remote_addr)
    return ok({"category": serialize(doc)}, "Category created", 201)


@bp.put("/<category_id>")
@role_required("admin")
def update_category(category_id):
    oid = to_object_id(category_id)
    if not oid:
        return not_found("Category not found")
    db = get_db()
    if not db.categories.find_one({"_id": oid}):
        return not_found("Category not found")

    data = request.get_json(silent=True) or {}
    update = {}
    if "name" in data:
        name = clean_str(data["name"], 100)
        if not name:
            return fail("Name cannot be empty", "VALIDATION", 400)
        update["name"] = name
    if "description" in data:
        update["description"] = clean_str(data["description"], 1000)
    if "image" in data:
        update["image"] = clean_str(data["image"], 500)
    if "is_active" in data:
        update["is_active"] = bool(data["is_active"])
    if "sort_order" in data:
        update["sort_order"] = _safe_int(data["sort_order"], 0)
    if "parent_id" in data:
        update["parent_id"] = to_object_id(data["parent_id"]) if data["parent_id"] else None

    if update:
        db.categories.update_one({"_id": oid}, {"$set": update})

    user = get_current_user()
    audit_log("category.update", actor_id=user["_id"], actor_role=user["role"],
              target_type="category", target_id=category_id,
              details={"fields": list(update.keys())}, ip=request.remote_addr)
    return ok({"category": serialize(db.categories.find_one({"_id": oid}))},
              "Category updated")


@bp.delete("/<category_id>")
@role_required("admin")
def delete_category(category_id):
    oid = to_object_id(category_id)
    if not oid:
        return not_found("Category not found")
    db = get_db()
    if db.products.count_documents({"category_id": oid}) > 0:
        return fail("Cannot delete a category that has products. Deactivate it instead.",
                    "CATEGORY_IN_USE", 409)
    result = db.categories.delete_one({"_id": oid})
    if result.deleted_count == 0:
        return not_found("Category not found")
    user = get_current_user()
    audit_log("category.delete", actor_id=user["_id"], actor_role=user["role"],
              target_type="category", target_id=category_id, ip=request.remote_addr)
    return ok(message="Category deleted")
