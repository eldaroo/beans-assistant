# Chat Simulation API

Simula conversaciones con el bot de WhatsApp desde el backend, sin necesidad de enviar mensajes reales.

## 🎯 Para qué sirve

- ✅ **Testing rápido** de cambios en agentes
- ✅ **Probar diferentes tenants** sin cambiar de WhatsApp
- ✅ **Debugging** de flujos conversacionales
- ✅ **Automatizar tests** de regresión
- ✅ **Demo del bot** sin WhatsApp

## 🚀 Endpoints

### 1. Mensaje simple

**POST** `/api/chat/simulate`

```json
{
  "phone": "+5491112345678",
  "message": "cuántos productos tengo?"
}
```

**Respuesta:**
```json
{
  "phone": "+5491112345678",
  "user_message": "cuántos productos tengo?",
  "bot_response": "Tenés 6 productos registrados:\n\n📦 Pulsera Roja: 10 unidades...",
  "metadata": {}
}
```

### 2. Múltiples mensajes (batch)

**POST** `/api/chat/simulate/batch`

```json
[
  {"phone": "+5491112345678", "message": "hola"},
  {"phone": "+5491112345678", "message": "cuántos productos tengo?"},
  {"phone": "+5491112345678", "message": "gracias"}
]
```

**Respuesta:** Array de respuestas

## 📖 Uso desde...

### Swagger UI (más fácil)

1. Abrí http://localhost:8000/docs
2. Buscá la sección **"Chat Simulation"**
3. Click en **POST /api/chat/simulate**
4. Click en **"Try it out"**
5. Editá el JSON:
   ```json
   {
     "phone": "+5491112345678",
     "message": "tu mensaje aquí"
   }
   ```
6. Click en **"Execute"**
7. Ver respuesta abajo

### cURL

```bash
curl -X POST "http://localhost:8000/api/chat/simulate" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+5491112345678",
    "message": "cuántos productos tengo?"
  }'
```

### PowerShell

```powershell
# Mensaje simple
$body = @{
    phone = "+5491112345678"
    message = "cuántos productos tengo?"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/chat/simulate" `
    -Method Post `
    -Body $body `
    -ContentType "application/json"
```

### Python

```python
import requests

response = requests.post(
    "http://localhost:8000/api/chat/simulate",
    json={
        "phone": "+5491112345678",
        "message": "cuántos productos tengo?"
    }
)

data = response.json()
print(f"Bot: {data['bot_response']}")
```

### JavaScript / Fetch

```javascript
const response = await fetch('http://localhost:8000/api/chat/simulate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    phone: '+5491112345678',
    message: 'cuántos productos tengo?'
  })
});

const data = await response.json();
console.log('Bot:', data.bot_response);
```

## 🧪 Script de testing

Ejecutá el script de prueba incluido:

```powershell
.\test_chat_api.ps1
```

Esto ejecuta varios tests automáticamente y muestra los resultados.

## 💡 Ejemplos de mensajes para probar

### Consultas
```json
{"phone": "+5491112345678", "message": "cuántos productos tengo?"}
{"phone": "+5491112345678", "message": "mostrame el stock"}
{"phone": "+5491112345678", "message": "cuál es mi ganancia?"}
{"phone": "+5491112345678", "message": "últimas ventas"}
```

### Registro de productos
```json
{"phone": "+5491112345678", "message": "registrar producto: Collar Azul, precio 800, costo 300"}
{"phone": "+5491112345678", "message": "agregar stock: 5 collares azules"}
```

### Ventas
```json
{"phone": "+5491112345678", "message": "registrar venta: 2 pulseras rojas"}
{"phone": "+5491112345678", "message": "vender: 1 collar azul a Maria"}
```

### Cancelaciones
```json
{"phone": "+5491112345678", "message": "cancelar última venta"}
{"phone": "+5491112345678", "message": "deshacer último gasto"}
```

## 🔧 Diferencias con WhatsApp real

| Característica | Chat Simulation | WhatsApp Real |
|----------------|----------------|---------------|
| Procesa mensaje | ✅ Sí | ✅ Sí |
| Ejecuta agentes | ✅ Sí | ✅ Sí |
| Modifica BD | ✅ Sí | ✅ Sí |
| Envía respuesta | ❌ Solo devuelve JSON | ✅ Envía por WhatsApp |
| Require Green API | ❌ No | ✅ Sí |
| Webhook público | ❌ No | ✅ Sí |

## 🎯 Workflow recomendado

### Para desarrollo de agentes:

1. **Modificar código** de agentes (graph.py, agents/*)
2. **Probar localmente** con `/api/chat/simulate`
3. **Iterar rápido** sin deployar
4. **Deployar al VPS** cuando esté listo

### Para testing:

```powershell
# Probar cambio rápido
Invoke-RestMethod -Uri "http://localhost:8000/api/chat/simulate" `
    -Method Post `
    -Body '{"phone":"+5491112345678","message":"test"}' `
    -ContentType "application/json"

# Verificar que la BD cambió
curl http://localhost:8000/api/tenants/+5491112345678/products
```

## ⚠️ Importante

- **Los cambios son REALES** - Modifica la base de datos PostgreSQL
- **Multi-tenant** - Usa el `phone` para seleccionar el tenant correcto
- **Mismo comportamiento** - Usa el mismo graph que WhatsApp
- **Solo para development** - No usar en producción

## 🐛 Debugging

Si hay errores, la respuesta incluye el stack trace:

```json
{
  "detail": "Error processing message: ..."
}
```

Ver logs del backend para más detalles:
```
INFO:     127.0.0.1:12345 - "POST /api/chat/simulate HTTP/1.1" 500
[ERROR] ...stack trace...
```

---

**¡Ahora podés probar el bot sin salir del navegador!** 🚀
