PRAGMA foreign_keys = ON;

-- Drop (para reiniciar fácil)
DROP TABLE IF EXISTS items_venta;
DROP TABLE IF EXISTS ventas;
DROP TABLE IF EXISTS movimientos_stock;
DROP TABLE IF EXISTS gastos;
DROP TABLE IF EXISTS productos;

-- PRODUCTOS
CREATE TABLE productos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sku TEXT NOT NULL UNIQUE,
  nombre TEXT NOT NULL,
  descripcion TEXT,
  costo_unitario_centavos INTEGER NOT NULL CHECK (costo_unitario_centavos >= 0),
  precio_unitario_centavos INTEGER NOT NULL CHECK (precio_unitario_centavos >= 0),
  esta_activo INTEGER NOT NULL DEFAULT 1,
  creado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

-- MOVIMIENTOS DE STOCK
-- tipo_movimiento: ENTRADA | SALIDA | AJUSTE
CREATE TABLE movimientos_stock (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  producto_id INTEGER NOT NULL,
  tipo_movimiento TEXT NOT NULL CHECK (tipo_movimiento IN ('ENTRADA','SALIDA','AJUSTE')),
  cantidad INTEGER NOT NULL CHECK (cantidad <> 0),
  razon TEXT,
  referencia TEXT,
  ocurrido_en TEXT NOT NULL DEFAULT (datetime('now')),
  creado_en TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (producto_id) REFERENCES productos(id)
);

-- VENTAS
-- estado: PAGADO | PENDIENTE | CANCELADO
CREATE TABLE ventas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  numero_venta TEXT NOT NULL UNIQUE,
  nombre_cliente TEXT,
  estado TEXT NOT NULL CHECK (estado IN ('PAGADO','PENDIENTE','CANCELADO')),
  moneda TEXT NOT NULL DEFAULT 'USD',
  monto_total_centavos INTEGER NOT NULL CHECK (monto_total_centavos >= 0),
  creado_en TEXT NOT NULL DEFAULT (datetime('now')),
  pagado_en TEXT
);

-- ITEMS DE VENTA
CREATE TABLE items_venta (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  venta_id INTEGER NOT NULL,
  producto_id INTEGER NOT NULL,
  cantidad INTEGER NOT NULL CHECK (cantidad > 0),
  precio_unitario_centavos INTEGER NOT NULL CHECK (precio_unitario_centavos >= 0),
  total_linea_centavos INTEGER NOT NULL CHECK (total_linea_centavos >= 0),
  creado_en TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (venta_id) REFERENCES ventas(id),
  FOREIGN KEY (producto_id) REFERENCES productos(id)
);

-- GASTOS
CREATE TABLE gastos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha_gasto TEXT NOT NULL DEFAULT (date('now')),
  categoria TEXT NOT NULL,
  descripcion TEXT,
  monto_centavos INTEGER NOT NULL CHECK (monto_centavos >= 0),
  moneda TEXT NOT NULL DEFAULT 'USD',
  creado_en TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =========================
-- VISTAS (VIEWS)
-- =========================

-- Stock actual por producto desde movimientos
CREATE VIEW stock_actual AS
SELECT
  p.id AS producto_id,
  p.sku,
  p.nombre,
  COALESCE(SUM(
    CASE
      WHEN m.tipo_movimiento IN ('ENTRADA','AJUSTE') THEN m.cantidad
      WHEN m.tipo_movimiento = 'SALIDA' THEN -m.cantidad
      ELSE 0
    END
  ), 0) AS cantidad_stock
FROM productos p
LEFT JOIN movimientos_stock m ON m.producto_id = p.id
GROUP BY p.id, p.sku, p.nombre;

-- Resumen de ventas pagadas por día
CREATE VIEW resumen_ventas AS
SELECT
  date(COALESCE(pagado_en, creado_en)) AS dia,
  COUNT(*) AS cantidad_ventas_pagadas,
  SUM(monto_total_centavos) AS ingresos_pagados_centavos
FROM ventas
WHERE estado = 'PAGADO'
GROUP BY date(COALESCE(pagado_en, creado_en))
ORDER BY dia DESC;

-- Ingresos totales (solo ventas PAGADAS)
CREATE VIEW ingresos_pagados AS
SELECT
  SUM(monto_total_centavos) AS total_ingresos_centavos,
  ROUND(SUM(monto_total_centavos) / 100.0, 2) AS ingresos_usd
FROM ventas
WHERE estado = 'PAGADO';

-- Total de gastos
CREATE VIEW total_gastos AS
SELECT
  SUM(monto_centavos) AS total_gastos_centavos,
  ROUND(SUM(monto_centavos) / 100.0, 2) AS gastos_usd
FROM gastos;

-- Resumen de ganancias (profit)
CREATE VIEW resumen_ganancias AS
SELECT
  ROUND(
    (COALESCE((SELECT ingresos_usd FROM ingresos_pagados), 0) -
     COALESCE((SELECT gastos_usd FROM total_gastos), 0)),
    2
  ) AS ganancia_usd;

