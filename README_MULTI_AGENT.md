# Beans&Co Multi-Agent Business System

Una arquitectura multi-agente con **LangGraph** para gestión de negocio que separa responsabilidades entre agentes especializados.

## Características

- **4 Agentes especializados** con responsabilidades claras
- **Clasificación inteligente de intención** (lectura vs. escritura)
- **Sin mezcla de responsabilidades** (read agents no escriben, write agents no hacen SQL)
- **Resolución de entidades** (referencias humanas → IDs de base de datos)
- **Soporte bilingüe** (Español e Inglés)
- **Orquestación con LangGraph** (flujo de estado tipado)

## Arquitectura

```
Usuario → Router → [Read | Resolver → Write → Read*] → Respuesta Final

* Solo en operaciones MIXED
```

### Agentes

1. **Intent Router Agent** (`agents/router.py`)
   - Clasifica la intención del usuario
   - Extrae entidades
   - NO ejecuta herramientas

2. **Read/Analytics Agent** (`agents/read_agent.py`)
   - Solo consultas SQL SELECT
   - Usa views del negocio
   - NO puede escribir

3. **Write/Operations Agent** (`agents/write_agent.py`)
   - Solo operaciones de negocio (Python)
   - NO genera SQL crudo
   - Valida datos antes de ejecutar

4. **Normalization/Resolver Agent** (`agents/resolver.py`)
   - Resuelve referencias ("pulseras negras" → product_id)
   - Normaliza fechas y montos
   - NO toma decisiones finales

## Instalación

### Prerrequisitos

```bash
python 3.10+
pip install -r requirements.txt
```

### Variables de Entorno

Crea un archivo `.env`:

```bash
GOOGLE_API_KEY=tu_api_key_aqui
GEMINI_MODEL=gemini-2.0-flash-exp  # opcional
```

### Inicializar Base de Datos

```bash
python init_db.py
python apply_views.py
```

## Uso

### Modo Interactivo

```bash
python graph.py
```

Esto abre una consola interactiva:

```
You> cuántas pulseras tengo de cada tipo?
[ROUTER] Intent classified as READ_ANALYTICS
[READ_AGENT] Executing query...
You have: BC-BRACELET-BLACK (37 units), BC-BRACELET-CLASSIC (45 units), ...

You> registrame una venta de 2 pulseras negras
[ROUTER] Intent classified as WRITE_OPERATION / REGISTER_SALE
[RESOLVER] Resolved "pulseras negras" → product_id: 2
[WRITE_AGENT] Registering sale...
✓ Sale registered (ID: 6, Total: $28.00)
  Current revenue: $1100.00
  Current profit: $850.00

You> exit
Goodbye!
```

### Single Query Mode

```bash
python graph.py -q "cuánto stock tengo en total?"
```

### Ejemplos Programáticos

```bash
# Ejecutar todos los tests
python example_usage.py

# Ejecutar tests específicos
python example_usage.py read       # Consultas analíticas
python example_usage.py write      # Operaciones de negocio
python example_usage.py mixed      # Operaciones mixtas
python example_usage.py full       # Flujo completo con verbose
```

## Ejemplos

### Consultas Analíticas (READ_ANALYTICS)

```python
"¿cuántas pulseras tengo de cada tipo?"
"what's my total revenue?"
"show me current profit"
"cuánto stock tengo en total"
```

**Flujo**: User → Router → Read Agent → Final Answer

### Operaciones de Negocio (WRITE_OPERATION)

```python
"registrame una venta de 20 pulseras negras"
"I sold 3 black bracelets"
"gasté 30 dólares en envíos ayer"
"crear producto nuevo con SKU BC-TEST"
```

**Flujo**: User → Router → Resolver → Write Agent → Final Answer

### Operaciones Mixtas (MIXED)

```python
"vendí 2 pulseras black, ¿cómo queda el stock?"
"register a sale of 1 bracelet and show me the new revenue"
```

**Flujo**: User → Router → Resolver → Write Agent → Read Agent → Final Answer

### Requests Ambiguos (AMBIGUOUS)

```python
"registrar algo"         # ¿Qué registrar?
"cuánto tengo"          # ¿De qué?
```

**Flujo**: User → Router → Final Answer (pide aclaración)

## Estructura del Proyecto

```
.
├── agents/
│   ├── __init__.py          # Exports
│   ├── state.py             # Estado tipado compartido
│   ├── router.py            # Intent Router Agent
│   ├── read_agent.py        # Read/Analytics Agent
│   ├── write_agent.py       # Write/Operations Agent
│   └── resolver.py          # Normalization/Resolver Agent
├── graph.py                 # Orquestación LangGraph
├── database.py              # Business actions
├── llm.py                   # Configuración LLM
├── example_usage.py         # Tests de ejemplo
├── ARCHITECTURE.md          # Documentación detallada
└── README_MULTI_AGENT.md    # Este archivo
```

