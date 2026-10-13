"""Data-access repository for the costing module (spec 003 M2).

SQL only; the landed-cost arithmetic and the completeness state live in
``costing_service`` (ARCHITECTURE convention: repository does SQL, service
computes). Queries use ``%s`` placeholders; the SQLite backend translates them.
Boolean columns are tested with the bare column (``WHERE p.is_active``) so the
same query runs on Postgres (boolean) and SQLite (integer) without a dialect cast.
"""

from database_config import db as database


class CostingRepository:
    """Encapsulates SQL/data access for costing."""

    def __init__(self, db_module=database):
        self.db = db_module

    # ------------------------------------------------------------------ types
    def list_bracelet_types(self):
        """Active products that have at least one BOM line (a costable type)."""
        query = """
            SELECT DISTINCT p.id AS id, p.sku AS sku, p.name AS name
            FROM products p
            JOIN bom_lines b ON b.product_id = p.id
            WHERE p.is_active
            ORDER BY p.name
        """
        return self.db.fetch_all(query)

    def countries_for(self, product_id):
        query = "SELECT DISTINCT country FROM bom_lines WHERE product_id = %s ORDER BY country"
        return [row["country"] for row in self.db.fetch_all(query, (product_id,))]

    def product(self, product_id):
        return self.db.fetch_one(
            "SELECT id, sku, name FROM products WHERE id = %s", (product_id,)
        )

    # -------------------------------------------------------------- materials
    def materials_breakdown(self, product_id, country):
        """BOM lines for (product, country) joined to each input's latest USD unit
        cost. ``unit_usd_cents`` is the most recent purchase's usd_amount_cents per
        unit of quantity, or NULL when the input has never been purchased (which
        makes the materials component pending, never summed as zero)."""
        query = """
            SELECT b.cost_input_id AS cost_input_id,
                   ci.name AS name,
                   b.quantity AS quantity,
                   (SELECT ip.usd_amount_cents * 1.0 / ip.quantity
                      FROM input_purchases ip
                     WHERE ip.cost_input_id = b.cost_input_id
                       AND ip.quantity > 0
                     ORDER BY ip.purchased_at DESC, ip.id DESC
                     LIMIT 1) AS unit_usd_cents
            FROM bom_lines b
            JOIN cost_inputs ci ON ci.id = b.cost_input_id
            WHERE b.product_id = %s AND b.country = %s
            ORDER BY ci.name
        """
        return self.db.fetch_all(query, (product_id, country))

    # ------------------------------------------------------- other components
    def labor_cost(self, product_id, country):
        query = """
            SELECT batch_payment_cents, units_completed
            FROM labor_costs
            WHERE product_id = %s AND country = %s
            ORDER BY recorded_at DESC, id DESC
            LIMIT 1
        """
        return self.db.fetch_one(query, (product_id, country))

    def packaging_cost(self, product_id, country):
        query = """
            SELECT usd_amount_cents
            FROM packaging_costs
            WHERE product_id = %s AND country = %s
            ORDER BY id DESC
            LIMIT 1
        """
        return self.db.fetch_one(query, (product_id, country))

    def shipping_lane(self, product_id, country):
        query = """
            SELECT usd_amount_cents, note
            FROM shipping_lanes
            WHERE product_id = %s AND country = %s
            ORDER BY id DESC
            LIMIT 1
        """
        return self.db.fetch_one(query, (product_id, country))

    def customs_duty(self, product_id, country):
        query = """
            SELECT usd_amount_cents, note
            FROM customs_duties
            WHERE product_id = %s AND country = %s
            ORDER BY id DESC
            LIMIT 1
        """
        return self.db.fetch_one(query, (product_id, country))

    def indirect_latest(self, country):
        """The most recent indirect pool for a country. units_produced NULL or 0
        means indirect allocation is pending for that month (no divide by zero)."""
        query = """
            SELECT period_month, pool_cents, units_produced
            FROM indirect_costs
            WHERE country = %s
            ORDER BY period_month DESC, id DESC
            LIMIT 1
        """
        return self.db.fetch_one(query, (country,))

    # ----------------------------------------------------- input purchases (AC7)
    @staticmethod
    def usd_cents_from(original_amount_cents: int, fx_rate: float) -> int:
        """Normalize an original-currency cents amount to USD cents at fx_rate.

        fx_rate is units of the original currency per 1 USD (e.g. 4000 COP/USD),
        so usd_cents = original_amount_cents / fx_rate, rounded to the cent."""
        if fx_rate <= 0:
            raise ValueError("fx_rate must be positive")
        return round(original_amount_cents / fx_rate)

    def record_input_purchase(
        self,
        *,
        cost_input_id: int,
        original_currency: str,
        original_amount_cents: int,
        fx_rate: float,
        quantity: float = 1,
        supplier_id=None,
        purchased_at=None,
    ) -> int:
        """Append one input purchase. The derived usd_amount_cents is stored
        alongside the original amount and rate (AC7 audit trail). This is
        append-only: a correction is a new call (a new row); no existing row is
        ever mutated. Returns the derived usd_amount_cents."""
        usd_amount_cents = self.usd_cents_from(original_amount_cents, fx_rate)
        from datetime import date

        query = """
            INSERT INTO input_purchases
              (cost_input_id, supplier_id, original_currency, original_amount_cents,
               fx_rate, usd_amount_cents, quantity, purchased_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        self.db.execute(
            query,
            (
                cost_input_id,
                supplier_id,
                original_currency,
                original_amount_cents,
                fx_rate,
                usd_amount_cents,
                quantity,
                purchased_at or date.today().isoformat(),
            ),
        )
        return usd_amount_cents

    def list_input_purchases(self, cost_input_id):
        """All purchases for an input, newest first (append-only history)."""
        query = """
            SELECT id, original_currency, original_amount_cents, fx_rate,
                   usd_amount_cents, quantity, purchased_at
            FROM input_purchases
            WHERE cost_input_id = %s
            ORDER BY purchased_at DESC, id DESC
        """
        return self.db.fetch_all(query, (cost_input_id,))
