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
    catalog: dict, category_id: str, name: str, description: str, price: float
) -> dict:
    cat = get_category(catalog, category_id)
    if cat is None:
        raise ValueError(f"Category {category_id!r} not found")
    base_id = name.lower().replace(" ", "-")
    existing_ids = {p["id"] for p in cat["products"]}
    product_id = base_id
    if product_id in existing_ids:
        product_id = f"{base_id}-{len(cat['products'])}"
    cat["products"].append(
        {
            "id": product_id,
            "name": name,
            "description": description,
            "price": price,
            "available": True,
        }
    )
    return catalog


def edit_product(
    catalog: dict, category_id: str, product_id: str, field: str, value
) -> dict:
    allowed = ("name", "description", "price", "available")
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
    cat["products"] = [p for p in cat["products"] if p["id"] != product_id]
    return catalog


def format_catalog_list(catalog: dict) -> str:
    lines = []
    for cat in catalog["categories"]:
        lines.append(f"\n{cat['name']}")
        if not cat["products"]:
            lines.append("  (no products)")
        else:
            for p in cat["products"]:
                status = "✅" if p["available"] else "❌"
                lines.append(f"  {status} {p['name']} — €{p['price']:.2f}")
    return "\n".join(lines)