-- =========================
-- DATOS DE EJEMPLO
-- =========================

INSERT INTO productos (sku, nombre, descripcion, costo_unitario_centavos, precio_unitario_centavos) VALUES
('BC-PULSERA-CLASICA', 'Pulsera de Granos de Café - Clásica', 'Pulsera artesanal con granos de café', 350, 1200),
('BC-PULSERA-NEGRA',   'Pulsera de Granos de Café - Negra',   'Cordón negro, granos de café',           400, 1400),
('BC-PULSERA-DORADA',  'Pulsera de Granos de Café - Dorada',  'Acentos dorados + granos de café',       550, 2000),
('BC-LLAVERO',         'Llavero de Granos de Café',           'Llavero hecho con granos de café',       200, 800);

-- Stock inicial (ENTRADA)
INSERT INTO movimientos_stock (producto_id, tipo_movimiento, cantidad, razon, referencia, ocurrido_en) VALUES
(1, 'ENTRADA',  50, 'Stock inicial', 'INIT-001', datetime('now','-20 days')),
(2, 'ENTRADA',  40, 'Stock inicial', 'INIT-001', datetime('now','-20 days')),
(3, 'ENTRADA',  25, 'Stock inicial', 'INIT-001', datetime('now','-20 days')),
(4, 'ENTRADA',  60, 'Stock inicial', 'INIT-001', datetime('now','-20 days'));

-- Gastos
INSERT INTO gastos (fecha_gasto, categoria, descripcion, monto_centavos, moneda) VALUES
(date('now','-18 days'), 'Materiales', 'Lote de granos de café A', 12000, 'USD'),
(date('now','-17 days'), 'Empaque', 'Cajas y etiquetas', 4500, 'USD'),
(date('now','-10 days'), 'Marketing', 'Anuncios en Instagram', 8000, 'USD'),
(date('now','-5 days'),  'Envíos',  'Recarga de cuenta de mensajería', 3000, 'USD');

-- Ventas + items + stock SALIDA
INSERT INTO ventas (numero_venta, nombre_cliente, estado, moneda, monto_total_centavos, creado_en, pagado_en) VALUES
('V-1001', 'Ana',   'PAGADO',     'USD', 2600, datetime('now','-12 days'), datetime('now','-12 days')),
('V-1002', 'Luis',  'PAGADO',     'USD', 1400, datetime('now','-8 days'),  datetime('now','-8 days')),
('V-1003', 'Mia',   'PENDIENTE',  'USD', 2000, datetime('now','-3 days'),  NULL),
('V-1004', 'João',  'CANCELADO',  'USD', 1200, datetime('now','-2 days'),  NULL),
('V-1005', 'Sofi',  'PAGADO',     'USD', 3200, datetime('now','-1 days'),  datetime('now','-1 days'));

-- Items para V-1001 (2 clásicas + 1 llavero)
INSERT INTO items_venta (venta_id, producto_id, cantidad, precio_unitario_centavos, total_linea_centavos) VALUES
(1, 1, 2, 1200, 2400),
(1, 4, 1,  800,  800);

-- Items para V-1002 (1 negra)
INSERT INTO items_venta (venta_id, producto_id, cantidad, precio_unitario_centavos, total_linea_centavos) VALUES
(2, 2, 1, 1400, 1400);

-- Items para V-1003 pendiente (1 dorada)
INSERT INTO items_venta (venta_id, producto_id, cantidad, precio_unitario_centavos, total_linea_centavos) VALUES
(3, 3, 1, 2000, 2000);

-- Items para V-1004 cancelada (1 clásica)
INSERT INTO items_venta (venta_id, producto_id, cantidad, precio_unitario_centavos, total_linea_centavos) VALUES
(4, 1, 1, 1200, 1200);

-- Items para V-1005 pagada (2 negras + 1 clásica)
INSERT INTO items_venta (venta_id, producto_id, cantidad, precio_unitario_centavos, total_linea_centavos) VALUES
(5, 2, 2, 1400, 2800),
(5, 1, 1, 1200, 1200);

-- Stock SALIDA para ventas PAGADAS solamente
INSERT INTO movimientos_stock (producto_id, tipo_movimiento, cantidad, razon, referencia, ocurrido_en) VALUES
(1, 'SALIDA', 2, 'Venta V-1001', 'V-1001', datetime('now','-12 days')),
(4, 'SALIDA', 1, 'Venta V-1001', 'V-1001', datetime('now','-12 days')),
(2, 'SALIDA', 1, 'Venta V-1002', 'V-1002', datetime('now','-8 days')),
(2, 'SALIDA', 2, 'Venta V-1005', 'V-1005', datetime('now','-1 days')),
(1, 'SALIDA', 1, 'Venta V-1005', 'V-1005', datetime('now','-1 days'));
