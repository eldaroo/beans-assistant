# Guía de Migración: Base de Datos en Español

## Problema Identificado

Cuando preguntas "¿cuántas pulseras negras hay?", el sistema falla porque:

1. ❌ Los nombres de productos están en **inglés**: `"Coffee Bean Bracelet - Black"`
2. ❌ La view `stock_current` **no existe** en tu base de datos
3. ❌ El agente busca "pulsera negra" en nombres en inglés

## Solución: Migrar a Español

Migrar completamente la base de datos a español con:
- Nombres de tablas en español
- Nombres de columnas en español
- Nombres de productos en español
- Todas las views creadas correctamente

---

## Opción 1: Migración Completa (Recomendada)

### Paso 1: Backup Actual

```bash
# El script hace backup automático, pero por seguridad:
cp beansco.db beansco_backup_manual.db
```

### Paso 2: Ejecutar Migración

```bash
python migrate_to_spanish.py
```

Esto hará:
- ✅ Backup automático de `beansco.db`
- ✅ Crear nueva base de datos `beansco_es.db` con schema en español
- ✅ Migrar todos tus datos existentes
- ✅ Traducir nombres de productos automáticamente
- ✅ Crear todas las views necesarias

### Paso 3: Activar Nueva Base de Datos

#### Opción A: Renombrar (Recomendada)

```bash
# Windows
move beansco.db beansco_en.db
move beansco_es.db beansco.db

# Linux/Mac
mv beansco.db beansco_en.db
mv beansco_es.db beansco.db
```

#### Opción B: Usar Directamente

```bash
python graph.py --db sqlite:///beansco_es.db
```

### Paso 4: Verificar

```bash
python graph.py
```

Prueba:
```
You> ¿cuántas pulseras negras hay?
```

Debería funcionar correctamente ahora.

---

## Opción 2: Base de Datos Nueva en Español

Si prefieres empezar de cero con datos en español:

### Paso 1: Crear Nueva BD

```bash
sqlite3 beansco_es.db < schema_spanish.sql
```

### Paso 2: Usar la Nueva BD

```bash
# Renombrar
mv beansco.db beansco_old.db
mv beansco_es.db beansco.db

# O usar directamente
python graph.py --db sqlite:///beansco_es.db
```

---

## Opción 3: Solo Arreglar Views (Mínimo)

Si solo quieres que funcione sin migrar todo:

### Paso 1: Crear las Views Faltantes

```bash
python apply_views.py
```

Esto crea:
- `stock_current`
- `profit_summary`
- `revenue_paid`
- `expenses_total`

### Paso 2: Actualizar Nombres de Productos

Ejecuta esto en SQLite:

```sql
sqlite3 beansco.db

-- Actualizar productos a español
UPDATE products SET name = 'Pulsera de Granos de Café - Clásica' WHERE sku = 'BC-BRACELET-CLASSIC';
UPDATE products SET name = 'Pulsera de Granos de Café - Negra' WHERE sku = 'BC-BRACELET-BLACK';
UPDATE products SET name = 'Pulsera de Granos de Café - Dorada' WHERE sku = 'BC-BRACELET-GOLD';
UPDATE products SET name = 'Llavero de Granos de Café' WHERE sku = 'BC-KEYCHAIN';

-- Actualizar descripciones
UPDATE products SET description = 'Pulsera artesanal con granos de café' WHERE sku = 'BC-BRACELET-CLASSIC';
UPDATE products SET description = 'Cordón negro, granos de café' WHERE sku = 'BC-BRACELET-BLACK';
UPDATE products SET description = 'Acentos dorados + granos de café' WHERE sku = 'BC-BRACELET-GOLD';
UPDATE products SET description = 'Llavero hecho con granos de café' WHERE sku = 'BC-KEYCHAIN';

.quit
```

---

## Comparación de Schemas

### Inglés (Actual)

```sql
-- Tablas
products
stock_movements
sales
sale_items
expenses

-- Views
stock_current
profit_summary
revenue_paid
expenses_total
```

### Español (Nuevo)

```sql
-- Tablas
productos
movimientos_stock
ventas
items_venta
gastos

-- Vistas
stock_actual
resumen_ganancias
ingresos_pagados
total_gastos
resumen_ventas
```

---

## Verificación Post-Migración

### 1. Verificar Tablas

```bash
sqlite3 beansco.db "SELECT name FROM sqlite_master WHERE type='table';"
```

Deberías ver:
```
productos
movimientos_stock
ventas
items_venta
gastos
```

### 2. Verificar Views

```bash
sqlite3 beansco.db "SELECT name FROM sqlite_master WHERE type='view';"
```

Deberías ver:
```
stock_actual
resumen_ganancias
ingresos_pagados
total_gastos
resumen_ventas
```

### 3. Verificar Productos

```bash
sqlite3 beansco.db "SELECT sku, nombre FROM productos LIMIT 5;"
```

