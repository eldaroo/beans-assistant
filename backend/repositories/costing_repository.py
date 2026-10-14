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

    def sale_price_cents(self, product_id):
        """The product's sale price in USD cents, or None when no price is set
        yet (price pending). Read for the margin compute (AC9); a margin is shown
        only when a price exists AND the landed cost is complete, so a missing
        price makes the margin pending, never a false figure."""
        row = self.db.fetch_one(
            "SELECT unit_price_cents FROM products WHERE id = %s", (product_id,)
        )
        if not row:
            return None
        return row["unit_price_cents"]

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

    # (M2's indirect_latest, which read the hand-entered units_produced column,
    # was removed in M4: the denominator now comes from production_records via
    # indirect_pool_latest + ProductionRepository.weekly_units. See D-M4-1.)

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

    # ---------------------------------------------- cost-input write paths (M3)
    def record_cost_input(self, *, name: str, category: str, unit: str = "u") -> int:
        """Create a cost input (one of the BOM categories: cafe, tostado, madera,
        hilo, piedras, broches) and return its id (T-012). RETURNING works on both
        Postgres and the modern SQLite the repo runs on (see products create)."""
        query = """
            INSERT INTO cost_inputs (name, category, unit)
            VALUES (%s, %s, %s)
            RETURNING id
        """
        row = self.db.fetch_one(query, (name, category, unit))
        return int(row["id"])

    def record_bom_line(self, *, product_id: int, cost_input_id: int, country: str, quantity: float) -> None:
        """Add a BOM line: how many of an input go into one bracelet of a type in
        a country (T-012). The materials component sums every BOM line's quantity
        times that input's latest USD unit cost."""
        query = """
            INSERT INTO bom_lines (product_id, cost_input_id, country, quantity)
            VALUES (%s, %s, %s, %s)
        """
        self.db.execute(query, (product_id, cost_input_id, country, quantity))

    def record_packaging_cost(self, *, product_id: int, country: str, usd_amount_cents: int) -> None:
        """Record the per-unit packaging cost for a bracelet type in a country
        (T-012). Newest row wins in the landed-cost read."""
        query = """
            INSERT INTO packaging_costs (product_id, country, usd_amount_cents)
            VALUES (%s, %s, %s)
        """
        self.db.execute(query, (product_id, country, usd_amount_cents))

    # ----------------------------------------------------- labor write path (M3)
    def record_labor_batch(
        self, *, product_id: int, country: str, batch_payment_cents: int, units_completed: int
    ) -> None:
        """Record a direct-labor batch payment over the units actually completed
        (T-013, AC11 completed basis). Per-unit labor is the payment divided by
        units COMPLETED, not planned, so a short batch raises the per-unit cost.
        Append-only: a correction is a new row, newest wins in the landed read."""
        query = """
            INSERT INTO labor_costs (product_id, country, batch_payment_cents, units_completed)
            VALUES (%s, %s, %s, %s)
        """
        self.db.execute(query, (product_id, country, batch_payment_cents, units_completed))

    # --------------------------------------- logistics write paths (M4, T-016)
    def record_shipping_lane(self, *, product_id: int, country: str, usd_amount_cents=None, note=None) -> None:
        """Record a shipping lane for a bracelet type into a country (T-016).
        ``usd_amount_cents`` None means the lane exists but is not yet priced
        (pending, never summed as zero); ``note`` carries the carrier or quote
        context. Append-only, newest row wins in the landed-cost read."""
        query = """
            INSERT INTO shipping_lanes (product_id, country, usd_amount_cents, note)
            VALUES (%s, %s, %s, %s)
        """
        self.db.execute(query, (product_id, country, usd_amount_cents, note))

    def record_customs_duty(self, *, product_id: int, country: str, usd_amount_cents=None, note=None) -> None:
        """Record a customs duty for a bracelet type entering a country (T-016).
        ``usd_amount_cents`` None means the duty is not yet known (pending, the
        pending-customs attention signal reads exactly this); ``note`` carries the
        HS code or broker context. Append-only, newest row wins."""
        query = """
            INSERT INTO customs_duties (product_id, country, usd_amount_cents, note)
            VALUES (%s, %s, %s, %s)
        """
        self.db.execute(query, (product_id, country, usd_amount_cents, note))

    # -------------------------------------------- indirect pool write path (M4)
    def record_indirect_pool(self, *, country: str, period_month: str, pool_cents: int) -> None:
        """Record the indirect-cost POOL (display stands plus overhead) for a
        country in a calendar month (T-014, AC12). The per-unit allocation is the
        pool divided by the units PRODUCED in that country that month, and those
        units are derived from production_records at compute time, never stored
        here (D-M3-9: attribute units by production period, not data-entry date).
        ``units_produced`` on the row is left NULL and is no longer read; it stays
        on the table for the M2/M3 schema compatibility. Append-only: a correction
        is a new row, newest wins (ORDER BY id DESC in the read)."""
        query = """
            INSERT INTO indirect_costs (country, period_month, pool_cents, units_produced)
            VALUES (%s, %s, %s, NULL)
        """
        self.db.execute(query, (country, period_month, pool_cents))

    def indirect_pool_latest(self, country):
        """The most recent indirect POOL for a country: its period_month and
        pool_cents, newest row wins. None when no pool was ever recorded (the
        indirect component is then pending: 'sin pool indirecto cargado'). The
        units-produced denominator is derived from production_records for that
        same month by the service, not read from this row (M4)."""
        query = """
            SELECT period_month, pool_cents
            FROM indirect_costs
            WHERE country = %s
            ORDER BY period_month DESC, id DESC
            LIMIT 1
        """
        return self.db.fetch_one(query, (country,))
