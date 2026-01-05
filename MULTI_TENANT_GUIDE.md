# Guía de Arquitectura Multi-Tenant

Sistema de bot de WhatsApp que maneja múltiples clientes con bases de datos y configuraciones separadas.

## Características

✅ **Un bot, múltiples clientes**: Un servidor maneja 5-50 negocios diferentes
✅ **Aislamiento total**: Cada cliente tiene su propia base de datos
✅ **Onboarding automático**: Setup interactivo mediante preguntas
✅ **Configuración personalizada**: Prompts, moneda, idioma por cliente
✅ **Escalable**: Fácil agregar nuevos clientes sin código

## Estructura de Archivos

```
supabase-sql-agent/
├── whatsapp_server_multitenant.py  # Servidor multi-tenant
├── tenant_manager.py               # Gestión de clientes
├── onboarding_agent.py            # Setup interactivo
├── data/
│   ├── clients/
│   │   ├── +5491112345678/       # Cliente 1
│   │   │   ├── business.db       # Base de datos propia
│   │   │   └── config.json       # Configuración propia
│   │   ├── +5491187654321/       # Cliente 2
│   │   │   ├── business.db
│   │   │   └── config.json
│   └── templates/
│       ├── default_schema.sql    # Schema por defecto
│       └── default_config.json   # Config por defecto
└── configs/
    └── tenant_registry.json      # Registro de clientes
```

## Cómo Funciona

### 1. Nuevo Cliente (Primera vez)

Cuando un número nuevo escribe:

```
Usuario: Hola
Bot: ¡Bienvenido! Veo que es la primera vez...
     ¿Cómo se llama tu negocio?

Usuario: Beans&Co
Bot: ¿Qué tipo de negocio tienes?

Usuario: Vendo pulseras artesanales
Bot: ¿En qué moneda trabajas? (USD, ARS, EUR, BRL)

Usuario: USD
Bot: ¿Quieres agregar productos ahora? (Sí/No)

Usuario: Sí
Bot: ¡Listo! ✅
     Tu negocio Beans&Co está configurado.
     ¿En qué puedo ayudarte?
```

**Lo que pasa detrás:**
1. Se crea carpeta `data/clients/+5491112345678/`
2. Se crea `business.db` con schema completo
3. Se guarda `config.json` con configuración personalizada
4. Se registra en `tenant_registry.json`

### 2. Cliente Existente

```
Usuario: Vendí 2 pulseras doradas
Bot: ✅ Venta registrada
     Total: $40.00
     Ganancia actual: $250.00
```

**Lo que pasa detrás:**
1. Se identifica el cliente por número de teléfono
2. Se usa SU base de datos (`data/clients/+5491112345678/business.db`)
3. Se usa SU configuración (moneda, prompts personalizados)

## Configuración por Cliente

Cada cliente tiene su `config.json`:

```json
{
  "business_name": "Beans&Co",
  "business_type": "Pulseras artesanales",
  "phone_number": "+5491112345678",
  "language": "es",
  "currency": "USD",
  "timezone": "America/Argentina/Buenos_Aires",
  "prompts": {
    "system_prompt": "Eres un asistente de Beans&Co...",
    "welcome_message": "¡Hola! Soy el asistente de Beans&Co..."
  },
  "features": {
    "audio_enabled": true,
    "sales_enabled": true,
    "expenses_enabled": true,
    "inventory_enabled": true
  },
  "created_at": "2026-01-03T18:00:00"
}
```

## Uso

### Iniciar el Servidor Multi-Tenant

```bash
# En local (desarrollo)
python whatsapp_server_multitenant.py

# En servidor (producción)
# Edita start_server.sh y cambia:
# python whatsapp_server.py → python whatsapp_server_multitenant.py

./start_server.sh
```

### Ver Clientes Registrados

```python
from tenant_manager import get_tenant_manager

tm = get_tenant_manager()

# Listar todos los clientes
clientes = tm.list_tenants()
for phone, info in clientes.items():
    print(f"{phone}: {info['business_name']}")

# Ver estadísticas de un cliente
stats = tm.get_tenant_stats("+5491112345678")
print(stats)
# {
#   "products": 5,
#   "sales": 23,
#   "revenue_usd": 450.00,
#   "profit_usd": 250.00
# }
```

