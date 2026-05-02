import json
import pytest
from utils import (
    load_catalog, save_catalog,
    get_category, get_product,
    add_product, edit_product, remove_product,
    format_catalog_list,
    load_orders, save_order, generate_order_id,
    calculate_total, format_order_notification,
)


@pytest.fixture
def catalog():
    return {
        "categories": [
            {
                "id": "devices",
                "name": "⚡ Devices",
                "products": [
                    {
                        "id": "vuse-alto",
                        "name": "Vuse Alto",
                        "description": "Pod device",
                        "price": 15.90,
                        "available": True,
                    }
                ],
            },
            {"id": "eliquids", "name": "💧 E-Liquids", "products": []},
        ]
    }


@pytest.fixture
def catalog_path(tmp_path, catalog):
    path = str(tmp_path / "catalog.json")
    with open(path, "w") as f:
        json.dump(catalog, f)
    return path


def test_load_catalog(catalog_path, catalog):
    result = load_catalog(catalog_path)
    assert result == catalog


def test_save_catalog(tmp_path, catalog):
    path = str(tmp_path / "out.json")
    save_catalog(catalog, path)
    with open(path) as f:
        result = json.load(f)
    assert result == catalog


def test_get_category_found(catalog):
    cat = get_category(catalog, "devices")
    assert cat["name"] == "⚡ Devices"


def test_get_category_not_found(catalog):
    assert get_category(catalog, "nonexistent") is None


def test_get_product_found(catalog):
    p = get_product(catalog, "devices", "vuse-alto")
    assert p["name"] == "Vuse Alto"
    assert p["price"] == 15.90


def test_get_product_not_found(catalog):
    assert get_product(catalog, "devices", "missing") is None


def test_add_product(catalog):
    result = add_product(catalog, "eliquids", "Mango Ice", "Sweet mango flavour.", 9.50)
    cat = get_category(result, "eliquids")
    assert len(cat["products"]) == 1
    p = cat["products"][0]
    assert p["name"] == "Mango Ice"
    assert p["price"] == 9.50
    assert p["available"] is True
    assert p["id"] == "mango-ice"
    assert p["image"] is None


def test_add_product_with_image(catalog):
    result = add_product(catalog, "eliquids", "Mango Ice", "Sweet mango flavour.", 9.50, image="AgACAgQAA")
    p = get_category(result, "eliquids")["products"][0]
    assert p["image"] == "AgACAgQAA"


def test_add_product_invalid_category(catalog):
    with pytest.raises(ValueError, match="Category 'missing' not found"):
        add_product(catalog, "missing", "X", "Y", 1.0)


def test_add_product_deduplicates_id(catalog):
    add_product(catalog, "eliquids", "Mango Ice", "Desc", 9.50)
    result = add_product(catalog, "eliquids", "Mango Ice", "Another", 10.00)
    cat = get_category(result, "eliquids")
    ids = [p["id"] for p in cat["products"]]
    assert len(ids) == len(set(ids)), "Product IDs must be unique"


def test_edit_product_price(catalog):
    result = edit_product(catalog, "devices", "vuse-alto", "price", 12.00)
    p = get_product(result, "devices", "vuse-alto")
    assert p["price"] == 12.00


def test_edit_product_available(catalog):
    result = edit_product(catalog, "devices", "vuse-alto", "available", False)
    p = get_product(result, "devices", "vuse-alto")
    assert p["available"] is False


def test_edit_product_image(catalog):
    file_id = "AgACAgQAAsome_file_id"
    result = edit_product(catalog, "devices", "vuse-alto", "image", file_id)
    p = get_product(result, "devices", "vuse-alto")
    assert p["image"] == file_id


def test_edit_product_invalid_field(catalog):
    with pytest.raises(ValueError, match="Invalid field"):
        edit_product(catalog, "devices", "vuse-alto", "color", "red")


def test_remove_product(catalog):
    result = remove_product(catalog, "devices", "vuse-alto")
    cat = get_category(result, "devices")
    assert cat["products"] == []


def test_remove_product_missing_category(catalog):
    with pytest.raises(ValueError, match="Category 'missing' not found"):
        remove_product(catalog, "missing", "vuse-alto")


def test_format_catalog_list(catalog):
    text = format_catalog_list(catalog)
    assert "Vuse Alto" in text
    assert "€15.90" in text
    assert "E-Liquids" in text
    assert "(no products)" in text


@pytest.fixture
def orders_path(tmp_path):
    return str(tmp_path / "orders.json")


@pytest.fixture
def sample_order():
    return {
        "id": "0001",
        "timestamp": "2026-04-09T14:00:00",
        "customer": {"name": "Jane Doe", "phone": "+34600000000"},
        "delivery": {"type": "delivery", "address": "Calle Mayor 1"},
        "items": [
            {"id": "vuse-alto", "name": "Vuse Alto", "qty": 1, "price": 15.90},
            {"id": "mango-ice", "name": "Mango Ice", "qty": 2, "price": 9.50},
        ],
        "total": 34.90,
        "payment": "paypal",
        "status": "pending",
    }


def test_load_orders_empty(orders_path):
    assert load_orders(orders_path) == []


def test_save_and_load_order(orders_path, sample_order):
    save_order(sample_order, orders_path)
    orders = load_orders(orders_path)
    assert len(orders) == 1
    assert orders[0]["id"] == "0001"


def test_save_order_appends(orders_path, sample_order):
    save_order(sample_order, orders_path)
    second = {**sample_order, "id": "0002"}
    save_order(second, orders_path)
    orders = load_orders(orders_path)
    assert len(orders) == 2


def test_generate_order_id_empty(orders_path):
    assert generate_order_id(orders_path) == "0001"


def test_generate_order_id_sequential(orders_path, sample_order):
    save_order(sample_order, orders_path)
    assert generate_order_id(orders_path) == "0002"


def test_calculate_total():
    items = [
        {"name": "A", "qty": 2, "price": 10.00},
        {"name": "B", "qty": 1, "price": 5.50},
    ]
    assert calculate_total(items) == 25.50


def test_format_order_notification_delivery(sample_order):
    text = format_order_notification(sample_order, "Test Shop")
    assert "NEW ORDER #0001" in text
    assert "Jane Doe" in text
    assert "+34600000000" in text
    assert "Calle Mayor 1" in text
    assert "Vuse Alto x1" in text
    assert "Mango Ice x2" in text
    assert "€34.90" in text
    assert "PayPal" in text


def test_format_order_notification_pickup():
    order = {
        "id": "0002",
        "timestamp": "2026-04-09T15:00:00",
        "customer": {"name": "Bob", "phone": "+34611111111"},
        "delivery": {"type": "pickup", "address": ""},
        "items": [{"id": "x", "name": "Item", "qty": 1, "price": 5.00}],
        "total": 5.00,
        "payment": "inperson",
        "status": "pending",
    }
    text = format_order_notification(order, "Shop")
    assert "Pickup in store" in text
    assert "In-Person" in text
