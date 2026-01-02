-- Initialize Database Schema for Beans&Co Business Assistant
-- Run this with: sqlite3 beansco.db < init_database.sql

-- Drop existing tables if they exist (optional, comment out if you want to keep data)
-- DROP TABLE IF EXISTS stock_movements;
-- DROP TABLE IF EXISTS sale_items;
-- DROP TABLE IF EXISTS sales;
-- DROP TABLE IF EXISTS expenses;
-- DROP TABLE IF EXISTS products;

-- Products table
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    unit_price_cents INTEGER NOT NULL,
    unit_cost_cents INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sales table
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_number TEXT UNIQUE NOT NULL,
    total_amount_cents INTEGER NOT NULL,
    status TEXT DEFAULT 'PAID' CHECK(status IN ('PAID', 'PENDING', 'CANCELLED')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sale items table
CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    line_total_cents INTEGER NOT NULL,
    FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- Stock movements table
CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    movement_type TEXT NOT NULL CHECK(movement_type IN ('IN', 'OUT', 'ADJUSTMENT')),
    quantity INTEGER NOT NULL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- Expenses table
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_date DATE DEFAULT (date('now')),
    category TEXT DEFAULT 'GENERAL',
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency TEXT DEFAULT 'USD',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_sales_created_at ON sales(created_at);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale_id ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_product_id ON sale_items(product_id);
CREATE INDEX IF NOT EXISTS idx_stock_movements_product_id ON stock_movements(product_id);
CREATE INDEX IF NOT EXISTS idx_expenses_expense_date ON expenses(expense_date);

-- Create views for common queries
CREATE VIEW IF NOT EXISTS stock_current AS
SELECT
    p.id AS product_id,
    p.sku,
    p.name,
    COALESCE(SUM(CASE
        WHEN sm.movement_type = 'IN' THEN sm.quantity
        WHEN sm.movement_type = 'OUT' THEN -sm.quantity
        WHEN sm.movement_type = 'ADJUSTMENT' THEN sm.quantity
    END), 0) AS stock_qty
FROM products p
LEFT JOIN stock_movements sm ON p.id = sm.product_id
GROUP BY p.id, p.sku, p.name;

CREATE VIEW IF NOT EXISTS revenue_paid AS
SELECT
    COALESCE(SUM(total_amount_cents), 0) AS total_revenue_cents
FROM sales
WHERE status = 'PAID';

CREATE VIEW IF NOT EXISTS profit_summary AS
SELECT
    COALESCE(
        (SELECT SUM(total_amount_cents) FROM sales WHERE status = 'PAID'),
        0
    ) / 100.0 - COALESCE(
        (SELECT SUM(amount_cents) FROM expenses),
        0
    ) / 100.0 AS profit_usd;

-- Insert default products (Beans&Co bracelets)
INSERT OR IGNORE INTO products (sku, name, description, unit_price_cents, unit_cost_cents)
VALUES
    ('BC-BRACELET-CLASSIC', 'Pulsera de Granos de Café - Clásica', 'Pulsera artesanal hecha con granos de café', 1200, 400),
    ('BC-BRACELET-BLACK', 'Pulsera de Granos de Café - Negra', 'Pulsera artesanal de granos de café negros', 1400, 450),
    ('BC-BRACELET-GOLD', 'Pulsera de Granos de Café - Dorada', 'Pulsera artesanal de granos de café dorados', 1600, 500),
    ('BC-KEYCHAIN', 'Llavero de Granos de Café', 'Llavero artesanal hecho con granos de café', 800, 250);

-- Add initial stock (optional - adjust quantities as needed)
INSERT OR IGNORE INTO stock_movements (product_id, movement_type, quantity, reason)
SELECT id, 'IN', 0, 'Initial stock'
FROM products;

-- Verification queries (run these after to check)
-- SELECT 'Tables created:' AS status;
-- SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
-- SELECT 'Products:' AS status;
-- SELECT * FROM products;
-- SELECT 'Stock:' AS status;
-- SELECT * FROM stock_current;
