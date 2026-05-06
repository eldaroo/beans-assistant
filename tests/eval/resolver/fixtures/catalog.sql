-- Extra products for the resolver eval, layered on top of the four
-- baseline products that init_complete_database.sql already seeds:
-- BC-BRACELET-CLASSIC, BC-BRACELET-BLACK, BC-BRACELET-GOLD, BC-KEYCHAIN.
--
-- The eval asserts results by resolved_sku, never by autoincrement id,
-- so adding/removing products here only affects the cases that name
-- those SKUs in their `expected` block.

INSERT INTO products (sku, name, description, unit_price_cents, unit_cost_cents) VALUES
    ('BC-BRACELET-RAINBOW',   'Pulsera de Granos de Café - Arcoíris',  'Pulsera artesanal multicolor',          1800, 600),
    ('BC-BRACELET-TURQUOISE', 'Pulseras Turquesas',                    'Pulsera artesanal turquesa',            1500, 480),
    ('BC-BRACELET-PURPLE',    'Pulseras Moradas',                      'Pulsera artesanal morada',              1500, 480),
    ('BC-BRACELET-WHITE',     'Pulseras Blancas',                      'Pulsera artesanal blanca',              1500, 480),
    ('BC-BRACELET-PINK',      'Pulseras Rosas',                        'Pulsera artesanal rosa',                1500, 480),
    ('BC-BRACELET-GREEN',     'Pulseras Verdes',                       'Pulsera artesanal verde',               1500, 480),
    ('BC-BRACELET-BLUE',      'Pulseras Azules',                       'Pulsera artesanal azul',                1500, 480),
    ('BC-NECKLACE-CLASSIC',   'Collar Clásico',                        'Collar artesanal clásico',              2500, 900),
    ('BC-EARRINGS-SILVER',    'Aros Plateados',                        'Aros artesanales plateados',            2200, 750);
