# Panel de Control - Guía Rápida

Panel de administración interactivo para gestionar bases de datos multi-tenant de Beans&Co.

## 🚀 Acceso Rápido

```bash
# Iniciar el backend
./start_server.sh

# Abrir en navegador
http://localhost:8000
```

## 📊 Funcionalidades Principales

### Dashboard Principal
- Lista de todos los tenants
- Estadísticas por tenant (Revenue, Profit, Products, Sales)
- Click en cualquier tenant para acceder a su panel detallado

### Panel de Tenant (Dashboard Detallado)

#### 1. Products Tab 🏷️
**Operaciones disponibles:**
- ✅ Ver todos los productos con SKU, nombre, descripción, costo y precio
- ➕ **Add Product**: Agregar nuevos productos
- ✏️ **Edit**: Modificar productos existentes (click en botón "Edit")
- 🗑️ **Delete**: Eliminar productos individuales
- ☑️ **Bulk Delete**: Seleccionar múltiples productos y eliminarlos juntos
- 🔄 Auto-refresh cada 30 segundos

**Cómo agregar un producto:**
1. Click en "Add Product"
2. Completar formulario:
   - SKU (identificador único)
   - Name (nombre del producto)
   - Description (opcional)
   - Cost (USD) - costo del producto
   - Price (USD) - precio de venta
3. Click "Save"

**Cómo editar un producto:**
1. Click en "Edit" en la fila del producto
2. Modificar los campos necesarios
3. Click "Save"

**Cómo eliminar múltiples productos:**
1. Marcar checkbox de los productos a eliminar
2. Click en "Delete Selected (N)"
3. Confirmar eliminación

#### 2. Stock Tab 📦
**Operaciones disponibles:**
- ✅ Ver stock actual de todos los productos activos
- ➕ **Add Stock**: Agregar inventario
- 🔴 Indicador rojo: stock en 0
- 🟢 Indicador verde: stock disponible

**Cómo agregar stock:**
1. Click en "Add Stock"
2. Seleccionar producto del dropdown
3. Ingresar cantidad
4. Agregar razón/motivo (opcional)
5. Click "Add Stock"

#### 3. Sales Tab 💰
**Operaciones disponibles:**
- ✅ Ver todas las ventas con número, cliente, estado, total y fecha
- 👁️ **View**: Ver detalles de la venta
- ❌ **Cancel**: Cancelar venta (solo si no está cancelada)
- 🏷️ Estados:
  - 🟢 PAID - Pagada
  - 🟡 PENDING - Pendiente
  - 🔴 CANCELLED - Cancelada

**Cómo ver detalles de una venta:**
1. Click en "View" en la fila de la venta
2. Se mostrará un modal con toda la información

**Cómo cancelar una venta:**
1. Click en "Cancel" en la fila de la venta
2. Confirmar cancelación
3. La venta quedará marcada como CANCELLED

#### 4. Expenses Tab 💳
**Operaciones disponibles:**
- ✅ Ver todos los gastos con fecha, categoría, descripción y monto
- ➕ **Add Expense**: Registrar nuevo gasto
- 🗑️ **Delete**: Eliminar gasto individual
- ☑️ **Bulk Delete**: Seleccionar múltiples gastos y eliminarlos juntos

**Cómo agregar un gasto:**
1. Click en "Add Expense"
2. Completar formulario:
   - Category (ej: "Alquiler", "Servicios", "Materiales")
   - Description (detalle opcional)
   - Amount (USD)
   - Date (fecha del gasto)
3. Click "Add Expense"

**Cómo eliminar múltiples gastos:**
1. Marcar checkbox de los gastos a eliminar
2. Click en "Delete Selected (N)"
3. Confirmar eliminación

## ⚡ Características Especiales

### Auto-Refresh (Actualización Automática)
- Los datos se actualizan automáticamente cada 30 segundos
- No necesitas recargar la página manualmente
- Las estadísticas (Revenue, Profit, etc.) se actualizan en tiempo real

### Refresh Manual
- Botón "Refresh" en la parte superior derecha
- Click para actualizar datos inmediatamente
- Útil cuando acabas de hacer cambios desde otro lugar

### Operaciones sin Recargar Página
- Todas las operaciones CRUD usan AJAX
- La página no se recarga al agregar/editar/eliminar
- Experiencia fluida y rápida

### Confirmaciones de Seguridad
- Confirmación antes de eliminar productos
- Confirmación antes de eliminar gastos
- Confirmación antes de cancelar ventas
- Confirmación antes de eliminaciones masivas

### Mensajes de Error Claros
- Si algo falla, verás un mensaje descriptivo
- Los errores se muestran con alert()
- Revisa la consola del navegador para más detalles (F12)

## 🎨 Diseño Responsivo

El panel funciona en:
- 💻 Desktop (experiencia completa)
- 📱 Tablet (diseño adaptado)
- 📱 Móvil (tablas con scroll horizontal)

## 🔧 Troubleshooting

### La página no carga
```bash
# Verificar que el backend esté corriendo
./check_server.sh

# Si no está corriendo, iniciarlo
./start_server.sh
```

### Los datos no se actualizan
- Click en el botón "Refresh" manualmente
- Verificar la consola del navegador (F12) para errores
- Verificar que la API esté respondiendo: http://localhost:8000/health

### Error al agregar/editar datos
- Verificar que todos los campos requeridos estén completos
- Verificar que los números sean válidos (sin letras)
- Revisar la consola del navegador para el mensaje de error exacto

### No aparecen los tenants
- Verificar que exista el archivo `configs/tenant_registry.json`
- Verificar que el backend se esté ejecutando desde el directorio raíz del proyecto

## 📚 Ejemplos de Uso

### Escenario 1: Agregar un nuevo producto y stock
1. Ir a tab "Products"
2. Click "Add Product"
3. Completar: SKU="BC-001", Name="Pulsera Premium", Cost="8.00", Price="20.00"
4. Click "Save"
5. Ir a tab "Stock"
6. Click "Add Stock"
7. Seleccionar "Pulsera Premium (BC-001)"
8. Cantidad: 50, Razón: "Stock inicial"
9. Click "Add Stock"
10. ✅ Producto creado con stock disponible!

### Escenario 2: Ver ventas del día y cancelar una
1. Ir a tab "Sales"
2. Revisar la columna "Date" para ver ventas de hoy
3. Click "View" para ver detalles de una venta específica
4. Si necesitas cancelarla, click "Cancel"
5. Confirmar la cancelación
6. ✅ Venta cancelada y marcada como CANCELLED

### Escenario 3: Registrar gastos del mes
1. Ir a tab "Expenses"
2. Click "Add Expense"
3. Completar: Category="Alquiler", Amount="500.00", Date="2026-01-01"
4. Click "Add Expense"
5. Repetir para otros gastos (servicios, materiales, etc.)
6. Ver total de gastos en el dashboard principal
7. ✅ Gastos registrados correctamente!

## 🆘 Soporte

Para reportar bugs o solicitar funcionalidades:
- Revisar README principal del proyecto
- Consultar documentación de la API en http://localhost:8000/docs
- Revisar logs del backend con `./check_server.sh`