## Operaciones Soportadas

### REGISTER_SALE

Registra una venta con stock automático.

**Campos requeridos**:
- `items`: Lista de `[{product_ref, quantity}]`

**Campos opcionales**:
- `status`: `PAID` (default) | `PENDING`

**Ejemplo**:
```
"registrame una venta de 5 pulseras classic y 2 keychains"
```

### REGISTER_EXPENSE

Registra un gasto de negocio.

**Campos requeridos**:
- `amount`: Monto en dólares
- `description`: Descripción del gasto

**Campos opcionales**:
- `category`: Categoría (default: GENERAL)
- `date`: Fecha (default: hoy)

**Ejemplo**:
```
"gasté 50 dólares en marketing ayer"
```

### REGISTER_PRODUCT

Crea un nuevo producto.

**Campos requeridos**:
- `sku`: Código único
- `name`: Nombre del producto
- `unit_price_cents`: Precio en centavos
- `unit_cost_cents`: Costo en centavos

**Campos opcionales**:
- `description`: Descripción

**Ejemplo**:
```
"crear producto BC-RING-SILVER con nombre 'Coffee Ring Silver' precio 25 dólares costo 10 dólares"
```

### ADD_STOCK

Añade o ajusta stock.

**Campos requeridos**:
- `product_ref`: Referencia al producto (SKU o nombre)
- `quantity`: Cantidad

**Campos opcionales**:
- `reason`: Razón del movimiento
- `movement_type`: `IN` (default) | `ADJUSTMENT`

**Ejemplo**:
```
"agregar 100 unidades de pulseras black"
```

## Extender el Sistema

### Agregar Nueva Operación

1. **Añadir tipo en `agents/state.py`**:
```python
OperationType = Literal[
    "REGISTER_SALE",
    "REGISTER_EXPENSE",
    "REGISTER_PRODUCT",
    "ADD_STOCK",
    "NEW_OPERATION",  # ← Nuevo
]
```

2. **Implementar función en `database.py`**:
```python
def new_operation(data: dict):
    # Tu implementación
    return {"status": "ok", ...}
```

3. **Actualizar `agents/write_agent.py`**:
```python
elif operation_type == "NEW_OPERATION":
    result = new_operation(entities)
    operation_summary = "..."
```

4. **Actualizar prompt del router** en `agents/router.py` para reconocer keywords

### Agregar Nuevo Agente

1. Crear `agents/new_agent.py`
2. Implementar función que recibe `AgentState` y devuelve actualizaciones
3. Añadir nodo en `graph.py`:
```python
new_agent = create_new_agent()
workflow.add_node("new_agent", new_agent)
workflow.add_edge("some_node", "new_agent")
```

## Troubleshooting

### "Product not found"

El resolver no pudo encontrar el producto. Verifica que:
- El SKU existe en la base de datos
- El nombre parcial coincide con algún producto

### "Missing required fields"

Falta información para completar la operación. El sistema te dirá qué campos faltan.

### Error de SQL

Verifica que las views existan:
```bash
python apply_views.py
```

### El LLM no clasifica bien

Ajusta el prompt en `agents/router.py` con más ejemplos específicos para tu caso de uso.

## Testing

### Tests Unitarios

Prueba cada agente de forma independiente:

```python
from agents import create_router_agent
from llm import get_llm

llm = get_llm()
router = create_router_agent(llm)

state = {
    "user_input": "cuántas pulseras tengo",
    "messages": [],
    "normalized_entities": {}
}

result = router(state)
assert result["intent"] == "READ_ANALYTICS"
```

### Tests de Integración

Usa `example_usage.py` para probar el flujo completo.

## Documentación Adicional

Ver [ARCHITECTURE.md](ARCHITECTURE.md) para:
- Diagramas detallados del flujo
- Especificaciones completas de cada agente
- Decisiones de diseño
- Guías de extensión avanzadas

## Comparación con el Agente Simple

| Aspecto | Agente Simple (`agent.py`) | Multi-Agente (`graph.py`) |
|---------|---------------------------|---------------------------|
| **Arquitectura** | Monolítico | Separación de responsabilidades |
| **Clasificación** | Dentro del prompt | Agente dedicado (Router) |
| **SQL** | Mezclado con business logic | Solo Read Agent |
| **Write** | Mezclado | Solo Write Agent |
| **Resolución** | En el prompt | Agente dedicado (Resolver) |
| **Escalabilidad** | Difícil agregar funcionalidad | Fácil agregar agentes |
| **Debugging** | Opaco | Estado visible en cada paso |
| **Testing** | Difícil | Cada agente se testea solo |

## Licencia

MIT

## Contribuciones

Ver issues o crear PRs en el repositorio.
