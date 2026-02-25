# WhatsApp Integration - Beans&Co Business Assistant

Integración completa del sistema multi-agente con WhatsApp usando Green API.

## 🚀 Inicio Rápido

### 1. Configura las credenciales en .env

Asegúrate de que tu archivo `.env` contiene las credenciales de Green API:

```bash
GREEN_API_INSTANCE_ID=tu-instance-id
GREEN_API_TOKEN=tu-api-token
```

### 2. Asegúrate de que tu instancia esté autorizada

Ve a la consola de Green API y verifica que tu instancia esté autorizada y conectada a WhatsApp.

### 3. Instala dependencias (si no las tienes)

```bash
pip install -r requirements.txt
```

### 4. Inicia el servidor de WhatsApp

```bash
python whatsapp_server.py
```

Verás algo como:

```
============================================================
WhatsApp Server - Beans&Co Business Assistant
============================================================
Instance ID: [tu-instance-id]
Starting message polling...
Press Ctrl+C to stop
============================================================
Instance state: authorized
✅ Instance is authorized and ready!
Waiting for incoming messages...
```

### 4. ¡Envía un mensaje de prueba!

Desde cualquier WhatsApp, envía un mensaje al número conectado a tu instancia de Green API.

Ejemplos de mensajes:
- "cuántas pulseras tengo?"
- "qué gastos hice la última semana?"
- "cuál es mi ganancia?"
- "registrame una venta de 2 pulseras negras"
- "entraron 15 pulseras doradas"

## 📱 Cómo Funciona

```
Usuario WhatsApp
      ↓
   📱 Mensaje
      ↓
Green API (polling cada 2 segundos)
      ↓
whatsapp_server.py
      ↓
Multi-Agent System (Router → Resolver/Read/Write → Final Answer)
      ↓
whatsapp_server.py
      ↓
Green API
      ↓
   📤 Respuesta
      ↓
Usuario WhatsApp
```

## 🔧 Archivos Creados

- **`whatsapp_client.py`** - Cliente de Green API
  - `send_message()` - Enviar mensaje
  - `receive_notification()` - Recibir notificación
  - `delete_notification()` - Confirmar procesamiento
  - `process_incoming_message()` - Extraer datos del mensaje

- **`whatsapp_server.py`** - Servidor principal
  - Polling loop (cada 2 segundos)
  - Integración con multi-agent system
  - Manejo de errores
  - Logging de mensajes

## 🎯 Capacidades

El asistente puede responder a:

### 📊 Consultas Analytics (READ)
- Stock de productos
- Ingresos totales
- Ganancias/pérdidas
- Gastos con filtros de tiempo
- Historial de ventas
- Información de productos

### ✍️ Operaciones (WRITE)
- Registrar ventas (con precios custom)
- Registrar gastos
- Agregar stock
- Crear productos

### 🔍 Ejemplos de Conversación

```
Usuario: "cuántas pulseras negras tengo?"
Bot: "- Pulsera de Granos de Café - Negra: 70 unidades"

Usuario: "qué gastos hice esta semana?"
Bot: "Historial de gastos:
- 2025-12-26: publicidad (GENERAL) - $200.00
- 2025-12-20: Courier account top-up (Shipping) - $30.00
Total gastado: $230.00 USD"

Usuario: "registrame una venta de 3 pulseras negras a 15 dolares cada una"
Bot: "Registering sale of 1 item type(s) with status PAID...
[OK] Sale registered (ID: 11, Total: $45.00)
  Current revenue: $208.00"
```

## ⚙️ Configuración

Las credenciales se cargan automáticamente desde el archivo `.env`:

```bash
GREEN_API_INSTANCE_ID=tu-instance-id
GREEN_API_TOKEN=tu-api-token
```

**Importante:** Nunca compartas tus credenciales en el código o en repositorios públicos. El archivo `.env` está excluido de git.

## 🛠️ Troubleshooting

### "Instance is not authorized"
- Ve a la consola de Green API
- Escanea el código QR con WhatsApp
- Espera a que el estado sea "authorized"

### "No incoming messages"
- Verifica que el servidor esté corriendo
- Asegúrate de enviar el mensaje al número correcto
- Revisa los logs del servidor

### "Error processing message"
- Revisa los logs para ver el error específico
- Verifica que la base de datos esté funcionando
- Asegúrate de que el LLM (Gemini) esté configurado

## 📚 Referencias

- [Green API Documentation](https://green-api.com/en/docs/api/)
- [Receiving Webhooks](https://green-api.com/en/docs/api/receiving/)
- [HTTP API Method](https://green-api.com/en/docs/api/receiving/technology-http-api/)

## 🚦 Estado del Sistema

Para verificar el estado de tu instancia:

```bash
python check_account.py
```

O programáticamente:

```python
import os
from dotenv import load_dotenv
from whatsapp_client import GreenAPIWhatsAppClient

load_dotenv()

client = GreenAPIWhatsAppClient(
    os.getenv("GREEN_API_INSTANCE_ID"),
    os.getenv("GREEN_API_TOKEN")
)
state = client.get_state_instance()
print(state)
```

## 🎉 ¡Listo!

Tu asistente de negocios ahora está disponible en WhatsApp 24/7! 🤖📱
