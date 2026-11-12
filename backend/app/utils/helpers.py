import re
import unicodedata
from bson import ObjectId


def is_valid_object_id(value):
    return isinstance(value, str) and ObjectId.is_valid(value)


def to_object_id(value):
    if is_valid_object_id(value):
        return ObjectId(value)
    return None


def slugify(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "item"


def unique_slug(collection, base, exclude_id=None):
    slug = base
    counter = 1
    query = {"slug": slug}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    while collection.find_one(query):
        slug = f"{base}-{counter}"
        counter += 1
        query["slug"] = slug
    return slug


def clamp_int(value, default, minimum, maximum):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, v))


def clamp_float(value, default, minimum, maximum):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, v))


def clean_str(value, max_len=500):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:max_len]


def serialize(doc):
    """Convert a Mongo document to a JSON-safe dict."""
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    for key, value in list(doc.items()):
        if isinstance(value, ObjectId):
            doc[key] = str(value)
        elif isinstance(value, list):
            doc[key] = [
                {k: (str(v) if isinstance(v, ObjectId) else v) for k, v in item.items()}
                if isinstance(item, dict) else item
                for item in value
            ]
    return doc


def serialize_list(docs):
    return [serialize(d) for d in docs]
