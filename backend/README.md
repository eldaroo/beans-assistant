# Beans&Co Multi-Tenant Backend API

REST API con FastAPI para gestión de bases de datos multi-tenant del sistema Beans&Co.

## Características

- **FastAPI**: Framework moderno y rápido
- **Multi-Tenant**: Gestión de múltiples clientes aislados
- **Admin UI**: Panel web básico incluido
- **Auto-Documentación**: Swagger UI en `/docs`
- **Sin Autenticación**: Fácil de usar y testear

## Estructura

```
backend/
├── app.py                   # Aplicación principal
├── api/                     # Endpoints de API
│   ├── tenants.py          # CRUD de tenants
│   ├── products.py         # CRUD de productos
│   ├── sales.py            # Gestión de ventas
│   ├── expenses.py         # Gestión de gastos
│   ├── stock.py            # Gestión de stock
│   └── analytics.py        # Analytics y métricas
├── models/
│   └── schemas.py          # Modelos Pydantic
├── templates/              # Templates HTML
│   ├── base.html
│   ├── tenants.html
│   └── tenant_detail.html
└── static/                 # Archivos estáticos
```

## Instalación

1. Instalar dependencias:
```bash
pip install -r backend/requirements.txt
```

## Uso

### Iniciar el Servidor

**IMPORTANTE**: El servidor debe ejecutarse desde el directorio raíz del proyecto para que las rutas relativas funcionen correctamente.

```bash
# Desde la raíz del proyecto (NO desde backend/)
python -m uvicorn backend.app:app --reload --port 8000
```

También puedes usar:
```bash
python -m backend.app
```

El servidor estará disponible en:
- **Admin UI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **API (JSON)**: http://localhost:8000/api/tenants

### API Endpoints

#### Tenants
- `GET /api/tenants` - Listar todos los tenants
- `GET /api/tenants/{phone}` - Obtener detalles de un tenant
- `POST /api/tenants` - Crear nuevo tenant
- `GET /api/tenants/{phone}/stats` - Estadísticas del tenant
- `DELETE /api/tenants/{phone}` - Eliminar tenant

#### Productos
- `GET /api/tenants/{phone}/products` - Listar productos
- `GET /api/tenants/{phone}/products/{id}` - Detalle de producto
- `POST /api/tenants/{phone}/products` - Crear producto
- `PUT /api/tenants/{phone}/products/{id}` - Actualizar producto
- `DELETE /api/tenants/{phone}/products/{id}` - Desactivar producto

#### Ventas
- `GET /api/tenants/{phone}/sales` - Listar ventas
- `GET /api/tenants/{phone}/sales/{id}` - Detalle de venta
- `POST /api/tenants/{phone}/sales` - Registrar venta
- `DELETE /api/tenants/{phone}/sales/{id}` - Cancelar venta

#### Gastos
- `GET /api/tenants/{phone}/expenses` - Listar gastos
- `POST /api/tenants/{phone}/expenses` - Registrar gasto
- `DELETE /api/tenants/{phone}/expenses/{id}` - Cancelar gasto

#### Stock
- `GET /api/tenants/{phone}/stock` - Ver stock actual
- `POST /api/tenants/{phone}/stock/add` - Agregar stock
- `GET /api/tenants/{phone}/stock/movements` - Historial de movimientos

#### Analytics
- `GET /api/tenants/{phone}/analytics/revenue` - Revenue total
- `GET /api/tenants/{phone}/analytics/profit` - Profit actual
- `GET /api/tenants/{phone}/analytics/sales-summary` - Resumen de ventas por día

## Ejemplos de Uso

### Listar Tenants
```bash
curl http://localhost:8000/api/tenants
```

### Ver Stats de un Tenant
```bash
curl http://localhost:8000/api/tenants/+5491153695627/stats
```

