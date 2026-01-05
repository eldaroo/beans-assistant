# Verificación de Cálculos - Beans&Co

## Resumen de Verificación

**Fecha:** 2026-01-03
**Estado:** ✅ TODOS LOS CÁLCULOS CORRECTOS

## Fórmulas Utilizadas

### 1. Revenue (Ingresos)
```sql
SELECT SUM(total_amount_cents) / 100.0 as revenue_usd
FROM sales
WHERE status = 'PAID'
```
**Estado:** ✅ CORRECTO

### 2. Expenses (Gastos)
```sql
SELECT SUM(amount_cents) / 100.0 as expenses_usd
FROM expenses
```
**Estado:** ✅ CORRECTO

### 3. Profit (Ganancia/Pérdida)
```sql
SELECT ROUND(
    (COALESCE((SELECT revenue_usd FROM revenue_paid), 0) -
     COALESCE((SELECT expenses_usd FROM expenses_total), 0)),
    2
) AS profit_usd
```
**Fórmula:** `Profit = Revenue - Expenses`

**Nota:** La vista NO incluye COGS (Cost of Goods Sold) porque el sistema no trackea el costo de los productos al momento de la venta. Solo se resta el total de gastos registrados.

**Estado:** ✅ CORRECTO

## Resultados de Prueba

### Base de Datos Principal (beansco.db)
- **Revenue:** $2,625.00
- **Expenses:** $11,176.00
- **Profit:** -$8,551.00
- **Estado:** PÉRDIDA

### Base de Datos Multi-Tenant (+5491153695627)
- **Revenue:** $2,317.00
- **Expenses:** $11,176.00
- **Profit:** -$8,859.00
- **Estado:** PÉRDIDA

## Problema Reportado y Solución

### Problema
Usuario reportó inconsistencia:
1. Sistema dijo "No hay gastos registrados" cuando preguntó "y mis gastos?"
2. Pero después mostró pérdida de $8,751, lo cual solo es posible con ~$11,000 en gastos

### Causa Raíz
El LLM pudo haber extraído incorrectamente un `time_period` (ej: "hoy") que filtró todos los gastos históricos (que son de diciembre 2025).

### Solución Implementada
1. **Mejor manejo de respuestas vacías:** Ahora cuando la query de gastos retorna 0 resultados, el sistema verifica si hay gastos en total. Si los hay, avisa:
   ```
   "No encontré gastos en el período consultado,
   pero hay X gastos en total.
   ¿Querés ver todos los gastos?"
   ```

2. **Debug logging:** Agregado logging para diagnosticar queries:
   ```python
   print(f"[DEBUG] Query Type: {query_type}")
   print(f"[DEBUG] Entities: {entities}")
   print(f"[DEBUG] SQL: {sql_query}")
   print(f"[DEBUG] Rows returned: {len(rows)}")
   ```

3. **Script de verificación:** Creado `verify_calculations.py` para verificar todos los cálculos en todas las bases de datos.

## Comando de Verificación

Para verificar todos los cálculos en cualquier momento:
```bash
python verify_calculations.py
```

Esto verificará:
- Revenue calculation (view vs direct query)
- Expenses calculation (view vs direct query)
- Profit calculation (formula correctness)
- Listado de gastos recientes
- Estado de cada base de datos

## Conclusión

✅ Los cálculos de profit, revenue y expenses están correctos
✅ Las vistas SQL funcionan correctamente
✅ Se agregaron safeguards para prevenir confusión del usuario
✅ Se agregó debugging para diagnosticar issues futuros
