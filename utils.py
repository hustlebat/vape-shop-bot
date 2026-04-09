import json
from pathlib import Path
from typing import Optional


# ── Catalog ────────────────────────────────────────────────────────────────────

def load_catalog(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_catalog(catalog: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)


def get_category(catalog: dict, category_id: str) -> Optional[dict]:
    for cat in catalog["categories"]:
        if cat["id"] == category_id:
            return cat
    return None


def get_product(catalog: dict, category_id: str, product_id: str) -> Optional[dict]:
    cat = get_category(catalog, category_id)
    if cat is None:
        return None
    for p in cat["products"]:
        if p["id"] == product_id:
            return p
    return None


def add_product(
    catalog: dict, category_id: str, name: str, description: str, price: float,
    image: Optional[str] = None,
) -> dict:
    cat = get_category(catalog, category_id)
    if cat is None:
        raise ValueError(f"Category {category_id!r} not found")
    base_id = name.lower().replace(" ", "-")
    existing_ids = {p["id"] for p in cat["products"]}
    product_id = base_id
    counter = 1
    while product_id in existing_ids:
        product_id = f"{base_id}-{counter}"
        counter += 1
    cat["products"].append(
        {
            "id": product_id,
            "name": name,
            "description": description,
            "price": price,
            "available": True,
            "image": image,
        }
    )
    return catalog


def edit_product(
    catalog: dict, category_id: str, product_id: str, field: str, value
) -> dict:
    allowed = ("name", "description", "price", "available", "image")
    if field not in allowed:
        raise ValueError(f"Invalid field {field!r}. Allowed: {allowed}")
    product = get_product(catalog, category_id, product_id)
    if product is None:
        raise ValueError(f"Product {product_id!r} not found in category {category_id!r}")
    product[field] = value
    return catalog


def remove_product(catalog: dict, category_id: str, product_id: str) -> dict:
    cat = get_category(catalog, category_id)
    if cat is None:
        raise ValueError(f"Category {category_id!r} not found")
    if not any(p["id"] == product_id for p in cat["products"]):
        raise ValueError(f"Product {product_id!r} not found in category {category_id!r}")
    cat["products"] = [p for p in cat["products"] if p["id"] != product_id]
    return catalog


def format_catalog_list(catalog: dict) -> str:
    lines = []
    for cat in catalog["categories"]:
        lines.append(cat['name'])
        if not cat["products"]:
            lines.append("  (no products)")
        else:
            for p in cat["products"]:
                status = "✅" if p["available"] else "❌"
                lines.append(f"  {status} {p['name']} — €{p['price']:.2f}")
    return "\n".join(lines)


# ── Orders ─────────────────────────────────────────────────────────────────────

def load_orders(path: str) -> list:
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_order(order: dict, path: str) -> None:
    orders = load_orders(path)
    orders.append(order)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(orders, f, indent=2, ensure_ascii=False)


def generate_order_id(path: str) -> str:
    orders = load_orders(path)
    return str(len(orders) + 1).zfill(4)


def calculate_total(items: list) -> float:
    return round(sum(item["price"] * item["qty"] for item in items), 2)


def format_order_notification(order: dict, shop_name: str) -> str:
    delivery = order["delivery"]
    if delivery["type"] == "delivery":
        location = f"📍 Delivery: {delivery['address']}"
    else:
        location = "📍 Pickup in store"

    items_text = "\n".join(
        f"  • {item['name']} x{item['qty']} — €{item['price'] * item['qty']:.2f}"
        for item in order["items"]
    )
    payment = "PayPal" if order["payment"] == "paypal" else "In-Person / Cash"

    return (
        f"🛒 NEW ORDER #{order['id']}\n\n"
        f"👤 {order['customer']['name']}\n"
        f"📞 {order['customer']['phone']}\n"
        f"{location}\n\n"
        f"Items:\n{items_text}\n\n"
        f"Total: €{order['total']:.2f}\n"
        f"💳 Payment: {payment}"
    )