### Crear Cliente Manualmente

```python
from tenant_manager import get_tenant_manager

tm = get_tenant_manager()

# Crear nuevo cliente
tm.create_tenant(
    phone_number="+5491199887766",
    business_name="Tienda de María",
    config={
        "currency": "ARS",
        "language": "es",
        "business_type": "Ropa"
    }
)
```

### Personalizar Configuración

Edita manualmente `data/clients/+5491112345678/config.json`:

```json
{
  "prompts": {
    "system_prompt": "Eres un experto en joyería artesanal...",
    "welcome_message": "¡Bienvenido a Beans&Co! ¿Qué necesitas?"
  },
  "features": {
    "audio_enabled": false,  // Deshabilitar audios
    "sales_enabled": true,
    "expenses_enabled": false  // Solo ventas, sin gastos
  }
}
```

## Ventajas de esta Arquitectura

### ✅ Aislamiento Total
- Cada cliente tiene su propia base de datos
- No hay riesgo de mezclar datos entre clientes
- Privacidad y seguridad garantizadas

### ✅ Personalización por Cliente
- Prompts customizados por negocio
- Moneda diferente por cliente (USD, ARS, EUR)
- Features habilitados/deshabilitados por cliente

### ✅ Onboarding Automático
- No necesitas crear clientes manualmente
- El bot configura todo mediante conversación
- 2 minutos para estar operativo

### ✅ Escalable
- Un servidor maneja 50+ clientes fácilmente
- Agregar clientes sin tocar código
- Backups independientes por cliente

### ✅ Fácil Migración
- Cada cliente es independiente
- Puedes mover un cliente a otro servidor
- Solo copias su carpeta

## Migraciones y Backups

### Backup de un Cliente

```bash
# Backup de un cliente específico
tar -czf backup_5491112345678.tar.gz data/clients/+5491112345678/

# Restore
tar -xzf backup_5491112345678.tar.gz -C data/clients/
```

### Backup de Todos los Clientes

```bash
# Backup completo
tar -czf backup_all_clients.tar.gz data/clients/ configs/tenant_registry.json

# Restore
tar -xzf backup_all_clients.tar.gz
```

### Migrar Cliente a Otro Servidor

```bash
# En servidor origen
scp -r data/clients/+5491112345678 user@nuevo-servidor:/ruta/data/clients/

# Actualizar registry en nuevo servidor
# Edita configs/tenant_registry.json y agrega el cliente
```

## Monitoreo

### Ver Actividad

```python
from tenant_manager import get_tenant_manager

tm = get_tenant_manager()

# Ver todos los clientes
for phone, info in tm.list_tenants().items():
    stats = tm.get_tenant_stats(phone)
    print(f"\n{info['business_name']} ({phone}):")
    print(f"  Productos: {stats['products']}")
    print(f"  Ventas: {stats['sales']}")
    print(f"  Ingresos: ${stats['revenue_usd']:.2f}")
    print(f"  Ganancia: ${stats['profit_usd']:.2f}")
```

## Troubleshooting

### Cliente no recibe mensajes

1. Verificar que el cliente esté registrado:
   ```python
   tm.tenant_exists("+5491112345678")
   ```

2. Verificar que la DB existe:
   ```bash
   ls data/clients/+5491112345678/business.db
   ```

3. Ver logs del servidor

### Resetear Cliente

```python
# Eliminar carpeta del cliente
import shutil
shutil.rmtree("data/clients/+5491112345678")

# Eliminar del registry
tm = get_tenant_manager()
del tm.registry["+5491112345678"]
tm._save_registry()

# Próximo mensaje iniciará onboarding de nuevo
```

## Próximos Pasos

1. **Dashboard Web**: Interfaz para ver todos los clientes
2. **Analytics**: Métricas agregadas de todos los clientes
3. **API REST**: Gestionar clientes vía API
4. **Auto-scaling**: Múltiples servidores con load balancer
5. **Notificaciones**: Alertas cuando un cliente tiene problemas

## Soporte

Para más información, ver:
- `tenant_manager.py` - Gestión de clientes
- `onboarding_agent.py` - Proceso de setup
- `whatsapp_server_multitenant.py` - Servidor principal