### Crear Producto
```bash
curl -X POST http://localhost:8000/api/tenants/+5491153695627/products \
  -H "Content-Type: application/json" \
  -d '{
    "sku": "BC-PREMIUM-001",
    "name": "Pulsera Premium",
    "description": "Pulsera de alta calidad",
    "unit_cost_cents": 800,
    "unit_price_cents": 2000
  }'
```

### Registrar Venta
```bash
curl -X POST http://localhost:8000/api/tenants/+5491153695627/sales \
  -H "Content-Type: application/json" \
  -d '{
    "status": "PAID",
    "items": [
      {"product_id": 2, "quantity": 5}
    ]
  }'
```

### Ver Stock Actual
```bash
curl http://localhost:8000/api/tenants/+5491153695627/stock
```

## Admin UI - Panel de Control Integral

Abre http://localhost:8000 en tu navegador para acceder al panel de administración.

### Funcionalidades Principales:

#### 🏠 Dashboard Principal
- Lista de todos los tenants con estadísticas
- Vista rápida de revenue, profit, productos y ventas por tenant

#### 📊 Tenant Detail (Panel de Control Completo)
Dashboard detallado por tenant con tabs interactivos:

**Products (Productos)**
- Tabla interactiva con datos en tiempo real
- Agregar/Editar/Eliminar productos individuales
- Selección múltiple con checkboxes
- Eliminación masiva de productos seleccionados
- Estados visuales (Active/Inactive)
- Auto-refresh cada 30 segundos

**Stock (Inventario)**
- Vista de stock actual en tiempo real
- Agregar stock con modal de formulario
- **✨ NUEVO: Editar cantidad directamente en cada fila** (inline editing)
- Botones de guardar/cancelar con atajos de teclado (Enter/Escape)
- Ajustes positivos y negativos con registro automático
- Indicadores visuales de disponibilidad
- Actualización automática

**Sales (Ventas)**
- Tabla con todas las ventas
- Ver detalles de cada venta
- Cancelar ventas individuales
- Estados visuales (PAID/PENDING/CANCELLED)
- Formato de fecha y montos

**Expenses (Gastos)**
- Tabla interactiva de gastos
- Agregar nuevos gastos
- Eliminar gastos individuales
- Selección múltiple y eliminación masiva
- Filtrado por categoría

#### ⚡ Características del Panel:
- **Actualización en tiempo real**: Auto-refresh cada 30 segundos
- **Sin recargar página**: Todas las operaciones CRUD con AJAX
- **Modales interactivos**: Formularios para agregar/editar datos
- **Confirmaciones**: Antes de eliminar registros
- **Mensajes de error**: Claros y descriptivos
- **Responsive**: Diseño adaptable a móviles y tablets

## Integración con Sistema Existente

El backend reutiliza completamente:
- `tenant_manager.py` - Para gestión de tenants
- `database.py` - Para todas las operaciones de base de datos

**Ventajas**:
- No duplica lógica de negocio
- Mismas validaciones que el agente conversacional
- Comportamiento consistente

## Notas Técnicas

### Precios
- Todos los precios se manejan en **cents** (centavos) internamente
- Conversión a USD: `cents / 100.0`
- Ejemplos:
  - 1200 cents = $12.00 USD
  - 1400 cents = $14.00 USD

### Multi-Tenant
- Cada tenant tiene su propia base de datos SQLite aislada
- Ubicación: `data/clients/{phone_number}/business.db`
- Total isolation entre tenants

### CORS
- Configurado para permitir todos los orígenes (`*`)
- Sin autenticación por ahora (desarrollo/testing)

## Próximos Pasos (Futuro)

1. ✅ API completa (DONE)
2. ✅ Admin UI básico (DONE)
3. 🔲 Autenticación JWT
4. 🔲 Roles de usuario (admin, viewer)
5. 🔲 UI mejorado con tablas interactivas
6. 🔲 Exportación de reportes (PDF, Excel)
7. 🔲 Webhooks para notificaciones

## Soporte

Para más información sobre la estructura de la base de datos y el sistema multi-tenant, consulta el README principal del proyecto.