Deberías ver:
```
BC-PULSERA-CLASICA|Pulsera de Granos de Café - Clásica
BC-PULSERA-NEGRA|Pulsera de Granos de Café - Negra
BC-PULSERA-DORADA|Pulsera de Granos de Café - Dorada
BC-LLAVERO|Llavero de Granos de Café
```

### 4. Verificar Stock

```bash
sqlite3 beansco.db "SELECT sku, nombre, cantidad_stock FROM stock_actual;"
```

---

## Pruebas Después de Migración

### Pruebas en Modo Interactivo

```bash
python graph.py
```

Prueba estos comandos:

```
# Consultas en español
You> ¿cuántas pulseras negras hay?
You> ¿cuántas pulseras tengo de cada tipo?
You> ¿cuál es mi ganancia total?
You> muéstrame todos los productos

# Operaciones
You> registrame una venta de 5 pulseras negras
You> gasté 50 dólares en marketing ayer
You> agregar 100 unidades de pulseras clásicas

# Mixto
You> vendí 2 pulseras doradas, ¿cómo queda el stock?
```

---

## Traducciones Automáticas

El script de migración traduce automáticamente:

### Nombres de Productos

| Inglés | Español |
|--------|---------|
| Coffee Bean Bracelet - Classic | Pulsera de Granos de Café - Clásica |
| Coffee Bean Bracelet - Black | Pulsera de Granos de Café - Negra |
| Coffee Bean Bracelet - Gold | Pulsera de Granos de Café - Dorada |
| Coffee Bean Keychain | Llavero de Granos de Café |

### Tipos de Movimiento

| Inglés | Español |
|--------|---------|
| IN | ENTRADA |
| OUT | SALIDA |
| ADJUSTMENT | AJUSTE |

### Estados de Venta

| Inglés | Español |
|--------|---------|
| PAID | PAGADO |
| PENDING | PENDIENTE |
| CANCELLED | CANCELADO |

### Categorías de Gastos

| Inglés | Español |
|--------|---------|
| Materials | Materiales |
| Packaging | Empaque |
| Marketing | Marketing |
| Shipping | Envíos |

---

## Actualización del Código (Opcional)

Si quieres que el código use la BD en español por defecto:

### 1. Actualizar `database.py`

Cambiar referencias de tablas:
```python
# Antes
"SELECT * FROM products WHERE ..."

# Después
"SELECT * FROM productos WHERE ..."
```

### 2. Actualizar `agents/read_agent.py`

El prompt ya soporta ambos idiomas, pero puedes cambiar los ejemplos.

---

## Rollback (Si algo sale mal)

### Si usaste Opción 1 (Migración):

```bash
# Restaurar backup
cp beansco_backup_YYYYMMDD_HHMMSS.db beansco.db
```

### Si usaste Opción 2 (Nueva BD):

```bash
# Volver a la antigua
mv beansco_old.db beansco.db
```

---

## Recomendaciones

### Para Producción

✅ **Usa Opción 1** (Migración completa)
- Preserva todos tus datos
- Migración limpia y verificada
- Backup automático

### Para Desarrollo/Testing

✅ **Usa Opción 2** (Nueva BD)
- Datos frescos en español
- Esquema limpio
- Fácil de resetear

### Para Arreglo Rápido

✅ **Usa Opción 3** (Solo views y nombres)
- Mantiene estructura actual
- Solo arregla lo mínimo necesario
- Menos riesgo

---

## FAQ

### ¿Perderé mis datos?

❌ No, el script hace backup automático y migra todos los datos.

### ¿Puedo mantener ambas bases de datos?

✅ Sí, puedes tener `beansco.db` (inglés) y `beansco_es.db` (español) y elegir cuál usar.

### ¿El multi-agente funciona con ambos idiomas?

✅ Sí, los prompts soportan ambos idiomas. El agente detecta automáticamente qué idioma usa la BD.

### ¿Qué pasa con mis business actions?

✅ Las funciones Python (`register_sale`, etc.) funcionan con ambos esquemas. Solo hay que pasar los nombres de columnas correctos.

### ¿Puedo hacer la migración gradualmente?

⚠️ No es recomendado. Es mejor hacer la migración completa de una vez para evitar inconsistencias.

---

## Soporte

Si tienes problemas:

1. Revisa los backups: `beansco_backup_*.db`
2. Verifica las views: `python apply_views.py`
3. Prueba con `verify_setup.py`
4. Consulta logs de migración

---

## Siguiente Paso

**Recomendación**: Ejecuta la Opción 1 (Migración Completa)

```bash
python migrate_to_spanish.py
```

Luego activa la nueva BD y prueba:

```bash
mv beansco.db beansco_en.db
mv beansco_es.db beansco.db
python graph.py
```

```
You> ¿cuántas pulseras negras hay?
```

Debería funcionar perfectamente. ✨
