"""
Spec T-006 / AC2 / D-004: register_products_batch makes SKUs unique within the
batch (against in-flight siblings) before any insert, so a set of variants that
share a base SKU all land instead of the whole batch rolling back.

This is the direct regression test for the screenshot collision where three
"Medias Multicolor Talle S/M/L" produced the identical SKU and nothing was
created. Runs on the sqlite backend (no langchain dependency).
"""
import pytest
from database import register_products_batch, fetch_all, fetch_one


@pytest.mark.unit
@pytest.mark.database
class TestBatchSkuDedup:
    def test_three_identical_base_skus_all_land(self, test_db):
        """Three products handed the same base SKU yield three distinct rows."""
        products = [
            {"sku": "BC-PROD-MEDIAS-MULTICOLOR", "name": "Medias Multicolor Talle S",
             "unit_price_cents": 1000, "unit_cost_cents": 0},
            {"sku": "BC-PROD-MEDIAS-MULTICOLOR", "name": "Medias Multicolor Talle M",
             "unit_price_cents": 1000, "unit_cost_cents": 0},
            {"sku": "BC-PROD-MEDIAS-MULTICOLOR", "name": "Medias Multicolor Talle L",
             "unit_price_cents": 1000, "unit_cost_cents": 0},
        ]

        result = register_products_batch(products)

        assert len(result) == 3
        skus = [r["sku"] for r in result]
        assert len(set(skus)) == 3, f"SKUs not unique: {skus}"

        rows = fetch_all(
            "SELECT sku, name, unit_price_cents FROM products WHERE name LIKE 'Medias Multicolor%'"
        )
        assert len(rows) == 3
        assert {r["unit_price_cents"] for r in rows} == {1000}

    def test_batch_sku_dedups_against_committed_row(self, test_db):
        """A batch SKU that already exists in the catalog gets bumped, not failed."""
        register_products_batch([
            {"sku": "BC-PROD-MEDIAS-AZUL", "name": "Medias Azules",
             "unit_price_cents": 500, "unit_cost_cents": 0},
        ])
        # Second batch reuses the same base SKU.
        result = register_products_batch([
            {"sku": "BC-PROD-MEDIAS-AZUL", "name": "Medias Azules Premium",
             "unit_price_cents": 700, "unit_cost_cents": 0},
        ])
        assert result[0]["sku"] != "BC-PROD-MEDIAS-AZUL"
        assert fetch_one("SELECT 1 FROM products WHERE sku = ?", (result[0]["sku"],))
