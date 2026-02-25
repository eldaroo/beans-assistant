# Guía de Edición de Stock

## Nueva Funcionalidad: Editar Cantidad de Stock en Línea

Ahora puedes editar directamente la cantidad de stock de cada producto desde la tabla de Stock.

## 🎯 Cómo Usar

### Editar Stock Directamente:

1. **Ve al tab "Stock"** en el dashboard de un tenant
2. **Click en "Edit Qty"** en la fila del producto que quieres modificar
3. **Aparecerá un campo de entrada** con la cantidad actual
4. **Ingresa la nueva cantidad** (puede ser mayor o menor)
5. **Guarda los cambios**:
   - Click en el botón verde ✓ (check) para guardar
   - Presiona **Enter** para guardar rápido
   - Click en el botón X para cancelar
   - Presiona **Escape** para cancelar rápido

### Ejemplos:

#### Aumentar Stock
- Stock actual: **10**
- Modificas a: **25**
- Resultado: Se agregan **+15** unidades
- Razón registrada: "Manual adjustment (increase)"

#### Disminuir Stock
- Stock actual: **50**
- Modificas a: **30**
- Resultado: Se quitan **-20** unidades
- Razón registrada: "Manual adjustment (decrease)"

#### Ajustar a Cero
- Stock actual: **5**
- Modificas a: **0**
- Resultado: Se quitan **-5** unidades
- Útil para corregir inventario o marcar productos sin stock

## 📋 Características

- ✅ **Edición en línea**: No necesitas abrir modal ni cambiar de página
- ✅ **Validación automática**: Solo acepta números positivos (incluyendo 0)
- ✅ **Atajos de teclado**: Enter para guardar, Escape para cancelar
- ✅ **Feedback visual**: Botones con íconos claros
- ✅ **Tracking automático**: Cada cambio se registra en el historial de movimientos
- ✅ **Actualización en tiempo real**: La tabla se actualiza inmediatamente
- ✅ **Historial completo**: Todos los ajustes quedan registrados con razón y timestamp

## 🔍 Ver Historial de Cambios

Para ver el historial completo de movimientos de stock (incluyendo los ajustes manuales):

```bash
# Via API
curl "http://localhost:8000/api/tenants/[PHONE]/stock/movements"

# O consulta directamente la base de datos
sqlite3 data/clients/[PHONE]/business.db "SELECT * FROM stock_movements ORDER BY occurred_at DESC LIMIT 20;"
```

## 🎨 UI/UX

- **Modo Display**: Muestra la cantidad actual con color (verde si >0, rojo si =0)
- **Modo Edit**:
  - Campo de entrada numérico de 24px de ancho
  - Botón verde (✓) para confirmar
  - Botón gris (✗) para cancelar
  - Se muestra solo en la fila que estás editando
  - El botón "Edit Qty" desaparece mientras editas

## 🔒 Seguridad

- ✅ Validación de input: Solo números enteros >= 0
- ✅ Validación de backend: Verifica que el producto exista
- ✅ No permite stock negativo: El mínimo es 0
- ✅ Manejo de errores: Mensajes claros si algo falla
- ✅ Transacciones atómicas: O todo se guarda o nada

## 🛠️ API Endpoint

### POST `/api/tenants/{phone}/stock/adjust`

**Request Body:**
```json
{
  "product_id": 1,
  "quantity": 5,      // Positivo para aumentar, negativo para disminuir
  "reason": "Manual adjustment (increase)"
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "Stock adjusted successfully (+5)",
  "data": {
    "status": "ok",
    "product_id": 1,
    "movement_id": 123
  }
}
```

## 💡 Tips

1. **Corrección de errores**: Si el stock está mal, simplemente edítalo al valor correcto
2. **Inventario físico**: Usa esta función para ajustar después de hacer conteo físico
3. **Múltiples cambios**: Puedes editar varios productos uno tras otro sin recargar
4. **Auto-refresh**: La tabla se actualiza automáticamente cada 30 segundos
5. **Refresh manual**: Click en el botón "Refresh" arriba a la derecha si quieres actualizar ya

## 🚀 Comandos Útiles

```bash
# Reiniciar backend para tomar cambios
bash restart_backend.sh

# Ver logs del backend
tail -f C:\Users\loko_\AppData\Local\Temp\claude\C--Users-loko--supabase-sql-agent\tasks\*.output

# Ver stock actual de un tenant
curl -s "http://localhost:8000/api/tenants/%2B541153695627/stock" | python -m json.tool
```

## 🎉 ¡Listo!

Ahora tienes control total sobre tu inventario desde el panel de administración. Cualquier cambio queda registrado y puedes hacer ajustes rápidos sin complicaciones.

**URL del Panel**: http://localhost:8000
