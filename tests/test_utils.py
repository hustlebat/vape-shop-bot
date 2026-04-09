import json
import pytest
from utils import (
    load_catalog, save_catalog,
    get_category, get_product,
    add_product, edit_product, remove_product,
    format_catalog_list,
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


def test_add_product_invalid_category(catalog):
    with pytest.raises(ValueError, match="Category 'missing' not found"):
        add_product(catalog, "missing", "X", "Y", 1.0)


def test_edit_product_price(catalog):
    result = edit_product(catalog, "devices", "vuse-alto", "price", 12.00)
    p = get_product(result, "devices", "vuse-alto")
    assert p["price"] == 12.00


def test_edit_product_available(catalog):
    result = edit_product(catalog, "devices", "vuse-alto", "available", False)
    p = get_product(result, "devices", "vuse-alto")
    assert p["available"] is False


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
